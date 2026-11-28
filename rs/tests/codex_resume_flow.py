"""Codex resume both ways on Windows (vision\\Spec\\SPEC-unified-interface.md, Step 0).

  A  a headless thread (reid <profile> exec --json) opens in a Reidcc session window and still knows
     what it was told
  B  two fresh Codex windows in one folder, each told a different word; the headless runner
     continues the thread Reidcc recorded for window 1 and gets window 1's word. The second window
     is there so a "most recent thread" lookup can't pass by accident.
  C  a fresh window sent a message and left with Ctrl+C twice at once: back in Reidcc, its new thread
     recorded
  D  a chat switched from Claude to Codex (SPEC-0.2.6): the thread Reidcc built from the transcript opens
     in a Reidcc window with interactive `codex resume`, and knows a word only the Claude turn was told

Real Codex: it needs the sign-in in ~/.codex (the other tests use a temp CODEX_HOME with none), runs
a few tiny turns, and deletes the threads it made afterwards (only files whose cwd is its temp
folder). Reidcc itself runs from a temp folder (guihome): the real reid.json / reid_state.json are
never touched. Kills only processes it started.

    python rs\\tests\\codex_resume_flow.py
"""
import os, sys, json, time, glob, random, string, shutil, subprocess, uuid
import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guihome
import session_flow as sf
from session_flow import check, Page, session_target, ours, screen, press

CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
SESSIONS = os.path.join(CODEX_HOME, "sessions")
PROFILE = "cx"


def word(prefix):
    return prefix + "-" + "".join(random.choice(string.ascii_uppercase) for _ in range(5))


def state(home):
    return json.load(open(os.path.join(home, "reid_state.json"), encoding="utf-8")).get("last") or {}


def threads_in(work, helpers=False):
    """{thread id: (path, text)} for Codex threads whose cwd is the test folder (subagent ones too if
    `helpers`)."""
    out = {}
    for f in glob.glob(os.path.join(SESSIONS, "*", "*", "*", "rollout-*.jsonl")):
        try:
            text = open(f, encoding="utf-8").read()
            meta = json.loads(text.split("\n", 1)[0])["payload"]
        except Exception:
            continue
        if os.path.normcase(meta.get("cwd", "")) == os.path.normcase(work) and (helpers or not isinstance(meta.get("source"), dict)):
            out[meta["id"]] = (f, text)
    return out


def headless(bin_, env, work, args):
    """reid <profile> exec --json …: (thread id from Codex's own output, last reply, rc)."""
    p = subprocess.run([os.path.join(bin_, "reid.exe"), PROFILE, "exec", "--json", "--skip-git-repo-check"] + args,
                       env=env, cwd=work, capture_output=True, text=True, encoding="utf-8", timeout=180,
                       stdin=subprocess.DEVNULL)  # codex exec waits on a stdin that never closes (a background run)
    tid, reply = None, ""
    for line in p.stdout.splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if e.get("type") == "thread.started":
            tid = e.get("thread_id")
        if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message":
            reply = e["item"].get("text", "")
    if p.returncode:
        print("      headless stderr: " + p.stderr.strip()[-600:])
    return tid, reply, p.returncode


class Window:
    """A Reidcc session window: type into its engine, read its screen."""
    def __init__(self, t, seen):
        target = session_target(seen, timeout=20)
        self.id = int(target["url"].split("id=")[1])
        self.page = Page(target)

    def write(self, data):
        self.page.js("window.__TAURI_INTERNALS__.invoke('sess_write', {id: %d, data: %s})" % (self.id, json.dumps(data)))

    def type(self, text):
        # Codex reads fast input as a paste, where Enter is a new line, and drops a `?` from a burst:
        # one character per write, pause, then Enter
        for ch in text:
            self.write(ch)
            time.sleep(0.01)
        time.sleep(2)
        self.write("\r")

    def ask(self, text, timeout=120):
        """Send a message and wait for Codex's turn to finish ("Worked for …"); the screen, or None."""
        before = screen(self.page).count("Worked for")
        self.type(text)
        end = time.time() + timeout
        while time.time() < end:
            s = screen(self.page)
            if s.count("Worked for") > before:
                return s
            time.sleep(0.5)
        print("      screen:\n      " + "\n      ".join(l for l in screen(self.page).splitlines() if l.strip())[-900:])
        return None

    def ready(self, timeout=60):
        """Codex's composer is up (its prompt line); answers a trust question first if one shows."""
        end = time.time() + timeout
        while time.time() < end:
            text = screen(self.page)
            if "trust" in text.lower() and ("1." in text or "Yes" in text):
                print("      trust question:\n      " + "\n      ".join(l for l in text.splitlines() if l.strip())[-900:])
                return False
            if "›" in text or "context left" in text or "% left" in text:
                return True
            time.sleep(0.5)
        print("      screen:\n      " + "\n      ".join(l for l in screen(self.page).splitlines() if l.strip())[-900:])
        return False


