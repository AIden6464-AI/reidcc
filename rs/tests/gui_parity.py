"""GUI parity: the Python GUI (python\\reid_gui.py) and the Rust GUI (Reidcc.exe) take the same actions,
and after each one their reid.json files must be byte for byte the same.

Each app gets its own temp Reidcc folder (guihome.make_home), both starting from a copy of the real
profiles. Python is driven in this process (its widgets' own invoke / variable writes, as a click or a
pick does); Rust through WebView2's DevTools protocol and the page's test hooks (window.__reid, which
go through the same event paths a click, a pick or a key takes).

Actions: new profile, duplicate, rename, every engine, every field to every value it offers (plus a
typed value where the field takes typing), both persona modes, each switch on and off, all of it on a
Claude and on a Codex profile; make default; delete (keep, then confirm). Fields a user can't change
(disabled) are skipped, and both apps must agree on which those are.

    python rs\\tests\\gui_parity.py          (needs rs\\target\\release\\Reidcc.exe built)
"""
import os, sys, json, time, difflib

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guihome

COMBOS = ("engine", "model", "auth", "persona", "proxy", "tools", "mcp")
TYPED = {"model": ["my-model", ""], "tools": ["Read,Bash", "all"], "args": ["--verbose", '--append "a b" -x', "--x;y", ""]}
CHECKS = ("memory", "chrome", "connectors", "safe")


class Py:
    def __init__(self, root):
        self.reid, self.gui = guihome.python_core(root)
        self.reid._CODEX_LOGIN[os.environ["CODEX_HOME"]] = "not signed in"  # no `codex login status` run
        self.app = self.gui.App(self.reid, cwd=os.path.join(root, "work"))
        self.pump(1.0)
        a = self.app
        self.cb = {"engine": a.cb_engine, "model": a.cb_model, "auth": a.cb_auth, "persona": a.cb_persona,
                   "proxy": a.cb_proxy, "tools": a.cb_tools, "mcp": a.cb_mcp}

    def pump(self, s=0.05):
        end = time.time() + s
        while time.time() < end:
            self.app.root.update()
            time.sleep(0.005)

    def values(self, key):
        return list(self.cb[key]["values"])

    def disabled(self):
        a = self.app
        d = {k: self.cb[k].instate(["disabled"]) for k in ("proxy", "tools", "mcp")}
        d.update({k: a.checks[k].instate(["disabled"]) for k in ("chrome", "connectors", "safe")})
        d["mode"] = a.mode_radios[0].instate(["disabled"])
        return d

    def pick(self, key, value):  # a pick (or typing) writes the variable; its trace saves
        self.app.v[key].set(value)
        self.pump()

    def check(self, key):
        self.app.checks[key].invoke()
        self.pump()

    def radio(self, i):
        self.app.mode_radios[i].invoke()
        self.pump()

    def select(self, name):
        a = self.app
        i = a.names.index(name)
        a.lb.selection_clear(0, "end")
        a.lb.selection_set(i)
        a.on_list()
        self.pump()

    def rename(self, text):
        self.app.v["name"].set(text)
        self.app.rename()  # what <Return> in the name field does
        self.pump()

    def button(self, which):
        a = self.app
        if which.startswith("msg:"):  # a button in the message bar
            label = which[4:]
            b = next(w for w in a.msg_actions.winfo_children() if w.cget("text") == label)
            b.invoke()
        else:
            {"new profile": a.new, "duplicate": a.dup, "delete": a.delete, "make default": a.set_default}[which]()
        self.pump()

    def current(self):
        return self.app.current


class Rs:
    def __init__(self, root):
        self.t = guihome.Tauri(root)
        time.sleep(1.0)
        self.t.js("__reid.login('not signed in')")
        self.settle()

    def settle(self):
        # every change is one invoke; wait until the page has its answer (no call in flight)
        time.sleep(0.12)

    def state(self):
        return self.t.js("__reid.state()")

    def values(self, key):
        return self.state()["choices"][key]

    def disabled(self):
        d = self.state()["disabled"]
        return {k: d[k] for k in ("proxy", "tools", "mcp", "chrome", "connectors", "safe", "mode")}

    def pick(self, key, value):
        if key in ("model", "tools", "args"):
            self.t.js("__reid.type(%s, %s)" % (json.dumps(key), json.dumps(value)))
        else:
            self.t.js("__reid.pick(%s, %s)" % (json.dumps(key), json.dumps(value)))
        self.settle()

    def check(self, key):
        self.t.js("__reid.check(%s)" % json.dumps(key))
        self.settle()

    def radio(self, i):
        self.t.js("__reid.radio(%d)" % i)
        self.settle()

    def select(self, name):
        names = self.state()["names"]
        self.t.js("__reid.selectRow(%d)" % names.index(name))
        self.settle()

    def rename(self, text):
        self.t.js("__reid.rename(%s)" % json.dumps(text))
        self.settle()

    def button(self, which):
        label = which[4:] if which.startswith("msg:") else which
        # the message bar comes first in the page, so "delete" there is found before the profile one
        if not self.t.js("__reid.button(%s)" % json.dumps(label)):
            raise RuntimeError("no button " + label)
        self.settle()

    def current(self):
        s = self.state()
        return s["names"][s["sel"]] if s["sel"] >= 0 else None

    def close(self):
        self.t.close()


