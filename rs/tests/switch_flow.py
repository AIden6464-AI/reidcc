"""The full context switch (vision\\Spec\\SPEC-0.2.6.md Part 2), against the real Claude Code, Codex and
OpenCode: one chat moves across all three engines, every direction once, and each engine answers from the
whole conversation it never saw.

  1  turn 1 (claude) gives codeword 1; every later turn switches engine, adds a codeword and asks for all
     the codewords so far: cl>cx, cx>oc, oc>cl, cl>oc, oc>cx, cx>cl
  2  each switch says "context carried: N turns" and starts a new session (never the profile's old one)
  3  the chat's transcript in REIDCC_HOME\\chats has both records of every turn, with its engine
  4  a refused turn leaves no record
  5  long chats: 240 messages resume in Claude and Codex; a transcript over 60% of OpenCode's window keeps
     the first turn, the newest and the gap line, and the turn still runs
  6  a stopped turn keeps its ask; a read-only switch carries the chat and writes nothing
  7  a folder whose path is too long for Reidcc to know Claude's session folder: the switch falls back to
     text and the turn runs; once Claude has made that folder, the next switch carries natively
  8  a writing switch into a busy folder is refused before anything is carried
  9  (debug build) an engine that won't resume the carried session: the turn runs once more as a new
     session with the conversation as text, the chat only ever sees the new id, and the next turn
     resumes it

Reidcc runs on a temp REIDCC_HOME; the engine sessions it makes are deleted afterwards.

    python rs\\tests\\switch_flow.py          (REIDCC_BIN=rs\\target\\debug for a debug build)
"""
import os, sys, json, glob, time, shutil, tempfile, subprocess, uuid

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


t_start = time.time()
root = tempfile.mkdtemp(prefix="reidsw_")
work, home = os.path.join(root, "work"), os.path.join(root, "home")
os.makedirs(work)
os.makedirs(home)
with open(os.path.join(home, "reid.json"), "w", encoding="utf-8") as f:
    json.dump({"default": "cl", "profiles": {"cl": {"model": "haiku"}, "cx": {"engine": "codex"}, "oc": {"engine": "opencode"}}}, f)
env = dict(os.environ, REIDCC_HOME=home)
chat = str(uuid.uuid4())
made = []  # (engine, session id)


def carried(n, engine):
    return f"context carried: {n} turn{'' if n == 1 else 's'} in a new {engine} session"


def said_in(evs):
    return "".join(e["text"] for e in of(evs, "text_delta"))


def slug(path):
    return "".join(c if c.isascii() and c.isalnum() else "-" for c in path)


def folder_lock(folder):
    """locks.rs folder_paths: FNV-1a of the folder's normcase(abspath), in REIDCC_HOME\\locks."""
    h = 0xcbf29ce484222325
    for b in os.path.normcase(os.path.abspath(folder)).rstrip("\\/").encode():
        h = ((h ^ b) * 0x100000001b3) & 0xFFFFFFFFFFFFFFFF
    os.makedirs(os.path.join(home, "locks"), exist_ok=True)
    return os.path.join(home, "locks", "%016x.lock" % h)


