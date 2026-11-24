"""The launcher's sizes (vision\\SPEC-vision-v1.md §1) in the Rust GUI: the window's size is its mode.
Alt+2 eases it to small (the folder, the sessions that run, combos), Alt+1 back to main; dragging it
smaller than main fits folds it to medium (the form), then small. A combo key opens that profile's session
window straight away (no gate at small), at main's size, and the session list shows it.

Same temp Reidcc folder and rules as session_flow.py: the real reid.json / reid_state.json are never
touched, and only processes started from the temp bin\\ are killed. Screenshot: session_shots\\small.png.

    python rs\\tests\\sizes_flow.py
"""
import os, re, sys, json, time, shutil, ctypes, urllib.request
import psutil, websocket
from ctypes import wintypes as W

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guihome
from session_flow import check, results, find, frame, ours, windows_of, Page, session_target, PORT, SHOTS

u32 = ctypes.windll.user32
u32.GetForegroundWindow.restype = W.HWND


def key(t, code, alt=False):
    t.js("window.dispatchEvent(new KeyboardEvent('keydown', {code: %s, key: %s, altKey: %s, bubbles: true, cancelable: true}))"
         % (json.dumps(code), json.dumps(code[-1]), "true" if alt else "false"))


def size_now(t):
    return t.js("[__reid.size(), innerWidth, innerHeight]")


def resize_outer(h, w, hgt):
    r = W.RECT()
    u32.GetWindowRect(W.HWND(h), ctypes.byref(r))
    u32.SetWindowPos(W.HWND(h), None, r.left, r.top, w, hgt, 0x0004 | 0x0010)


def folder_in(t, where):
    return t.js("__reid.folderIn(%s)" % json.dumps(where))


