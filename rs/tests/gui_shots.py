"""Side-by-side screenshots of the Python GUI (python\\reid_gui.py) and the Rust GUI (rs\\app, Reidcc.exe).

Both run at once against one temp Reidcc folder (guihome.make_home), so every path and word on screen
is the same. For each state it saves <state>_py.png, <state>_rs.png and <state>.png (the two side by
side, Python left) under rs\\tests\\gui_shots\\. Client areas only, via PrintWindow.

The Python gate is its own layered window over the launcher (window alpha + a colour key in ghost
mode); its shot is that window's picture composited over the launcher's the way Windows does.

    python rs\\tests\\gui_shots.py            (needs rs\\target\\release\\Reidcc.exe built)
"""
import os, sys, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guihome
from PIL import Image, ImageChops, ImageDraw

OUT = os.path.join(HERE, "gui_shots")
FRAMES = (124, 371, 825)  # ms after the press: mid rise, mid ignite, mid open (design 90/270/600 x PACE)


def pump(app, s=0.3):
    end = time.time() + s
    while time.time() < end:
        app.root.update()
        time.sleep(0.01)


def side(a, b, path):
    pad, head = 12, 26
    img = Image.new("RGB", (a.width + b.width + pad * 3, max(a.height, b.height) + head + pad), (40, 40, 40))
    d = ImageDraw.Draw(img)
    d.text((pad, 7), "Python (reid_gui.py)", fill=(230, 230, 230))
    d.text((a.width + pad * 2, 7), "Rust (Reidcc.exe)", fill=(230, 230, 230))
    img.paste(a, (pad, head))
    img.paste(b, (a.width + pad * 2, head))
    img.save(path)


def composite(base, over, alpha, key=None):
    """A layered window (alpha byte + optional colour key) over the window below it."""
    a = int(min(alpha, 0.999) * 255) / 255.0
    out = Image.blend(base, over.resize(base.size), a)
    if key:  # key-coloured pixels are holes: the launcher shows through unchanged
        k = Image.new("RGB", over.size, key)
        d = ImageChops.difference(over.convert("RGB"), k).convert("L")
        out.paste(base, (0, 0), d.point(lambda v: 255 if v == 0 else 0))
    return out


class Py:
    def __init__(self, root):
        self.reid, gui = guihome.python_core(root)
        self.gui = gui
        self.app = gui.App(self.reid, cwd=os.path.join(root, "work"))
        pump(self.app, 1.5)  # the gate overlay maps after 250 ms; resident frames load one per tick
        self.app.root.focus_force()  # an active window, so Tk draws its focus rings
        self.hwnd = int(self.app.root.wm_frame(), 16)

    def select(self, name):
        a = self.app
        i = a.names.index(name)
        a.lb.selection_clear(0, "end")
        a.lb.selection_set(i)
        a.lb.see(i)
        a.on_list()
        pump(a)
        a.lb.focus_set()
        pump(a)

    def login(self, status):
        self.reid._CODEX_LOGIN[os.environ.get("CODEX_HOME", "")] = status
        self.app._login_done()
        pump(self.app)

    def shot(self):
        pump(self.app, 0.2)
        return guihome.client_shot(self.hwnd)

    def gate_shot(self, alpha, key=None):
        base = self.shot()
        g = self.app.gate
        g.win.update()
        over = guihome.client_shot(int(g.win.wm_frame(), 16))
        return composite(base, over, alpha, key)

    def ghost(self):
        g = self.app.gate
        g.set_mode("ghost")
        g.place()
        g.set_alpha(g.GHOST)
        return self.gate_shot(g.GHOST, g.meta["key"])

    def gate_at(self, ms):
        """The opening as it stands ms after the press (hovered first, as the Rust hook assumes)."""
        g = self.app.gate
        steps = g.meta["steps"]
        for n in g.resident() + g.frames(steps[-1][0]):
            g.image(n)
        g.set_mode("gate")
        g.place()
        t = ms / g.PACE
        frame = g.frames(steps[0][0])[0]
        for name, n, start, dur in steps:
            for i in range(n):
                if start + dur * i / n <= t:
                    frame = g.frames(name)[i]
        g.canvas.itemconfigure(g.item, image=g.image(frame))
        end = steps[-1][2] + steps[-1][3]
        a = g.GHOST + (g.SOLID - g.GHOST) * self.gui.ease(min(1.0, ms / (steps[0][3] * g.PACE)))
        g.set_alpha(a)
        g.set_tag("REIDCC · READY" if t >= end else "REIDCC · OPENING", self.gui.C["text2"] if t >= end else self.gui.C["bronze"])
        return a

    def dark(self, title, sub):
        g = self.app.gate
        steps = g.meta["steps"]
        a = self.gate_at((steps[2][2] + steps[2][3]) * g.PACE)
        g.set_tag("REIDCC · OPENING", self.gui.C["bronze"])
        g.canvas.itemconfigure(g.head, text=title + " · opening…")
        g.canvas.itemconfigure(g.subhead, text=sub)
        return a

    def gate_off(self):
        g = self.app.gate
        g.set_alpha(0)
        g.set_mode("ghost")
        pump(self.app, 0.1)


