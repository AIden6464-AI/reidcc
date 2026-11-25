"""One window (vision\\Spec\\SPEC-one-window.md) in the Rust GUI: the launcher docks into a session window
beside the terminal or full over it, goes back home, and a session that ends turns its window into Reidcc.

Same temp Reidcc folder and rules as session_flow.py: the real reid.json / reid_state.json are never
touched, and only processes started from the temp bin\\ are killed. Screenshots: rs\\tests\\dock_shots\\.

    python rs\\tests\\dock_flow.py
"""
import os, sys, json, time, shutil, ctypes, urllib.request
import psutil
from ctypes import wintypes as W

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guihome
from session_flow import check, results, find, frame, ours, Page, session_target, press, PORT
from sizes_flow import key, size_now, resize_inner, visible, pod_hwnd, PodPage
from session_flow import windows_of

u32 = ctypes.windll.user32
SHOTS = os.path.join(HERE, "dock_shots")
COL = 500  # panel.rs COL, logical px


def shot(h, name):
    guihome.client_shot(h).save(os.path.join(SHOTS, name + ".png"))


def desk(rect, name):
    """The screen around a window (shows where it sits and how it grew), not just its client area."""
    from PIL import ImageGrab
    l, t, r, b = rect
    ImageGrab.grab(bbox=(l - 20, t, r + 20, b + 20), all_screens=True).save(os.path.join(SHOTS, name + ".png"))


def wait(cond, secs=4):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.05)
    return cond()


def term_key(page, code, alt=False):
    page.js("__term.textarea.dispatchEvent(new KeyboardEvent('keydown', {code: %s, key: %s, altKey: %s, bubbles: true, cancelable: true}))"
            % (json.dumps(code), json.dumps(code[-1]), "true" if alt else "false"))


def open_session(t, name, seen):
    title = "claude · " + name
    press(t, name)
    h = None
    wait(lambda: visible(find(t.proc.pid, title)), 8)
    h = find(t.proc.pid, title)
    page = Page(session_target(seen)) if h else None
    return title, h, page


