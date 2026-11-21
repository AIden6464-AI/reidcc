"""Stage 0 parity: reid.exe must print exactly what reid.py prints (vision/Spec/SPEC-rust-rewrite.md).

Runs both against a temp Reidcc folder: reid.json is the real profiles plus edge cases, personas/,
mds/, json/ and proxy/ are linked read-only, codex/ is fresh. Compares stdout, stderr and the exit
code byte for byte (temp file names masked), the Codex prompt files both write, and the reid.json
a missing config gets. Never touches E:\\reidcc\\reid.json or reid_state.json.

    python rs\\tests\\parity.py [--keep] [-k substring]
"""
import os, re, sys, json, time, shutil, subprocess, tempfile, difflib

HERE = os.path.dirname(os.path.abspath(__file__))
REIDCC = os.path.dirname(os.path.dirname(HERE))
RS = os.path.join(REIDCC, "rs", "target", "release", "reid.exe")
RS_STATUSLINE = '"%s" "--statusline"' % RS.replace("\\", "/")
TRACEBACK = "Traceback (most recent call last)"
# Differences accepted for stage 0, each with its reason. Anything else that differs fails.
KNOWN = {"--dry c-toml-bad": "TOML error wording is the toml crate's, not tomllib's (same line and column)"}
MASK = re.compile(r"reid_(prompt|settings)_\d+_[a-z0-9_]{8}")  # the pid is in the name (sweep_temps)

PY_WRAPPER = r'''
import sys
sys.path.insert(0, %r)
import reid
reid.statusline_command = lambda: %r   # the one intended difference: the CLI that runs the statusline
sys.exit(reid.main(sys.argv[1:]))
''' % (os.path.join(REIDCC, "python"), RS_STATUSLINE)

JSON_CASES = ['', '  ', '{', '{"a"', '{"a":', '{"a":1', '{"a":1,', '{"a":1,}', '{a:1}', '[1,]', '[1 2]', '"abc',
              '"a\x01"', '"a\\x"', '"a\\u12"', '"a\\', '01', '1 2', 'tru', '{"a":1}x', '\ufeff{}', '[', '[1,',
              '{"a" 1}', '{"a":1 "b":2}', '-', '1.', '1e', '{"a":\n  [1,\n  2,,]}', '{"\u00e9":"\x1f"}', '[1,\n]',
              '{"a":1,\n}', '\n\n  x', '{"a":1}\r\n{"b"', '[]']

TOML = '''model = "gpt-5"
model_provider = "test"
ratio = 0.5
flag = true
mixed = [1, "a", 2.0]
when = 1979-05-27T07:32:00Z
"odd key" = "v\\u00e9"

[model_providers.test]
name = "Test"
base_url = "https://example.invalid/v1"
env_key = "TEST_KEY"
query_params = {}

[env]
TEST_KEY = "not-a-real-key"
NUM = 5
'''

LONG_MEM = "# Long-term memory\n\n## Pinned facts\n" + "".join("- fact %d: é ünïcode line\n" % i for i in range(60)) + \
           "\n## Journal\n" + "".join("- 2026-01-%02d - entry %d with some words in it\n" % (i % 28 + 1, i) for i in range(300))


