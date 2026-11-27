"""OpenCode as the third engine (vision\\Spec\\SPEC-0.2.6.md Part 3): reid --stream and the launch on a temp
folder, against the real OpenCode with the user's own setup (its default model).

  1  a writing turn streams (started with a ses_ id Reidcc picked, a tool line, text, tokens) and edits a file
  2  --resume continues that session: it remembers the file; OpenCode's own list names the session after its
     first ask (a standalone run makes no title), and the resume doesn't rename it
  3  read-only: told to write and to run a shell command, nothing changes
  4  read-only refuses a profile whose args pick another agent or --auto
  5  effort is the model's variant: a real one runs, a made-up one comes back as OpenCode's error
  6  a persona reaches the turn, added or replacing; memory goes in the same prompt file
  7  --dry shows --standalone and the config layer; ~/.config/opencode/opencode.json is byte-identical

Reidcc runs on a temp REIDCC_HOME; the OpenCode sessions it makes are deleted afterwards.

    python rs\\tests\\opencode_flow.py          (REIDCC_BIN=rs\\target\\debug for a debug build)
"""
import os, sys, json, shutil, tempfile, subprocess, hashlib

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.environ.get("REIDCC_BIN") or os.path.join(os.path.dirname(os.path.dirname(HERE)), "rs", "target", "release")
REID = os.path.join(BIN, "reid.exe")
USER_CONFIG = os.path.expanduser("~/.config/opencode/opencode.json")
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


def digest(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else None


root = tempfile.mkdtemp(prefix="reidoc_")
work, home = os.path.join(root, "work"), os.path.join(root, "home")
os.makedirs(work)
os.makedirs(os.path.join(home, "personas"))
with open(os.path.join(home, "personas", "pine.md"), "w", encoding="utf-8") as f:
    f.write("End every reply with the word PINEAPPLE on its own line.\n")
profiles = {
    "oc": {"engine": "opencode"},
    "oc-agent": {"engine": "opencode", "args": ["--agent", "build"]},
    "oc-auto": {"engine": "opencode", "args": ["--auto"]},
    "oc-pine": {"engine": "opencode", "persona": "personas/pine.md", "memory": True},
    "oc-pine-r": {"engine": "opencode", "persona": "personas/pine.md", "mode": "replace"},
    "oc-bogus": {"engine": "opencode", "effort": "made-up-effort"},
}
with open(os.path.join(home, "reid.json"), "w", encoding="utf-8") as f:
    json.dump({"default": "oc", "profiles": profiles}, f)
with open(os.path.join(home, "reidcc_memory.md"), "w", encoding="utf-8") as f:
    f.write("# Long-term memory\n\n## Pinned facts\n- The test codeword is MARMALADE.\n\n## Journal\n")
env = dict(os.environ, REIDCC_HOME=home)
sids = set()
before = digest(USER_CONFIG)


def stream(args, timeout=300):
    p = subprocess.run([REID, "--stream", *args], cwd=work, env=env, capture_output=True, text=True,
                       encoding="utf-8", timeout=timeout, stdin=subprocess.DEVNULL)
    evs = events(p.stdout)
    sids.update(e["session_id"] for e in of(evs, "started"))
    return evs, p.returncode, p.stderr


try:
    # 1 a writing turn
    evs, rc, err = stream(["oc", "Create the file hello.txt containing exactly: hi from opencode. Then say done."])
    started = of(evs, "started")
    sid = started[0]["session_id"] if started else ""
    check("1 started with a ses_ id", sid.startswith("ses_"), evs[:3])
    check("1 a tool line", of(evs, "tool_call"), [e for e in evs if e["type"] != "text_delta"])
    check("1 the file was written", os.path.exists(os.path.join(work, "hello.txt")), os.listdir(work))
    usage = of(evs, "usage")
    check("1 tokens counted", usage and (usage[-1].get("tokens") or {}).get("in", 0) > 0, usage)
    check("1 done, exit 0", of(evs, "done") and of(evs, "done")[-1]["exit_code"] == 0 and rc == 0, (rc, err[-500:]))

    # 2 resume
    evs, rc, err = stream(["oc", "--resume", sid, "What is the name of the file you just created? Answer with the name only."])
    check("2 the same session", [e["session_id"] for e in of(evs, "started")] in ([sid], []) and rc == 0, (evs[:2], err[-300:]))
    check("2 it remembers", "hello.txt" in text_of(evs), text_of(evs))
    listed = subprocess.run([shutil.which("opencode") or "opencode", "session", "list"], cwd=work, capture_output=True,
                            text=True, encoding="utf-8", timeout=60).stdout
    row = next((l for l in listed.splitlines() if l.startswith(sid)), "")
    check("2 OpenCode's list names it after the first ask", "\tCreate the file hello.txt containing exactly: hi from openco…\t" in row, listed[-600:])

    # 3 read-only
    evs, rc, err = stream(["oc", "--read-only", "Do two things with your tools: create the file b.txt containing hi, and run the shell command: echo hi > c.txt"])
    check("3 read-only turn ran", rc == 0, err[-300:])
    check("3 nothing written", sorted(os.listdir(work)) == ["hello.txt"], os.listdir(work))

    # 4 read-only refuses a profile that brings its own guards
    for name in ["oc-agent", "oc-auto"]:
        evs, rc, err = stream([name, "--read-only", "hi"])
        refused = [e for e in of(evs, "error") if e.get("kind") == "refused"]
        check(f"4 read-only refuses {name}", refused and "Read-only" in refused[0]["message"], evs)

    # 5 effort
    evs, rc, err = stream(["oc-bogus", "Say just: ok"])
    errors = of(evs, "error")
    check("5 a made-up effort is OpenCode's error", errors and "made-up-effort" in json.dumps(errors), (evs, err[-300:]))

    # 6 persona and memory
    evs, rc, err = stream(["oc-pine", "What is the test codeword? Answer in one line."])
    said = text_of(evs)
    check("6 the persona reaches the turn", "PINEAPPLE" in said, said)
    check("6 memory reaches the turn", "MARMALADE" in said, said)
    evs, rc, err = stream(["oc-pine-r", "Say hello in one line."])
    check("6 a replace-mode persona reaches the turn", "PINEAPPLE" in text_of(evs), text_of(evs))

    # 7 --dry and the user's own config
    p = subprocess.run([REID, "--dry", "oc-pine"], cwd=work, env=env, capture_output=True, text=True, encoding="utf-8")
    check("7 --dry shows --standalone", "--standalone" in p.stdout, p.stdout + p.stderr)
    check("7 --dry shows the config layer", "config layer:" in p.stdout and "instructions" in p.stdout, p.stdout)
    check("7 opencode.json untouched", digest(USER_CONFIG) == before)
finally:
    exe = shutil.which("opencode")
    for sid in sids:
        if exe and sid.startswith("ses_"):
            subprocess.run([exe, "session", "delete", sid, "--standalone"], capture_output=True, timeout=60)
    shutil.rmtree(root, ignore_errors=True)

print(f"{sum(results)}/{len(results)} passed")
sys.exit(0 if all(results) else 1)
