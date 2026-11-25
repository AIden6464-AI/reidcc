"""Session windows (vision\\SPEC-vision-v1.md §2) in the Rust GUI: open gate opens a Reidcc session
window running the engine in an embedded terminal, shown out of the gate's dark.

Runs against a temp Reidcc folder (guihome), with Reidcc.exe and reid.exe copied into it, so the
real reid.json / reid_state.json are never touched. Three Claude profiles:
  win_live  plain Claude: the window, the bar, the shimmer, resizing, closing with x
  win_ok    claude --version: ends by itself with 0 -> window closes, launcher says so
  win_fail  claude --no-such-flag: fails -> the window stays with the code, any key closes
Nothing is typed into Claude. Kills only processes it started (reid.exe from the temp bin\\ and
their children). Screenshots go to rs\\tests\\session_shots\\.

    python rs\\tests\\session_flow.py
"""
import os, sys, json, time, shutil, ctypes, urllib.request
import psutil, websocket
from ctypes import wintypes as W

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guihome

u32 = ctypes.windll.user32
dwm = ctypes.windll.dwmapi
u32.GetForegroundWindow.restype = W.HWND
SHOTS = os.path.join(HERE, "session_shots")
PORT = 9333
results = []


def check(name, ok, info=""):
    results.append(ok)
    print("%s  %s%s" % ("ok  " if ok else "FAIL", name, ("  " + str(info)) if info else ""))


