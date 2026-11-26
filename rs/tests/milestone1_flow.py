"""Milestone 1 acceptance (vision\\Spec\\SPEC-unified-interface.md): reid --stream on a disposable git repo.

  1  a Claude Code write turn changes the repo; its events come through one stream
  2  Switch writes .reid\\handoff.md (folder, profile · engine, changes, tests, note) and a Codex
     read-only review gets it; told to write anyway, Codex changes 0 files
  3  while a Claude turn streams: resuming its session (stream or interactive), a second writing turn
     and a new window in the folder are refused, a read-only turn streams alongside; killing the turn's
     reid.exe frees its locks (the OS drops them); two windows share the folder and a headless writing
     turn can't join them; once they're closed the session resumes

Real Claude (haiku) and Codex: needs both signed in. Reidcc runs on a temp REIDCC_HOME; the Claude
sessions and Codex threads it makes are deleted afterwards. Kills only processes it started.

    python rs\\tests\\milestone1_flow.py
"""
import os, sys, json, glob, time, shutil, stat, tempfile, threading, subprocess, hashlib
import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.environ.get("REIDCC_BIN") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "rs", "target", "release")
REID = os.path.join(BIN, "reid.exe")
CODEX_SESSIONS = os.path.join(os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex"), "sessions")
CLAUDE_PROJECTS = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects")
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS  " if ok else "FAIL  ") + name + ("" if ok or detail == "" else "  " + str(detail)[:600]))


def events(text):
    out = []
    for line in text.splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            pass
    return out


def of(evs, kind):
    return [e for e in evs if e.get("type") == kind]


def text_of(evs):
    return "".join(e["text"] for e in of(evs, "text_delta"))


class Repo:
    def __init__(self):
        self.root = tempfile.mkdtemp(prefix="reidm1_")
        self.work = os.path.join(self.root, "work")
        self.home = os.path.join(self.root, "home")
        os.makedirs(self.work)
        os.makedirs(self.home)
        with open(os.path.join(self.home, "reid.json"), "w", encoding="utf-8") as f:
            json.dump({"default": "cl", "profiles": {"cl": {"model": "haiku"}, "cx": {"engine": "codex"}}}, f)
        self.env = dict(os.environ, REIDCC_HOME=self.home)
        git = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *a], cwd=self.work, check=True, capture_output=True)
        git("init", "-q")
        with open(os.path.join(self.work, "README.md"), "w", newline="\n") as f:
            f.write("base\n")
        git("add", ".")
        git("commit", "-qm", "init")
        self.procs, self.sids = [], set()

    def stream(self, args, timeout=300):
        p = subprocess.run([REID, "--stream", *args], cwd=self.work, env=self.env, capture_output=True,
                           text=True, encoding="utf-8", timeout=timeout, stdin=subprocess.DEVNULL)
        evs = events(p.stdout)
        self.sids.update(e["session_id"] for e in of(evs, "started"))
        return evs, p.returncode, p.stderr

    def start(self, args):
        """A turn left running: (Popen, events list filled as they arrive)."""
        p = subprocess.Popen([REID, "--stream", *args], cwd=self.work, env=self.env, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, encoding="utf-8")
        self.procs.append(p)
        evs = []

        def read():
            for line in p.stdout:
                evs.extend(events(line))
                self.sids.update(e["session_id"] for e in of(evs[-1:], "started"))
        threading.Thread(target=read, daemon=True).start()
        return p, evs

    def window(self):
        """An interactive session (reid cl) in a hidden console of its own, like a Reidcc window."""
        si = subprocess.STARTUPINFO()
        si.dwFlags, si.wShowWindow = subprocess.STARTF_USESHOWWINDOW, 0  # SW_HIDE
        p = subprocess.Popen([REID, "cl"], cwd=self.work, env=self.env, creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=si)
        self.procs.append(p)
        return p

    def windows(self):
        """Live interactive sessions' records (sessions/<id>.json)."""
        out = []
        for f in glob.glob(os.path.join(self.home, "sessions", "*.json")):
            try:
                rec = json.load(open(f, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if rec.get("mode") == "interactive" and psutil.pid_exists(rec.get("pid", 0)):
                self.sids.add(rec["id"])
                out.append(rec)
        return out

    def kill(self, p):
        try:
            for c in psutil.Process(p.pid).children(recursive=True):
                c.kill()
            p.kill()
            p.wait(10)
        except psutil.Error:
            pass

    def files(self):
        """{relative path: sha1} of everything but .git and .reid."""
        out = {}
        for d, dirs, names in os.walk(self.work):
            dirs[:] = [x for x in dirs if x not in (".git", ".reid")]
            for n in names:
                full = os.path.join(d, n)
                out[os.path.relpath(full, self.work)] = hashlib.sha1(open(full, "rb").read()).hexdigest()
        return out

    def state(self):
        return json.load(open(os.path.join(self.home, "reid_state.json"), encoding="utf-8")).get("last") or {}

    def held(self, sid):
        """Is sessions\\<sid>.lock held? (an open-for-write fails while a live process has it)."""
        try:
            open(os.path.join(self.home, "sessions", sid + ".lock"), "a").close()
            return False
        except PermissionError:
            return True

    def cleanup(self):
        for p in self.procs:
            try:
                for c in psutil.Process(p.pid).children(recursive=True):
                    c.kill()
                p.kill()
            except psutil.Error:
                pass
        time.sleep(0.5)
        gone = 0
        for f in glob.glob(os.path.join(CODEX_SESSIONS, "*", "*", "*", "rollout-*.jsonl")):
            try:
                meta = json.loads(open(f, encoding="utf-8").readline())["payload"]
                if os.path.normcase(meta.get("cwd", "")) == os.path.normcase(self.work):
                    os.remove(f)
                    gone += 1
            except Exception:
                pass
        for sid in self.sids:
            for f in glob.glob(os.path.join(CLAUDE_PROJECTS, "*", sid + ".jsonl")):
                os.remove(f)
                gone += 1
                shutil.rmtree(f[:-6], ignore_errors=True)  # its subagent folder, if any
                try:
                    os.rmdir(os.path.dirname(f))
                except OSError:
                    pass
        print("      removed %d test session file(s)" % gone)
        shutil.rmtree(self.root, onerror=lambda fn, p, _: (os.chmod(p, stat.S_IWRITE), fn(p)))


def main():
    r = Repo()
    try:
        # ---- 1: Claude write turn ----------------------------------------------------------------
        evs, rc, err = r.stream(["cl", "Append the line 'edited by claude' to README.md and create hello.txt "
                                       "containing exactly: hello. Do nothing else, then say done."])
        s1 = (of(evs, "started") or [{}])[0].get("session_id")
        tools = [e["name"] for e in of(evs, "tool_call")]
        use = (of(evs, "usage") or [{}])[-1]
        check("claude write turn: started, tool calls, done 0", s1 and tools and of(evs, "done") == [{"type": "done", "exit_code": 0}] and rc == 0,
              (rc, tools, evs[-3:], err[-300:]))
        check("claude usage: context % and cost", isinstance(use.get("context_pct"), int) and isinstance(use.get("cost_usd"), float), use)
        readme = open(os.path.join(r.work, "README.md"), encoding="utf-8").read()
        check("the repo changed (README.md edited, hello.txt made)", "edited by claude" in readme and os.path.exists(os.path.join(r.work, "hello.txt")), readme)
        check("reid --resume would continue it", r.state().get("sid") == s1 and r.state().get("engine") == "claude", r.state())
        left = os.listdir(os.path.join(r.home, "sessions")) + os.listdir(os.path.join(r.home, "locks"))
        check("a finished turn leaves no locks", left == [], left)

        # ---- 2: Switch -> Codex read-only review -------------------------------------------------
        before = r.files()
        evs, rc, err = r.stream(["cx", "--read-only", "--switch-from", "cl", "--tests", "none run", "--note", "NOTE-M1Q",
                                 "Review the change in one sentence. Then create review.txt with your verdict "
                                 "and append the line 'codex was here' to README.md."])
        hp = os.path.join(r.work, ".reid", "handoff.md")
        md = open(hp, encoding="utf-8").read() if os.path.exists(hp) else ""
        want = ["Folder: " + r.work, "From: cl · claude", " M README.md", "?? hello.txt", "README.md | 1 +", "none run", "NOTE-M1Q"]
        check("handoff.md: folder, cl · claude, changes, diff stat, tests, note", all(w in md for w in want) and ".reid" not in md.split("## Changed files")[-1],
              [w for w in want if w not in md] or md)
        s2 = (of(evs, "started") or [{}])[0].get("session_id")
        use = (of(evs, "usage") or [{}])[-1]
        check("codex read-only turn: started, text, done 0", s2 and text_of(evs) and of(evs, "done") == [{"type": "done", "exit_code": 0}],
              (rc, evs[-3:], err[-300:]))
        check("codex usage: context unknown (null), never 0", "context_pct" in use and use["context_pct"] is None, use)
        after = r.files()
        changed = sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))
        check("codex read-only: 0 files modified", changed == [], changed)
        thread = ""
        for f in glob.glob(os.path.join(CODEX_SESSIONS, "*", "*", "*", "rollout-*%s.jsonl" % s2)):
            thread = open(f, encoding="utf-8").read()
        check("codex got the handoff in its turn", "NOTE-M1Q" in thread and "From: cl" in thread, len(thread))

        # ---- 3: locks ----------------------------------------------------------------------------
        a, aev = r.start(["cl", "Write a 2500-word story about a lighthouse keeper. Output only the story, no tools."])
        end = time.time() + 90
        while time.time() < end and not of(aev, "started"):
            time.sleep(0.2)
        sa = (of(aev, "started") or [{}])[0].get("session_id")
        check("a long claude turn starts", sa and a.poll() is None, aev[-3:])
        check("its session lock is held by the OS", sa and r.held(sa))
        rec = json.load(open(os.path.join(r.home, "sessions", "%s.json" % sa), encoding="utf-8")) if sa else {}
        check("sessions/<id>.json: pid, no hwnd needed", rec.get("pid") == a.pid and rec.get("hwnd") is None and rec.get("mode") == "write", rec)

        evs, rc, _ = r.stream(["cl", "--resume", sa or "x", "Say hi."], timeout=60)
        e = (of(evs, "error") or [{}])[0]
        check("stream --resume of a running session is refused, naming its pid",
              rc == 1 and e.get("kind") == "refused" and "open in another window" in e.get("message", "") and str(a.pid) in e.get("message", ""), evs)
        check("(reid --resume targets it)", r.state().get("sid") == sa, r.state())
        p = subprocess.run([REID, "--resume", "cl"], cwd=r.work, env=r.env, capture_output=True, text=True, encoding="utf-8",
                           timeout=60, stdin=subprocess.DEVNULL)
        check("interactive reid --resume of it is refused", p.returncode == 1 and "open in another window" in p.stderr, (p.returncode, p.stderr[-300:]))
        evs, rc, _ = r.stream(["cl", "Say hi."], timeout=60)
        e = (of(evs, "error") or [{}])[0]
        check("a second writing turn in the folder is refused", rc == 1 and "writing in this folder" in e.get("message", ""), evs)

        p = subprocess.run([REID, "cl"], cwd=r.work, env=r.env, capture_output=True, text=True, encoding="utf-8",
                           timeout=60, stdin=subprocess.DEVNULL)
        check("a new window in the folder is refused while it writes", p.returncode == 1 and "writing in this folder" in p.stderr,
              (p.returncode, p.stderr[-300:]))

        n0 = len(of(aev, "text_delta"))
        evs, rc, _ = r.stream(["cl", "--read-only", "Reply with just the word PONG."], timeout=120)
        n1 = len(of(aev, "text_delta"))
        check("a read-only turn streams alongside", rc == 0 and "PONG" in text_of(evs), (rc, evs[-3:]))
        check("... while the long turn kept streaming", a.poll() is None and n1 > n0, (a.poll(), n0, n1))

        kids = [c for c in psutil.Process(a.pid).children(recursive=True)]
        psutil.Process(a.pid).kill()  # only reid.exe: the OS must free its locks, its job must take claude down
        a.wait(10)
        time.sleep(1)
        alive = [c.pid for c in kids if c.is_running() and c.status() != psutil.STATUS_ZOMBIE]
        check("killing reid.exe takes its engine down too", kids and alive == [], (len(kids), alive))
        check("... and the OS dropped its session lock", sa and not r.held(sa))

        wins = [r.window(), r.window()]
        end = time.time() + 30
        while time.time() < end and len(r.windows()) < 2:
            time.sleep(0.5)
        check("two windows share one folder", len(r.windows()) == 2, r.windows())
        evs, rc, _ = r.stream(["cl", "Say hi."], timeout=60)
        e = (of(evs, "error") or [{}])[0]
        check("a headless writing turn is refused while windows are open there", rc == 1 and "window is open" in e.get("message", ""), evs)
        for w in wins:
            r.kill(w)
        evs, rc, err = r.stream(["cl", "--resume", sa or "x", "Reply with just the word BACK."], timeout=180)
        st = (of(evs, "started") or [{}])[0].get("session_id")
        check("with the windows gone, the killed session resumes (session and folder locks recovered)", rc == 0 and st == sa and "BACK" in text_of(evs),
              (rc, st, evs[-3:], err[-300:]))
    finally:
        r.cleanup()
    print("\n%d/%d passed" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
