"""TUI parity: reid.exe's TUI must act like reid.py's (vision/Spec/SPEC-rust-tui-gui.md, part 1).

Runs both TUIs in a pseudo-terminal (ConPTY via pywinpty) at 80x24, 100x30 and 160x45 and sends the same
keys to each. After each sequence the reid.json both wrote must match byte for byte, and so must the
editor calls, the exit code, the number of steps that ran and reid_state.json (session ids and times
masked). Screens aren't compared any more: the TUI's look is SPEC-one-look's, not reid.py's (its Part 8).

Each run gets the same temp Reidcc folder (REIDCC_HOME), reset between runs: personas/, mds/ and json/
are junctions, proxy/ files are copied, codex/ is fresh. Never touches E:\\reidcc\\reid.json or
reid_state.json.

    rs\\tests\\.venv\\Scripts\\python rs\\tests\\tui_parity.py [--keep] [-k substring] [--size 80x24]

Needs pywinpty and pyte in rs\\tests\\.venv (python -m venv rs\\tests\\.venv; .venv\\Scripts\\pip install
pywinpty pyte). Run with another Python, it re-runs itself with that one.
"""
import os, re, sys, json, time, shutil, subprocess, tempfile, threading

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")
try:
    import pyte
    from winpty import PtyProcess
except ImportError:
    if os.path.exists(VENV_PY) and os.path.abspath(sys.executable).lower() != VENV_PY.lower():
        sys.exit(subprocess.call([VENV_PY, os.path.abspath(__file__)] + sys.argv[1:]))
    raise

sys.path.insert(0, HERE)
import parity  # noqa: E402  (junction, TOML, the CLI wrapper)

REIDCC = parity.REIDCC
RS = parity.RS
SIZES = [(80, 24), (100, 30), (160, 45)]
K = {"up": "\x1b[A", "down": "\x1b[B", "right": "\x1b[C", "left": "\x1b[D", "enter": "\r", "esc": "\x1b",
     "home": "\x1b[H", "end": "\x1b[F"}
# reid.py runs on the Python that made the venv, not the venv's own copy
BASE_PY = getattr(sys, "_base_executable", sys.executable)
SID = "00000000-0000-4000-8000-000000000000"
# Differences accepted, each with its reason: {sequence label: reason}. Anything else that differs fails.
_CODEX_PROXY = ("Codex has its own proxy in Rust (SPEC-codex-proxy.md, 2026-11-23): its proxy row isn't greyed "
                "and the refusal no longer names the proxy; the Python app still refuses it")
KNOWN = {label: _CODEX_PROXY for label in ("browse", "edit codex claude-fields", "new rename delete default",
                                           "launch codex --version, gate skipped", "launch claude --version",
                                           "reid back + resume")}

EXTRA_PROFILES = {
    "t-missing-persona": {"persona": "personas/nope.md"},
    "t-codex-claude": {"engine": "codex", "proxy": "slim", "tools": [], "safe": True},
    "t-codex-toml": {"engine": "codex", "settings": "codex/test.toml", "model": "gpt-5.1",
                     "persona": "personas/plain.md", "mode": "replace"},
    "t-tools": {"tools": ["Read", "Bash"], "mcp": "none", "safe": True, "no_connectors": True,
                "args": ["--verbose", "a b", "c\"d"]},
    "A very long profile name that does not fit": {"memory": True, "mcp": "proxy/mini-mcp.json"},
    "t-back": {"model": "sonnet"},
    "t-claude-ver": {"model": "opus", "args": ["--version"]},
    "t-codex-ver": {"engine": "codex", "args": ["--version"]},
}

EDITOR_CMD = '@echo off\r\necho %~1>> "%~dp0editor.log"\r\n'


