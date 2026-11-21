"""Reidcc GUI -- the app face of reid. Same reid.json, same engine.

Opened by reid.py when it's started as an app (double-click, Start Menu, pythonw)
or with `reid --gui`. `open gate` opens a terminal running `reid <profile>`, so /reid,
resume and the TUI all work there exactly as when you type `reid` yourself.

Look and words follow vision/: reidcc-palette.md, reidcc_design_motion_system.md
("Direction from Reid": everything on one screen, nothing hidden in settings) and
reidcc-voice.md. Bone on near-black, one emerald signal, folder -> profile -> open gate.
"""
import os
import sys
import json
import glob
import time
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, font as tkfont

# Tokens from vision/reidcc-palette.md
C = {
    "canvas": "#040404", "s1": "#0E0D0C", "s2": "#171513", "stone": "#292723",
    "line": "#2A2724", "line2": "#4A4540", "linework": "#928A82",
    "text": "#D6D0C8", "text2": "#9F978E", "text3": "#746F69",
    "emerald": "#00C463", "bronze": "#C99A45", "oxide": "#C0584B",
}
SUB = "subscription"
NO_PERSONA = "none"
TOOLS_CHOICES = ["all", "core", "core + web", "web only", "none"]
MCP_DEFAULT = "your servers"
MODES = (("append", "add to Claude Code's prompt"), ("replace", "replace Claude Code's prompt"))
PAD = 40

# Windows Terminal geometry, measured 2026-11-17 on WT 1.25 (default profile): a cell is 9x19 px, the
# window adds 49x65 px, and its frame sits 8 px left of --pos (invisible resize border). Only has to
# be close: the session window opens over the launcher, out of the gate's dark last frame.
WT_CELL, WT_CHROME, WT_BORDER = (9, 19), (49, 65), 8
WT_CLASS = "CASCADIA_HOSTING_WINDOW_CLASS"

if os.name == "nt":
    import ctypes
    from ctypes import wintypes as W
    _u32 = ctypes.windll.user32
    _u32.SetWindowLongPtrW.argtypes = [W.HWND, ctypes.c_int, ctypes.c_ssize_t]
    _u32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    _u32.GetWindowLongW.restype = ctypes.c_long
    _u32.GetWindowLongW.argtypes = [W.HWND, ctypes.c_int]
    _u32.SetWindowLongW.argtypes = [W.HWND, ctypes.c_int, ctypes.c_long]
    _u32.GetWindowRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
    _u32.ShowWindow.argtypes = [W.HWND, ctypes.c_int]
    _u32.IsWindowVisible.argtypes = [W.HWND]
    _u32.SetForegroundWindow.argtypes = [W.HWND]
    _u32.GetForegroundWindow.restype = W.HWND
    _u32.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
    _ENUM = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
    _u32.EnumWindows.argtypes = [_ENUM, W.LPARAM]
else:
    _u32 = None


def top_hwnd(widget):
    """The real top-level HWND of a Tk toplevel (winfo_id is its inner child window)."""
    return int(widget.wm_frame(), 16)


def own(widget, owner):
    """Make owner (the launcher) own this window: it then always stays above the launcher and never
    above other apps. Tk's `wm transient` doesn't do this for borderless windows, and a withdrawn
    transient window never maps again."""
    _u32.SetWindowLongPtrW(top_hwnd(widget), -8, top_hwnd(owner))  # -8: GWLP_HWNDPARENT


def set_exstyle(widget, add=0, remove=0):
    h = top_hwnd(widget)
    _u32.SetWindowLongW(h, -20, (_u32.GetWindowLongW(h, -20) | add) & ~remove)  # -20: GWL_EXSTYLE


def theme_titlebar(root):
    """Windows' own title bar in the palette: canvas background, text-2 title, hairline border.
    Keeps native drag/snap/resize. Windows 10 ignores the colours (dark mode still applies)."""
    if not _u32:
        return
    root.update_idletasks()
    h, dwm = top_hwnd(root), ctypes.windll.dwmapi
    ref = lambda c: int(c[5:7] + c[3:5] + c[1:3], 16)  # "#RRGGBB" -> COLORREF 0x00BBGGRR
    for attr, val in ((20, 1), (34, ref(C["line"])), (35, ref(C["canvas"])), (36, ref(C["text2"]))):
        v = ctypes.c_int(val)  # 20 dark mode, 34 border, 35 caption, 36 title text
        dwm.DwmSetWindowAttribute(W.HWND(h), attr, ctypes.byref(v), ctypes.sizeof(v))


EX_LAYERED, EX_TRANSPARENT, EX_TOOLWINDOW, EX_NOACTIVATE = 0x80000, 0x20, 0x80, 0x08000000


def wt_windows():
    """Visible Windows Terminal windows, as a set of HWND ints."""
    out = set()

    def cb(h, _):
        b = ctypes.create_unicode_buffer(64)
        _u32.GetClassNameW(h, b, 64)
        if b.value == WT_CLASS and _u32.IsWindowVisible(h):
            out.add(h)
        return True
    _u32.EnumWindows(_ENUM(cb), 0)
    return out