def quit_(w, t):
    """/quit: Codex ends, reid records the session, the window turns back into Reidcc."""
    w.type("/quit")
    end = time.time() + 15
    while time.time() < end and w.page.ws.connected:
        try:
            if "Back from Codex" in (t.js("__reid.state().msg") or ""):
                break
        except Exception:
            pass
        time.sleep(0.5)
    time.sleep(1)


def codex_cmdline(bin_):
    """Command lines of codex.exe processes under our reid.exe."""
    return [" ".join(p.cmdline()) for p in ours(bin_) if p.name().lower() == "codex.exe" and p.is_running()]


def main():
    if not os.path.exists(os.path.join(CODEX_HOME, "auth.json")):
        print("skip  no Codex sign-in in %s" % CODEX_HOME)
        return 0
    real = {f: os.path.getmtime(os.path.join(guihome.REIDCC, f)) for f in ("reid.json", "reid_state.json")}
    root, home = guihome.make_home()
    work = os.path.join(root, "work")
    cfgp = os.path.join(home, "reid.json")
    cfg = json.load(open(cfgp, encoding="utf-8"))
    cfg.pop("open_in", None)
    cfg["profiles"][PROFILE] = {"engine": "codex"}
    cfg["profiles"]["swcl"] = {"model": "haiku"}  # D's Claude turn
    json.dump(cfg, open(cfgp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    bin_ = os.path.join(home, "bin")
    os.makedirs(bin_)
    for exe in ("Reidcc.exe", "reid.exe"):
        shutil.copy(os.path.join(guihome.RELEASE, exe), bin_)
    env = dict(guihome.env_for(root), CODEX_HOME=CODEX_HOME)
    t, seen = None, set()
    try:
        # ---- A: headless thread -> Reidcc window ------------------------------------------------
        plum = word("PLUM")
        tid, reply, rc = headless(bin_, env, work, ["Remember the word %s. Reply with just OK." % plum])
        check("headless run: Codex names its thread", bool(tid) and rc == 0, "%s rc %s reply %r" % (tid, rc, reply[:60]))
        last = state(home)
        check("reid recorded that exact thread", last.get("sid") == tid and last.get("engine") == "codex", last)

        t = guihome.Tauri(root, port=sf.PORT, exe=os.path.join(bin_, "Reidcc.exe"), extra_env={"CODEX_HOME": CODEX_HOME})
        time.sleep(1.0)
        names = t.js("__reid.state().names")
        t.js("__reid.selectRow(%d)" % names.index(PROFILE))
        time.sleep(0.4)
        t.js("__reid.button('resume')")
        w = Window(t, seen)
        ok = w.ready()
        cmd = codex_cmdline(bin_)
        check("resume opens that thread in a Reidcc window", ok and any(("resume " + str(tid)) in c for c in cmd), cmd)
        before = screen(w.page).count(plum)
        text = w.ask("What word did I ask you to remember? Reply with just the word.") or ""
        ok = text.count(plum) > before
        check("the window's Codex still knows the word", ok, plum)
        if not ok:
            print("      screen:\n      " + "\n      ".join(l for l in text.splitlines() if l.strip())[-1200:])
        quit_(w, t)

        # ---- B: two fresh windows in one folder -> headless continues window 1 -------------------
        fig, kiwi = word("FIG"), word("KIWI")
        press(t, PROFILE)
        w1 = Window(t, seen)
        w1.ready()
        w1.ask("Remember the word %s. Reply with just OK." % fig)
        time.sleep(4.5)  # the launcher's note clears
        press(t, PROFILE)
        w2 = Window(t, seen)
        w2.ready()
        w2.ask("Remember the word %s. Reply with just OK." % kiwi)
        time.sleep(3)  # reid looks for its thread every second

        mine = threads_in(work)
        t1 = next((i for i, (_, x) in mine.items() if fig in x), None)
        t2 = next((i for i, (_, x) in mine.items() if kiwi in x), None)
        newest = max(mine, key=lambda i: os.path.getctime(mine[i][0])) if mine else None
        check("two windows, two threads in one folder; the newest is window 2's", bool(t1 and t2 and t1 != t2 and newest == t2),
              "w1 %s w2 %s newest %s" % (t1, t2, newest))
        check("window 2 recorded its own thread", state(home).get("sid") == t2, state(home).get("sid"))
        quit_(w1, t)
        end = time.time() + 15
        while time.time() < end and state(home).get("sid") != t1:
            time.sleep(0.5)
        rec = state(home).get("sid")
        check("window 1 ending records window 1's thread", rec == t1, rec)
        tid2, reply2, rc2 = headless(bin_, env, work, ["resume", rec or "none",
                                                       "What word did I ask you to remember? Reply with just the word."])
        check("headless runner continues window 1's exact thread", tid2 == t1 and fig in reply2 and kiwi not in reply2,
              "thread %s reply %r" % (tid2, reply2[:80]))
        quit_(w2, t)

        # ---- C: Ctrl+C twice right after sending: back at once, the new thread still recorded -------
        known = set(threads_in(work))
        press(t, PROFILE)
        w3 = Window(t, seen)
        w3.ready()
        w3.write("Remember the word %s. Reply with just OK." % word("PEAR"))
        time.sleep(2)  # paste guard, as in type()
        w3.write("\r")
        time.sleep(0.1)
        for _ in range(2):
            w3.write("\x03")
            time.sleep(0.3)
        end = time.time() + 15
        while time.time() < end and "Back from Codex" not in (t.js("__reid.state().msg") or ""):
            time.sleep(0.3)
        made = sorted(set(threads_in(work)) - known)
        check("a quick Ctrl+C exit comes back and records its new thread",
              len(made) == 1 and state(home).get("sid") == made[0], (made, state(home).get("sid"), t.js("__reid.state().msg")))

        # ---- D: a chat switched from Claude: the built thread in interactive codex resume ----------
        lime, chat = word("LIME"), str(uuid.uuid4())

        def turn(profile, prompt, *extra):
            p = subprocess.run([os.path.join(bin_, "reid.exe"), "--stream", profile, "--chat", chat, *extra, prompt],
                               env=env, cwd=work, capture_output=True, text=True, encoding="utf-8", timeout=300,
                               stdin=subprocess.DEVNULL)
            evs = [json.loads(l) for l in p.stdout.splitlines() if l.startswith("{")]
            return evs, p.returncode, p.stderr

        evs, rc, err = turn("swcl", "Remember the word %s. Reply with just: noted." % lime)
        check("a Claude turn in a chat", rc == 0, err[-300:])
        evs, rc, err = turn(PROFILE, "Reply with just: ok.", "--switch-from", "swcl")
        notes = [e["text"] for e in evs if e.get("type") == "note"]
        started = [e["session_id"] for e in evs if e.get("type") == "started"]
        built = started[0] if started else None
        check("the switch carries the chat into a Codex thread Reidcc built",
              rc == 0 and notes == ["context carried: 1 turn in a new codex session"] and state(home).get("sid") == built,
              (notes, started, state(home).get("sid"), err[-300:]))
        t.js("__reid.selectRow(%d)" % t.js("__reid.state().names").index(PROFILE))
        time.sleep(0.4)
        t.js("__reid.button('resume')")
        w4 = Window(t, seen)
        ok = w4.ready()
        cmd = codex_cmdline(bin_)
        check("resume opens the built thread in a Reidcc window", ok and any(("resume " + str(built)) in c for c in cmd), cmd)
        # the answer is read from the thread, not the screen: a window behind the launcher repaints late
        w4.type("What word did I ask you to remember? Reply with just the word.")
        said, end = [], time.time() + 120
        while time.time() < end and not said:
            time.sleep(1)
            lines = threads_in(work).get(built, ("", ""))[1].splitlines()
            events = [json.loads(line) for line in lines if line.startswith("{") and line.endswith("}")]  # not a line still being written
            said = [e["payload"].get("message", "") for e in events
                    if e.get("type") == "event_msg" and e["payload"].get("type") == "agent_message"][1:]  # past the switch turn's
        check("interactive Codex knows the word from the Claude turn", said and lime in said[-1], (lime, said))
        quit_(w4, t)
    finally:
        for p in ours(bin_):
            try:
                p.kill()
            except psutil.Error:
                pass
        if t:
            t.close()
        time.sleep(0.5)
        made = threads_in(work, helpers=True)
        for f, _ in made.values():
            try:
                os.remove(f)
            except OSError:
                pass
        print("      removed %d test thread(s) from %s" % (len(made), SESSIONS))
        slug = "".join(c if c.isascii() and c.isalnum() else "-" for c in work)  # D's Claude session
        for d in glob.glob(os.path.join(os.path.expanduser("~/.claude/projects"), glob.escape(slug[:200]) + "*")):
            shutil.rmtree(d, ignore_errors=True)
        guihome.remove_home(root)
    after = {f: os.path.getmtime(os.path.join(guihome.REIDCC, f)) for f in ("reid.json", "reid_state.json")}
    check("real reid.json / reid_state.json untouched", real == after)
    print("\n%d/%d passed" % (sum(sf.results), len(sf.results)))
    return 0 if all(sf.results) else 1


if __name__ == "__main__":
    sys.exit(main())