# ------------------------------------------------------------------ home ---
def make_home(root, work, work2):
    home = os.path.join(root, "home")
    os.makedirs(home)
    for d in parity.LINKED:
        parity.junction(os.path.join(home, d), os.path.join(REIDCC, d))
    os.makedirs(os.path.join(home, "proxy"))
    for f in os.listdir(os.path.join(REIDCC, "proxy")):
        if os.path.isfile(os.path.join(REIDCC, "proxy", f)):
            shutil.copy(os.path.join(REIDCC, "proxy", f), os.path.join(home, "proxy"))
    parity.junction(os.path.join(home, "proxy", ".venv"), os.path.join(REIDCC, "proxy", ".venv"))
    os.makedirs(os.path.join(home, "codex", "prompts"))
    open(os.path.join(home, "codex", "test.toml"), "w", encoding="utf-8", newline="").write(parity.TOML)
    shutil.copy(os.path.join(REIDCC, "reidcc_memory.md"), home)
    cfg = json.load(open(os.path.join(REIDCC, "reid.json"), encoding="utf-8"))
    cfg["profiles"].update(EXTRA_PROFILES)
    base_cfg = json.dumps(cfg, indent=2, ensure_ascii=False).encode("utf-8")
    state = {"last": {"profile": "main2", "cwd": work, "sid": SID, "at": "2026-11-20T10:30:00"},
             "recent_dirs": [work, work2, os.path.join(root, "gone")]}
    base_state = json.dumps(state, indent=2, ensure_ascii=False).encode("utf-8")
    return home, base_cfg, base_state


def reset_home(home, cfg_bytes, state_bytes):
    open(os.path.join(home, "reid.json"), "wb").write(cfg_bytes)
    st = os.path.join(home, "reid_state.json")
    if state_bytes is None:
        if os.path.exists(st):
            os.remove(st)
    else:
        open(st, "wb").write(state_bytes)
    for f in os.listdir(home):
        if f.endswith((".tmp", ".lock")):
            os.remove(os.path.join(home, f))
    d = os.path.join(home, "codex", "prompts")
    for f in os.listdir(d):
        if not f.startswith(".base-"):
            os.remove(os.path.join(d, f))


# --------------------------------------------------------------- terminal ---
class Term:
    """One TUI in a ConPTY, its output fed to a pyte screen."""

    def __init__(self, argv, cwd, env, cols, rows):
        self.cols, self.rows = cols, rows
        self.screen = pyte.Screen(cols, rows)
        self.stream = pyte.Stream(self.screen)
        self.lock = threading.Lock()
        self.last = time.time()
        self.chunks = 0
        self.proc = PtyProcess.spawn(argv, cwd=cwd, env=env, dimensions=(rows, cols))
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        while True:
            try:
                data = self.proc.read(65536)
            except (EOFError, OSError):
                break
            if not data:
                if not self.proc.isalive():
                    break
                time.sleep(0.01)
                continue
            with self.lock:
                self.stream.feed(data)
                self.last = time.time()
                self.chunks += 1

    def send(self, s):
        if self.proc.isalive():
            self.proc.write(s)

    def text(self):
        with self.lock:
            return "\n".join(self.screen.display)

    def settle(self, quiet=0.3, first=3.0, timeout=20.0, since=None):
        """Wait for output after `since` (up to `first` s), then for `quiet` s without output; and
        while the Codex sign-in check still says checking…, keep waiting for its redraw.
        Every key repaints, so `first` only runs out when the machine is busy; at 1 s a slow
        repaint was snapshotted before it came (a stale screen, seen under load)."""
        start = time.time()
        n0 = since if since is not None else self.chunks
        while time.time() - start < first and self.chunks == n0 and self.proc.isalive():
            time.sleep(0.02)
        while time.time() - start < timeout:
            if time.time() - self.last >= quiet and ("checking…" not in self.text() or time.time() - start > 15):
                return
            time.sleep(0.02)

    def until(self, text, timeout=60.0):
        start = time.time()
        while time.time() - start < timeout:
            if text in self.text():
                return True
            time.sleep(0.05)
        return False

    def wait_exit(self, timeout=30.0):
        start = time.time()
        while self.proc.isalive() and time.time() - start < timeout:
            time.sleep(0.05)
        time.sleep(0.3)  # the last output
        return None if self.proc.isalive() else self.proc.exitstatus

    def snapshot(self):
        with self.lock:
            rows = []
            for y in range(self.rows):
                line = self.screen.buffer[y]
                rows.append([(line[x].data, line[x].fg, line[x].bg, line[x].bold, line[x].reverse,
                              line[x].underscore, line[x].italics) for x in range(self.cols)])
            return rows

    def kill(self):
        if self.proc.isalive():
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)], capture_output=True)