def window_rect(h):
    r = W.RECT()
    _u32.GetWindowRect(h, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom


def lock_foreground(on):
    """While the gate plays, other apps can't take the foreground, so the new terminal opens without
    grabbing the keyboard (keys go on skipping the gate). Windows lifts it by itself on Alt or a click
    elsewhere. Only works when called from the foreground app, which the launcher is at a press."""
    _u32.LockSetForegroundWindow(1 if on else 2)  # LSFW_LOCK / LSFW_UNLOCK


def fine_timer(on):
    """1 ms timer ticks while the gate plays (one begin per end). Otherwise Tk's after() lands on
    Windows' 15.6 ms tick and the frames arrive 5-20 ms late in a sawtooth."""
    (ctypes.windll.winmm.timeBeginPeriod if on else ctypes.windll.winmm.timeEndPeriod)(1)


def bring_front(h):
    lock_foreground(False)
    _u32.ShowWindow(h, 5)  # SW_SHOW
    _u32.SetForegroundWindow(h)  # allowed while the launcher is the foreground app (it was just pressed)
    if _u32.GetForegroundWindow() != h:
        # Focus moved meanwhile: a tap of Alt lifts Windows' foreground lock for one switch.
        _u32.keybd_event(0x12, 0, 0, 0)
        _u32.keybd_event(0x12, 0, 2, 0)
        _u32.SetForegroundWindow(h)


def ease(t):
    return 1 - (1 - t) ** 3  # fast start, soft stop, no overshoot


class Gate:
    """The gate (SPEC-gate.md). One borderless window over the launcher's client area:
    - ghost: the gate's blueprint lines at GHOST strength, see-through and click-through, on hover;
    - gate: the full art, which rises out of its lines, ignites and opens while the session starts;
      the view pushes through the lit passage into the dark, and the session window appears there.
    Frames fill the launcher (python\\build\\make_assets.py). Tk has no per-widget opacity, hence a separate
    layered window (window alpha + colour key)."""
    GHOST = 0.14
    PACE = 1.375   # the opening's speed: 10% slower, then 25% slower again (Reid, 2026-11-17)
    SOLID = 0.999  # not 1.0: at 1.0 Tk drops WS_EX_LAYERED and our click-through bits with it

    def __init__(self, app):
        self.app, self.root = app, app.root
        path = asset(os.path.join("assets", "gate.json"))
        self.meta = json.load(open(path)) if path else None
        self.ok = bool(self.meta) and _u32 is not None
        self.active = False
        self.images, self.flags, self.timers = {}, {}, []
        self.alpha, self.mode = 0.0, None
        self._fade_job = self._hover_job = self._poll_job = None
        self._gen = 0
        if not self.ok:
            return
        self.win = tk.Toplevel(self.root)
        self.win.withdraw()  # mapped in _first_map, once it can be made click-through
        self.win.overrideredirect(True)
        self.win.attributes("-alpha", 0.0)
        self.canvas = tk.Canvas(self.win, highlightthickness=0, bd=0, bg=self.meta["key"])
        self.canvas.pack(fill="both", expand=True)
        self.item = self.canvas.create_image(0, 0, anchor="nw")
        self.tag = self.canvas.create_text(0, 0, anchor="e", text="", font=app.F["tag"])
        # shown on the dark last frame while the session window is still starting
        self.head = self.canvas.create_text(0, 0, anchor="nw", text="", fill=C["text2"], font=app.F["mono"])
        self.subhead = self.canvas.create_text(0, 0, anchor="nw", text="", fill=C["text3"], font=app.F["tag"])
        self.canvas.bind("<Button-1>", lambda e: self.skip())
        self.root.bind("<Configure>", lambda e: self.place() if e.widget is self.root else None, add="+")
        self.root.bind("<Deactivate>", lambda e: self.calm(), add="+")
        self.root.after(250, self._first_map)

    # -- setup
    def _first_map(self):
        focus = self.root.focus_get()
        self.set_mode("ghost")
        self.place()
        self.win.deiconify()
        self.win.update_idletasks()
        own(self.win, self.root)
        self._style()
        if focus:
            focus.focus_force()  # mapping the overlay must not take the launcher's focus
        self._load(self.resident(), 20)

    def _style(self):
        click_through = EX_TRANSPARENT if self.mode == "ghost" else 0
        set_exstyle(self.win, add=EX_LAYERED | EX_TOOLWINDOW | EX_NOACTIVATE | click_through,
                    remove=0 if click_through else EX_TRANSPARENT)

    def frames(self, step):
        return ["%s%02d" % (step, i) for i in range(next(s[1] for s in self.meta["steps"] if s[0] == step))]

    # Frames fill the launcher, so each one is ~3.5 MB in memory. The ghost, the closed gate and the
    # steps before the last stay loaded; the last step's frames (the most) load while the gate is
    # hovered or the first steps play (~12 ms each), and are freed again afterwards.
    def resident(self):
        return ["ghost", "gate"] + [n for s in self.meta["steps"][:-1] for n in self.frames(s[0])]

    def warm(self):
        self._load(self.frames(self.meta["steps"][-1][0]), 1, self._gen)

    def cool(self):
        self._gen += 1  # stops a warm() still loading
        for n in self.frames(self.meta["steps"][-1][0]):
            self.images.pop(n, None)

    def _load(self, names, gap, gen=None):
        """One frame per tick, so nothing else waits on it."""
        todo = [n for n in names if n not in self.images]
        if todo and gen in (None, self._gen):
            self.image(todo[0])
            self.root.after(gap, lambda: self._load(todo[1:], gap, gen))

    def image(self, name):
        if name not in self.images:
            rel = {"ghost": "gate_ghost.png", "gate": "gate.png"}.get(name) or "gate_%s/%s.png" % (name[:-2], name[-2:])
            path = asset(os.path.join("assets", *rel.split("/")))
            self.images[name] = tk.PhotoImage(file=path) if path else None
        return self.images[name]

    # -- drawing
    def set_mode(self, mode):
        if mode == self.mode:
            return
        self.mode = mode
        if mode == "ghost":
            self.canvas.configure(bg=self.meta["key"])
            self.win.attributes("-transparentcolor", self.meta["key"])
            self.canvas.itemconfigure(self.item, image=self.image("ghost"))
            for item in (self.tag, self.head, self.subhead):
                self.canvas.itemconfigure(item, text="")
        else:
            self.win.attributes("-transparentcolor", "")
            self.canvas.configure(bg=self.meta["bg"])
            self.canvas.itemconfigure(self.item, image=self.image("gate"))
        self._style()

    def place(self):
        r = self.root
        w, h = r.winfo_width(), r.winfo_height()
        self.win.geometry("%dx%d+%d+%d" % (w, h, r.winfo_rootx(), r.winfo_rooty()))
        iw, ih = self.meta["size"]
        self.x0, self.y0 = (w - iw) // 2, (h - ih) // 2
        self.canvas.coords(self.item, self.x0, self.y0)
        self.canvas.coords(self.tag, self.x0 + self.meta["tag"][0], self.y0 + self.meta["tag"][1])
        self.canvas.coords(self.head, 24, 20)       # where the terminal's first line will be
        self.canvas.coords(self.subhead, 24, 44)

    def set_tag(self, text, color):
        self.canvas.itemconfigure(self.tag, text=text, fill=color)

    def set_alpha(self, a):
        self.alpha = a
        self.win.attributes("-alpha", min(a, self.SOLID))

    def fade(self, to, ms, then=None):
        if self._fade_job:
            self.root.after_cancel(self._fade_job)
            self._fade_job = None
        start, t0 = self.alpha, time.perf_counter()

        def step():
            t = min(1.0, (time.perf_counter() - t0) * 1000 / ms) if ms > 0 else 1.0
            self.set_alpha(start + (to - start) * ease(t))
            if t < 1:
                self._fade_job = self.root.after(15, step)
            else:
                self._fade_job = None
                if then:
                    then()
        step()

    # -- the ghost
    def hover(self, key, on):
        """key: which control (pointer or focus on open gate / resume). Ghost while any is on."""
        if not self.ok or self.active:
            return
        self.flags[key] = on
        if self._hover_job:
            self.root.after_cancel(self._hover_job)
            self._hover_job = None
        if any(self.flags.values()):
            def show():
                self._hover_job = None
                self.set_mode("ghost")
                self.place()
                self.fade(self.GHOST, 140)
                self.warm()  # a press is likely: get the opening ready
            self._hover_job = self.root.after(60, show)  # sweeping past the button doesn't flash it
        else:
            self.fade(0, 120)

    def calm(self):
        """The launcher lost focus (alt-tab, a dialog): no ghost left hanging over it."""
        if self.ok and not self.active:
            self.flags.clear()
            self.cool()
            if self._hover_job:
                self.root.after_cancel(self._hover_job)
                self._hover_job = None
            self.fade(0, 120)

    # -- opening the gate
    def plan(self):
        """Where the session window goes: over the launcher, at its size (wt --pos/--size values)."""
        l, t, r, b = window_rect(top_hwnd(self.root))
        cols = max(40, round((r - l - WT_CHROME[0]) / WT_CELL[0]))
        rows = max(10, round((b - t - WT_CHROME[1]) / WT_CELL[1]))
        return {"pos": "%d,%d" % (l + WT_BORDER, t), "size": "%d,%d" % (cols, rows)}

    def open(self, launch, title, sub):
        """launch(plan) -> (note, uses_wt). The session starts first; the gate never delays it."""
        app = self.app
        if not self.ok:
            note, _ = launch(None)
            app.say(note, "quiet", seconds=4)
            return
        for job in (self._hover_job, self._fade_job):
            if job:
                self.root.after_cancel(job)
        self._hover_job = self._fade_job = None
        self.flags.clear()
        plan = self.plan()
        before = wt_windows()
        lock_foreground(True)
        try:
            self.note, self.uses_wt = launch(plan)
        except OSError as e:
            lock_foreground(False)
            self.fade(0, 0)
            app.say("Couldn't open the session (%s). Check that Windows Terminal or Claude Code still runs." % e,
                    "error")
            return
        self.active, self.done = True, False
        fine_timer(True)
        self.t0, self.before, self.plan_ = time.perf_counter(), before, plan
        self.found, self.hidden, self.dark = None, False, False
        self.title, self.sub = title, sub
        self.root.focus_set()  # keys now skip instead of typing into a field
        steps = self.meta["steps"]  # rise, ignite, open: [name, frames, start ms, ms]
        self.warm()                 # if not hovered first: loads while rise and ignite play
        self.set_mode("gate")
        self.canvas.itemconfigure(self.item, image=self.image(self.frames(steps[0][0])[0]))
        self.place()
        self.set_tag("REIDCC · OPENING", C["bronze"])
        if self.uses_wt:
            self._poll()
        self.fade(self.SOLID, steps[0][3] * self.PACE)          # 1. the window solidifies while the gate rises
        for name, _, start, dur in steps:                       # 2. ignite, 3. open and push through
            self.play(self.frames(name), start, dur)
        end = steps[-1][2] + steps[-1][3]
        if self.uses_wt:
            self.at(end, self.in_the_dark)                      # 4. the session window appears in the dark
        else:
            self.at(end, lambda: self.set_tag("REIDCC · READY", C["text2"]))
            self.at(end + 300, lambda: self.fade(0, 180 * self.PACE, then=self.finish))

    def at(self, ms, fn):
        """Run fn at ms (design timing, scaled by PACE) after the press, on schedule even if a frame ran late."""
        delay = ms * self.PACE - (time.perf_counter() - self.t0) * 1000
        self.timers.append(self.root.after(max(0, int(delay)), fn))

    def play(self, names, start, dur):
        for i, n in enumerate(names):
            self.at(start + dur * i / len(names), lambda n=n: self.canvas.itemconfigure(self.item, image=self.image(n)))

    def _poll(self):
        """Watch for the new terminal window. While the gate plays it stays hidden: Claude Code is
        already starting behind it, and the window would otherwise cover the gate (WT shows its
        window ~0.25 s after launch when it's already running)."""
        self._poll_job = None
        elapsed = time.perf_counter() - self.t0
        if self.found is None:
            new = wt_windows() - self.before
            if new:
                self.found = new.pop()
                if not self.active:          # skipped already: just bring it forward
                    self.hand_over()
                    return
                self.set_tag("REIDCC · READY", C["text2"])  # READY is real: the window exists
                self.maybe_handoff()
            elif elapsed > 8:
                if self.active:
                    self.timeout()
                return
        if self.found is not None and self.active and not self.done:
            if _u32.IsWindowVisible(self.found):  # WT may show itself again while it starts up
                _u32.ShowWindow(self.found, 0)    # SW_HIDE
                self.hidden = True
            if _u32.GetForegroundWindow() == self.found:
                # A hidden window can keep the keyboard: keys meant to skip would type into the
                # session. Take it back (allowed: the press that opened the gate was the last input).
                _u32.SetForegroundWindow(top_hwnd(self.root))
                self.root.focus_force()
        if self.found is None or (self.active and not self.done):
            self._poll_job = self.root.after(10 if elapsed < 2 else 50, self._poll)

    def in_the_dark(self):
        """The view has gone through the passage into the dark. The session window appears here; if it
        isn't up yet, say what's opening where its first line will be."""
        self.dark = True
        if self.found is None:
            self.canvas.itemconfigure(self.head, text=self.title + " · opening…")
            self.canvas.itemconfigure(self.subhead, text=self.sub)
        self.maybe_handoff()

    def maybe_handoff(self):
        """5. The real terminal window is shown over the launcher, out of the dark."""
        if not (self.active and self.dark and self.found is not None) or self.done:
            return
        self.done = True
        self.hand_over()
        self.root.after(int(150 * self.PACE), lambda: self.fade(0, 180 * self.PACE, then=self.finish))      # 6. return

    def timeout(self):
        self.fade(0, 180 * self.PACE, then=lambda: self.finish(
            "The session window didn't appear. It may still be starting.", "info"))

    def skip(self):
        """Any key or click: straight to the end. Exactly one session either way."""
        if not self.active:
            return
        if self.found is not None and self.hidden:
            self.hand_over()
        self.done = True
        self.finish()

    def finish(self, note=None, kind="quiet"):
        if not self.active:
            return
        self.active = False
        fine_timer(False)
        lock_foreground(False)
        for t in self.timers:
            self.root.after_cancel(t)
        self.timers = []
        if self._fade_job:
            self.root.after_cancel(self._fade_job)
            self._fade_job = None
        self.set_alpha(0)
        self.set_mode("ghost")
        self.cool()
        if self.found is None and self.uses_wt and self._poll_job is None:
            self._poll()  # skipped before the window appeared: keep watching to bring it forward
        self.app.say(note or self.note, kind, seconds=4)
        if self.found is None:
            self.app.lb.focus_set()

    def hand_over(self):
        """The session window to the front. Tk focus moves first: focusing afterwards would pull
        the keyboard back to the launcher."""
        self.app.lb.focus_set()
        bring_front(self.found)
        self.hidden = False


def asset(name):
    """A bundled file: next to the frozen app's data, else in the Reidcc folder
    (source runs from its python folder, one level down)."""
    for base in (getattr(sys, "_MEIPASS", None), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        if base and os.path.exists(os.path.join(base, name)):
            return os.path.join(base, name)
    return None


class App:
    def __init__(self, core, cwd=None):
        self.core = core
        self.loading = False
        self.current = None
        self.names = []
        self._msg_timer = None
        self._recheck = None
        self.not_ready = None  # the error text while the selected profile can't start
        state = core.load_state()
        recent = [d for d in state.get("recent_dirs", []) if os.path.isdir(d)]
        start = cwd if cwd and os.path.isdir(cwd) else (recent[0] if recent else os.path.expanduser("~"))

        self.root = root = tk.Tk()
        root.title("Reidcc")
        ico = asset("reidcc.ico")
        if ico:
            try:
                root.iconbitmap(default=ico)
            except tk.TclError:
                pass
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        h = min(880, sh - 140)  # leave room for the title bar and the taskbar
        # Place it ourselves: Windows' cascade can push the bottom bar under the taskbar.
        root.geometry("1000x%d+%d+%d" % (h, max(0, (sw - 1000) // 2), max(0, (sh - 48 - h - 40) // 2)))
        root.minsize(960, min(820, h))
        root.configure(bg=C["canvas"])
        theme_titlebar(root)
        self._fonts()
        self._style()

        self.folder = tk.StringVar(value=core.show_path(start))
        self._build_footer()
        self._build_msgbar()
        self._build_main()
        self._build_gate()
        self._keys()
        cfg = self.cfg()
        self.reload(select=cfg.get("default") if cfg else None)
        (self.lb if recent or cwd else self.b_pick).focus_set()

    # ------------------------------------------------------------ style ---
    def _fonts(self):
        fams = set(tkfont.families(self.root))
        ui = next((f for f in ("Inter", "Geist", "Segoe UI Variable Text", "Segoe UI", "Helvetica")
                   if f in fams), "TkDefaultFont")
        mono = next((f for f in ("Geist Mono", "JetBrains Mono", "Cascadia Mono", "Consolas", "Menlo")
                     if f in fams), "TkFixedFont")
        # Negative sizes are pixels, matching the design doc's px values.
        self.F = {"title": (ui, -20), "head": (ui, -16), "body": (ui, -14), "btn": (ui, -13),
                  "label": (ui, -13), "mono": (mono, -12), "tag": (mono, -11)}

    def _style(self):
        s = ttk.Style(self.root)
        s.theme_use("clam")
        s.configure(".", background=C["canvas"], foreground=C["text"], font=self.F["btn"],
                    bordercolor=C["line"], lightcolor=C["s1"], darkcolor=C["s1"],
                    troughcolor=C["s1"], focuscolor=C["line2"])
        s.configure("TCombobox", fieldbackground=C["s1"], background=C["s1"], foreground=C["text"],
                    arrowcolor=C["text3"], insertcolor=C["text"], bordercolor=C["line"],
                    lightcolor=C["s1"], darkcolor=C["s1"], padding=(8, 3), arrowsize=12)
        s.map("TCombobox",
              fieldbackground=[("readonly", C["s1"])], background=[("active", C["s2"])],
              foreground=[("disabled", C["text3"]), ("readonly", C["text"])], bordercolor=[("focus", C["line2"])],
              selectbackground=[("readonly", C["s1"]), ("!readonly", C["stone"])],
              selectforeground=[("readonly", C["text"]), ("!readonly", C["text"])],
              arrowcolor=[("disabled", C["line2"]), ("active", C["text"])])
        for w in ("TCheckbutton", "TRadiobutton"):
            s.configure(w, background=C["canvas"], foreground=C["text"], font=self.F["label"],
                        indicatorbackground=C["s1"], indicatorforeground=C["s1"],
                        upperbordercolor=C["line2"], lowerbordercolor=C["line2"], padding=(0, 2))
            # disabled first: a checked or picked box that can't be changed must look it (Astra's review)
            s.map(w, indicatorforeground=[("disabled", "selected", C["s1"]), ("selected", C["canvas"])],
                  indicatorbackground=[("disabled", "selected", C["line2"]), ("disabled", C["canvas"]),
                                       ("selected", C["text"]), ("active", C["s2"])],
                  upperbordercolor=[("disabled", C["line"])], lowerbordercolor=[("disabled", C["line"])],
                  foreground=[("disabled", C["text3"])], background=[("active", C["canvas"])])
        s.configure("Vertical.TScrollbar", background=C["s2"], troughcolor=C["s1"], bordercolor=C["line"],
                    arrowcolor=C["text3"], lightcolor=C["s2"], darkcolor=C["s2"], gripcount=0)
        s.map("Vertical.TScrollbar", background=[("active", C["stone"])])
        o = self.root.option_add
        o("*TCombobox*Listbox.background", C["s2"])
        o("*TCombobox*Listbox.foreground", C["text"])
        o("*TCombobox*Listbox.selectBackground", C["stone"])
        o("*TCombobox*Listbox.selectForeground", C["text"])
        o("*TCombobox*Listbox.font", self.F["mono"])
        o("*TCombobox*Listbox.borderWidth", 0)

    def label(self, parent, text="", fg="text", font="body", **kw):
        return tk.Label(parent, text=text, bg=C["canvas"], fg=C[fg], font=self.F[font], anchor="w", **kw)

    def button(self, parent, text, cmd, primary=False):
        bg, fg = (C["text"], C["canvas"]) if primary else (C["s1"], C["text"])
        hover = C["linework"] if primary else C["s2"]
        b = tk.Button(parent, text=text, command=cmd, font=self.F["btn"], bg=bg, fg=fg,
                      activebackground=hover, activeforeground=fg, relief="flat", bd=0,
                      padx=22 if primary else 12, pady=5, cursor="hand2", takefocus=1,
                      highlightthickness=1, highlightbackground=C["line"], highlightcolor=C["line2"])
        b.bind("<Enter>", lambda e: b.configure(bg=hover))
        b.bind("<Leave>", lambda e: b.configure(bg=bg))
        return b

    def entry(self, parent, var, width=None):
        return tk.Entry(parent, textvariable=var, bg=C["s1"], fg=C["text"], insertbackground=C["text"],
                        relief="flat", font=self.F["mono"], highlightthickness=1, width=width or 20,
                        highlightbackground=C["line"], highlightcolor=C["line2"],
                        selectbackground=C["stone"], selectforeground=C["text"], disabledbackground=C["s1"])

    def hairline(self, parent):
        return tk.Frame(parent, bg=C["line"], height=1)

    # ----------------------------------------------------------- layout ---
    def _build_footer(self):
        """Flow hint + status tag."""
        self.footer = tk.Frame(self.root, bg=C["canvas"])
        self.footer.pack(side="bottom", fill="x")
        self.hairline(self.footer).pack(fill="x")
        row = tk.Frame(self.footer, bg=C["canvas"])
        row.pack(fill="x", padx=PAD, pady=9)
        self.label(row, "folder → profile → open gate", "text3", "mono").pack(side="left")
        self.status_text = self.label(row, "", "text2", "mono")
        self.status_text.pack(side="right")
        self.status_dot = self.label(row, "●", "emerald", "mono")
        self.status_dot.pack(side="right", padx=(0, 6))

    def _build_msgbar(self):
        """One inline line for errors, confirmations and notes. Never a popup."""
        self.msgbar = tk.Frame(self.root, bg=C["canvas"], height=34)
        self.msgbar.pack(side="bottom", fill="x")
        self.msgbar.pack_propagate(False)
        self.msg_label = self.label(self.msgbar, "", "text", "body", justify="left")
        self.msg_label.pack(side="left", padx=(PAD, 12))
        self.msg_actions = tk.Frame(self.msgbar, bg=C["canvas"])
        self.msg_actions.pack(side="left")

    def _build_main(self):
        self.main = m = tk.Frame(self.root, bg=C["canvas"])
        m.pack(fill="both", expand=True)
        path = asset(os.path.join("assets", "banner.png"))
        if path:
            self.banner = tk.PhotoImage(file=path)
            tk.Label(m, image=self.banner, bg=C["canvas"], bd=0).pack(pady=(14, 0))
        col = tk.Frame(m, bg=C["canvas"])
        col.pack(fill="both", expand=True, padx=PAD)
        self.label(col, "Open a folder. Start coding.", "text", "title").pack(anchor="w", pady=(12, 2))
        self.label(col, "Pick a project and a profile. Your persona, memory and settings are already there.",
                   "text2", "body").pack(anchor="w")

        # 1. folder
        fr = tk.Frame(col, bg=C["canvas"])
        fr.pack(fill="x", pady=(16, 14))
        self.label(fr, "folder", "text3", "label", width=8).pack(side="left")
        self.e_folder = self.entry(fr, self.folder)
        self.e_folder.pack(side="left", fill="x", expand=True, ipady=5)
        self.e_folder.bind("<Return>", lambda e: (self.commit_folder(), "break")[1])
        self.b_pick = self.button(fr, "pick folder", self.pick_folder)
        self.b_pick.pack(side="left", padx=(8, 0))
        self.b_recent = self.button(fr, "open recent ▾", self.open_recent)
        self.b_recent.pack(side="left", padx=(8, 0))
        self.hairline(col).pack(fill="x")

        # 2. profile: list on the left, the selected profile's fields on the right
        panel = tk.Frame(col, bg=C["canvas"])
        panel.pack(fill="both", expand=True, pady=(12, 0))
        self._build_profile_list(panel)
        tk.Frame(panel, bg=C["line"], width=1).pack(side="left", fill="y", padx=18)
        self._build_fields(panel)

        # 3. go
        self.hairline(col).pack(fill="x", pady=(10, 0))
        act = tk.Frame(col, bg=C["canvas"])
        act.pack(fill="x", pady=(10, 4))
        self.button(act, "open memory", self.open_memory).pack(side="left")
        self.button(act, "open reid.json", lambda: self.core.open_file(self.core.CONFIG)).pack(side="left", padx=(8, 0))
        self.b_go = self.button(act, "open gate", self.go, primary=True)
        self.b_go.pack(side="right")
        self.b_resume = self.button(act, "resume", lambda: self.go(resume=True))
        self.b_resume.pack(side="right", padx=(0, 8))

    def _build_profile_list(self, panel):
        left = tk.Frame(panel, bg=C["canvas"])
        left.pack(side="left", fill="y")
        self.label(left, "profiles", "text3", "label").pack(anchor="w", pady=(0, 6))
        box = tk.Frame(left, bg=C["canvas"])
        box.pack(fill="both", expand=True)
        self.lb = tk.Listbox(box, width=24, height=8, bg=C["s1"], fg=C["text"], font=self.F["mono"],
                             selectbackground=C["stone"], selectforeground=C["text"], activestyle="none",
                             relief="flat", bd=0, highlightthickness=1, highlightbackground=C["line"],
                             highlightcolor=C["line2"], exportselection=False)
        sb = ttk.Scrollbar(box, orient="vertical", command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        self.lb.pack(side="left", fill="both", expand=True)
        sb.pack(side="left", fill="y")
        self.lb.bind("<<ListboxSelect>>", self.on_list)
        g = tk.Frame(left, bg=C["canvas"])
        g.pack(fill="x", pady=(8, 0))
        g.columnconfigure((0, 1), weight=1, uniform="a")
        for i, (text, cmd) in enumerate((("new profile", self.new), ("duplicate", self.dup),
                                         ("delete", self.delete), ("make default", self.set_default))):
            self.button(g, text, cmd).grid(row=i // 2, column=i % 2, sticky="ew",
                                           padx=(0, 6) if i % 2 == 0 else 0, pady=(0, 6))

    def _build_fields(self, panel):
        right = tk.Frame(panel, bg=C["canvas"])
        right.pack(side="left", fill="both", expand=True)
        head = tk.Frame(right, bg=C["canvas"])
        head.pack(fill="x", pady=(0, 6))
        self.p_title = self.label(head, "", "text", "head")
        self.p_title.pack(side="left")
        self.tags = self.label(head, "", "text2", "tag")
        self.tags.pack(side="left", padx=(12, 0))

        form = tk.Frame(right, bg=C["canvas"])
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.v = {k: tk.StringVar() for k in ("name", "engine", "model", "auth", "persona", "mode", "proxy",
                                               "tools", "mcp", "args")}
        self.b = {k: tk.BooleanVar() for k in ("memory", "chrome", "connectors", "safe")}
        r = 0

        def row(text, widget, extra=(), span=1):
            nonlocal r
            self.label(form, text, "text3", "label").grid(row=r, column=0, sticky="w", pady=2, padx=(0, 14))
            widget.grid(row=r, column=1, columnspan=span, sticky="ew", pady=2,
                        ipady=2 if isinstance(widget, tk.Entry) else 0)
            for i, w in enumerate(extra):
                w.grid(row=r, column=2 + i, padx=(6, 0), pady=2)
            r += 1

        e_name = self.entry(form, self.v["name"])
        e_name.bind("<Return>", lambda ev: self.rename())
        e_name.bind("<FocusOut>", lambda ev: self.rename())
        # engine: on the name row, right above model (SPEC-codex-opencode.md), so the form keeps its height
        ef = tk.Frame(form, bg=C["canvas"])
        self.label(ef, "engine", "text3", "label").pack(side="left", padx=(0, 8))
        self.cb_engine = ttk.Combobox(ef, textvariable=self.v["engine"], state="readonly", font=self.F["mono"],
                                      values=list(self.core.ENGINES), width=8)
        self.cb_engine.pack(side="left")
        row("name", e_name, (ef,))
        ef.grid_configure(columnspan=2, sticky="w")
        self.cb_model = ttk.Combobox(form, textvariable=self.v["model"], font=self.F["mono"])
        row("model", self.cb_model)
        self.cb_auth = ttk.Combobox(form, textvariable=self.v["auth"], state="readonly", font=self.F["mono"])
        row("sign-in", self.cb_auth)
        self.cb_persona = ttk.Combobox(form, textvariable=self.v["persona"], state="readonly", font=self.F["mono"])
        self.b_browse = self.button(form, "browse", self.browse_persona)
        self.b_open_persona = self.button(form, "open persona", self.open_persona)
        row("persona", self.cb_persona, (self.b_browse, self.b_open_persona))
        mf = tk.Frame(form, bg=C["canvas"])
        self.mode_radios = []
        for mode, txt in MODES:
            rb = ttk.Radiobutton(mf, text=txt, value=mode, variable=self.v["mode"])
            rb.pack(side="left", padx=(0, 16))
            self.mode_radios.append(rb)
        row("persona mode", mf, span=3)
        self.cb_proxy = ttk.Combobox(form, textvariable=self.v["proxy"], state="readonly", font=self.F["mono"],
                                     values=["off"] + self.core.PROXY_CHOICES)
        row("proxy", self.cb_proxy)
        self.cb_tools = ttk.Combobox(form, textvariable=self.v["tools"], font=self.F["mono"], values=TOOLS_CHOICES)
        row("tools", self.cb_tools)
        self.cb_mcp = ttk.Combobox(form, textvariable=self.v["mcp"], state="readonly", font=self.F["mono"])
        row("mcp", self.cb_mcp)
        sf = tk.Frame(form, bg=C["canvas"])
        self.checks = {}
        for k, txt in (("memory", "memory"), ("chrome", "chrome"), ("connectors", "connectors"),
                       ("safe", "safe mode")):
            self.checks[k] = ttk.Checkbutton(sf, text=txt, variable=self.b[k], command=self.apply)
            self.checks[k].pack(side="left", padx=(0, 16))
        row("switches", sf, span=3)
        row("extra args", self.entry(form, self.v["args"]))

        cmdf = tk.Frame(right, bg=C["canvas"])
        cmdf.pack(fill="x", pady=(8, 0))
        self.label(cmdf, "command", "text3", "label").pack(anchor="w")
        self.preview = self.label(cmdf, "", "text3", "tag", justify="left")
        self.preview.pack(anchor="w", fill="x")
        self.root.bind("<Configure>", self._wrap, add="+")

        for k in ("engine", "model", "auth", "persona", "mode", "proxy", "tools", "mcp", "args"):
            self.v[k].trace_add("write", lambda *a: self.apply())

    def _wrap(self, e=None):
        w = self.root.winfo_width()
        self.preview.configure(wraplength=max(300, w - 2 * PAD - 300))
        self.msg_label.configure(wraplength=max(300, w - 2 * PAD - 260))

    def _retry(self):
        self._recheck = None
        cfg = self.cfg()
        if cfg and self.current in cfg["profiles"]:
            self.refresh(cfg)

    def _keys(self):
        r = self.root

        def key(fn):  # while the gate plays, every key skips it instead
            return lambda e: self.gate.skip() if self.gate.active else fn(e)
        r.bind("<Return>", key(self.on_return))
        r.bind("<Escape>", key(lambda e: self.clear_msg()))
        r.bind("<Control-Return>", key(lambda e: self.go()))
        r.bind("<Control-o>", key(lambda e: self.pick_folder()))
        r.bind("<Control-r>", key(lambda e: self.go(resume=True)))

    # ------------------------------------------------------------ gate ---
    def _build_gate(self):
        """The gate overlay (SPEC-gate.md): a ghost on hover of open gate / resume, the opening on press."""
        self.gate = Gate(self)
        for key, b in (("go", self.b_go), ("resume", self.b_resume)):
            b.bind("<Enter>", lambda e, k=key: self.gate.hover(k + ":ptr", True), add="+")
            b.bind("<Leave>", lambda e, k=key: self.gate.hover(k + ":ptr", False), add="+")
            b.bind("<FocusIn>", lambda e, k=key: self.gate.hover(k + ":focus", True), add="+")
            b.bind("<FocusOut>", lambda e, k=key: self.gate.hover(k + ":focus", False), add="+")
        self.root.bind("<Unmap>", lambda e: self.gate.calm() if e.widget is self.root else None, add="+")
        self.root.bind("<Key>", lambda e: self.gate.skip())  # only reached while the gate has focus

    def on_return(self, e):
        """Enter: a focused button presses itself; on the profile list (or nothing) it means go."""
        w = self.root.focus_get()
        if isinstance(w, tk.Button):
            w.invoke()
        elif w is None or w in (self.lb, self.root):
            self.go()

    # -------------------------------------------------------- messages ---
    def say(self, text, kind="info", actions=(), seconds=None):
        """kind: info (bone), error (oxide), quiet (muted). actions: [(label, callback)]."""
        if self._msg_timer:
            self.root.after_cancel(self._msg_timer)
            self._msg_timer = None
        self.msg_label.configure(text=text, fg={"error": C["oxide"], "quiet": C["text3"]}.get(kind, C["text"]))
        for w in self.msg_actions.winfo_children():
            w.destroy()
        btns = []
        for text_, cb in actions:
            b = self.button(self.msg_actions, text_, lambda cb=cb: (self.clear_msg(), cb()))
            b.pack(side="left", padx=(0, 8))
            btns.append(b)
        if seconds:
            self._msg_timer = self.root.after(int(seconds * 1000), self.clear_msg)
        return btns

    def clear_msg(self):
        if self.msg_label.cget("text") or self.msg_actions.winfo_children():
            self.say("")

    # ------------------------------------------------------------- data ---
    def cfg(self):
        try:
            return self.core.load_config()
        except self.core.ReidError as e:
            self.say(str(e), "error", [("open reid.json", lambda: self.core.open_file(self.core.CONFIG))])
            return None

    def save(self, cfg):
        self.core.save_json(self.core.CONFIG, cfg)

    def reload(self, select=None):
        cfg = self.cfg()
        if not cfg or not cfg["profiles"]:
            return
        self.names = list(cfg["profiles"])
        self.lb.delete(0, "end")
        for n in self.names:
            self.lb.insert("end", " " + n + ("  ●" if n == cfg.get("default") else ""))  # Listbox has no padx
        target = select if select in self.names else (self.current if self.current in self.names else self.names[0])
        self.load_profile(cfg, target)

    def on_list(self, e=None):
        sel = self.lb.curselection()
        if sel and self.names[sel[0]] != self.current:
            self.select(self.names[sel[0]])

    def select(self, name):
        self.rename()  # keep a name typed but not yet confirmed
        cfg = self.cfg()
        if cfg and name in cfg["profiles"]:
            self.load_profile(cfg, name)

    def load_profile(self, cfg, name):
        core = self.core
        p = cfg["profiles"][name]
        self.current = name
        i = self.names.index(name)
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(i)
        self.lb.see(i)
        self.loading = True
        try:
            engine = str(p.get("engine") or "claude")
            codex = core.is_codex(p)
            # each engine lists its own models: Claude's names, or the ones other Codex profiles use
            same = {q.get("model") for q in cfg["profiles"].values()
                    if q.get("model") and str(q.get("engine") or "claude") == engine}
            used = sorted(same - set(core.BASE_MODELS))
            self.cb_model["values"] = (core.BASE_MODELS if engine == "claude" else []) + used
            self.v["engine"].set(engine)
            # each engine lists its own sign-in: your login, or its kind of file
            self.cb_auth["values"] = [self._login_choice(codex)] + core.signin_files(codex)
            if codex and not p.get("settings") and core.codex_login_cached() is None:
                self._check_login()
            personas = (sorted(glob.glob(os.path.join(core.HOME, "personas", "*.md")))
                        + sorted(glob.glob(os.path.join(core.PROXY_DIR, "*-system.md")))
                        + sorted(glob.glob(os.path.join(core.HOME, "mds", "*.md"))))
            pvals = [NO_PERSONA] + [core.relpath(f) for f in personas]
            if p.get("persona") and p["persona"] not in pvals:
                pvals.append(p["persona"])
            self.cb_persona["values"] = pvals
            mcps = sorted(core.relpath(f) for f in glob.glob(os.path.join(core.PROXY_DIR, "*mcp*.json")))
            mvals = [MCP_DEFAULT, "none"] + mcps
            if p.get("mcp") and p["mcp"] not in mvals:
                mvals.append(p["mcp"])
            self.cb_mcp["values"] = mvals

            self.v["name"].set(name)
            self.v["model"].set(p.get("model", ""))
            self.v["auth"].set(p.get("settings") or self._login_choice(codex))
            self.v["persona"].set(p.get("persona") or NO_PERSONA)
            self.v["mode"].set(p.get("mode") or "append")
            self.v["proxy"].set("+".join(core.proxy_list(p)) or "off")
            self.v["tools"].set(self._tools_label(p))
            self.v["mcp"].set(p.get("mcp") or MCP_DEFAULT)
            self.v["args"].set(core.args_text(p.get("args")))
            self.b["memory"].set(bool(p.get("memory")))
            self.b["safe"].set(bool(p.get("safe")))
            self.b["chrome"].set(not p.get("no_chrome"))
            self.b["connectors"].set(not p.get("no_connectors"))
        finally:
            self.loading = False
        self.refresh(cfg)

    def _login_choice(self, codex):
        """The first sign-in choice: `subscription` for Claude, `codex login · <status>` for Codex."""
        return self.core.codex_login_label() if codex else SUB

    def _check_login(self):
        """`codex login status` takes about a second: ask off the UI thread, then update the sign-in row."""
        if getattr(self, "_login_busy", False):
            return
        self._login_busy = True

        def work():
            self.core.codex_login()
            self.root.after(0, self._login_done)
        threading.Thread(target=work, daemon=True).start()

    def _login_done(self):
        self._login_busy = False
        cfg = self.cfg()
        p = cfg["profiles"].get(self.current) if cfg else None
        if not p or not self.core.is_codex(p):
            return
        self.loading = True
        try:
            self.cb_auth["values"] = [self._login_choice(True)] + self.core.signin_files(True)
            if not p.get("settings"):
                self.v["auth"].set(self._login_choice(True))
        finally:
            self.loading = False
        self.refresh(cfg)

    def _tools_label(self, p):
        if "tools" not in p:
            return "all"
        t = p.get("tools") or []
        core = self.core
        for label, key in (("none", []), ("core", core.CORE_TOOLS),
                           ("core + web", core.CORE_TOOLS + core.WEB_TOOLS), ("web only", core.WEB_TOOLS)):
            if t == key:
                return label
        return ",".join(t)

    def _tools_value(self, label):
        core = self.core
        label = label.strip()
        table = {"all": None, "": None, "none": [], "core": core.CORE_TOOLS,
                 "core + web": core.CORE_TOOLS + core.WEB_TOOLS, "web only": core.WEB_TOOLS}
        if label in table:
            return None if table[label] is None else list(table[label])
        return [t.strip() for t in label.split(",") if t.strip()]

    def apply(self):
        """Write the fields into the selected profile and save."""
        if self.loading or not self.current:
            return
        cfg = self.cfg()
        p = cfg["profiles"].get(self.current) if cfg else None
        if p is None:
            return

        def put(key, val):
            if val in (None, "", False) or (isinstance(val, list) and not val and key != "tools"):
                p.pop(key, None)
            else:
                p[key] = val

        engine = self.v["engine"].get() or "claude"
        if engine != str(p.get("engine") or "claude"):
            # a model belongs to one engine: start from the new engine's default
            self.loading = True
            try:
                self.v["model"].set("")
            finally:
                self.loading = False
            put("engine", None if engine == "claude" else engine)
            put("model", None)
            put("settings", None)  # sign-in files are per engine too
            self.save(cfg)
            self.load_profile(cfg, self.current)  # new model and sign-in lists for the new engine
            self.say("Engine is now %s. Model and sign-in reset to its defaults." % engine, "quiet", seconds=3)
            return
        mode_changed = (p.get("mode") or "append") != self.v["mode"].get()
        put("model", self.v["model"].get().strip())
        auth = self.v["auth"].get()
        put("settings", None if auth == SUB or auth.startswith(self.core.CODEX_LOGIN) else auth)
        persona = self.v["persona"].get()
        put("persona", None if persona == NO_PERSONA else persona)
        put("mode", self.v["mode"].get() if p.get("persona") else None)
        proxy = self.v["proxy"].get()
        put("proxy", None if proxy == "off" else proxy)
        tools = self._tools_value(self.v["tools"].get())
        if tools is None:
            p.pop("tools", None)
        else:
            p["tools"] = tools
        mcp = self.v["mcp"].get()
        put("mcp", None if mcp == MCP_DEFAULT else mcp)
        if self.v["args"].get() != self.core.args_text(p.get("args")):  # untouched args stay exactly as saved
            put("args", self.core.args_parse(self.v["args"].get()))
        put("memory", self.b["memory"].get())
        put("safe", self.b["safe"].get())
        put("no_chrome", not self.b["chrome"].get())
        put("no_connectors", not self.b["connectors"].get())
        self.save(cfg)
        self.refresh(cfg)
        if mode_changed and p.get("mode") == "replace" and self.core.is_codex(p):
            self.say(self.core.CODEX_REPLACE_HINT, "quiet", seconds=4)
        else:
            self.say("Saved.", "quiet", seconds=1.5)

    def refresh(self, cfg):
        """Header, tags, status tag and command preview for the selected profile."""
        core = self.core
        name = self.current
        p = cfg["profiles"][name]
        persona = core.persona_name(p) if p.get("persona") else ""
        tags = (["PERSONA · " + persona.upper()] if persona else []) + (["MEMORY · ON"] if p.get("memory") else [])
        codex = core.is_codex(p)
        if codex:  # the reason the greyed-out fields are greyed out
            tags = [core.CODEX_TAG] + tags
        self.p_title.configure(text=name)
        self.tags.configure(text=" · ".join(tags))
        tool = "Codex" if codex else "Claude Code"
        for rb, (mode, _txt) in zip(self.mode_radios, MODES):
            rb.configure(text=("replace %s's prompt" if mode == "replace" else "add to %s's prompt") % tool)
            rb.state(["!disabled"] if persona else ["disabled"])
        self._engine_fields(p, codex)
        error, text, have = core.profile_check(cfg, name, self.real_folder())
        if error:
            self.status_dot.configure(fg=C["oxide"])
            self.status_text.configure(text="not ready")
            self.preview.configure(text=error, fg=C["oxide"])
            # Look again on our own: e.g. Claude Code mid-update, or reid.json fixed in an editor.
            if self._recheck:
                self.root.after_cancel(self._recheck)
            self._recheck = self.root.after(3000, self._retry)
            self.not_ready = error
            return
        if self.not_ready:  # recovered: drop the stale error if it's still showing
            if self.msg_label.cget("text") == self.not_ready:
                self.clear_msg()
            self.not_ready = None
        self.status_dot.configure(fg=C["emerald"])
        self.status_text.configure(text="ready" + (" · " + " + ".join(have) if have else ""))
        self.preview.configure(text=text, fg=C["text3"])

    def _engine_fields(self, p, codex):
        """Claude-only fields stay on screen for a Codex profile (nothing hidden), disabled while they're
        off. One that's still on stays live so it can be turned off; the preview says it blocks the gate."""
        live = {  # widget -> is its Claude-only setting on? (sign-in, persona, memory work for both)
            self.cb_proxy: bool(self.core.proxy_list(p)), self.cb_tools: "tools" in p,
            self.cb_mcp: bool(p.get("mcp")), self.checks["safe"]: bool(p.get("safe")),
            self.checks["chrome"]: bool(p.get("no_chrome")), self.checks["connectors"]: bool(p.get("no_connectors")),
        }
        for w, on in live.items():
            if not codex:
                w.state(["!disabled"])
                if isinstance(w, ttk.Combobox) and w is not self.cb_tools:
                    w.state(["readonly"])
            else:
                w.state(["!disabled"] if on else ["disabled"])
        self.b_resume.configure(fg=C["text3"] if codex else C["text"])

    # ---------------------------------------------------------- folder ---
    def real_folder(self):
        return os.path.abspath(os.path.expanduser(self.folder.get().strip().strip('"')))

    def set_folder(self, path):
        self.folder.set(self.core.show_path(path))
        self.lb.focus_set()  # folder -> profile, keyboard continuity

    def commit_folder(self):
        if os.path.isdir(self.real_folder()):
            self.set_folder(self.real_folder())
            self.clear_msg()
        else:
            self.say("Can't find that folder. It may have moved.", "error", [("pick again", self.pick_folder)])

    def pick_folder(self):
        start = self.real_folder() if os.path.isdir(self.real_folder()) else os.path.expanduser("~")
        d = filedialog.askdirectory(title="pick folder", initialdir=start)
        if d:
            self.set_folder(os.path.normpath(d))
            self.clear_msg()

    def open_recent(self):
        dirs = [d for d in self.core.load_state().get("recent_dirs", []) if os.path.isdir(d)]
        if not dirs:
            self.say("No projects yet. Pick a folder to start.", "info", [("pick folder", self.pick_folder)])
            return
        menu = tk.Menu(self.root, tearoff=0, bg=C["s2"], fg=C["text"], activebackground=C["stone"],
                       activeforeground=C["text"], font=self.F["mono"], bd=0, relief="flat")
        menu.add_command(label="recent", state="disabled")
        for d in dirs:
            menu.add_command(label=self.core.show_path(d), command=lambda d=d: self.set_folder(d))
        b = self.b_recent
        menu.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

    # ---------------------------------------------------------- actions ---
    def rename(self):
        new = self.v["name"].get().strip()
        if self.loading or not self.current or not new or new == self.current:
            return
        cfg = self.cfg()
        if not cfg:
            return
        if new in cfg["profiles"]:
            self.say("A profile named %s already exists." % new, "error")
            self.v["name"].set(self.current)
            return
        cfg["profiles"] = {(new if k == self.current else k): v for k, v in cfg["profiles"].items()}
        if cfg.get("default") == self.current:
            cfg["default"] = new
        self.save(cfg)
        self.current = new
        self.reload(select=new)

    def _unique(self, cfg, base):
        n, i = base, 2
        while n in cfg["profiles"]:
            n, i = "%s-%d" % (base, i), i + 1
        return n

    def new(self):
        cfg = self.cfg()
        if cfg:
            n = self._unique(cfg, "new")
            cfg["profiles"][n] = {"model": "opus"}
            self.save(cfg)
            self.reload(select=n)

    def dup(self):
        cfg = self.cfg()
        if cfg:
            n = self._unique(cfg, self.current + "-copy")
            cfg["profiles"][n] = json.loads(json.dumps(cfg["profiles"][self.current]))
            self.save(cfg)
            self.reload(select=n)

    def delete(self):
        cfg = self.cfg()
        if not cfg:
            return
        if len(cfg["profiles"]) == 1:
            self.say("Can't delete the last profile.", "error")
            return
        name = self.current

        def really():
            c = self.cfg()
            if not c or name not in c["profiles"]:
                return
            del c["profiles"][name]
            if c.get("default") not in c["profiles"]:
                c["default"] = next(iter(c["profiles"]))
            self.save(c)
            self.current = None
            self.reload(select=c["default"])
            self.say("Deleted %s." % name, "quiet", seconds=3)

        btns = self.say("Delete profile %s?" % name, "info", [("delete", really), ("keep", lambda: None)])
        btns[1].focus_set()  # the safe choice has focus

    def set_default(self):
        cfg = self.cfg()
        if cfg:
            cfg["default"] = self.current
            self.save(cfg)
            self.reload(select=self.current)
            self.say("Default is now %s." % self.current, "quiet", seconds=3)

    def browse_persona(self):
        f = filedialog.askopenfilename(title="persona", initialdir=os.path.join(self.core.HOME, "personas"),
                                       filetypes=[("Markdown", "*.md"), ("Text", "*.txt"), ("All", "*.*")])
        if f:
            rel = self.core.relpath(f)
            vals = list(self.cb_persona["values"])
            if rel not in vals:
                self.cb_persona["values"] = vals + [rel]
            self.v["persona"].set(rel)

    def open_persona(self):
        p = self.v["persona"].get()
        if p and p != NO_PERSONA:
            self.core.open_file(self.core.resolve(p))
        else:
            self.say("This profile has no persona.", "quiet", seconds=3)

    def open_memory(self):
        cfg = self.cfg()
        if cfg:
            self.core.open_file(self.core.memory_path(cfg, cfg["profiles"].get(self.current)))

    def go(self, resume=False):
        core = self.core
        cfg = self.cfg()
        if not cfg or not self.current or self.gate.active:  # one session per press
            return
        name = self.current
        cwd = self.real_folder()
        prof = cfg["profiles"][name]
        engine = str(prof.get("engine") or "claude")
        if resume and engine != "claude":
            self.say("Resume is for Claude profiles for now. open gate starts a new Codex session.", "info", seconds=5)
            return
        if core.is_codex(prof) and not prof.get("settings") and core.codex_login_cached() == "not signed in":
            core.codex_login(refresh=True)  # signed in from a terminal since? (about a second)
            self._login_done()
        if resume:
            last = core.load_state().get("last")
            if not last:
                self.say("Nothing to resume yet.", "info", seconds=4)
                return
            cwd = last.get("cwd") or cwd
        if not os.path.isdir(cwd):
            self.say("Can't find that folder. It may have moved.", "error", [("pick again", self.pick_folder)])
            return
        try:  # catch config problems here instead of in a terminal that closes
            _a, _e, temps = core.build(cfg, name, [], cwd, prepare=False)  # the session prepares its own
            for t in temps:
                os.remove(t)
        except core.ReidError as e:
            self.say(str(e), "error", [("try again", lambda: self.go(resume))])
            return
        # reidcc.com when packaged, python reid.py from source
        cmd = core.cli_command() + (["--resume", name] if resume else [name])

        def launch(plan):
            wt = shutil.which("wt")
            if wt:
                where = ["--pos", plan["pos"], "--size", plan["size"]] if plan else []
                # wt reads a bare ; as "next command", even inside an argument; \; is a plain ;
                tab = [a.replace(";", "\\;") for a in ["--title", "Reidcc · " + name, "-d", cwd] + cmd]
                subprocess.Popen([wt, "-w", "new"] + where + ["new-tab"] + tab)
                return "Session open in Windows Terminal.", True
            if sys.platform == "win32":
                subprocess.Popen(cmd, cwd=cwd, creationflags=getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10))
            else:
                term = shutil.which("x-terminal-emulator") or shutil.which("gnome-terminal")
                subprocess.Popen([term, "--"] + cmd if term else cmd, cwd=cwd)
            return "Session open in a new window.", False

        self.gate.open(launch, engine + " · " + name, core.show_path(cwd))

def run(core, cwd=None):
    App(core, cwd).root.mainloop()
    return 0
