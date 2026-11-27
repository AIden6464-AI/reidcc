"""Milestone 2B acceptance (vision\\Spec\\SPEC-unified-interface.md Part 6): the TUI's chat view on a disposable repo.
chat_flow.py's round trip, in a pseudo-terminal:

  1  c (beside r resume) opens the chat view on the selected profile and the TUI's folder
  2  a Claude write turn streams, edits the repo and shows what it changed (ctrl+d: the diff); a second
     turn is stopped mid-stream and its engine goes down with it
     2b ctrl+e tune: this chat's effort reaches claude (--effort low); reid.json stays as it is
  3  tab -> codex, ctrl+r read-only: the .reid/handoff.md divider, no context shown (Codex reports none), nothing written
  4  ctrl+t resumes the Claude session (--resume <id>) in a console of its own; the composer then
     refuses: Codex writing ("A Reidcc window is open in this folder.", ctrl+r sends it read-only) and
     Claude ("in terminal", cleared once the terminal lets go)
  5  reid --chat [profile] opens the view straight away; esc leaves

Real Claude (haiku) and Codex: needs both signed in (Codex in ~/.codex). reid runs on a temp home; the
Claude sessions and Codex threads it makes are deleted afterwards. Kills only processes it started.

    python rs\\tests\\tui_chat_flow.py

Needs pywinpty, pyte and psutil in rs\\tests\\.venv; run with another Python, it re-runs itself with that one.
"""
import os, re, sys, json, glob, time, shutil, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")
try:
    import pyte, psutil, winpty  # noqa: F401
except ImportError:
    if os.path.exists(VENV_PY) and os.path.abspath(sys.executable).lower() != VENV_PY.lower():
        sys.exit(subprocess.call([VENV_PY, os.path.abspath(__file__)] + sys.argv[1:]))
    raise
sys.path.insert(0, HERE)
import guihome  # noqa: E402
from tui_parity import Term  # noqa: E402

CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
CLAUDE_PROJECTS = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects")
CL, CX = "m2cl", "m2cx"
COLS, ROWS = 120, 40
TAB, CTRL_R, CTRL_T, CTRL_D, ESC, ENTER = "\t", "\x12", "\x14", "\x04", "\x1b", "\r"
CTRL_E, DOWN, RIGHT = "\x05", "\x1b[B", "\x1b[C"
results = []


def check(name, ok, info=""):
    results.append(bool(ok))
    print("%s  %s%s" % ("ok  " if ok else "FAIL", name, ("" if ok or info == "" else "  " + str(info)[:600])))


def ready(bar):
    """The bar's right side when no turn runs: "ready", then the context only if the engine reported it."""
    return bar.rstrip().endswith("ready") or "ready · context" in bar


class View:
    """The chat view in a Term: its bar is the first line, the composer the last few."""

    def __init__(self, term):
        self.t = term

    def lines(self):
        return self.t.text().split("\n")

    def bar(self):
        return self.lines()[0]

    def controls(self):
        """The line with the picked profile, the read-only toggle and the primary key."""
        return next((l for l in reversed(self.lines()) if "read-only" in l and ("send" in l or "switch" in l or "stop" in l)), "")

    def note(self):
        return next((l.strip() for l in self.lines()[-8:] if re.match(r"\s*(in terminal|locked|refused)  ", l)), "")

    def key(self, k, wait=0.4):
        self.t.send(k)
        time.sleep(wait)

    def type(self, text):
        self.t.send(text)
        time.sleep(0.3)

    def idle(self, timeout=240):
        """Wait for the bar to say ready (and stay so)."""
        time.sleep(0.8)
        end = time.time() + timeout
        while time.time() < end:
            if ready(self.bar()):
                time.sleep(0.5)
                if ready(self.bar()):
                    return True
            time.sleep(0.2)
        return False

    def pick(self, profile, limit=60):
        for _ in range(limit):
            if (" %s · " % profile) in self.controls():
                return True
            self.key(TAB, 0.15)
        return False


def ours(bin_):
    out = []
    for p in psutil.process_iter(["exe"]):
        try:
            if (p.info["exe"] or "").lower().startswith(bin_.lower()) and p.is_running():
                out.append(p)
        except psutil.Error:
            pass
    return out


def cmdlines(bin_, needle):
    out = []
    for p in ours(bin_):
        try:
            if needle in p.cmdline():
                out.append(p.cmdline())
        except psutil.Error:
            pass
    return out