TIME = re.compile(r"\d\d:\d\d")


def masked(snap):
    """The `last … · HH:MM` row shows when the last session started; the two runs start minutes apart."""
    out = []
    for row in snap:
        text = "".join(c[0] for c in row)
        if text.startswith(" last "):
            row = list(row)
            for m in TIME.finditer(text):
                for x in range(m.start(), m.end()):
                    row[x] = ("X",) + row[x][1:]
        out.append(row)
    return out


# -------------------------------------------------------------- sequences ---
def keys(*names):
    return [K.get(n, n) for n in names]


def type_(text):
    return text + "\r"


def sequences(n_profiles):
    """(label, steps, options). A step is a string to send, or a tuple (send, wait) where wait is
    "settle" (default), ("text", s), "exit", ("sleep", s) (no snapshot) or ("break",) (reid.json
    is broken before sending)."""
    names = list(json.loads(BASE_CFG)["profiles"])
    idx = names.index
    up_to = lambda name: [K["down"]] * idx(name)  # from the first profile
    seqs = []

    # every profile selected: down through all, wrap, up, digits, then quit
    seqs.append(("browse", keys(*(["down"] * n_profiles)) + keys("up", "k", "j", "3", "9", "1", "0", "z") +
                 [("q", "exit")], {}))

    # every edit picker on a Claude profile, opened and chosen
    s = up_to("opus47") + ["e"]
    s += ["\r", K["esc"]]                                   # engine: open, back
    s += [K["down"], "\r", "j", "j", "\r"]                  # model: two down, choose
    s += [K["down"], "\r", "j", "\r"]                       # sign-in: first settings file
    s += [K["down"], "\r", K["end"], "\r", type_("personas/plain.md")]  # persona: a typed path not found
    s += ["\r", K["end"], "\r", type_('"%s"' % os.path.join(HOME, "personas", "plain.md"))]  # found
    s += ["\r", "k", "\r"]                                  # persona: one up in the list
    s += [K["down"], "\r", "\r"]                            # persona mode: replace, then add
    s += [K["down"], "\r"]                                  # memory
    s += [K["down"], "\r", "j", "j", "\r"]                  # proxy
    s += [K["down"], "\r", "j", "j", "\r"]                  # tools: core + web
    s += ["\r", K["end"], "\r", type_("Read, Bash ,,Grep")]  # tools: type a list
    s += [K["down"], "\r", "j", "\r"]                       # mcp: none
    s += ["\r", "j", "j", "\r"]                             # mcp: a file
    s += [K["down"], "\r", K["down"], "\r", K["down"], "\r"]  # chrome, connectors, safe
    s += [K["down"], "\r", type_('--verbose "a b" c\\"d')]  # extra args
    s += ["\r", type_("-")]                                 # extra args cleared
    s += [K["down"], "\r", type_("opus47-x")]               # rename
    s += ["o", "m", K["esc"], "d", ("q", "exit")]
    seqs.append(("edit claude", s, {}))

    # the same profile's pickers, cancelled each way (esc, q, left), and typed paths that don't exist
    s = up_to("main2") + ["e", K["down"], "\r", K["end"], "\r", "\r"]   # type a model id: empty = cancel
    s += [K["down"], "\r", K["end"], "\r", type_("nope\\x.json")]        # sign-in: missing path
    s += [K["down"], "\r", "q", "\r", K["left"]]                        # persona: q, left
    s += [K["down"], "\r"]                                                # mode needs a persona
    s += [K["down"], K["down"], "\r", K["home"], "\r"]                    # proxy home
    s += [K["down"] * 2, "\r", K["end"], "\r", type_("nope.json")]        # mcp missing path
    s += [K["down"] * 5, "\r", type_("claude")]                           # rename to an existing name
    s += ["\r", type_("main2")]                                           # rename to itself
    s += ["\r", type_("main2-renamed")]                                   # rename, default follows? (not default)
    s += [K["esc"], "e", K["esc"], ("q", "exit")]
    seqs.append(("edit cancels", s, {}))

    # a Codex profile: greyed fields, Claude's fields refused, engine switch both ways, Codex models
    s = up_to("new") + ["e"]
    s += [K["down"] * 6, "\r"]                              # proxy: Claude's
    s += [K["down"], "\r", K["down"], "\r", K["down"], "\r", K["down"], "\r", K["down"], "\r"]
    s += [K["up"] * 11, "\r", "k", "\r"]                    # engine -> claude
    s += ["\r", "j", "\r"]                                  # engine -> codex
    s += [K["down"], "\r", "\r"]                            # model: first codex model
    s += ["\r", K["end"], "\r", type_("gpt-5.1-codex")]     # model: typed
    s += [K["down"], "\r", "j", "\r"]                       # sign-in: codex/test.toml
    s += ["\r", "k", "\r"]                                  # sign-in: back to codex login
    s += [K["down"], "\r", "j", "\r", K["down"], "\r"]      # persona + replace mode
    s += [K["esc"], ("q", "exit")]
    seqs.append(("edit codex", s, {}))

    # a Codex profile with Claude's fields on: they stay changeable so they can be turned off
    s = up_to("t-codex-claude") + ["e", K["down"] * 6, "\r", "\r"]   # proxy: open, keep
    s += ["\r", K["home"], "\r"]                                    # proxy -> off
    s += [K["down"], "\r", K["home"], "\r", K["down"] * 4, "\r"]   # tools -> all, safe off
    s += [K["up"] * 11, "\r", "k", "\r", "\r", "j", "\r"]         # engine claude and back
    s += [K["esc"], ("q", "exit")]
    seqs.append(("edit codex claude-fields", s, {}))

    # new / rename / delete / default
    s = up_to("main2") + ["n", type_("t-new"), K["down"], "\r", "j", "\r", K["esc"]]
    s += ["n", type_("main2"), "n", "\r"]                   # exists; empty = cancel
    s += ["x", "n", "x", "y"]                               # keep, then delete
    s += ["d", K["up"], "d", "x", "y"]                      # default, delete the default
    s += [K["home"], "e"] + [K["down"]] * 13 + ["\r", type_("renamed-default"), K["esc"]]
    s += ["9", "x", "\x03"]                                 # Ctrl+C at the question: quits
    s.append(("", "exit"))
    seqs.append(("new rename delete default", s, {}))

    # folder picker and typed folders; memory from the main screen
    s = ["w", K["esc"], "w", "j", "\r", "w", "\r", "w", K["end"], "\r", type_("Z:\\nowhere here"),
         "w", K["end"], "\r", type_('"%s"' % WORK), "m", ("q", "exit")]
    seqs.append(("folder", s, {}))

    # the last profile can't be deleted; nothing to resume; resume on Codex
    s = up_to("new") + ["r", "1", "r"]
    seqs.append(("resume messages", s + [("q", "exit")], {"state": None}))

    # broken reid.json while open: on the main screen, and inside the edit screen
    seqs.append(("broken json main", ["j", ("j", ("break",)), ("", "exit")], {}))
    seqs.append(("broken json edit", ["e", K["down"] * 5, ("\r", ("break",)), ("", "exit")], {}))

    # a not-ready profile: no gate, the error says why
    seqs.append(("launch not ready", up_to("t-missing-persona") + ["\r", ("q", "exit")], {}))

    # real launches that end at once: Codex comes back (the gate skipped by a key), Claude's /exit quits
    s = up_to("t-codex-ver") + [("\r", ("sleep", 0.45)), ("z", ("text", "Back from Codex.")), "j", ("q", "exit")]
    seqs.append(("launch codex --version, gate skipped", s, {}))
    s = up_to("t-claude-ver") + [("\r", "exit")]
    seqs.append(("launch claude --version", s, {}))

    # /reid back: a stand-in Claude (cmd.exe) that the test ends with the flag file, then r resumes it
    s = up_to("t-back") + [("\r", ("sleep", 0.3)), (" ", ("text", ">")),
                           (type_('echo back> "%REID_FLAG%"'), ("text", "Back from the session.")),
                           ("r", ("text", ">")), (type_("exit 3"), ("text", "Session ended with code 3")),
                           ("q", "exit")]
    seqs.append(("reid back + resume", s, {"fake_claude": True}))

    # from the CLI: quitting Codex lands in the TUI; so does /reid after reid --resume
    seqs.append(("cli codex lands in tui", ["j", ("q", "exit")],
                 {"args": ["t-codex-ver"], "start": "Back from Codex."}))
    s = [(type_('echo back> "%REID_FLAG%"'), ("text", "Back from the session.")), ("q", "exit")]
    seqs.append(("cli resume, /reid lands in tui", s, {"args": ["--resume", "t-back"], "start": ">",
                                                       "fake_claude": True}))
    return seqs