class PodPage(Page):
    """The mini pod's page (ui\\pod.html) over the DevTools protocol."""
    def __init__(self):
        end = time.time() + 10
        while True:
            pages = json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2))
            p = next((p for p in pages if p.get("type") == "page" and "pod.html" in p.get("url", "")), None)
            if p or time.time() > end:
                break
            time.sleep(0.1)
        if not p:
            raise RuntimeError("no pod page")
        self.ws = websocket.create_connection(p["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        self.n = 0


def pod_hwnd(t):
    """The pod: Reidcc's other top-level window with the launcher's title (session windows have their own)."""
    title = windows_of(t.proc.pid).get(t.hwnd, ("", False))[0]
    return next((h for h, (tt, _) in windows_of(t.proc.pid).items() if tt == title and h != t.hwnd), None)


def visible(h):
    return bool(h) and bool(u32.IsWindowVisible(W.HWND(h)))


def mini_pod(t, bin_, seen):
    """vision v1 §1, the mini pod: Alt+3 folds the launcher into the capsule where it was; a slot per
    session, hover names it; Alt+1 unfolds; dragging the launcher small folds it; Alt+F4 on it quits."""
    title = "claude · size_live"
    key(t, "Digit2", alt=True)
    time.sleep(0.6)
    key(t, "Digit1")  # combo 1: size_live
    end, h = time.time() + 5, None
    while time.time() < end and not visible(h):
        h = find(t.proc.pid, title)
        time.sleep(0.05)
    page = Page(session_target(seen)) if h else None
    launcher = frame(t.hwnd)
    key(t, "Digit3", alt=True)
    end, p = time.time() + 5, None
    while time.time() < end and not (visible(p) and not visible(t.hwnd)):
        p = pod_hwnd(t)
        time.sleep(0.05)
    check("Alt+3: the launcher folds into the pod", visible(p) and not visible(t.hwnd))
    if not p:
        return
    time.sleep(1.3)  # the pod has polled the sessions and fitted its width
    sc = u32.GetDpiForWindow(W.HWND(p)) / 96
    pr = frame(p)
    check("the pod: a capsule 64 px tall, at least 320 wide", abs((pr[3] - pr[1]) - 64 * sc) <= 2 and pr[2] - pr[0] >= 320 * sc - 2, pr)
    check("where the launcher was", pr[:2] == launcher[:2], "pod %s, launcher %s" % (pr, launcher))
    pod = PodPage()
    slot = pod.js("document.querySelector('.slot') && document.querySelector('.slot').textContent") or ""
    check("one slot for the session: mark, profile, dot, elapsed", pod.js("__pod.slots()") == 1
          and bool(re.fullmatch(r"CLsize_live●\d\d:\d\d.*", slot)), slot)
    d = pod.js("__pod.details({elapsed_ms: 102000, context: 42, limit: 61, rc: null})")
    check("a Claude slot carries its own usage", d == "01:42 · ctx 42% · lim 61%", d)
    d = pod.js("__pod.details({elapsed_ms: 5000, context: null, limit: null, rc: 2})")
    check("a failed slot shows its code", d == "00:05 · code 2", d)
    room = pod.js("innerWidth - 22 - document.getElementById('dock').getBoundingClientRect().right")
    check("one row: still 64 px tall, the slots fit inside the round ends", abs((frame(p)[3] - frame(p)[1]) - 64 * sc) <= 2
          and room >= 0, "room %s, %s" % (room, frame(p)))
    pod.js("window.__TAURI_INTERNALS__.invoke('pod_fit', {width: 700})")
    time.sleep(0.4)
    f = frame(p)
    check("more slots: it grows sideways, same height", abs((f[2] - f[0]) - 700 * sc) <= 2 and abs((f[3] - f[1]) - 64 * sc) <= 2, f)
    pod.js("window.__TAURI_INTERNALS__.invoke('pod_fit', {width: 99999})")
    time.sleep(0.4)
    f = frame(p)
    info = (ctypes.c_uint32 * 10)(40)
    u32.GetMonitorInfoW(u32.MonitorFromWindow(W.HWND(p), 2), info)
    work = tuple(ctypes.c_int32(v).value for v in info[5:9])
    check("never wider than the screen, never off it", f[0] >= work[0] and f[2] <= work[2], "pod %s, work area %s" % (f, work))
    pod.js("window.__TAURI_INTERNALS__.invoke('pod_fit', {width: 320})")
    u32.SetWindowPos(W.HWND(p), None, pr[0], pr[1], 0, 0, 0x0001 | 0x0004 | 0x0010)
    time.sleep(0.4)
    from PIL import ImageGrab
    u32.SetWindowPos(W.HWND(p), W.HWND(0), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # on top for the shot (HWND_TOP)
    time.sleep(0.3)
    shot = ImageGrab.grab(bbox=pr, all_screens=True)
    shot.save(os.path.join(SHOTS, "pod.png"))
    s1 = (0x0E, 0x0D, 0x0C)
    mid = shot.getpixel((shot.width // 2, shot.height - 4))
    corner = shot.getpixel((1, 1))
    check("the corners show what's behind it, the capsule is surface-1", corner != s1 and max(abs(a - b) for a, b in zip(mid, s1)) <= 3,
          "corner %s, inside %s" % (corner, mid))

    pod.js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'Digit1', key: '1', altKey: true}))")
    end = time.time() + 5
    while time.time() < end and not (visible(t.hwnd) and not visible(p)):
        time.sleep(0.05)
    time.sleep(0.5)
    s = size_now(t)
    check("Alt+1 on the pod: the launcher comes back main, from the pod's corner", visible(t.hwnd) and not visible(p) and s[0] == "main"
          and frame(t.hwnd)[:2] == pr[:2], "%s at %s" % (s, frame(t.hwnd)))

    resize_outer(t.hwnd, 300, 200)
    end = time.time() + 5
    while time.time() < end and not (visible(p) and not visible(t.hwnd)):
        time.sleep(0.05)
    check("dragged smaller than 340x240: it folds into the pod", visible(p) and not visible(t.hwnd))
    pod.js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'Digit2', key: '2', altKey: true}))")
    time.sleep(0.8)
    s = size_now(t)
    check("Alt+2 on the pod: small", visible(t.hwnd) and s[0] == "small" and s[1:] == [380, 400], s)

    if page:
        procs = ours(bin_)
        page.js("document.getElementById('close').click()")
        end = time.time() + 5
        while time.time() < end and (find(t.proc.pid, title) or any(q.is_running() for q in procs)):
            time.sleep(0.1)
    key(t, "Digit3", alt=True)
    time.sleep(1.3)
    check("no sessions: the pod says so", pod.js("__pod.slots()") == 0 and pod.js("__pod.usage()") == "No sessions running.", pod.js("__pod.usage()"))
    u32.PostMessageW(W.HWND(p), 0x0010, 0, 0)  # WM_CLOSE, as Alt+F4 sends
    try:
        t.proc.wait(timeout=5)
        quit_ = True
    except Exception:
        quit_ = False
    check("closing the pod closes Reidcc (nothing hidden left running)", quit_)