def edge_profiles():
    p = {
        "e-badengine": {"engine": "CODEX"}, "e-falseengine": {"engine": False}, "e-nullengine": {"engine": None, "model": "opus"},
        "e-missing-persona": {"persona": "personas/nope.md"},
        "e-merge": {"settings": "tjson/merge.json", "settings_json": {"permissions": {"allow": ["Read"]}, "x": "é\u2028"}},
        "e-merge-own-status": {"settings": "tjson/status.json"},
        "e-sj-list": {"settings_json": [1]}, "e-sj-empty-list": {"settings_json": []},
        "e-toml-on-claude": {"settings": "codex/test.toml"},
        "e-proxy-bad": {"proxy": "slim+nope"}, "e-proxy-both": {"proxy": ["slim", "ultra"]},
        "e-proxy-drop": {"proxy": " Slim , capture", "proxy_drop": ["a", "b"]},
        "e-tools-empty": {"tools": []}, "e-tools-null": {"tools": None}, "e-tools-two": {"tools": ["Read", "Bash"]},
        "e-safe-api": {"safe": True, "settings": "json/iyh.json"}, "e-safe": {"safe": True, "no_connectors": True},
        "e-mcp": {"mcp": "proxy/mini-mcp.json"}, "e-mcp-missing": {"mcp": "nope.json"}, "e-mcp-none": {"mcp": "none"},
        "e-env": {"env": {"FOO": 1, "BAR": True, "ENABLE_CLAUDEAI_MCP_SERVERS": "x", "PATH": None}},
        "e-args": {"args": ["--verbose", "a b", 'c"d', "e\\"]}, "e-args-str": {"args": "xy"},
        "e-mem-long": {"memory": True, "memory_file": "tmem_long.md"},
        "e-mem-limit": {"memory": True, "memory_file": "tmem_long.md", "memory_limit": 500},
        "e-mem-tiny": {"memory": True, "memory_file": "tmem_long.md", "memory_limit": 10},
        "e-mem-plain": {"memory": True, "memory_file": "tmem_plain.md"},
        "e-mem-empty": {"memory": True, "memory_file": "tmem_empty.md"},
        "e-persona-replace": {"persona": "tpersonas/crlf.md", "mode": "replace", "memory": True},
        "e-persona-add": {"persona": "tpersonas/crlf.md"},
        "e-persona-blank": {"persona": "tpersonas/blank.md"},
        "e-statusline-off": {"statusline": False}, "e-statusline-null": {"statusline": None, "settings_json": {"a": 1}},
        "e-model-num": {"model": 5}, "e-ünï name": {"model": "sonnet", "no_chrome": True},
        "c-plain": {"engine": "codex"}, "c-mem": {"engine": "codex", "memory": True},
        "c-persona": {"engine": "codex", "persona": "tpersonas/crlf.md"},
        "c-replace": {"engine": "codex", "persona": "tpersonas/crlf.md", "mode": "replace", "memory": True},
        "c-claude-model": {"engine": "codex", "model": "opus"}, "c-claude-model2": {"engine": "codex", "model": "Claude-x"},
        "c-claude-settings": {"engine": "codex", "settings": "json/iyh.json"},
        "c-proxy": {"engine": "codex", "proxy": "slim", "tools": []},
        "c-three": {"engine": "codex", "proxy": "slim", "tools": None, "safe": True},
        "c-toml": {"engine": "codex", "settings": "codex/test.toml", "model": "gpt-5.1"},
        "c-toml-nomodel": {"engine": "codex", "settings": "codex/test.toml", "statusline": False},
        "c-toml-envbad": {"engine": "codex", "settings": "codex/envbad.toml"},
        "c-toml-bad": {"engine": "codex", "settings": "codex/bad.toml"},
        "c-toml-missing": {"engine": "codex", "settings": "codex/nope.toml"},
        "c-args-C": {"engine": "codex", "args": ["-Cx"]}, "c-args-cd": {"engine": "codex", "args": ["--cd=y"]},
        "c-resume": {"engine": "codex", "args": ["resume"]},
        "c-mi": {"engine": "codex", "memory": True, "args": ["-c", "model_instructions_file=x"]},
        "c-mi-off": {"engine": "codex", "args": ["-c", "model_instructions_file=x"]},
        "c-mp": {"engine": "codex", "settings": "codex/test.toml", "args": ["--config=model_provider = x"]},
        "c-cfg": {"engine": "codex", "memory": True, "args": ["-c", "model_reasoning_effort=\"high\"", "-pfoo", "--enable", "x"]},
        "C Wëird--name!": {"engine": "codex", "memory": True},
    }
    for i in range(len(JSON_CASES)):
        p["e-json%02d" % i] = {"settings": "tjson/b%02d.json" % i}
    return p


LINKED = ("personas", "mds", "json")  # read-only folders the temp home links to


def junction(link, target):
    subprocess.run(["cmd", "/c", "mklink", "/J", link, target], check=True, capture_output=True)