# ------------------------------------------------------------------- run ---
def run_seq(which, label, steps, opts, cols, rows, env_base):
    reset_home(HOME, BASE_CFG, opts.get("state", BASE_STATE))
    log = os.path.join(ROOT, "editor.log")
    if os.path.exists(log):
        os.remove(log)
    env = dict(env_base)
    if opts.get("fake_claude"):
        env["PATH"] = FAKEBIN + ";" + env["PATH"]
    args = opts.get("args", ["--tui"])
    argv = [RS] + args if which == "rs" else [BASE_PY, PYRUN] + args
    t = Term(argv, WORK, env, cols, rows)
    snaps = []
    exit_code = "running"
    try:
        started = t.until(opts.get("start", "profiles"), 30)
        t.settle()
        snaps.append(("start" if started else "start: timed out waiting for %r" % opts.get("start", "profiles"),
                      masked(t.snapshot())))
        if not started:
            print("  (%s %s: never showed %r)" % (which, label, opts.get("start", "profiles")))
        for n, step in enumerate(steps):
            send, wait = (step, "settle") if isinstance(step, str) else step
            if wait == ("break",):
                open(os.path.join(HOME, "reid.json"), "w", encoding="utf-8").write('{"profiles": {"a": {}},}')
                wait = "settle"
            n0 = t.chunks
            t.send(send)
            if wait == "settle":
                t.settle(since=n0)
            elif wait == "exit":
                exit_code = t.wait_exit()
            elif wait[0] == "text":
                if not t.until(wait[1]):
                    snaps.append(("step %d %r: timed out waiting for %r" % (n, send, wait[1]), masked(t.snapshot())))
                t.settle()
            elif wait[0] == "sleep":
                time.sleep(wait[1])
                continue
            snaps.append(("step %d %r" % (n, send), masked(t.snapshot())))
            if not t.proc.isalive() and exit_code == "running":
                exit_code = t.wait_exit()
                snaps.append(("exited", masked(t.snapshot())))
                break
    finally:
        t.kill()
    cfg = open(os.path.join(HOME, "reid.json"), "rb").read()
    st = os.path.join(HOME, "reid_state.json")
    state = open(st, "rb").read() if os.path.exists(st) else None
    if state:
        state = re.sub(rb'"(sid|at)": "[^"]*"', rb'"\1": "X"', state)
    editor = open(log, "rb").read() if os.path.exists(log) else b""
    return {"snaps": snaps, "cfg": cfg, "state": state, "editor": editor, "exit": exit_code}