def resize_inner(t, w, h):
    """Resize so the page gets w x h CSS px (the frame stays what it is)."""
    sc = u32.GetDpiForWindow(W.HWND(t.hwnd)) / 96
    r = W.RECT()
    u32.GetWindowRect(W.HWND(t.hwnd), ctypes.byref(r))
    iw, ih = t.js("[innerWidth, innerHeight]")
    resize_outer(t.hwnd, r.right - r.left + round((w - iw) * sc), r.bottom - r.top + round((h - ih) * sc))
    time.sleep(0.4)


def wheel(t, sel):
    t.js("document.querySelector(%s).dispatchEvent(new WheelEvent('wheel', {deltaY: 100, bubbles: true, cancelable: true}))" % json.dumps(sel))
    time.sleep(0.4)


def form_checks(t, cfgp, w0, h0):
    """The form (vision\\Spec\\SPEC-form.md Part 5): the old launcher's layout for a narrower window."""
    t.js("window.__slides = []; const a = Element.prototype.animate;"
         "Element.prototype.animate = function (k, o) { __slides.push(this.id); return a.call(this, k, o); }")
    resize_inner(t, 500, 860)
    s = size_now(t)
    check("500 x 860: the form, with the folder in it", s[0] == "medium" and folder_in(t, "medium"), s)
    check("dragging there cuts (no push)", t.js("__slides") == [], t.js("__slides"))
    vis = t.js("['#medium', '#main', '.lb'].map(q => document.querySelector(q).offsetParent !== null)")
    check("the form shows; the wide layout and its list don't", vis == [True, False, False], vis)
    rows = t.js("""[...document.querySelectorAll('.fgrid > :not(.lbl):not(.fbtns)')].map(e => {
        const r = e.getBoundingClientRect(); return [Math.round(r.top), Math.round(r.height)]; })""")
    pitch = {b[0] - a[0] for a, b in zip(rows, rows[1:])}
    check("every row is 26 px tall on a 34 px pitch (%d rows)" % len(rows),
          len(rows) == 17 and {h for _, h in rows} == {26} and pitch == {34}, rows)
    rights = t.js("""[...document.querySelectorAll('.fgrid > .fwide, .fgrid > .fbtns')].map(e =>
        Math.round(e.getBoundingClientRect().right)).concat([Math.round(document.querySelector('.fbar').getBoundingClientRect().right)])""")
    check("every right edge lines up (fields, button columns, the bottom bar)", max(rights) - min(rights) <= 1, rights)
    bar = t.js("[...document.querySelector('.fbar').children].map(b => b.textContent)")
    check("one bottom bar, open gate last", bar == ["open memory", "open reid.json", "resume", "open gate"], bar)
    fonts = t.js("[getComputedStyle(document.querySelector('.fgrid > .lbl')).fontSize, getComputedStyle(document.querySelector('.wordmark')).fontSize]")
    check("labels 14 px, the wordmark 28 px", fonts == ["14px", "28px"], fonts)
    texts = t.js("[...document.querySelectorAll('#medium .fcell .check')].map(c => c.textContent)")
    check("each switch is its own row with its sentence", len(texts) == 4 and texts[0] == "add your memory file to the session", texts)
    check("nothing sticks out sideways", t.js("document.getElementById('medium').scrollWidth <= innerWidth"))
    os.makedirs(SHOTS, exist_ok=True)
    guihome.client_shot(t.hwnd).save(os.path.join(SHOTS, "form.png"))

    st0 = t.js("__reid.state()")
    check("at 500 x 860 everything fits, no scrolling", t.js(
        "(b => b.scrollHeight <= b.clientHeight)(document.querySelector('.fbody'))"),
        t.js("(b => [b.scrollHeight, b.clientHeight])(document.querySelector('.fbody'))"))
    wheel(t, "#medium .fgrid > .combo:nth-child(5)")  # the profile combo: the wheel steps to the next profile
    st = t.js("[__reid.state().sel, __reid.state().title, __reid.state().name]")
    want = st0["sel"] + 1
    check("picking in the profile combo selects that profile", st == [want, st0["names"][want], st0["names"][want]], st)
    mem0 = t.js("__reid.state().vars.memory")
    t.js("document.querySelector('#medium .fcell .check').click()")
    time.sleep(0.3)
    check("a checkbox row is the same switch", t.js("__reid.state().vars.memory") == (not mem0))
    t.js("document.querySelector('#medium .fcell .check').click()")
    time.sleep(0.3)
    check("the prompt combo follows the persona mode, greyed with it",
          t.js("document.querySelectorAll('#medium .fgrid > .combo')[2].classList.contains('disabled') === __reid.state().disabled.mode"))
    t.js("document.querySelector('#medium .fgrid > .check').click()")  # default
    time.sleep(0.4)
    d = json.load(open(cfgp, encoding="utf-8")).get("default")
    check("the default row makes this profile the default", d == st0["names"][want] and t.js(
        "document.querySelector('#medium .fgrid > .check .ind') !== null"), d)

    # the form's opening (vision\Spec\SPEC-hand.md): the emblem, not the gate
    t.js("__reid.hover(true)")
    time.sleep(0.4)
    check("hovering open gate in the form shows the emblem's ghost", t.js("__reid.ghostOf()") == "emblem", t.js("__reid.ghostOf()"))
    t.js("__reid.hover(false)")
    time.sleep(0.3)
    t.js("__reid.selectRow(%d)" % t.js("__reid.state().names").index("size_live"))
    time.sleep(0.3)
    t.js("__reid.button('open gate')")
    end, op = time.time() + 3, None
    while time.time() < end and not op:
        op = t.js("__reid.opening()")
        time.sleep(0.03)
    check("open gate in the form plays the emblem", op == {"name": "emblem", "active": True}, op)
    title, end, h = "claude · size_live", time.time() + 8, None
    while time.time() < end and not (h and u32.IsWindowVisible(W.HWND(h)) and not t.js("__reid.opening().active")):
        h = find(t.proc.pid, title)
        time.sleep(0.05)
    check("then the session window appears and the emblem is done",
          bool(h) and bool(u32.IsWindowVisible(W.HWND(h))) and not t.js("__reid.opening().active"))
    if h:
        u32.PostMessageW(W.HWND(h), 0x10, 0, 0)  # WM_CLOSE: the pod test later opens size_live again
        end = time.time() + 6
        while time.time() < end and find(t.proc.pid, title):
            time.sleep(0.1)
        time.sleep(1.2)  # the session's processes end after its window

    resize_inner(t, 500, 720)
    scroll = t.js("""(() => { const b = document.querySelector('.fbody'), g = [...document.querySelectorAll('button')]
        .find(x => x.textContent === 'open gate').getBoundingClientRect();
        return [b.scrollHeight > b.clientHeight, g.bottom <= innerHeight, __reid.size()]; })()""")
    check("500 x 720: still the form, it scrolls, open gate stays on screen", scroll == [True, True, "medium"], scroll)
    resize_inner(t, 470, 720)
    check("narrower than the old minsize: small", size_now(t)[0] == "small", size_now(t))
    resize_inner(t, 500, 860)
    t.js("__slides = []")
    key(t, "Digit2", alt=True)
    time.sleep(0.6)
    reduced = t.js("matchMedia('(prefers-reduced-motion: reduce)').matches")
    slides = t.js("__slides")
    check("Alt+2 from medium (the form) pushes small in (a cut with reduced motion)",
          size_now(t)[0] == "small" and (slides == [] if reduced else slides == ["medium", "small"]), (reduced, slides))