def main():
    os.makedirs(OUT, exist_ok=True)
    root, home = guihome.make_home()
    # a profile that can't start: its persona file is missing
    cfgp = os.path.join(home, "reid.json")
    cfg = json.load(open(cfgp, encoding="utf-8"))
    cfg["profiles"]["broken"] = {"model": "opus", "persona": "personas/missing.md"}
    with open(cfgp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    rs = None
    saved = []
    try:
        rs = guihome.Tauri(root)
        py = Py(root)
        time.sleep(1.0)

        def rs_select(name):
            names = rs.js("__reid.state().names")
            rs.js("__reid.selectRow(%d)" % names.index(name))
            time.sleep(0.4)
            rs.js("__reid.focusList()")
            time.sleep(0.2)

        def save(state, a, b):
            a.save(os.path.join(OUT, state + "_py.png"))
            b.save(os.path.join(OUT, state + "_rs.png"))
            side(a, b, os.path.join(OUT, state + ".png"))
            d = ImageChops.difference(a.convert("RGB"), b.convert("RGB")).convert("L").point(lambda v: 255 if v > 40 else 0)
            n = sum(d.histogram()[255:])
            e = "" if state.startswith(("opening", "dark")) else ", %d emerald" % guihome.emeralds(b)  # 1.3: one per screen
            saved.append("%s (%d px differ by >40%s)" % (state, n, e))

        def both(state, name, login=None):
            py.select(name)
            rs_select(name)
            if login:
                py.login(login)
                rs.js("__reid.login(%s)" % json.dumps(login))
                time.sleep(0.4)
            save(state, py.shot(), guihome.client_shot(rs.hwnd))

        both("claude", "claude")
        both("codex_signed_in", "new", "ChatGPT")
        both("codex_not_signed_in", "new", "not signed in")
        both("not_ready", "broken")

        py.select("mini")
        rs_select("mini")
        py.app.delete()
        rs.js("__reid.button('delete')")
        time.sleep(0.4)
        save("message_actions", py.shot(), guihome.client_shot(rs.hwnd))
        py.app.clear_msg()
        rs.js("__reid.button('keep')")
        py.select("claude")
        rs_select("claude")

        a = py.ghost()
        rs.js("__reid.ghost()")
        time.sleep(0.5)
        save("ghost", a, guihome.client_shot(rs.hwnd))
        py.gate_off()
        rs.js("__reid.gateOff()")

        for i, ms in enumerate(FRAMES, 1):
            alpha = py.gate_at(ms)
            rs.js("__reid.gateAt(%d)" % ms)
            time.sleep(0.6)
            save("opening_%d" % i, py.gate_shot(alpha), guihome.client_shot(rs.hwnd))
        py.gate_off()
        rs.js("__reid.gateOff()")

        title, sub = "claude · claude", py.reid.show_path(os.path.join(root, "work"))
        alpha = py.dark(title, sub)
        rs.js("__reid.dark(%s, %s)" % (json.dumps(title), json.dumps(sub)))
        time.sleep(0.8)
        save("dark_handoff", py.gate_shot(alpha), guihome.client_shot(rs.hwnd))
        py.gate_off()
        rs.js("__reid.gateOff()")
        py.app.root.destroy()
    finally:
        if rs:
            rs.close()
        guihome.remove_home(root)
    print("saved to", OUT)
    for s_ in saved:
        print(" ", s_)


if __name__ == "__main__":
    main()
