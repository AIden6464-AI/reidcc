"""The temp Reidcc folder the GUI tests run against (gui_parity.py, gui_shots.py).

Like parity.py's make_home: personas\\, mds\\, json\\ and assets\\ are junctions (read-only), proxy\\ is
a copy of its files, codex\\ is fresh, reid.json is a copy of the real profiles, reid_state.json is
its own. Never touches E:\\reidcc\\reid.json or reid_state.json.
"""
import os, sys, json, shutil, subprocess, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REIDCC = os.path.dirname(os.path.dirname(HERE))
PYDIR = os.path.join(REIDCC, "python")
RELEASE = os.environ.get("REIDCC_BIN") or os.path.join(REIDCC, "rs", "target", "release")  # REIDCC_BIN: test another build
LINKED = ("personas", "mds", "json", "assets")
# check names hold → and ·: a cp1252 console would crash printing them (tui_parity.py does the same)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def junction(link, target):
    subprocess.run(["cmd", "/c", "mklink", "/J", link, target], check=True, capture_output=True)


def make_home(root=None):
    root = root or tempfile.mkdtemp(prefix="reidgui_")
    home = os.path.join(root, "home")
    os.makedirs(home)
    for d in LINKED:
        junction(os.path.join(home, d), os.path.join(REIDCC, d))
    os.makedirs(os.path.join(home, "proxy"))
    for f in os.listdir(os.path.join(REIDCC, "proxy")):
        if os.path.isfile(os.path.join(REIDCC, "proxy", f)):
            shutil.copy(os.path.join(REIDCC, "proxy", f), os.path.join(home, "proxy"))
    if os.path.isdir(os.path.join(REIDCC, "proxy", ".venv")):
        junction(os.path.join(home, "proxy", ".venv"), os.path.join(REIDCC, "proxy", ".venv"))
    os.makedirs(os.path.join(home, "codex", "prompts"))
    os.makedirs(os.path.join(root, "codex_home"))  # CODEX_HOME for both apps: never ~/.codex
    os.makedirs(os.path.join(root, "work"))        # the project folder sessions open in
    cfg = json.load(open(os.path.join(REIDCC, "reid.json"), encoding="utf-8"))
    with open(os.path.join(home, "reid.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    with open(os.path.join(home, "reid_state.json"), "w", encoding="utf-8") as f:
        json.dump({"recent_dirs": [os.path.join(root, "work")]}, f, indent=2)
    shutil.copy(os.path.join(REIDCC, "reidcc_memory.md"), home)
    return root, home


def unlink_junctions(home):
    for d in LINKED + (os.path.join("proxy", ".venv"),):
        p = os.path.join(home, d)
        if os.path.lexists(p):
            os.rmdir(p)  # removes the junction, never what it points at


def remove_home(root):
    unlink_junctions(os.path.join(root, "home"))
    shutil.rmtree(root, ignore_errors=True)


def env_for(root):
    """The environment both apps run with: the temp home, a temp CODEX_HOME, no EDITOR."""
    env = dict(os.environ, REIDCC_HOME=os.path.join(root, "home"), CODEX_HOME=os.path.join(root, "codex_home"))
    env.pop("EDITOR", None)
    return env


def client_shot(hwnd):
    """The window's client area as a PIL image, via PrintWindow (works when covered, and for WebView2)."""
    import ctypes
    from ctypes import wintypes as W
    from PIL import Image
    u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
    u32.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
    u32.GetClientRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
    u32.ClientToScreen.argtypes = [W.HWND, ctypes.POINTER(W.POINT)]
    u32.GetWindowDC.argtypes = [W.HWND]
    u32.GetWindowDC.restype = W.HDC
    u32.PrintWindow.argtypes = [W.HWND, W.HDC, W.UINT]
    g32.CreateCompatibleDC.argtypes = [W.HDC]
    g32.CreateCompatibleDC.restype = W.HDC
    g32.CreateCompatibleBitmap.argtypes = [W.HDC, ctypes.c_int, ctypes.c_int]
    g32.CreateCompatibleBitmap.restype = W.HBITMAP
    g32.SelectObject.argtypes = [W.HDC, W.HGDIOBJ]
    g32.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, ctypes.c_void_p, ctypes.c_void_p, W.UINT]
    g32.DeleteObject.argtypes = [W.HGDIOBJ]
    g32.DeleteDC.argtypes = [W.HDC]
    u32.ReleaseDC.argtypes = [W.HWND, W.HDC]
    wr, cr, pt = W.RECT(), W.RECT(), W.POINT(0, 0)
    u32.GetWindowRect(hwnd, ctypes.byref(wr))
    u32.GetClientRect(hwnd, ctypes.byref(cr))
    u32.ClientToScreen(hwnd, ctypes.byref(pt))
    w, h = wr.right - wr.left, wr.bottom - wr.top
    wdc = u32.GetWindowDC(hwnd)
    mdc = g32.CreateCompatibleDC(wdc)
    bmp = g32.CreateCompatibleBitmap(wdc, w, h)
    g32.SelectObject(mdc, bmp)
    u32.PrintWindow(hwnd, mdc, 2)  # PW_RENDERFULLCONTENT
    class BIH(ctypes.Structure):
        _fields_ = [("biSize", W.DWORD), ("biWidth", W.LONG), ("biHeight", W.LONG), ("biPlanes", W.WORD),
                    ("biBitCount", W.WORD), ("biCompression", W.DWORD), ("biSizeImage", W.DWORD),
                    ("biXPelsPerMeter", W.LONG), ("biYPelsPerMeter", W.LONG), ("biClrUsed", W.DWORD),
                    ("biClrImportant", W.DWORD)]
    bih = BIH(ctypes.sizeof(BIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * h * 4)
    g32.GetDIBits(mdc, bmp, 0, h, buf, ctypes.byref(bih), 0)
    g32.DeleteObject(bmp)
    g32.DeleteDC(mdc)
    u32.ReleaseDC(hwnd, wdc)
    img = Image.frombuffer("RGB", (w, h), buf, "raw", "BGRX", 0, 1)
    x0, y0 = pt.x - wr.left, pt.y - wr.top
    return img.crop((x0, y0, x0 + cr.right, y0 + cr.bottom))


def emeralds(img):
    """How many separate emerald spots (#00C463-ish, at least 4 px) a shot shows. SPEC-one-look 1.3:
    one per screen, meaning ready or live."""
    img = img.convert("RGB")
    w, h = img.size
    px = img.load()
    on = set()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            if g > 140 and g > r + 90 and g > b + 40:
                on.add((x, y))
    spots = 0
    while on:
        todo, n = [on.pop()], 0
        while todo:
            x, y = todo.pop()
            n += 1
            for q in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if q in on:
                    on.remove(q)
                    todo.append(q)
        spots += n >= 4
    return spots


def find_window(pid, title=None, timeout=20):
    """Find the visible launcher or a window with the exact requested title."""
    import ctypes, time
    from ctypes import wintypes as W
    u32 = ctypes.windll.user32
    found = []
    ENUM = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)

    def cb(h, _):
        p = W.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(p))
        b = ctypes.create_unicode_buffer(64)
        u32.GetWindowTextW(h, b, 64)
        name = b.value
        matches = name == title if title is not None else (
            name == "Reidcc" or (name.startswith("Reidcc ") and name[7:8].isdigit())
        )
        if p.value == pid and matches and u32.IsWindowVisible(h):
            found.append(h)
        return True
    end = time.time() + timeout
    while time.time() < end:
        found.clear()
        u32.EnumWindows(ENUM(cb), 0)
        if found:
            return found[0]
        time.sleep(0.1)
    raise RuntimeError("no %s window for pid %d" % (title or "Reidcc launcher", pid))