def main():
    real = {f: os.path.getmtime(os.path.join(guihome.REIDCC, f)) for f in ("reid.json", "reid_state.json")}
    root, home = guihome.make_home()
    cfgp = os.path.join(home, "reid.json")
    cfg = json.load(open(cfgp, encoding="utf-8"))
    cfg.pop("open_in", None)  # the default: session windows
    cfg["profiles"] = {"size_live": {"model": "sonnet"}, **cfg["profiles"]}  # first, so key 1 opens it
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
        start = size_now(t)
        check("starts main", start[0] == "main", start)

        key(t, "Digit2", alt=True)
        time.sleep(0.6)
        s = size_now(t)
        check("Alt+2: small (semi-mini), about 380x400", s[0] == "small" and abs(s[1] - 380) <= 2 and abs(s[2] - 400) <= 2, s)
        check("small has the folder", folder_in(t, "small"))
        names = t.js("__reid.state().names")
        combos = t.js("__reid.combos()")
        check("combos: 1-9 in profile order", combos == ["%d%s" % (i + 1, n) for i, n in enumerate(names[:9])], combos)
        check("no sessions yet", t.js("__reid.sessions()") == "No sessions running.", t.js("__reid.sessions()"))
        os.makedirs(SHOTS, exist_ok=True)
        guihome.client_shot(t.hwnd).save(os.path.join(SHOTS, "small.png"))

        i = names.index("size_live")
        if i < 9:
            title = "claude · size_live"
            t0 = time.time()
            key(t, "Digit%d" % (i + 1))
            h, visible = None, False
            while time.time() - t0 < 5 and not visible:
                h = find(t.proc.pid, title)
                visible = bool(h) and bool(u32.IsWindowVisible(W.HWND(h)))
                time.sleep(0.05)
            check("a combo key opens that profile's session window, no gate", visible, "%.2fs" % (time.time() - t0))
            if h:
                sc = u32.GetDpiForWindow(W.HWND(h)) / 96
                f = frame(h)
                check("the session window opens at main's size", f[2] - f[0] >= 1000 * sc - 4 and f[3] - f[1] >= 800 * sc, f)
                page = Page(session_target(seen))
                end, text = time.time() + 5, ""
                while time.time() < end and "size_live" not in text:
                    text = t.js("__reid.sessions()") or ""
                    time.sleep(0.2)
                check("the session list shows it running", "claude · size_live" in text and "running" in text, text)
                procs = ours(bin_)
                page.js("document.getElementById('close').click()")
                end = time.time() + 5
                while time.time() < end and (find(t.proc.pid, title) or any(p.is_running() for p in procs)):
                    time.sleep(0.1)
                time.sleep(1.2)
                check("closed: the list is empty again", t.js("__reid.sessions()") == "No sessions running.", t.js("__reid.sessions()"))
        else:
            print("skip  size_live isn't in the first nine profiles")

        key(t, "Digit1", alt=True)
        time.sleep(0.6)
        s = size_now(t)
        check("Alt+1: back to main, its size", s[0] == "main" and s[1:] == start[1:], "%s, started %s" % (s, start))
        check("the folder is back in main", folder_in(t, "main"))

        r = W.RECT()
        u32.GetWindowRect(W.HWND(t.hwnd), ctypes.byref(r))
        w0, h0 = r.right - r.left, r.bottom - r.top
        form_checks(t, cfgp, w0, h0)
        resize_outer(t.hwnd, w0, h0)
        time.sleep(0.4)
        check("dragged back: main", size_now(t)[0] == "main" and folder_in(t, "main"), size_now(t))

        mini_pod(t, bin_, seen)
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
