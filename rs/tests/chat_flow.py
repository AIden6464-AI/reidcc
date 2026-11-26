"""Milestone 2 acceptance (vision\\Spec\\SPEC-unified-interface.md Part 6): the chat window on a disposable repo.

  1  open chat (beside resume) opens a chat window on the launcher's folder and profile
  2  a Claude write turn streams, edits the repo, and shows what it changed (from git); a second
     turn is stopped mid-stream and its engine goes down with it
  3  switch -> codex, read-only: the .reid/handoff.md divider, no context shown (Codex reports none), nothing written
     2b tune (Milestone 2C): this chat's effort reaches claude (--effort low); reid.json stays as it is
  4  open terminal resumes the Claude session (--resume <id>) in a session window; the composer then
     refuses: Codex writing ("A Reidcc window is open in this folder.", send read-only runs it read-only)
     and Claude ("in terminal", cleared once the terminal lets go)

Real Claude (haiku) and Codex: needs both signed in (Codex in ~/.codex). Reidcc runs on a temp home;
the Claude sessions and Codex threads it makes are deleted afterwards. Kills only processes it started.

    python rs\\tests\\chat_flow.py
"""
import os, sys, json, glob, time, shutil, subprocess, urllib.request
import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guihome
import session_flow as sf

CODEX_HOME = os.environ.get("CODEX_HOME") or os.path.expanduser("~/.codex")
CLAUDE_PROJECTS = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects")
CL, CX = "m2cl", "m2cx"
results = []


def check(name, ok, info=""):
    results.append(bool(ok))
    print("%s  %s%s" % ("ok  " if ok else "FAIL", name, ("" if ok or info == "" else "  " + str(info)[:600])))


class Chat(sf.Page):
    def __init__(self, target):
        import websocket
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        self.n = 0
        end = time.time() + 15
        while not self.js("!!(window.__chat && __chat.state().cur)"):
            if time.time() > end:
                raise RuntimeError("chat page never loaded")
            time.sleep(0.1)

    def st(self):
        return self.js("__chat.state()")

    def turn(self, prompt, timeout=240):
        """Send and wait for the turn to end; returns the last reply's text, tools and meta."""
        self.js("__chat.type(%s)" % json.dumps(prompt))
        self.js("__chat.click('#go')")
        self.wait_idle(timeout)
        return self.last()

    def wait_idle(self, timeout=240):
        time.sleep(0.5)
        end = time.time() + timeout
        while self.st()["running"] and time.time() < end:
            time.sleep(0.3)

    def last(self):
        return self.js("""(() => { const r = [...document.querySelectorAll('.reply')].pop();
            if (!r) return {};
            return { text: [...r.querySelectorAll('.text')].map(e => e.textContent).join(''),
                     tools: [...r.querySelectorAll('.tool')].map(e => e.textContent),
                     fail: [...r.querySelectorAll('.fail')].map(e => e.textContent).join(' '),
                     meta: (r.querySelector('.meta') || {}).textContent || '',
                     changed: [...r.querySelectorAll('.changed .file > span:first-child')].map(e => e.textContent) }; })()""")


def chat_target(timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        pages = [p for p in json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % sf.PORT, timeout=2))
                 if p.get("type") == "page" and "chat.html?id=" in p.get("url", "")]
        if pages:
            return pages[0]
        time.sleep(0.2)
    raise RuntimeError("no chat page")