def main():
    os.makedirs(SHOTS, exist_ok=True)
    real = {f: os.path.getmtime(os.path.join(guihome.REIDCC, f)) for f in ("reid.json", "reid_state.json")}
    root, home = guihome.make_home()
    cfgp = os.path.join(home, "reid.json")
    cfg = json.load(open(cfgp, encoding="utf-8"))
    cfg.pop("open_in", None)
    cfg["profiles"]["dock_live"] = {"model": "sonnet"}
    cfg["profiles"]["dock_two"] = {"model": "sonnet"}
    cfg["profiles"]["dock_ends"] = {"model": "opus", "args": ["--version"]}
    pair = lambda a, b: {"layout": {"split": "h", "portion": 0.5, "first": {"profile": a}, "second": {"profile": b}}}
    cfg["rigs"] = {"pair": pair("dock_live", "dock_two"), "ends": pair("dock_live", "dock_ends")}
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
        sc = u32.GetDpiForWindow(W.HWND(t.hwnd)) / 96

        # 1. the launcher's own bar at each size
        bar = t.js("__reid.bar()")
        check("the launcher draws its own bar: RC, title, - [] x", "Reidcc" in bar and "dev" in bar, bar.replace("\n", " | "))
        shot(t.hwnd, "01_main")
        resize_inner(t, 500, 836)
        time.sleep(0.5)
        shot(t.hwnd, "02_medium")
        key(t, "Digit2", alt=True)
        time.sleep(0.8)
        shot(t.hwnd, "03_small")
        key(t, "Digit1", alt=True)
        time.sleep(0.8)

        # 2. RC on a session's bar: beside, full, closed
        title, h, page = open_session(t, "dock_live", seen)
        check("a session window opens", bool(h))
        if not h:
            return 1
        time.sleep(1.5)
        home_vis = visible(t.hwnd)  # the launcher stays behind a session it opened; docking gives that back
        before, cols = frame(h), page.js("__term.cols")
        shot(h, "04_session")
        page.js("document.getElementById('mark').click()")
        wait(lambda: t.js("__reid.docked()") == "beside")
        time.sleep(0.6)
        now = frame(h)
        check("RC: the launcher opens beside", t.js("__reid.docked()") == "beside", t.js("__reid.docked()"))
        # it grows on its left; with no room there the screen edge pushes it right
        check("the window grew by the column, on its left", abs((now[2] - now[0]) - (before[2] - before[0]) - COL * sc) <= 3
              and now[1] == before[1] and now[3] == before[3] and (now[2] == before[2] or now[0] == 0), (before, now))
        check("the terminal kept its size (no resize)", page.js("__term.cols") == cols, (cols, page.js("__term.cols")))
        check("the launcher's back button names the session", "dock_live" in t.js("__reid.bar()"), t.js("__reid.bar()").replace("\n", " | "))
        check("the launcher's own window stays hidden", not visible(t.hwnd))
        shot(h, "05_beside")
        desk(now, "05b_beside_desktop")

        page.js("document.getElementById('mark').click()")
        wait(lambda: t.js("__reid.docked()") == "full")
        time.sleep(0.5)
        check("RC again: full", t.js("__reid.docked()") == "full")
        check("full keeps the window where it was", frame(h) == now, (now, frame(h)))
        check("the terminal is hidden, not resized", page.js("__term.cols") == cols)
        shot(h, "06_full")

        page.js("document.getElementById('mark').click()")
        wait(lambda: not t.js("__reid.docked()"), 3)
        time.sleep(0.5)
        check("RC a third time: closed", not t.js("__reid.docked()"))
        check("the window is back to the terminal's size and place", frame(h) == before, (before, frame(h)))
        check("the launcher went home, as it was (behind the session)", visible(t.hwnd) == home_vis)
        shot(h, "07_closed")

        # 3. keys: Alt+2 / Alt+1 in the terminal, Escape and the back button in the launcher
        term_key(page, "Digit2", alt=True)
        check("Alt+2 in the terminal: beside", wait(lambda: t.js("__reid.docked()") == "beside"))
        esc = "window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', code: 'Escape', bubbles: true}))"
        msg = t.js("__reid.state().msg")
        if msg:  # Escape is layered (spec Keys): a message showing goes first
            t.js(esc)
            check("Escape with a message showing: the message goes, Reidcc stays", wait(lambda: not t.js("__reid.state().msg"), 2)
                  and t.js("__reid.docked()") == "beside", msg)
        t.js(esc)
        check("Escape in the launcher: back to the terminal", wait(lambda: not t.js("__reid.docked()")))
        term_key(page, "Digit1", alt=True)
        check("Alt+1 in the terminal: full", wait(lambda: t.js("__reid.docked()") == "full"))
        time.sleep(0.4)
        t.js("document.querySelector('#lbar .lback').click()")
        check("← back: the terminal again", wait(lambda: not t.js("__reid.docked()")))
        time.sleep(0.4)
        check("the window ends where it started", frame(h) == before, (before, frame(h)))

        # 4. open gate from the docked launcher: the new session opens over, Reidcc goes home behind it
        page.js("document.getElementById('mark').click()")
        wait(lambda: t.js("__reid.docked()") == "beside")
        time.sleep(0.5)
        title2, h2, page2 = open_session(t, "dock_two", seen)
        check("open gate from the docked launcher opens a session", bool(h2))
        check("the launcher went home (not docked)", wait(lambda: not t.js("__reid.docked()"), 6))
        time.sleep(0.6)
        check("the first window is back to its size", frame(h) == before, (before, frame(h)))
        if h2:
            shot(h2, "08_go_from_docked")

        # 5. the pod: docked, Alt+3 folds from home and the host shrinks back
        if page2:
            page2.js("document.getElementById('mark').click()")
            wait(lambda: t.js("__reid.docked()") == "beside")
            time.sleep(0.4)
            key(t, "Digit3", alt=True)
            p = None
            wait(lambda: visible(pod_hwnd(t)), 5)
            p = pod_hwnd(t)
            check("docked + Alt+3: the launcher folds into the pod", visible(p) and not t.js("__reid.docked()"))
            if p:
                time.sleep(1.3)  # the pod has drawn its slots
                desk(frame(p), "09_pod")  # a see-through window: PrintWindow gets only its fill
                PodPage().js("window.dispatchEvent(new KeyboardEvent('keydown', {code: 'Digit1', key: '1', altKey: true}))")
                check("Alt+1 on the pod: the launcher is back", wait(lambda: visible(t.hwnd) and not visible(p), 4))

        # 6. a session that ends by itself turns its window into Reidcc
        for hh in (h, h2):
            if hh:
                u32.PostMessageW(W.HWND(hh), 0x0010, 0, 0)  # WM_CLOSE: our own windows
        time.sleep(4.5)
        title3, h3, page3 = open_session(t, "dock_ends", seen)
        rect = frame(h3) if h3 else None
        check("the ending session opened", bool(h3))
        ok = wait(lambda: h3 and not find(t.proc.pid, title3) and visible(t.hwnd), 10)
        time.sleep(0.6)
        check("it ended: its window is gone and Reidcc is there", ok, windows_of(t.proc.pid))
        if rect:
            check("Reidcc took the session window's place and size", frame(t.hwnd) == rect, (rect, frame(t.hwnd)))
        shot(t.hwnd, "10_ended_becomes_reidcc")
        check("the launcher says how it ended", "ended" in (t.js("__reid.state().msg") or "") or bool(t.js("__reid.state().msg")), t.js("__reid.state().msg"))

        # 7. a frame (a rig's two panes): RC docks beside them, closing gives the frame back
        def rig(name):
            before = set(windows_of(t.proc.pid))
            t.js("window.__TAURI_INTERNALS__.invoke('rig_open', {name: %s})" % json.dumps(name))
            wait(lambda: any(windows_of(t.proc.pid).get(w, ("", 0))[0] == "Reidcc · sessions" and visible(w)
                             for w in set(windows_of(t.proc.pid)) - before), 10)
            g = next((w for w in set(windows_of(t.proc.pid)) - before if windows_of(t.proc.pid)[w][0] == "Reidcc · sessions"), None)
            if not g:
                return None, []
            top, new = max(seen, default=0), []
            def two():  # both panes at once: session_target takes only the newest
                nonlocal new
                new = sorted((p for p in json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % PORT, timeout=2))
                              if "session.html?id=" in p.get("url", "") and int(p["url"].split("id=")[1]) > top),
                             key=lambda p: int(p["url"].split("id=")[1]))
                return len(new) >= 2
            wait(two, 10)
            seen.update(int(p["url"].split("id=")[1]) for p in new)
            return g, [Page(p) for p in new[:2]]
        g, panes = rig("pair")
        check("a rig opens its frame", bool(g) and len(panes) == 2)
        if g:
            time.sleep(1.5)
            fb, fcols = frame(g), [p.js("__term.cols") for p in panes]
            shot(g, "11_frame")
            panes[0].js("document.getElementById('mark').click()")
            check("RC in a frame pane: beside", wait(lambda: t.js("__reid.docked()") == "beside"))
            time.sleep(0.6)
            fn = frame(g)
            check("the frame grew by the column", abs((fn[2] - fn[0]) - (fb[2] - fb[0]) - COL * sc) <= 3, (fb, fn))
            check("its tiles moved right, same size (no resize)", [p.js("__term.cols") for p in panes] == fcols,
                  (fcols, [p.js("__term.cols") for p in panes]))
            check("the back button says sessions", "sessions" in t.js("__reid.bar()"), t.js("__reid.bar()").replace("\n", " | "))
            shot(g, "12_frame_beside")
            desk(fn, "12b_frame_beside_desktop")
            panes[1].js("document.getElementById('mark').click()")  # RC again (any pane): full
            wait(lambda: t.js("__reid.docked()") == "full")
            panes[1].js("document.getElementById('mark').click()")
            check("RC twice more: closed", wait(lambda: not t.js("__reid.docked()")))
            time.sleep(0.5)
            check("the frame is back to its size and place", frame(g) == fb, (fb, frame(g)))
            u32.PostMessageW(W.HWND(g), 0x0010, 0, 0)
            time.sleep(3)

        # 8. a pane that ends by itself: it goes, and Reidcc docks beside what's left
        g, panes = rig("ends")
        check("the ending rig opens its frame", bool(g))
        if g:
            ok = wait(lambda: t.js("__reid.docked()") == "beside", 10)
            check("a pane ended: Reidcc docks beside the pane left", ok, t.js("__reid.docked()"))
            time.sleep(0.6)
            left = find(t.proc.pid, "claude · dock_live")  # two panes less one: the frame gives way to the pane's own window
            check("the pane left has its own window, Reidcc beside it", visible(left) and "dock_live" in t.js("__reid.bar()"),
                  (windows_of(t.proc.pid), t.js("__reid.bar()").replace("\n", " | ")))
            if left:
                shot(left, "13_frame_pane_ended")
            check("the launcher says how it ended", bool(t.js("__reid.state().msg")), t.js("__reid.state().msg"))
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
