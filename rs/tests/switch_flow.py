"""The full context switch (vision\\Spec\\SPEC-0.2.6.md Part 2), against the real Claude Code, Codex and
OpenCode: one chat moves across all three engines, every direction once, and each engine answers from the
whole conversation it never saw.

  1  turn 1 (claude) gives codeword 1; every later turn switches engine, adds a codeword and asks for all
     the codewords so far: cl>cx, cx>oc, oc>cl, cl>oc, oc>cx, cx>cl
  2  each switch says "context carried: N turns" and starts a new session (never the profile's old one)
  3  the chat's transcript in REIDCC_HOME\\chats has both records of every turn, with its engine
  4  a refused turn leaves no record

Reidcc runs on a temp REIDCC_HOME; the engine sessions it makes are deleted afterwards.

    python rs\\tests\\switch_flow.py          (REIDCC_BIN=rs\\target\\debug for a debug build)
"""
import os, sys, json, glob, shutil, tempfile, subprocess, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.environ.get("REIDCC_BIN") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "rs", "target", "release")
REID = os.path.join(BIN, "reid.exe")
ENGINE = {"cl": "claude", "cx": "codex", "oc": "opencode"}
WORDS = ["PERIWINKLE-42", "TANGERINE-7", "COBALT-19", "SAFFRON-3", "JUNIPER-88", "OBSIDIAN-5", "MAGENTA-61"]
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


root = tempfile.mkdtemp(prefix="reidsw_")
work, home = os.path.join(root, "work"), os.path.join(root, "home")
os.makedirs(work)
os.makedirs(home)
with open(os.path.join(home, "reid.json"), "w", encoding="utf-8") as f:
    json.dump({"default": "cl", "profiles": {"cl": {"model": "haiku"}, "cx": {"engine": "codex"}, "oc": {"engine": "opencode"}}}, f)
env = dict(os.environ, REIDCC_HOME=home)
chat = str(uuid.uuid4())
made = []  # (engine, session id)


def turn(profile, prompt, *extra):
    p = subprocess.run([REID, "--stream", profile, "--chat", chat, *extra, prompt], cwd=work, env=env, capture_output=True,
                       text=True, encoding="utf-8", timeout=400, stdin=subprocess.DEVNULL)
    evs = events(p.stdout)
    made.extend((ENGINE[profile], e["session_id"]) for e in of(evs, "started"))
    return evs, p.returncode, p.stderr


try:
    evs, rc, err = turn("cl", f"Remember codeword 1: {WORDS[0]}. Reply with just: noted.")
    check("1 claude turn ran", rc == 0 and of(evs, "started"), (rc, err[-300:], evs[-3:]))
    sids = {"cl": of(evs, "started")[0]["session_id"] if of(evs, "started") else ""}
    order = ["cl", "cx", "oc", "cl", "oc", "cx", "cl"]
    for n in range(1, len(order)):
        src, dst = order[n - 1], order[n]
        ask = (f"Remember codeword {n + 1}: {WORDS[n]}. Then list every codeword I have given you in this "
               "conversation, in order, one per line, nothing else.")
        evs, rc, err = turn(dst, ask, "--switch-from", src)
        name = f"{n + 1} {ENGINE[src]} > {ENGINE[dst]}"
        notes = [e["text"] for e in of(evs, "note")]
        check(f"{name}: carried", notes == [f"context carried: {n} turns in a new {ENGINE[dst]} session"], (notes, err[-300:]))
        started = [e["session_id"] for e in of(evs, "started")]
        check(f"{name}: a new session", started and started[0] != sids.get(dst), (started, sids.get(dst)))
        said = "".join(e["text"] for e in of(evs, "text_delta"))
        missing = [w for w in WORDS[:n + 1] if w not in said]
        check(f"{name}: knows every codeword", not missing and rc == 0, (missing, said, err[-300:]))
        if started:
            sids[dst] = started[0]

    # 3 the transcript
    path = os.path.join(home, "chats", chat + ".jsonl")
    records = [json.loads(l) for l in open(path, encoding="utf-8")] if os.path.exists(path) else []
    check("3 two records per turn", len(records) == 2 * len(order), len(records))
    check("3 each record names its engine", [r.get("engine") for r in records[::2]] == [ENGINE[p] for p in order],
          [r.get("engine") for r in records])
    check("3 roles alternate", [r.get("role") for r in records] == ["user", "assistant"] * len(order))

    # 4 a refused turn leaves no record
    evs, rc, err = turn("cl", "hi", "--resume", "no-such-session")
    check("4 refused", [e for e in of(evs, "error") if e.get("kind") == "refused"], evs)
    after = sum(1 for _ in open(path, encoding="utf-8")) if os.path.exists(path) else 0
    check("4 no record for it", after == len(records), after)
finally:
    opencode = shutil.which("opencode")
    claude_dir = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")
    codex_dirs = [os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex"), os.path.join(home, "codex")]
    for engine, sid in set(made):
        if engine == "opencode" and opencode:
            subprocess.run([opencode, "session", "delete", sid, "--standalone"], capture_output=True, timeout=60)
        elif engine == "claude":
            for f in glob.glob(os.path.join(claude_dir, "projects", "*", sid + ".jsonl")):
                os.remove(f)
        elif engine == "codex":
            for d in codex_dirs:
                for f in glob.glob(os.path.join(d, "sessions", "*", "*", "*", f"*{sid}.jsonl")):
                    os.remove(f)
    shutil.rmtree(root, ignore_errors=True)

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