def ours(bin_):
    return [p for p in sf.ours(bin_) if p.is_running()]


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
    cfg.pop("open_in", None)
    cfg["profiles"][CL] = {"model": "haiku"}
    cfg["profiles"][CX] = {"engine": "codex"}
    json.dump(cfg, open(cfgp, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
    bin_ = os.path.join(home, "bin")
    os.makedirs(bin_)
    for exe in ("Reidcc.exe", "reid.exe"):
        shutil.copy(os.path.join(guihome.RELEASE, exe), bin_)
    t, c, sids = None, None, {}
    try:
        t = guihome.Tauri(root, port=sf.PORT, exe=os.path.join(bin_, "Reidcc.exe"), extra_env={"CODEX_HOME": CODEX_HOME})
        time.sleep(1.0)
        # ---- 1: open chat ------------------------------------------------------------------------
        row = t.js("""(() => { const top = b => Math.round(b.getBoundingClientRect().top), all = [...document.querySelectorAll('#main button')];
            const chat = all.find(b => b.textContent === 'open chat');
            return all.filter(b => b.offsetParent && top(b) === top(chat))
                .sort((a, b) => a.getBoundingClientRect().left - b.getBoundingClientRect().left).map(b => b.textContent); })()""")
        check("open chat sits beside resume, before open gate", row[-3:] == ["open chat", "resume", "open gate"], row)
        names = t.js("__reid.state().names")
        t.js("__reid.selectRow(%d)" % names.index(CL))
        time.sleep(0.4)
        t.js("__reid.button('open chat')")
        c = Chat(chat_target())
        st = c.st()
        bar = c.js("document.getElementById('where').textContent")
        check("the chat window is on the launcher's folder and profile", st["cur"] == CL and "work" in bar and "claude" in bar, bar)
        where = c.js("[document.querySelector('#where b').textContent, document.getElementById('where').title]")
        check("the bar shows the folder's name, its full path on hover", where[0] == "work" and where[1].endswith("work") and len(where[1]) > 4, where)
        check("the composer says what a Claude turn may do: edits · no shell", c.js("document.getElementById('cap').textContent") == "edits · no shell")
        check("its one bone button is send", st["primary"] == "send" and c.js("document.querySelectorAll('.btn.primary').length") == 1)
        md = lambda text: c.js("__chat.md(%s)" % json.dumps(text))
        out = md("Option<T> and `Vec<u8>` <script>x</script>")
        check("markdown: raw HTML is escaped first (Option<T> stays text)",
              "Option&lt;T&gt;" in out and "<code>Vec&lt;u8&gt;</code>" in out and "<script" not in out, out)
        out = md("Here:\n```rust\nfn x() -> Option<u8> {")
        check("markdown: a fence still streaming is already a code block, its ``` hidden",
              '<pre class="code open">fn x() -&gt; Option&lt;u8&gt; {</pre>' in out and "```" not in out, out)
        out = md("# Title\n**ok** see [calc.py](C:/w/calc.py:9)\n```\na\n```\nend")
        check("markdown: heading, bold, link text (target as tooltip), a closed fence",
              out.startswith("<b>Title</b>") and "<b>ok</b>" in out and '<span class="mdlink" title="C:/w/calc.py:9">calc.py</span>' in out
              and '<pre class="code">a</pre>end' in out, out)
        out = md("[The `--version` check](C:/w/reid.py:2173) and `arr[0](x)`")
        check("markdown: a link's text can hold code; code never becomes a link",
              out == '<span class="mdlink" title="C:/w/reid.py:2173">The <code>--version</code> check</span> and <code>arr[0](x)</code>', out)

        # ---- 2: Claude write turn, then stop -------------------------------------------------------
        r = c.turn("Create a file named hello.txt containing exactly the text: hi\nThen reply with just DONE.")
        sids = c.st()["sids"]
        on_disk = open(os.path.join(work, "hello.txt"), encoding="utf-8").read().strip() if os.path.exists(os.path.join(work, "hello.txt")) else None
        check("the Claude turn streamed and wrote hello.txt", on_disk == "hi" and "DONE" in r.get("text", "") and bool(sids.get(CL)), r)
        check("its tool calls show as lowercase lines", any(x.startswith("write") for x in r.get("tools", [])), r.get("tools"))
        check("tool lines show paths relative to the folder", r.get("tools") and not any(
            w in x.lower() for x in r["tools"] for w in (work.lower(), work.lower().replace("\\", "/"))), r.get("tools"))
        zero = c.js("[...document.querySelectorAll('.changed .head .zero')].map(e => e.textContent)")
        check("a zero count is muted, not oxide", zero == ["−0"], zero)
        check("changed (from git) lists hello.txt", r.get("changed") == ["hello.txt"], r.get("changed"))
        check("the meta line: context % and edits", "context " in r["meta"] and "%" in r["meta"] and r["meta"].endswith("edits"), r["meta"])

        c.js("__chat.type(%s)" % json.dumps("Count from 1 to 300, one number per line, nothing else."))
        c.js("__chat.click('#go')")
        end = time.time() + 120
        while time.time() < end and len(c.last().get("text", "")) < 20:
            time.sleep(0.2)
        running = c.st()
        check("while it streams the button is stop and the meter is live",
              running["running"] and running["primary"] == "stop" and c.js("!!document.querySelector('#meters .live')"), running)
        c.js("__chat.click('#go')")
        c.wait_idle(30)
        r = c.last()
        time.sleep(1.0)
        left = [p.name() for p in ours(bin_)]
        check("stop ends the turn (meta: stopped) and takes its engine down", r["meta"] == "stopped" and not left, (r["meta"], left))

        # ---- 2b: tune: this chat's effort reaches the engine, reid.json stays as it is ----------------
        c.js("document.querySelector('#tune').click()")
        end = time.time() + 20
        while time.time() < end and not c.js("document.querySelectorAll('#teffort option').length"):
            time.sleep(0.2)
        c.js("(() => { const s = document.querySelector('#teffort'); s.value = 'low'; s.dispatchEvent(new Event('change')); })()")
        label = c.js("document.querySelector('#tune').textContent")
        check("the tune button says what this chat changed", "low" in label, label)
        c.js("__chat.type('Reply with just OK.')")
        c.js("__chat.click('#go')")
        end, argv = time.time() + 60, []
        while time.time() < end and not any("--effort low" in x for x in argv):
            argv = [" ".join(p.cmdline()) for p in ours(bin_) if "--with" in p.cmdline() or "--effort" in p.cmdline()]
            time.sleep(0.1)
        c.wait_idle()
        check("the tuned turn runs reid --stream --with and claude --effort low",
              any('"effort":"low"' in x for x in argv) and any("--effort low" in x for x in argv), argv)
        saved = json.load(open(cfgp, encoding="utf-8"))["profiles"][CL]
        check("reid.json keeps the profile as it was", saved == {"model": "haiku"}, saved)
        c.js("document.querySelector('#tune').click()")

        # ---- 3: switch -> codex, read-only -----------------------------------------------------------
        files = lambda: sorted(x for x in os.listdir(work) if x != ".reid")
        before = files()
        c.js("__chat.pick('%s')" % CX)
        check("picking codex turns send into switch → codex", c.st()["primary"] == "switch → codex", c.st()["primary"])
        c.js("__chat.readOnly(true)")
        cap = c.js("document.getElementById('cap').textContent")
        check("a read-only Codex turn: read-only · shell", cap == "read-only · shell", cap)
        r = c.turn("Review what changed in this folder. Reply with one short sentence.")
        div = c.js("[...document.querySelectorAll('.switch')].map(d => d.textContent)")
        check("the switch divider names .reid/handoff.md", len(div) == 1 and "claude → codex" in div[0] and ".reid/handoff.md" in div[0], div)
        check(".reid/handoff.md was written", os.path.exists(os.path.join(work, ".reid", "handoff.md")))
        check("codex answered read-only, its unreported context left out of the meta line",
              bool(r.get("text")) and "context" not in r["meta"] and r["meta"].endswith("read-only") and not r.get("changed"), r)
        side = c.js("[document.querySelector('#meters').textContent, document.querySelector('#context').textContent]")
        check("the bar and the sidebar leave it out too: no 'unknown', no —",
              side[0] == "ready" and not any(w in side[1] for w in ("context", "unknown", "—")), side)
        fold = c.js("[...[...document.querySelectorAll('.reply')].pop().querySelectorAll('.thead')].map(e => e.textContent)")
        if len(r.get("tools", [])) >= 3:
            check("%d tool lines fold into one line" % len(r["tools"]),
                  len(fold) == 1 and fold[0] in ("ran %d commands ›" % len(r["tools"]), "%d tool calls ›" % len(r["tools"])), fold)
            opened = c.js("(() => { const r = [...document.querySelectorAll('.reply')].pop(); r.querySelector('.thead').click();"
                          " return [r.querySelector('.thead').textContent, r.querySelector('.tlist').offsetHeight]; })()")
            check("a click opens the fold", opened[0].endswith("⌄") and opened[1] > 0, opened)
        else:
            check("fewer than 3 tool lines stay unfolded", fold == [], (fold, r.get("tools")))
        check("codex shell lines show the command, not the PowerShell wrapper",
              not any("pwsh" in x.lower() and "-command" in x.lower() for x in r.get("tools", [])), r.get("tools"))
        check("the read-only turn wrote nothing", files() == before and open(os.path.join(work, "hello.txt"), encoding="utf-8").read().strip() == "hi", files())
        sids = c.st()["sids"]
        check("the conversation is with codex now; the button is send again", c.st()["cur"] == CX and c.st()["primary"] == "send"
              and bool(sids.get(CX)), c.st())

        # ---- 4: open terminal, then the composer's locks ---------------------------------------------
        c.js("__chat.pick('%s')" % CL)
        c.js("__chat.click('#term')")
        end, cmd = time.time() + 20, []
        while time.time() < end and not cmd:
            cmd = [" ".join(p.cmdline()) for p in ours(bin_) if p.name().lower() == "reid.exe" and "--id" in p.cmdline()]
            time.sleep(0.3)
        check("open terminal resumes the Claude session (--resume %s --id <id>)" % CL,
              any(("--resume %s --id %s" % (CL, sids[CL])) in x for x in cmd), cmd)
        time.sleep(3)  # reid takes the session's lock before Claude starts

        c.js("__chat.pick('%s')" % CX)
        c.js("__chat.readOnly(false)")
        c.js("__chat.type('Add a line to README.md.')")
        c.js("__chat.click('#go')")
        c.wait_idle(60)
        note = c.st()["note"]
        check("codex writing is refused: a Reidcc window is open in this folder (no PID)",
              "A Reidcc window is open in this folder." in note and "focus window" in note and "send read-only" in note
              and "pid" not in note.lower(), note)
        check("the refused ask stays in the field", c.js("document.getElementById('field').value") == "Add a line to README.md.")
        c.js("[...document.querySelectorAll('#note .act')].find(b => b.textContent === 'send read-only').click()")
        c.wait_idle(240)
        r = c.last()
        check("send read-only runs it read-only", "read-only" in r.get("meta", "") and c.st()["readOnly"] and not c.st()["note"], r)
        check("README.md is untouched", open(os.path.join(work, "README.md"), encoding="utf-8").read() == "base\n")

        hp = os.path.join(work, ".reid", "handoff.md")
        h0 = open(hp, encoding="utf-8").read()
        c.js("__chat.pick('%s')" % CL)
        c.js("__chat.readOnly(false)")
        c.js("__chat.type('Say hi.')")
        c.js("__chat.click('#go')")
        c.wait_idle(60)
        st = c.st()
        check("claude is refused while its session is in the terminal",
              st["note"].startswith("in terminal") and "focus terminal" in st["note"] and st["cur"] == CX, st)
        check("a refused switch leaves no divider", c.js("document.querySelectorAll('.switch').length") == 1)
        check("and writes no handoff; the sidebar keeps the real one", open(hp, encoding="utf-8").read() == h0
              and c.js("document.getElementById('handoff').textContent").startswith("%s → %s" % (CL, CX)),
              c.js("document.getElementById('handoff').textContent"))
        for p in ours(bin_):
            if p.name().lower() == "reid.exe" and "--id" in p.cmdline():
                for k in p.children(recursive=True) + [p]:
                    try:
                        k.kill()
                    except psutil.Error:
                        pass
        end = time.time() + 10
        while time.time() < end and c.st()["note"]:
            time.sleep(0.3)
        check("once the terminal lets go, the note clears", not c.st()["note"], c.st()["note"])
    finally:
        sids.update((c.st()["sids"] if c else {}) or {})
        if t:
            t.close()
        for p in ours(bin_):
            try:
                p.kill()
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
        for sid in sids.values():
            for f in glob.glob(os.path.join(CLAUDE_PROJECTS, "*", sid + ".jsonl")):
                os.remove(f)
                gone += 1
                shutil.rmtree(f[:-6], ignore_errors=True)
                try:
                    os.rmdir(os.path.dirname(f))
                except OSError:
                    pass
        print("      removed %d test session file(s)" % gone)
        guihome.remove_home(root)
        now = {f: os.path.getmtime(os.path.join(guihome.REIDCC, f)) for f in real}
        check("the real reid.json / reid_state.json untouched", now == real)
    print("\n%d/%d passed" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