def main():
    root_py, home_py = guihome.make_home()
    root_rs, home_rs = guihome.make_home()
    results, notes = [], []
    last = [open(os.path.join(home_py, "reid.json"), "rb").read()]
    rs = None
    try:
        rs = Rs(root_rs)
        py = Py(root_py)

        def compare(label):
            a = open(os.path.join(home_py, "reid.json"), "rb").read()
            b = open(os.path.join(home_rs, "reid.json"), "rb").read()
            same = a == b
            diff = ""
            if not same:
                diff = "\n".join(list(difflib.unified_diff(a.decode("utf-8").splitlines(), b.decode("utf-8").splitlines(),
                                                           "python", "rust", n=1, lineterm=""))[2:14])
            results.append((label, same, diff, a != last[0]))
            last[0] = a
            if py.current() != rs.current():
                notes.append("%s: selected profile differs (python %s, rust %s)" % (label, py.current(), rs.current()))

        def both(label, fn, *args):
            getattr(py, fn)(*args)
            getattr(rs, fn)(*args)
            compare(label)

        def every_field(tag):
            dp, dr = py.disabled(), rs.disabled()
            if dp != dr:
                notes.append("%s: disabled fields differ: python %s, rust %s" % (tag, dp, dr))
            for key in COMBOS[1:]:
                if key in dp and dp[key]:
                    continue
                vp, vr = py.values(key), rs.values(key)
                if vp != vr:
                    notes.append("%s %s: choices differ: python %s, rust %s" % (tag, key, vp, vr))
                for v in vp + TYPED.get(key, []):
                    both("%s: %s = %r" % (tag, key, v), "pick", key, v)
            for v in TYPED["args"]:
                both("%s: args = %r" % (tag, v), "pick", "args", v)
            # persona modes need a persona
            personas = [v for v in py.values("persona") if v != "none"]
            both("%s: persona = %r" % (tag, personas[0]), "pick", "persona", personas[0])
            if not py.disabled()["mode"]:
                for i, m in enumerate(("append", "replace", "append")):
                    both("%s: persona mode %s" % (tag, m), "radio", i % 2)
            both("%s: persona = none" % tag, "pick", "persona", "none")
            for k in CHECKS:
                if py.disabled().get(k):
                    continue
                both("%s: %s switch" % (tag, k), "check", k)
                both("%s: %s switch back" % (tag, k), "check", k)

        both("new profile", "button", "new profile")
        both("duplicate", "button", "duplicate")
        both("rename to parity-a", "rename", "parity-a")
        both("rename to an existing name (refused)", "rename", "claude")
        for e in py.values("engine"):
            both("engine = %s" % e, "pick", "engine", e)
        both("engine = claude", "pick", "engine", "claude")
        every_field("claude")
        both("engine = codex", "pick", "engine", "codex")
        every_field("codex")
        # a Codex profile with Claude-only settings still on: those stay live so they can be turned off
        both("engine = claude again", "pick", "engine", "claude")
        both("proxy = capture", "pick", "proxy", "capture")
        both("safe on", "check", "safe")
        both("engine = codex with proxy+safe on", "pick", "engine", "codex")
        every_field("codex+live")
        both("engine = claude", "pick", "engine", "claude")
        both("make default", "button", "make default")
        both("delete, then keep", "button", "delete")
        both("keep", "button", "msg:keep")
        both("delete", "button", "delete")
        both("delete: confirm", "button", "msg:delete")
        both("select mini", "select", "mini")
        both("duplicate mini", "button", "duplicate")
        both("rename mini-copy to parity b", "rename", "parity b")
        both("make default", "button", "make default")
        both("delete parity b", "button", "delete")
        both("delete: confirm", "button", "msg:delete")
        py.app.root.destroy()
    finally:
        if rs:
            rs.close()
        guihome.remove_home(root_py)
        guihome.remove_home(root_rs)

    same = sum(1 for r in results if r[1])
    print("gui parity: %d/%d actions left reid.json byte-identical (%d of them changed the file)"
          % (same, len(results), sum(1 for r in results if r[3])))
    for label, s, diff, _ in results:
        if not s:
            print("  DIFFERS after: %s\n%s" % (label, "\n".join("      " + l for l in diff.splitlines())))
    for n in notes:
        print("  note:", n)
    return 0 if same == len(results) and not notes else 1


if __name__ == "__main__":
    sys.exit(main())