class Page:
    """One WebView2 page over the DevTools protocol."""
    def __init__(self, target):
        self.ws = websocket.create_connection(target["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        self.n = 0
        end = time.time() + 15
        while not self.js("!!(window.__term && document.getElementById('meters'))"):
            if time.time() > end:
                raise RuntimeError("session page never loaded")
            time.sleep(0.1)

    def cdp(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = json.loads(self.ws.recv())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m["result"]

    def js(self, expr):
        r = self.cdp("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")


def session_target(seen, timeout=10):
    end = time.time() + timeout
    while time.time() < end:
        pages = [p for p in json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2))
                 if p.get("type") == "page" and "session.html?id=" in p.get("url", "")]
        new = [p for p in pages if int(p["url"].split("id=")[1]) > max(seen, default=0)]
        if new:
            p = max(new, key=lambda p: int(p["url"].split("id=")[1]))
            seen.add(int(p["url"].split("id=")[1]))
            return p
        time.sleep(0.1)
    raise RuntimeError("no session page")


def windows_of(pid):
    """{hwnd: (title, visible)} for every top-level window of pid."""
    out = {}
    ENUM = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    def cb(h, _):
        p = W.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        if p.value == pid:
            b = ctypes.create_unicode_buffer(128)
            u32.GetWindowTextW(h, b, 128)
            out[h] = (b.value, bool(u32.IsWindowVisible(h)))
        return True
    u32.EnumWindows(ENUM(cb), 0)
    return out


def find(pid, title):
    return next((h for h, (t, _) in windows_of(pid).items() if t == title), None)


def frame(h):
    r = W.RECT()
    dwm.DwmGetWindowAttribute(W.HWND(h), 9, ctypes.byref(r), ctypes.sizeof(r))
    return (r.left, r.top, r.right, r.bottom)


def ours(bin_):
    """reid.exe processes started from the temp bin\\, with everything under them."""
    out = []
    for p in psutil.process_iter(["name", "exe"]):
        try:
            if p.info["name"] == "reid.exe" and os.path.dirname(p.info["exe"] or "") == bin_:
                out += [p] + p.children(recursive=True)
        except psutil.Error:
            pass
    return out


def screen(page):
    return page.js("""(() => { const b = __term.buffer.active, out = [];
        for (let i = 0; i < b.length; i++) out.push(b.getLine(i).translateToString(true));
        return out.join('\\n'); })()""")


def press(t, name):
    names = t.js("__reid.state().names")
    t.js("__reid.selectRow(%d)" % names.index(name))
    time.sleep(0.4)
    t0 = time.time()
    t.js("__reid.button('open gate')")
    return t0


def live(t, bin_, seen):
    title = "claude · win_live"
    t0 = press(t, "win_live")
    h = None
    while time.time() - t0 < 3 and not h:
        h = find(t.proc.pid, title)
        time.sleep(0.02)
    check("session window made at the press", bool(h), "%.2fs" % (time.time() - t0))
    if not h:
        return
    check("hidden while the gate plays", not windows_of(t.proc.pid)[h][1])
    shown = None
    while time.time() - t0 < 8:
        if windows_of(t.proc.pid).get(h, ("", False))[1]:
            shown = time.time() - t0
            break
        time.sleep(0.02)
    check("shown out of the dark at the hand-off", shown is not None, "%.2fs after the press" % (shown or 0))
    time.sleep(0.5)
    check("it has the keyboard", u32.GetForegroundWindow() == h)
    lf, sf = frame(t.hwnd), frame(h)
    check("over the launcher at its size", all(abs(a - b) <= 2 for a, b in zip(lf, sf)), "launcher %s, session %s" % (lf, sf))
    page = Page(session_target(seen))
    text, end = "", time.time() + 25
    while time.time() < end:
        text = screen(page)
        if len(text.strip()) > 40 and "Claude" in text:
            break
        time.sleep(0.5)
    check("Claude draws in the terminal", "Claude" in text, "%d chars" % len(text.strip()))
    print("      " + "\n      ".join(l for l in text.splitlines() if l.strip())[:1600])
    where, meters = page.js("document.getElementById('where').textContent"), page.js("document.getElementById('meters').textContent")
    check("bar: where you are and who's loaded (lowercase tags)", "win_live" in where and where.endswith("· claude") and "PROFILE" not in where, where)
    check("bar: elapsed clock", any(c.isdigit() for c in meters), meters)
    check("bar: live dot while running", meters.lstrip().startswith("●") or "· ●" in meters, meters)
    check("no duplicate REIDCC banner in a session window", "REIDCC ·" not in text, "")
    os.makedirs(SHOTS, exist_ok=True)
    guihome.client_shot(h).save(os.path.join(SHOTS, "live.png"))

    still = page.js("document.body.classList.contains('moving')")
    l, tp, r, b = frame(h)
    moving = []
    for i in range(8):
        u32.SetWindowPos(W.HWND(h), None, l + 10 * (i + 1), tp, 0, 0, 0x0001 | 0x0004 | 0x0010)  # NOSIZE|NOZORDER|NOACTIVATE
        time.sleep(0.04)
        moving.append(page.js("document.body.classList.contains('moving')"))
    shot_moving = guihome.client_shot(h)
    time.sleep(0.4)
    after = page.js("document.body.classList.contains('moving')")
    check("shimmer only while it moves", not still and any(moving) and not after, "still %s, moving %s, after %s" % (still, moving, after))
    shot_moving.save(os.path.join(SHOTS, "moving.png"))

    fits = """(() => { const s = document.querySelector('.xterm-screen').getBoundingClientRect(),
        t = document.getElementById('term'), b = t.getBoundingClientRect(), p = 12;
        return [Math.round(s.bottom), Math.round(b.bottom - p), Math.round(s.right), Math.round(b.right - p)]; })()"""
    sb, hb, sr, hr = page.js(fits)
    check("the whole grid shows (last row and column inside the gutter)", sb <= hb and sr <= hr,
          "grid bottom %d / area %d, right %d / %d" % (sb, hb, sr, hr))
    cols, rows = page.js("__term.cols"), page.js("__term.rows")
    u32.SetWindowPos(W.HWND(h), None, l, tp, (r - l) + 200, (b - tp) - 157, 0x0004 | 0x0010)
    time.sleep(1.0)
    cols2, rows2 = page.js("__term.cols"), page.js("__term.rows")
    check("resizing refits the terminal", cols2 > cols and rows2 < rows, "%dx%d -> %dx%d" % (cols, rows, cols2, rows2))
    sb, hb, sr, hr = page.js(fits)
    check("still the whole grid after resizing", sb <= hb and sr <= hr, "grid bottom %d / area %d, right %d / %d" % (sb, hb, sr, hr))

    procs = ours(bin_)
    check("the session runs reid.exe with Claude under it", any(p.name().lower().startswith(("claude", "node")) for p in procs[1:]) or len(procs) > 1,
          [p.name() for p in procs])
    page.js("document.getElementById('close').click()")
    gone = False
    end = time.time() + 5
    while time.time() < end:
        if not find(t.proc.pid, title) and not any(p.is_running() for p in procs):
            gone = True
            break
        time.sleep(0.1)
    check("x closes the window and ends the session", gone, [p.name() for p in procs if p.is_running()])


def ends_ok(t, seen):
    title = "claude · win_ok"
    t0 = press(t, "win_ok")
    seen_win, closed = False, None
    while time.time() - t0 < 15:
        h = find(t.proc.pid, title)
        if h and windows_of(t.proc.pid).get(h, ("", False))[1]:  # it may close between the two looks
            seen_win = True
        if seen_win and not h:
            closed = time.time() - t0
            break
        time.sleep(0.05)
    check("a clean exit closes the window by itself", closed is not None, "%.1fs after the press" % (closed or 0))
    time.sleep(0.3)
    msg = t.js("__reid.state().msg")
    check("the launcher comes back and says so", msg == "Back from the session.", msg)
    check("the launcher has the keyboard", u32.GetForegroundWindow() == t.hwnd)


def ends_failed(t, seen, home):
    title = "claude · win_fail"
    press(t, "win_fail")
    page = Page(session_target(seen))
    meters, end = "", time.time() + 15
    while time.time() < end:
        meters = page.js("document.getElementById('meters').textContent")
        if "failed" in meters:
            break
        time.sleep(0.2)
    check("a failure stays open with its code", "failed · code" in meters and bool(find(t.proc.pid, title)), meters)
    text = screen(page)
    check("the error is readable", "no-such-flag" in text or "unknown option" in text.lower(), text.strip()[-200:])
    h = find(t.proc.pid, title)
    if h:
        guihome.client_shot(h).save(os.path.join(SHOTS, "failed.png"))
    page.js("__term.focus()")
    page.cdp("Input.dispatchKeyEvent", type="keyDown", key="a", code="KeyA", text="a", windowsVirtualKeyCode=65)
    page.cdp("Input.dispatchKeyEvent", type="keyUp", key="a", code="KeyA", windowsVirtualKeyCode=65)
    end = time.time() + 3
    while time.time() < end and find(t.proc.pid, title):
        time.sleep(0.1)
    check("any key closes it", not find(t.proc.pid, title))
    state = json.load(open(os.path.join(home, "reid_state.json"), encoding="utf-8"))
    check("sessions are remembered in the temp state", (state.get("last") or {}).get("profile") in ("win_ok", "win_fail"),
          (state.get("last") or {}).get("profile"))


def clicks_while_opening(t, bin_, seen):
    """open gate on a Codex profile that looks signed out first re-runs `codex login status` (about a
    second) holding nothing. A click on another row meanwhile must answer at once: it used to wait on the
    launcher's lock, and with the window build behind it the whole app could hang."""
    t.js("__reid.login(null)")  # cached: not signed in
    press(t, "win_codex")
    t0 = time.time()
    r = t.js("""Promise.race([
        window.__TAURI_INTERNALS__.invoke('select', {name: 'win_live', typed: ''}).then(() => 'answered'),
        new Promise((ok) => setTimeout(() => ok('stuck'), 5000))])""")
    answered = time.time() - t0
    msg, end = "", time.time() + 15
    while time.time() < end and "signed in" not in (msg or ""):
        msg = t.js("__reid.state().msg")
        time.sleep(0.05)
    refused = time.time() - t0
    # Before the fix open gate held the lock from start to end, so the click could only answer after it.
    check("a click during open gate's sign-in check answers before it ends", r == "answered" and answered < refused,
          "%s after %.2fs; open gate finished after %.2fs: %s" % (r, answered, refused, msg))


def codex_tui(t, bin_, seen):
    """Codex's full-screen TUI in the window (CODEX_HOME is the temp one: never ~/.codex)."""
    title = "codex · win_codex"
    # The temp CODEX_HOME has no sign-in: tell the launcher it's signed in (test hook) so Codex starts
    # and draws its own full-screen sign-in screen, which is what this checks.
    t.js("__reid.login('Logged in using ChatGPT')")
    press(t, "win_codex")
    try:
        page = Page(session_target(seen))
    except RuntimeError as e:
        check("Codex opens in a session window", False, "%s; launcher: %s" % (e, t.js("__reid.state().msg")))
        return
    text, end = "", time.time() + 30
    while time.time() < end:
        text = screen(page)
        if len([l for l in text.splitlines() if l.strip()]) > 4:
            time.sleep(2)
            text = screen(page)
            break
        time.sleep(0.5)
    if "isn't signed in" in text:
        # reid.exe checks the sign-in itself; a real one would mean ~/.codex, which tests never use
        print("skip  Codex's TUI: the temp CODEX_HOME isn't signed in, so reid.exe stops before Codex starts")
        meters = page.js("document.getElementById('meters').textContent")
        check("Codex's refusal stays on screen, readable", "failed" in meters, "%s | %s" % (text.strip().splitlines()[-1], meters))
    else:
        check("Codex's TUI draws", len([l for l in text.splitlines() if l.strip()]) > 4, "%d lines" % len(text.splitlines()))
        print("      " + "\n      ".join(l for l in text.splitlines() if l.strip())[:1600])
    h = find(t.proc.pid, title)
    if h:
        guihome.client_shot(h).save(os.path.join(SHOTS, "codex.png"))
        procs = ours(bin_)
        page.js("document.getElementById('close').click()")
        end = time.time() + 5
        while time.time() < end and (find(t.proc.pid, title) or any(p.is_running() for p in procs)):
            time.sleep(0.1)
        check("x ends the Codex session", not find(t.proc.pid, title) and not any(p.is_running() for p in procs))


def main():
    real = {f: os.path.getmtime(os.path.join(guihome.REIDCC, f)) for f in ("reid.json", "reid_state.json")}
    root, home = guihome.make_home()
    cfgp = os.path.join(home, "reid.json")
    cfg = json.load(open(cfgp, encoding="utf-8"))
    cfg.pop("open_in", None)  # the default: session windows
    cfg["profiles"]["win_live"] = {"model": "sonnet"}
    cfg["profiles"]["win_ok"] = {"model": "opus", "args": ["--version"]}
    cfg["profiles"]["win_fail"] = {"model": "opus", "args": ["--no-such-flag"]}
    cfg["profiles"]["win_codex"] = {"engine": "codex"}
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    bin_ = os.path.join(home, "bin")
    os.makedirs(bin_)
    for exe in ("Reidcc.exe", "reid.exe"):
        shutil.copy(os.path.join(guihome.RELEASE, exe), bin_)
    t, seen = None, set()
    try:
        t = guihome.Tauri(root, port=PORT, exe=os.path.join(bin_, "Reidcc.exe"))
        time.sleep(1.0)
        live(t, bin_, seen)
        time.sleep(4.5)  # let the gate's note clear
        ends_ok(t, seen)
        time.sleep(4.5)
        ends_failed(t, seen, home)
        time.sleep(4.5)
        clicks_while_opening(t, bin_, seen)
        time.sleep(4.5)
        codex_tui(t, bin_, seen)
    finally:
        for p in ours(bin_):
            try:
                p.kill()
            except psutil.Error:
                pass
        if t:
            t.close()
        time.sleep(0.5)
        guihome.remove_home(root)
    after = {f: os.path.getmtime(os.path.join(guihome.REIDCC, f)) for f in ("reid.json", "reid_state.json")}
    check("real reid.json / reid_state.json untouched", real == after)
    print("\n%d/%d passed" % (sum(results), len(results)))
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