class Tauri:
    """Reidcc.exe (Rust) under test: started with the temp home, driven through WebView2's
    DevTools protocol (the page's own event paths, via window.__reid)."""

    def __init__(self, root, port=9333, extra_env=None, exe=None):
        import time, json as _json, urllib.request
        import websocket
        env = env_for(root)
        env.update(REIDCC_GUI_TEST="1", WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=%d" % port)
        env.update(extra_env or {})
        self.proc = subprocess.Popen([exe or os.path.join(RELEASE, "Reidcc.exe")], env=env, cwd=os.path.join(root, "work"))
        self.hwnd = find_window(self.proc.pid)
        end = time.time() + 20
        while True:
            try:
                pages = _json.load(urllib.request.urlopen("http://127.0.0.1:%d/json" % port, timeout=2))
                page = next(p for p in pages if p.get("type") == "page")
                break
            except Exception:
                if time.time() > end:
                    raise
                time.sleep(0.2)
        self.ws = websocket.create_connection(page["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
        self.n = 0
        # draw focus as if the window were active even when it isn't (the Tk window beside it is
        # active while both are shot), so focus rings show the same in both
        self.cdp("Emulation.setFocusEmulationEnabled", enabled=True)
        end = time.time() + 20
        while not self.js("!!window.__reid"):
            if time.time() > end:
                raise RuntimeError("page never got its test hooks")
            time.sleep(0.1)

    def cdp(self, method, **params):
        import json as _json
        self.n += 1
        self.ws.send(_json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            m = _json.loads(self.ws.recv())
            if m.get("id") == self.n:
                if "error" in m:
                    raise RuntimeError(m["error"])
                return m["result"]

    def js(self, expr):
        r = self.cdp("Runtime.evaluate", expression=expr, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in r:
            raise RuntimeError(r["exceptionDetails"])
        return r["result"].get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass
        self.proc.kill()  # our own process, by its handle
        self.proc.wait()


def python_core(root):
    """Import the Python app in this process, pointed at the temp home. Call once per process."""
    for k, v in env_for(root).items():
        os.environ[k] = v
    os.environ.pop("EDITOR", None)
    sys.path.insert(0, PYDIR)
    import reid
    import reid_gui
    assert reid.HOME == os.path.join(root, "home"), reid.HOME
    return reid, reid_gui