def compare(py, rs):
    problems = []
    if len(py["snaps"]) != len(rs["snaps"]):
        problems.append("%d screens vs %d (%s / %s)" % (len(py["snaps"]), len(rs["snaps"]),
                                                       py["snaps"][-1][0], rs["snaps"][-1][0]))
    if rs["state"]:
        # Rust's resume record also names the engine, and keeps Codex sessions too (SPEC-unified-interface Step 0)
        last = rb'  "last": \{[^}]*\},\r?\n'
        s = re.sub(rb'"engine": "claude",\r?\n\s*', b"", rs["state"])
        if b'"engine": "codex"' in s:
            m = re.search(last, py["state"] or b"")
            s = re.sub(last, (m.group(0) if m else b"").replace(b"\\", b"\\\\"), s)
        rs = dict(rs, state=s)
    for k in ("cfg", "state", "editor", "exit"):
        if py[k] != rs[k]:
            problems.append("%s differs: py %r / rs %r" % (k, py[k] if k == "exit" else (py[k] or b"")[:200],
                                                            rs[k] if k == "exit" else (rs[k] or b"")[:200]))
    return problems


def main():
    global ROOT, HOME, BASE_CFG, BASE_STATE, WORK, PYRUN, FAKEBIN
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    keep = "--keep" in sys.argv
    only = sys.argv[sys.argv.index("-k") + 1] if "-k" in sys.argv else ""
    sizes = SIZES
    if "--size" in sys.argv:
        c, r = sys.argv[sys.argv.index("--size") + 1].split("x")
        sizes = [(int(c), int(r))]
    ROOT = tempfile.mkdtemp(prefix="reidtui_")
    WORK = os.path.join(ROOT, "work dir é")
    work2 = os.path.join(ROOT, "other")
    os.makedirs(WORK)
    os.makedirs(work2)
    HOME, BASE_CFG, BASE_STATE = make_home(ROOT, WORK, work2)
    PYRUN = os.path.join(ROOT, "pyrun.py")
    open(PYRUN, "w").write(parity.PY_WRAPPER)
    FAKEBIN = os.path.join(ROOT, "fakebin")
    exe_dir = os.path.join(FAKEBIN, "node_modules", "@anthropic-ai", "claude-code", "bin")
    os.makedirs(exe_dir)
    open(os.path.join(FAKEBIN, "claude.cmd"), "w").write("@echo off\r\n")
    shutil.copy(os.path.join(os.environ["SystemRoot"], "System32", "cmd.exe"), os.path.join(exe_dir, "claude.exe"))
    editor = os.path.join(ROOT, "editor.cmd")
    open(editor, "w", newline="").write(EDITOR_CMD)
    env = dict(os.environ, REIDCC_HOME=HOME, EDITOR=editor)
    for k in ("COLUMNS", "LINES"):
        env.pop(k, None)
    n_profiles = len(json.loads(BASE_CFG)["profiles"])
    total, fails, known = 0, [], []
    try:
        for cols, rows in sizes:
            for label, steps, opts in sequences(n_profiles):
                full = "%dx%d %s" % (cols, rows, label)
                if only and only not in full:
                    continue
                total += 1
                py = run_seq("py", label, steps, opts, cols, rows, env)
                rs = run_seq("rs", label, steps, opts, cols, rows, env)
                problems = compare(py, rs)
                if problems and label in KNOWN:
                    known.append(full)
                    print("known %s: %s" % (full, KNOWN[label]))
                elif problems:
                    fails.append(full)
                    print("DIFF  %s (%d screens)" % (full, len(py["snaps"])))
                    for p in problems:
                        print("  " + p)
                else:
                    distinct = len({tuple(map(tuple, s)) for _, s in py["snaps"]})
                    print("ok    %s (%d steps, %d distinct screens, exit %s)" % (full, len(py["snaps"]), distinct, py["exit"]))
                sys.stdout.flush()
    finally:
        print("\n%d/%d identical, %d accepted (KNOWN), %d differ" % (total - len(fails) - len(known), total,
                                                                    len(known), len(fails)))
        if keep:
            print("kept", ROOT)
        else:
            parity.unlink_junctions(HOME)
            shutil.rmtree(ROOT, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
