"""The launch flow of the Rust GUI: open gate opens Windows Terminal over the launcher and the session
starts there; resume does the same with --resume.

The session is a profile whose args end it at once (claude --version). Reidcc.exe and reid.exe run
from a copy inside the temp Reidcc folder: the terminal tab may not get this process's environment,
and reid.exe then finds its Reidcc folder from where it lives, so it still writes the temp
reid_state.json, never E:\\reidcc's. Checks the real reid.json / reid_state.json stay untouched.
Closes (WM_CLOSE) only terminal windows it opened that are still there.

    python rs\\tests\\gui_flow.py
"""
import os, sys, json, time, shutil, ctypes
import psutil
from ctypes import wintypes as W

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guihome

u32 = ctypes.windll.user32
WT_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"


def wt_windows():
    out = {}
    ENUM = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    def cb(h, _):
        c = ctypes.create_unicode_buffer(64)
        u32.GetClassNameW(h, c, 64)
        if c.value == WT_CLASS:
            t = ctypes.create_unicode_buffer(256)
            u32.GetWindowTextW(h, t, 256)
            out[h] = t.value
        return True
    u32.EnumWindows(ENUM(cb), 0)
    return out


def stamp(path):
    return os.path.getmtime(path) if os.path.exists(path) else None


def run_one(t, button, home, before):
    """Press button; follow the terminal window it opens until it closes (or 20 s)."""
    t0 = time.time()
    if not t.js("__reid.button(%s)" % json.dumps(button)):
        return {"error": "no %s button" % button}
    seen, first, shown, titles, msgs, cmds, rect = None, None, None, set(), [], [], None
    r = W.RECT()
    u32.GetWindowRect(t.hwnd, ctypes.byref(r))
    launcher = (r.left, r.top, r.right, r.bottom)
    while time.time() - t0 < 20:
        for p in psutil.process_iter(["name", "exe", "cmdline"]):
            try:
                if p.info["name"] == "reid.exe" and os.path.dirname(p.info["exe"] or "") == os.path.join(home, "bin"):
                    c = " ".join(p.info["cmdline"][1:])
                    if c not in cmds:
                        cmds.append(c)
            except Exception:
                pass
        m = t.js("__reid.state().msg")
        if m and m not in msgs:
            msgs.append(m)
        now = wt_windows()
        new = [h for h in now if h not in before]
        if new and seen is None:
            seen, first = new[0], time.time() - t0
        if seen is not None:
            if seen in now:
                titles.add(now[seen])
                r = W.RECT()
                u32.GetWindowRect(seen, ctypes.byref(r))
                rect = (r.left, r.top, r.right, r.bottom)
                if shown is None and u32.IsWindowVisible(seen):
                    shown = time.time() - t0
            elif time.time() - t0 > 3:
                break  # the session ended, its window closed, and the gate is done
        time.sleep(0.05)
    still = seen is not None and seen in wt_windows()
    if still:
        u32.PostMessageW(seen, 0x0010, 0, 0)  # WM_CLOSE: only the window this press opened
    state = json.load(open(os.path.join(home, "reid_state.json"), encoding="utf-8"))
    return {"window_found_s": first and round(first, 2), "window_shown_s": shown and round(shown, 2),
            "titles": sorted(titles), "closed_by_itself": seen is not None and not still,
            "launcher_rect": launcher, "terminal_rect": rect, "messages": msgs, "reid.exe args": cmds, "last": state.get("last")}


def main():
    real = {f: stamp(os.path.join(guihome.REIDCC, f)) for f in ("reid.json", "reid_state.json")}
    root, home = guihome.make_home()
    cfgp = os.path.join(home, "reid.json")
    cfg = json.load(open(cfgp, encoding="utf-8"))
    cfg["profiles"]["flow"] = {"model": "opus", "args": ["--version"]}
    cfg["open_in"] = "terminal"  # this checks the Windows Terminal path; session_flow.py checks session windows
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    bin_ = os.path.join(home, "bin")
    os.makedirs(bin_)
    for exe in ("Reidcc.exe", "reid.exe"):
        shutil.copy(os.path.join(guihome.RELEASE, exe), bin_)
    t = None
    try:
        t = guihome.Tauri(root, exe=os.path.join(bin_, "Reidcc.exe"))
        time.sleep(1.0)
        names = t.js("__reid.state().names")
        t.js("__reid.selectRow(%d)" % names.index("flow"))
        time.sleep(0.4)
        before = wt_windows()
        go = run_one(t, "open gate", home, before)
        time.sleep(5)  # the gate's note clears after 4 s
        before = wt_windows()
        resume = run_one(t, "resume", home, before)
        time.sleep(1)
    finally:
        if t:
            t.close()
        guihome.remove_home(root)
    after = {f: stamp(os.path.join(guihome.REIDCC, f)) for f in ("reid.json", "reid_state.json")}
    print("open gate:", json.dumps(go, ensure_ascii=False))
    print("resume:   ", json.dumps(resume, ensure_ascii=False))
    print("real reid.json / reid_state.json untouched:", real == after)


if __name__ == "__main__":
    main()