def turn(profile, prompt, *extra, chat_id=None, cwd=None, reid=REID, more_env=None):
    p = subprocess.run([reid, "--stream", profile, "--chat", chat_id or chat, *extra, prompt], cwd=cwd or work,
                       env=dict(env, **(more_env or {})), capture_output=True,
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
        check(f"{name}: carried", notes == [carried(n, ENGINE[dst])], (notes, err[-300:]))
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

    # 5 long chats, written straight into the transcript
    def fake_chat(n, filler, words):
        cid = str(uuid.uuid4())
        with open(os.path.join(home, "chats", cid + ".jsonl"), "w", encoding="utf-8") as f:
            for i in range(n):
                said = words.get(i, f"note {i}") + " " + filler
                f.write(json.dumps({"role": "user", "profile": "cl", "engine": "claude", "model": "haiku", "text": said}) + "\n")
                f.write(json.dumps({"role": "assistant", "profile": "cl", "engine": "claude", "model": "haiku",
                                    "parts": [{"text": f"noted {i}"}]}) + "\n")
        return cid

    ask = "List every codeword I have given you in this conversation, one per line, nothing else."
    long_chat = fake_chat(120, "", {0: "The first codeword is AMBER-1.", 60: "The middle codeword is VIOLET-60."})
    for k, dst in enumerate(["cl", "cx"]):  # the claude turn joins the chat too: codex carries 121
        evs, rc, err = turn(dst, ask, "--switch-from", "oc", chat_id=long_chat)
        said = "".join(e["text"] for e in of(evs, "text_delta"))
        notes = [e["text"] for e in of(evs, "note")]
        check(f"5 {ENGINE[dst]} resumes a 240-message session", notes == [f"context carried: {120 + k} turns in a new {ENGINE[dst]} session"]
              and "AMBER-1" in said and "VIOLET-60" in said, (notes, said, err[-300:]))
    big = fake_chat(150, "x" * 3000, {0: "The first codeword is AMBER-1.", 149: "The newest codeword is CORAL-149."})
    evs, rc, err = turn("oc", ask, "--switch-from", "cl", chat_id=big)
    said = "".join(e["text"] for e in of(evs, "text_delta"))
    notes = [e["text"] for e in of(evs, "note")]
    started = [e["session_id"] for e in of(evs, "started")]
    check("5 over 60% of OpenCode's window: still carried, the turn runs", notes == ["context carried: 150 turns in a new opencode session"]
          and rc == 0 and "AMBER-1" in said and "CORAL-149" in said, (notes, said, err[-300:]))
    exported = subprocess.run([shutil.which("opencode") or "opencode", "session", "export", started[0] if started else "none", "--standalone"],
                              capture_output=True, text=True, encoding="utf-8", timeout=60, cwd=work, env=dict(os.environ, PWD=work)).stdout
    check("5 the session has the gap line, the first and the newest turn",
          "earlier turns left out" in exported and "AMBER-1" in exported and "CORAL-149" in exported and "note 5 " not in exported,
          exported[:300])

    # 6 a stopped turn keeps its ask; a read-only switch carries and writes nothing
    stopped = str(uuid.uuid4())
    evs, rc, err = turn("oc", "Remember the codeword STOPPED-31. Reply with just: noted.", chat_id=stopped)
    proc = subprocess.Popen([REID, "--stream", "cl", "--chat", stopped, "--switch-from", "oc",
                             "Count from 1 to 400, one number per line, nothing else."], cwd=work, env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL, text=True, encoding="utf-8")
    end, seen = time.time() + 120, []
    while time.time() < end:
        line = proc.stdout.readline()
        if not line:
            break
        seen += events(line)
        if of(seen, "text_delta"):  # it's answering: stop it, as the chat's stop does (a kill)
            break
    made.extend(("claude", e["session_id"]) for e in of(seen, "started"))
    subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    proc.wait(30)
    recs = [json.loads(l) for l in open(os.path.join(home, "chats", stopped + ".jsonl"), encoding="utf-8")]
    check("6 the stopped turn's ask is in the transcript, with no reply",
          [(r["role"], r["engine"]) for r in recs] == [("user", "opencode"), ("assistant", "opencode"), ("user", "claude")]
          and recs[-1]["text"].startswith("Count from 1"), (recs, seen[:3]))
    before = sorted(os.listdir(work))
    evs, rc, err = turn("cx", "Create the file z.txt containing hi. Then tell me the codeword I gave you, nothing else.",
                        "--read-only", "--switch-from", "cl", chat_id=stopped)
    notes = [e["text"] for e in of(evs, "note")]
    check("6 a read-only switch carries the chat, stopped turn included", notes == [carried(2, "codex")] and "STOPPED-31" in said_in(evs),
          (notes, said_in(evs), err[-300:]))
    check("6 and writes nothing", sorted(os.listdir(work)) == before and not os.path.exists(os.path.join(work, "z.txt")), os.listdir(work))

    # 7 a folder too long for Reidcc to name Claude's session folder
    deep = root
    while len(deep) < 215:
        deep = os.path.join(deep, "a_rather_long_folder_name")
    os.makedirs(deep)
    check("7 the folder's name is past Claude's 200", len(slug(deep)) > 200, len(deep))
    longc = str(uuid.uuid4())
    evs, rc, err = turn("oc", "Remember the codeword LONGPATH-77. Reply with just: noted.", chat_id=longc, cwd=deep)
    evs, rc, err = turn("cl", "What codeword did I give you? Answer with it only.", "--switch-from", "oc", chat_id=longc, cwd=deep)
    notes = [e["text"] for e in of(evs, "note")]
    check("7 no Claude folder yet: passed as text, and the turn runs",
          len(notes) == 1 and notes[0].startswith("context passed as text: claude didn't take the session") and rc == 0
          and "LONGPATH-77" in said_in(evs), (notes, said_in(evs), err[-300:]))
    evs, rc, err = turn("oc", "Say just: ok.", "--switch-from", "cl", chat_id=longc, cwd=deep)
    evs, rc, err = turn("cl", "What codeword did I give you? Answer with it only.", "--switch-from", "oc", chat_id=longc, cwd=deep)
    notes = [e["text"] for e in of(evs, "note")]
    check("7 once Claude made its folder, the switch carries natively", notes == [carried(3, "claude")] and rc == 0
          and "LONGPATH-77" in said_in(evs), (notes, said_in(evs), err[-300:]))

    # 8 a busy folder refuses a writing switch before anything is carried
    with open(folder_lock(work), "a"):  # held open: reid's exclusive open of the lock fails, as with a window
        evs, rc, err = turn("cl", "Say hi.", "--switch-from", "cx")
    refused = [e for e in of(evs, "error") if e.get("kind") == "refused"]
    check("8 refused: the folder is busy", refused and "open in this folder" in refused[0]["message"], evs)
    check("8 nothing was carried", not of(evs, "note") and not of(evs, "started"), evs)

    # 9 an engine that won't resume the carried session (the debug build's test hook resumes an id that
    # doesn't exist, after carrying the real session)
    debug = os.path.join(os.path.dirname(os.path.dirname(HERE)), "rs", "target", "debug", "reid.exe")
    if not os.path.exists(debug):
        print("skip  9: no debug build (cargo build -p reid)")
    else:
        dead = str(uuid.uuid4())
        evs, rc, err = turn("oc", "Remember the codeword DEADEND-12. Reply with just: noted.", chat_id=dead)
        for n, (src, dst) in enumerate([("oc", "cl"), ("cl", "cx")], 1):
            name = f"9 {ENGINE[dst]}"
            evs, rc, err = turn(dst, "What codeword did I give you? Answer with it only.", "--switch-from", src, chat_id=dead,
                                reid=debug, more_env={"REIDCC_TEST_DEAD_RESUME": "1"})
            notes = [e["text"] for e in of(evs, "note")]
            check(f"{name}: carried, then passed as text when it wouldn't resume",
                  len(notes) == 2 and notes[0] == carried(2 * n - 1, ENGINE[dst])  # each step adds its turn and a follow-up
                  and notes[1].startswith(f"context passed as text: {ENGINE[dst]} didn't resume the session ("), (notes, err[-300:]))
            started = [e["session_id"] for e in of(evs, "started")]
            errors = of(evs, "error")
            check(f"{name}: one started, the new session's; no error shown", len(started) == 1 and not errors, (started, errors))
            check(f"{name}: the retry knows the conversation", "DEADEND-12" in said_in(evs) and rc == 0, (said_in(evs), err[-300:]))
            if started:
                evs, rc, err = turn(dst, "Say the codeword again, nothing else.", "--resume", started[0], chat_id=dead)
                check(f"{name}: the next turn resumes the new session", [e["session_id"] for e in of(evs, "started")] in ([started[0]], [])
                      and not of(evs, "note") and "DEADEND-12" in said_in(evs) and rc == 0, (evs[:2], said_in(evs), err[-300:]))
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
    # Codex sessions this run carried but never used (part 9's dead resumes): their cwd is in the temp folder
    for d in codex_dirs:
        for f in glob.glob(os.path.join(d, "sessions", "*", "*", "*", "rollout-*.jsonl")):
            try:
                if os.path.getmtime(f) > t_start and json.loads(open(f, encoding="utf-8").readline())["payload"]["cwd"].startswith(root):
                    os.remove(f)
            except (OSError, ValueError, KeyError):
                pass
    # every Claude session folder this run's temp folders made (the stopped and fallback turns' too)
    for d in glob.glob(os.path.join(claude_dir, "projects", slug(root)[:200] + "*")):
        shutil.rmtree(d, ignore_errors=True)
    shutil.rmtree(root, ignore_errors=True)

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