def make_home(root):
    home = os.path.join(root, "home")
    os.makedirs(home)
    for d in LINKED:
        junction(os.path.join(home, d), os.path.join(REIDCC, d))
    # proxy\: its own copy (sessions write proxy\logs\), sharing only the mitmproxy install
    os.makedirs(os.path.join(home, "proxy"))
    for f in os.listdir(os.path.join(REIDCC, "proxy")):
        if os.path.isfile(os.path.join(REIDCC, "proxy", f)):
            shutil.copy(os.path.join(REIDCC, "proxy", f), os.path.join(home, "proxy"))
    junction(os.path.join(home, "proxy", ".venv"), os.path.join(REIDCC, "proxy", ".venv"))
    os.makedirs(os.path.join(home, "codex", "prompts"))
    for d in ("tjson", "tpersonas"):
        os.makedirs(os.path.join(home, d))
    w = lambda rel, text, nl="": open(os.path.join(home, rel), "w", encoding="utf-8", newline=nl).write(text)
    w("codex/test.toml", TOML)
    w("codex/bad.toml", 'model = "x"\nbroken line\n')
    w("codex/envbad.toml", 'model = "x"\nenv = "nope"\n')
    w("tjson/merge.json", json.dumps({"permissions": {"deny": ["Bash"], "allow": ["Edit"]}, "model": "ü", "n": 1.5e20}))
    w("tjson/status.json", json.dumps({"statusLine": {"type": "command", "command": "mine"}}))
    for i, c in enumerate(JSON_CASES):
        w("tjson/b%02d.json" % i, c)
    w("tpersonas/crlf.md", "You are Tëst.\r\nLine two\r\n\r\n  trailing  \r\n\r\n")
    w("tpersonas/blank.md", "\n\n   \n")
    shutil.copy(os.path.join(REIDCC, "reidcc_memory.md"), home)
    w("tmem_long.md", LONG_MEM)
    w("tmem_plain.md", "no sections here é\n" * 600)
    w("tmem_empty.md", "  \n\t\n")
    cfg = json.load(open(os.path.join(REIDCC, "reid.json"), encoding="utf-8"))
    cfg["profiles"].update(edge_profiles())
    json.dump(cfg, open(os.path.join(home, "reid.json"), "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    return home


def unlink_junctions(home):
    for d in LINKED + (os.path.join("proxy", ".venv"),):
        p = os.path.join(home, d)
        if os.path.lexists(p):
            os.rmdir(p)  # removes the junction, never what it points at


def run(which, home, args, cwd, stdin=b"", env_extra=None, drop=()):
    env = dict(os.environ, REIDCC_HOME=home, **(env_extra or {}))
    for k in ("EDITOR",) + tuple(drop):
        env.pop(k, None)
    argv = [RS] + args if which == "rs" else [sys.executable, os.path.join(home, "..", "pyrun.py")] + args
    p = subprocess.run(argv, cwd=cwd, env=env, input=stdin, capture_output=True, timeout=120)
    clean = lambda b: re.sub(r"127\.0\.0\.1:\d+", "127.0.0.1:PORT",
                             MASK.sub(r"reid_\1_XXXXXXXX", b.decode("utf-8", "replace")))
    return p.returncode, clean(p.stdout), clean(p.stderr)


def prompts(home):
    d = os.path.join(home, "codex", "prompts")
    return {n: open(os.path.join(d, n), "rb").read() for n in sorted(os.listdir(d))}


def main():
    keep = "--keep" in sys.argv
    only = sys.argv[sys.argv.index("-k") + 1] if "-k" in sys.argv else ""
    root = tempfile.mkdtemp(prefix="reidparity_")
    open(os.path.join(root, "pyrun.py"), "w").write(PY_WRAPPER)
    home = make_home(root)
    work = os.path.join(root, "work dir é")
    os.makedirs(work)
    names = list(json.load(open(os.path.join(home, "reid.json"), encoding="utf-8"))["profiles"])
    cases = [["-l"], ["-h"], ["--help"], ["--dry"], ["--dry", "-c"], ["--dry", "not-a-profile", "do X"],
             ["--dry", "slim", "a b", 'q"x', "back\\", ""], ["--back"]]
    cases += [["--dry", n] for n in names]
    status_in = [b"", b"{}", b"garbage", json.dumps({"workspace": {"current_dir": os.path.expanduser("~") + "\\kiln"},
                 "context_window": {"used_percentage": 91.5},
                 "rate_limits": {"five_hour": {"used_percentage": "76"}, "seven_day": {"used_percentage": 12.5}}}).encode(),
                 json.dumps({"cwd": "D:/x/y", "context_window": {"used_percentage": 74.5}, "rate_limits": {}}).encode()]
    fails, crashes, n = [], [], 0
    for args in cases:
        label = " ".join(args)
        if only and only not in label:
            continue
        n += 1
        before = prompts(home)
        py = run("py", home, args, work)
        after_py = prompts(home)
        for name in set(after_py) - set(before):
            if not name.startswith(".base-"):
                os.remove(os.path.join(home, "codex", "prompts", name))
        rs = run("rs", home, args, work)
        if label in ("-h", "--help"):
            # The version and update flags are specific to the versioned, installable Rust build.
            rc, stdout, stderr = rs
            rs = rc, re.sub(r"^    reid --(version|update) +.*\r?\n", "", stdout, flags=re.M), stderr
        after_rs = prompts(home)
        problems = []
        if py != rs and TRACEBACK in py[2] and TRACEBACK not in rs[2]:
            crashes.append(label)
            print("pycrash %s: Python raised %s; Rust: rc %d %s" % (label, py[2].strip().splitlines()[-1][:120], rs[0],
                                                                 (rs[1] + rs[2]).strip().splitlines()[-1][:150]))
            continue
        if py != rs:
            problems.append("output differs")
        new_base = [k for k in set(after_rs) - set(after_py) if k.startswith(".base-")]
        if new_base:
            problems.append("Rust made its own Codex base-prompt cache (%s): the cache key differs" % new_base)
        for k in set(after_py) | set(after_rs):
            if not k.startswith(".base-") and after_py.get(k) != after_rs.get(k):
                problems.append("prompt file %s differs" % k)
        if problems == ["output differs"] and label in KNOWN:
            crashes.append(label)
            print("known  %s: %s" % (label, KNOWN[label]))
            continue
        if problems:
            fails.append(label)
            print("DIFF  %s: %s" % (label, "; ".join(problems)))
            if py != rs:
                for part, a, b in (("rc", str(py[0]), str(rs[0])), ("stdout", py[1], rs[1]), ("stderr", py[2], rs[2])):
                    if a != b:
                        print("  -- %s (- python, + rust)" % part)
                        for line in difflib.unified_diff(a.splitlines(), b.splitlines(), lineterm="", n=0):
                            if not line.startswith(("---", "+++", "@@")):
                                print("  " + line[:300])
        else:
            print("ok    %s" % label)
    for i, data in enumerate(status_in):
        for prof in (None, "e-persona-replace", "o-opus47", "missing"):
            label = "--statusline #%d %s" % (i, prof)
            if only and only not in label:
                continue
            n += 1
            extra = {"REID_PROFILE": prof} if prof else {}
            py, rs = run("py", home, ["--statusline"], work, data, extra), run("rs", home, ["--statusline"], work, data, extra)
            print(("ok    " if py == rs else "DIFF  ") + label)
            if py != rs:
                fails.append(label)
                print("  py:", repr(py)[:300], "\n  rs:", repr(rs)[:300])
    # Real launches that end at once (the engine prints its version): the session path and the
    # reid_state.json write. Session ids and times are masked; the rest must match.
    state = os.path.join(home, "reid_state.json")
    mask_state = lambda b: re.sub(r'"(sid|at)": "[^"]*"', r'"\1": "X"', b.decode("utf-8")) if b else b
    for args in (["main2", "--version"], ["e-safe-api", "--version"], ["c-plain", "--version"], ["mini", "-v"],
                 ["slim", "--version"], ["e-proxy-drop", "--version"]):
        label = "launch " + " ".join(args)
        if only and only not in label:
            continue
        n += 1
        outs = []
        for which in ("py", "rs"):
            if os.path.exists(state):
                os.remove(state)
            r = run(which, home, args, work)
            outs.append((r, mask_state(open(state, "rb").read() if os.path.exists(state) else None)))
        print(("ok    " if outs[0] == outs[1] else "DIFF  ") + label)
        if outs[0] != outs[1]:
            fails.append(label)
            print("  py:", repr(outs[0])[:500], "\n  rs:", repr(outs[1])[:500])
    # Audit fixes (2026-11-20): checked on both CLIs, not only compared.
    # A claude.cmd or codex.cmd in the folder never runs, even without the
    # NoDefaultCurrentDirectoryInExePath that Claude Code puts in this environment.
    trap = os.path.join(root, "trap;dir")
    os.makedirs(trap)
    for f in ("claude.cmd", "codex.cmd", "codex.exe"):
        open(os.path.join(trap, f), "w").write("@echo trapped\n")
    for args in (["--dry", "main2"], ["--dry", "c-plain"]):
        label = "cwd hijack " + args[1]
        if only and only not in label:
            continue
        n += 1
        outs = [run(w, home, args, trap, drop=("NODEFAULTCURRENTDIRECTORYINEXEPATH",)) for w in ("py", "rs")]
        hit = [w for w, o in zip(("py", "rs"), outs) if trap.lower() in (o[1] + o[2]).lower() or o[0] != 0]
        ok = outs[0] == outs[1] and not hit
        print(("ok    " if ok else "FAIL  ") + label + ("" if ok else ": ran from the folder or failed: %s" % hit))
        if not ok:
            fails.append(label)
            print("  py:", repr(outs[0])[:300], "\n  rs:", repr(outs[1])[:300])
    # The temp sweep keeps old files of a running pid, removes old ones of a dead pid; a stale
    # reid_state.json.lock is cleared; no lock or .tmp is left behind.
    label = "sweep + state lock"
    if not only or only in label:
        n += 1
        tmpd = os.path.join(root, "tmp")
        os.makedirs(tmpd)
        gone = subprocess.Popen([sys.executable, "-c", "0"])
        gone.wait()
        files = {"reid_settings_%d_aaaaaaaa.json" % os.getpid(): (True, True),   # old, running: keep
                 "reid_prompt_%d_bbbbbbbb.md" % gone.pid: (True, False),         # old, dead: remove
                 "reid_settings_cccccccc.json": (True, False),                   # old, no pid: remove
                 "reid_prompt_%d_dddddddd.md" % gone.pid: (False, True)}         # new: keep
        want = sorted(f for f, (_, keep) in files.items() if keep)
        lock = state + ".lock"
        problems = []
        for which in ("py", "rs"):
            for f, (old, _) in files.items():
                p = os.path.join(tmpd, f)
                open(p, "w").write("x")
                if old:
                    os.utime(p, (time.time() - 7 * 3600,) * 2)
            open(lock, "w").close()
            os.utime(lock, (time.time() - 20,) * 2)
            if os.path.exists(state):
                os.remove(state)
            run(which, home, ["main2", "--version"], work, env_extra={"TEMP": tmpd, "TMP": tmpd})
            left = sorted(f for f in os.listdir(tmpd) if f in files)
            if left != want:
                problems.append("%s sweep left %s" % (which, left))
            if os.path.exists(lock):
                problems.append("%s left the lock" % which)
            if not os.path.exists(state):
                problems.append("%s wrote no state" % which)
            stray = [f for f in os.listdir(home) if f.endswith(".tmp")]
            if stray:
                problems.append("%s left %s" % (which, stray))
            for f in os.listdir(tmpd):
                os.remove(os.path.join(tmpd, f))
        print(("ok    " if not problems else "FAIL  ") + label + ("" if not problems else ": " + "; ".join(problems)))
        if problems:
            fails.append(label)
    # reid.json missing or broken
    for label, text in (("config missing", None), ("config broken", '{"profiles": {"a": {}},}'),
                        ("config empty", ""), ("config no profiles", '{"default": "x", "profiles": {}}'),
                        ("config bad default", '{"default": "x", "profiles": {"a": {"model": "opus"}, "b": {}}}')):
        if only and only not in label:
            continue
        n += 1
        h2 = os.path.join(root, label.replace(" ", "_"))
        os.makedirs(h2)
        cfgp = os.path.join(h2, "reid.json")
        outs = []
        for which in ("py", "rs"):
            if text is None:
                if os.path.exists(cfgp):
                    os.remove(cfgp)
            else:
                open(cfgp, "w", encoding="utf-8").write(text)
            r = run(which, h2, ["-l"], work)
            outs.append((r, open(cfgp, "rb").read() if os.path.exists(cfgp) else None))
        print(("ok    " if outs[0] == outs[1] else "DIFF  ") + label)
        if outs[0] != outs[1]:
            fails.append(label)
            print("  py:", repr(outs[0])[:400], "\n  rs:", repr(outs[1])[:400])
    print("\n%d/%d identical, %d accepted (Python crashes and Rust doesn't, or listed in KNOWN), %d differ"
          % (n - len(fails) - len(crashes), n, len(crashes), len(fails)))
    if keep:
        print("kept", root)
    else:
        unlink_junctions(home)
        shutil.rmtree(root, ignore_errors=True)
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