def engine_argv(bin_, needle):
    """The engine children (claude / codex) of reid --stream turns whose command line has `needle`."""
    out = []
    for p in ours(bin_):
        try:
            if "--stream" in p.cmdline():
                out += [" ".join(k.cmdline()) for k in p.children(recursive=True) if needle in " ".join(k.cmdline())]
        except psutil.Error:
            pass
    return out


def main():
    if not os.path.exists(os.path.join(CODEX_HOME, "auth.json")):
        print("skip  no Codex sign-in in %s" % CODEX_HOME)
        return 0
    real = {f: os.path.getmtime(os.path.join(guihome.REIDCC, f)) for f in ("reid.json", "reid_state.json")}
    root, home = guihome.make_home()
    work = os.path.join(root, "work")
    git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=work, check=True, capture_output=True)
    git("init", "-q")
    with open(os.path.join(work, "README.md"), "w", newline="\n") as f:
        f.write("base\n")
    git("add", ".")
    git("commit", "-qm", "init")
    cfgp = os.path.join(home, "reid.json")
    cfg = json.load(open(cfgp, encoding="utf-8"))
    cfg["profiles"][CL] = {"model": "haiku"}
    cfg["profiles"][CX] = {"engine": "codex"}
    json.dump(cfg, open(cfgp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    bin_ = os.path.join(home, "bin")
    os.makedirs(bin_)
    shutil.copy(os.path.join(guihome.RELEASE, "reid.exe"), bin_)
    reid = os.path.join(bin_, "reid.exe")
    env = dict(guihome.env_for(root), CODEX_HOME=CODEX_HOME)
    term, sid = None, None
    try:
        # ---- 1: c opens the chat view ----------------------------------------------------------------
        term = Term([reid, "--tui"], work, env, COLS, ROWS)
        term.settle()
        v = View(term)
        check("the TUI's key legend has c chat beside r resume", "r resume · c chat" in term.text(), term.text()[-400:])
        for _ in range(len(cfg["profiles"]) + 1):
            if any("→" in l and (" %s " % CL) in l for l in v.lines()):
                break
            v.key("\x1b[B", 0.15)
        v.key("c", 0.8)
        check("c opens the chat view on the selected profile and folder",
              ("%s · claude" % CL) in v.bar() and "work" in v.bar() and "ready" in v.bar(), v.bar())
        check("its one primary key is send", v.controls().rstrip().endswith("↵ send"), v.controls())
        check("the composer says what a Claude turn may do: edits · no shell", "edits · no shell" in v.controls(), v.controls())

        # ---- 2: Claude write turn, then stop ---------------------------------------------------------
        v.type("Create a file named hello.txt containing exactly the text: hi. Then reply with just DONE.")
        v.key(ENTER, 0)
        v.idle()
        screen = term.text()
        p = os.path.join(work, "hello.txt")
        on_disk = open(p, encoding="utf-8").read().strip() if os.path.exists(p) else None
        check("the Claude turn streamed and wrote hello.txt", on_disk == "hi" and "DONE" in screen, screen)
        tools = [l.strip() for l in v.lines() if re.match(r"\s+write\s", l)]
        check("its tool calls show as lowercase lines, paths relative", tools and not any(work.lower() in x.lower() for x in tools), tools)
        check("changed (from git) lists hello.txt, its zero muted",
              "changed · 1 file" in screen and "hello.txt" in screen and "−0" in screen, screen)
        meta = next((l.strip() for l in v.lines() if re.match(r"\s*\d\d:\d\d · context ", l)), "")
        check("the meta line: context % and edits", "%" in meta and meta.endswith("edits"), meta)
        v.key(CTRL_D)
        check("ctrl+d shows the diff", "│ +hi" in term.text(), term.text())
        v.key(CTRL_D)
        check("and ctrl+d again closes it", "│ +hi" not in term.text())

        v.type("Count from 1 to 300, one number per line, nothing else.")
        v.key(ENTER, 0)
        end, streams = time.time() + 120, []
        while time.time() < end:
            streams = streams or cmdlines(bin_, "--stream")
            if sum(1 for l in v.lines() if l.strip() in ("3", "4", "5", "6")) >= 2:
                break
            time.sleep(0.2)
        sid = next((c[c.index("--resume") + 1] for c in streams if "--resume" in c), None)
        check("the second turn resumes the Claude session", bool(sid), streams)
        check("while it streams the key is esc stop and the meter is live",
              v.controls().rstrip().endswith("esc stop") and "●" in v.bar(), (v.controls(), v.bar()))
        v.key(ESC, 0)
        v.idle(30)
        time.sleep(1.0)
        left = [p.cmdline() for p in ours(bin_) if p.pid != term.proc.pid]
        check("esc stops the turn (meta: stopped) and takes its engine down",
              any(l.strip() == "stopped" for l in v.lines()) and not left, left)

        # ---- 2b: ctrl+e tune: this chat's effort reaches the engine, reid.json stays as it is ---------
        v.type("/effort high")
        v.key(ENTER)
        check("/effort high is this chat's effort, not a message",
              "· high" in v.controls() and not any("› /effort" in l for l in v.lines()), v.controls())
        v.type("/effort default")
        v.key(ENTER)
        check("/effort default undoes it", "· high" not in v.controls(), v.controls())
        v.key(CTRL_E)
        check("ctrl+e opens the tune panel on the picked profile", any(l.strip().startswith("tune %s" % CL) for l in v.lines()), v.lines()[:4])
        v.key(DOWN)
        v.key(RIGHT)
        v.key(ESC)
        check("-> on effort picks low; the controls line says so", "· low" in v.controls(), v.controls())
        v.type("Reply with just OK.")
        v.key(ENTER, 0)
        end, withs, tuned = time.time() + 60, [], []
        while time.time() < end and not tuned:
            withs = withs or cmdlines(bin_, "--with")
            tuned = engine_argv(bin_, "--effort low")
            time.sleep(0.1)
        v.idle()
        check("the tuned turn runs reid --stream --with and claude --effort low",
              any('"effort":"low"' in " ".join(c) for c in withs) and bool(tuned), (withs, tuned))
        saved = json.load(open(cfgp, encoding="utf-8"))["profiles"][CL]
        check("reid.json keeps the profile as it was", saved == {"model": "haiku"}, saved)

        # ---- 3: switch -> codex, read-only -----------------------------------------------------------
        files = lambda: sorted(x for x in os.listdir(work) if x != ".reid")
        before = files()
        check("tab to codex turns send into switch → codex", v.pick(CX) and v.controls().rstrip().endswith("↵ switch → codex"), v.controls())
        v.key(CTRL_R)
        check("ctrl+r ticks read-only", "✓ read-only" in v.controls(), v.controls())
        check("a read-only Codex turn: read-only · shell", "read-only · shell" in v.controls(), v.controls())
        v.type("Review what changed in this folder. Reply with one short sentence.")
        v.key(ENTER, 0)
        v.idle()
        screen = term.text()
        check("the switch divider names .reid/handoff.md", "switch · claude → codex · .reid/handoff.md" in screen, screen)
        check(".reid/handoff.md was written", os.path.exists(os.path.join(work, ".reid", "handoff.md")))
        meta = next((l.strip() for l in reversed(v.lines()) if re.match(r"\s*\d\d:\d\d · ", l)), "")
        check("codex answered read-only, its unreported context left out", meta.endswith("read-only") and "context" not in meta, meta)
        check("codex's real token counts in the meta line", bool(re.search(r"\d[\d.]*k? in · \d[\d.]*k? out", meta)), meta)
        check("the bar leaves the unreported context out too", ready(v.bar()) and "context" not in v.bar(), v.bar())
        check("the read-only turn wrote nothing", files() == before and open(p, encoding="utf-8").read().strip() == "hi", files())
        check("the conversation is with codex now; the key is send again",
              ("%s · codex" % CX) in v.bar() and v.controls().rstrip().endswith("↵ send"), (v.bar(), v.controls()))

        # ---- 4: ctrl+t, then the composer's locks ----------------------------------------------------
        v.pick(CL)
        v.key(CTRL_T)
        end, cmd = time.time() + 20, []
        while time.time() < end and not cmd:
            cmd = [" ".join(c) for c in cmdlines(bin_, "--id")]
            time.sleep(0.3)
        check("ctrl+t resumes the Claude session (--resume %s --id <id>) in its own console" % CL,
              sid and any(("--resume %s --id %s" % (CL, sid)) in x for x in cmd), cmd)
        time.sleep(3)  # reid takes the session's lock before Claude starts

        v.pick(CX)
        v.key(CTRL_R)  # read-only off: a writing turn
        v.type("Add a line to README.md.")
        v.key(ENTER, 0)
        v.idle(60)
        note = v.note()
        check("codex writing is refused: a Reidcc window is open in this folder (no PID)",
              note.startswith("locked") and "A Reidcc window is open in this folder." in note and "ctrl+r sends it read-only" in note
              and "pid" not in note.lower(), note)
        check("the refused ask stays in the field", any("› Add a line to README.md." in l for l in v.lines()[-8:]), v.lines()[-8:])
        v.key(CTRL_R, 0)
        v.idle()
        meta = next((l.strip() for l in reversed(v.lines()) if re.match(r"\s*\d\d:\d\d · ", l)), "")
        check("ctrl+r sends it read-only", "read-only" in meta and "✓ read-only" in v.controls() and not v.note(), (meta, v.note()))
        check("README.md is untouched", open(os.path.join(work, "README.md"), encoding="utf-8").read() == "base\n")

        hp = os.path.join(work, ".reid", "handoff.md")
        h0 = open(hp, encoding="utf-8").read()
        v.pick(CL)
        v.key(CTRL_R)  # write again
        v.type("Say hi.")
        v.key(ENTER, 0)
        v.idle(60)
        note = v.note()
        # a switch carries the chat into a new Claude session, so the held one doesn't matter: the
        # terminal's window holds the folder (SPEC-0.2.6 Part 2)
        check("switching back to claude is refused while the terminal holds the folder",
              note.startswith("locked") and "A Reidcc window is open in this folder." in note and ("%s · codex" % CX) in v.bar(),
              (note, v.bar()))
        check("a refused switch leaves no divider and writes no handoff",
              "codex → claude" not in term.text() and open(hp, encoding="utf-8").read() == h0)
        for p_ in ours(bin_):
            try:
                if "--id" in p_.cmdline():
                    for k in p_.children(recursive=True) + [p_]:
                        try:
                            k.kill()
                        except psutil.Error:
                            pass
            except psutil.Error:
                pass
        end = time.time() + 10
        while time.time() < end and cmdlines(bin_, "--id"):
            time.sleep(0.3)
        v.key(ENTER, 0)
        v.idle(90)
        screen = term.text()
        check("once the terminal lets go, the switch runs and carries the chat",
              "context carried:" in screen and ("%s · claude" % CL) in v.bar() and not v.note(), (screen[-600:], v.note()))
        v.key(ESC, 0.8)
        check("esc leaves the chat for the profile list", "r resume · c chat" in term.text(), term.text()[-300:])
        v.key("q", 0)
        check("and q quits the TUI", term.wait_exit() == 0)
        term = None

        # ---- 5: reid --chat [profile] ----------------------------------------------------------------
        term = Term([reid, "--chat", CX], work, env, COLS, ROWS)
        term.settle()
        check("reid --chat %s opens the chat view on it" % CX, ("%s · codex" % CX) in View(term).bar(), View(term).bar())
        term.send(ESC)
        check("esc leaves (exit 0)", term.wait_exit() == 0)
        term = Term([reid, "--chat", "nope"], work, env, COLS, ROWS)
        rc = term.wait_exit()
        check("reid --chat on no such profile says so (exit 1)", rc == 1 and "No profile named nope." in term.text(), (rc, term.text()[:300]))
        term = None
    finally:
        if term:
            term.send("\x03")
        for p_ in ours(bin_):
            try:
                p_.kill()
            except psutil.Error:
                pass
        time.sleep(0.5)
        gone = 0
        for f in glob.glob(os.path.join(CODEX_HOME, "sessions", "*", "*", "*", "rollout-*.jsonl")):
            try:
                meta = json.loads(open(f, encoding="utf-8").readline())["payload"]
                if os.path.normcase(meta.get("cwd", "")) == os.path.normcase(work):
                    os.remove(f)
                    gone += 1
            except Exception:
                pass
        for proj in glob.glob(os.path.join(CLAUDE_PROJECTS, "*")):
            # Claude names a project folder after its path: this test's work folder only
            if os.path.basename(proj).lower() == re.sub(r"[^a-zA-Z0-9]", "-", work).lower():
                gone += len(glob.glob(os.path.join(proj, "*.jsonl")))
                shutil.rmtree(proj, ignore_errors=True)
        print("      removed %d test session file(s)" % gone)
        guihome.remove_home(root)
        now = {f: os.path.getmtime(os.path.join(guihome.REIDCC, f)) for f in real}
        check("the real reid.json / reid_state.json untouched", now == real)
    print("\n%d/%d passed" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
