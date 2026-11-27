"""The website's shots (vision\\Spec\\SPEC-website-0.2.5.md Part 4), taken from the real app on a clean demo setup.

A temp Reidcc home with demo profiles (main, review, quick, cx), a demo memory file and no personas but
plain.md; the demo project is E:\\projects\\kiln (made here, emptied again after). Nothing from the real
reid.json, memory, personas or sessions is on screen. One real Claude chat turn and one real Claude
session (sonnet) run, and their session files are deleted afterwards. Writes site\\public\\shots\\*.webp
only (never rs\\tests\\*_shots). Kills only processes it started.

    python rs\\tests\\site_shots.py        (needs rs\\target\\release built with REIDCC_DEV=1)
"""
import os, sys, json, glob, time, shutil, ctypes, tempfile, subprocess
import psutil
from ctypes import wintypes as W
from PIL import Image, ImageGrab

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guihome
from session_flow import find, frame, ours, Page, session_target, screen, press, PORT
from sizes_flow import key, resize_inner, visible, pod_hwnd
from chat_flow import Chat, chat_target

u32 = ctypes.windll.user32
OUT = os.path.join(guihome.REIDCC, "site", "public", "shots")
KILN = r"E:\projects\kiln"
DEMO_ROOT = os.path.join(tempfile.gettempdir(), "reidcc-demo")
SESSION_SIZE = (1000, 514)  # the terminal alone, CSS px; RC adds the launcher's column
CLAUDE_PROJECTS = os.path.join(os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude"), "projects")
CANVAS = "#040404"  # the site's background, behind the see-through pod
CHAT_SIZE = (1120, 720)  # CSS px
THUMB = 0.5  # the four sizes, all at one scale so they compare

KILN_FILES = {
    "README.md": "# kiln\n\nA tiny static site generator: Markdown in `pages/`, HTML out in `site/`.\n",
    "build.py": (
        '"""kiln: turn pages/*.md into site/*.html with one template."""\n'
        "import pathlib\n\n"
        'TEMPLATE = pathlib.Path("template.html").read_text()\n\n\n'
        "def render(md):\n"
        "    out = []\n"
        "    for line in md.splitlines():\n"
        '        if line.startswith("# "):\n'
        '            out.append(f"<h1>{line[2:]}</h1>")\n'
        "        elif line.strip():\n"
        '            out.append(f"<p>{line}</p>")\n'
        '    return "\\n".join(out)\n\n\n'
        "def main():\n"
        '    site = pathlib.Path("site")\n'
        "    site.mkdir(exist_ok=True)\n"
        '    for page in sorted(pathlib.Path("pages").glob("*.md")):\n'
        '        html = TEMPLATE.replace("{{body}}", render(page.read_text()))\n'
        '        (site / f"{page.stem}.html").write_text(html)\n\n\n'
        'if __name__ == "__main__":\n'
        "    main()\n"),
    "template.html": "<!doctype html>\n<title>kiln</title>\n<main>{{body}}</main>\n",
    "pages/index.md": "# kiln\n\nNotes from the workshop.\n",
    "pages/glazes.md": "# Glazes\n\nCeladon at cone 10.\n",
}
MEMORY = ("# Long-term memory\n\n## Pinned facts\n- kiln is a static site generator in Python, no dependencies.\n\n"
          "## Journal\n- 2026-11-20 - kiln: first pages build.\n")
CHAT_PROMPT = ("Read build.py and template.html, then add pages/about.md: a heading and two sentences on what "
               "kiln is. Reply in one sentence.")
SESSION_PROMPT = "In two short sentences: what does this project do, and what's the one thing you'd add next?"


def save(img, name, width=None):
    img = img.convert("RGB")
    if width and img.width != width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)
    img.save(os.path.join(OUT, name + ".webp"), "WEBP", quality=80, method=6)
    print("shot  %s.webp  %dx%d" % (name, img.width, img.height))


def thumb(img, name):
    save(img, name, round(img.width * THUMB))


def wait(cond, secs=10):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.2)
    return cond()


def make_kiln():
    if os.path.isdir(KILN) and os.listdir(KILN):
        raise SystemExit("%s isn't empty: it's the demo project's place. Move what's there first." % KILN)
    for rel, text in KILN_FILES.items():
        p = os.path.join(KILN, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", newline="\n", encoding="utf-8") as f:
            f.write(text)
    git = lambda *a: subprocess.run(["git", "-c", "user.name=kiln", "-c", "user.email=kiln@example.com", *a],
                                    cwd=KILN, check=True, capture_output=True)
    git("init", "-q")
    git("add", ".")
    git("commit", "-qm", "kiln")


def empty_kiln():
    def writable(fn, p, _):
        os.chmod(p, 0o666)  # git's read-only object files
        fn(p)
    for name in os.listdir(KILN):
        p = os.path.join(KILN, name)
        shutil.rmtree(p, onerror=writable) if os.path.isdir(p) else os.remove(p)


def make_home():
    root = DEMO_ROOT  # a fixed, plain name: settings shows the local data folder
    if os.path.exists(root):
        raise SystemExit("%s is left over from a run that didn't finish: delete it first." % root)
    home = os.path.join(root, "home")
    os.makedirs(os.path.join(home, "personas"))
    guihome.junction(os.path.join(home, "assets"), os.path.join(guihome.REIDCC, "assets"))
    shutil.copy(os.path.join(guihome.REIDCC, "personas", "plain.md"), os.path.join(home, "personas"))
    os.makedirs(os.path.join(home, "codex", "prompts"))
    os.makedirs(os.path.join(root, "codex_home"))
    os.makedirs(os.path.join(root, "work"))
    cfg = {"default": "main", "profiles": {
        "main": {"model": "sonnet", "memory": True},
        "review": {"model": "opus"},
        "quick": {"model": "haiku"},
        "cx": {"engine": "codex"},
    }}
    json.dump(cfg, open(os.path.join(home, "reid.json"), "w", encoding="utf-8"), indent=2)
    json.dump({"recent_dirs": [KILN]}, open(os.path.join(home, "reid_state.json"), "w", encoding="utf-8"), indent=2)
    with open(os.path.join(home, "reidcc_memory.md"), "w", encoding="utf-8") as f:
        f.write(MEMORY)
    bin_ = os.path.join(home, "bin")
    os.makedirs(bin_)
    for exe in ("Reidcc.exe", "reid.exe"):
        shutil.copy(os.path.join(guihome.RELEASE, exe), bin_)
    return root, home, bin_


def resize_window(h, w, hgt):
    """Client area w x hgt (96 DPI: CSS px are pixels), top-left kept."""
    r, c = W.RECT(), W.RECT()
    u32.GetWindowRect(W.HWND(h), ctypes.byref(r))
    u32.GetClientRect(W.HWND(h), ctypes.byref(c))
    u32.SetWindowPos(W.HWND(h), None, max(r.left, 0), max(r.top, 0),
                     (r.right - r.left) + w - c.right, (r.bottom - r.top) + hgt - c.bottom, 0x0004 | 0x0010)
    time.sleep(0.6)


def as_installed(t):
    """The bar's title as an installed copy shows it: a local build is a dev build (REIDCC_DEV=1) and says so."""
    t.js(r"""(() => { const w = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        for (let n; (n = w.nextNode());) n.nodeValue = n.nodeValue.replace(/(Reidcc \d+\.\d+\.\d+) dev\b/, '$1'); })()""")


def sess_write(page, data):
    page.js("window.__TAURI_INTERNALS__.invoke('sess_write', {id: +new URLSearchParams(location.search).get('id'), data: %s})"
            % json.dumps(data))


def settled(page, secs=3.0, timeout=150):
    """The terminal stopped changing for `secs` (the engine is done talking)."""
    end, last, since = time.time() + timeout, None, time.time()
    while time.time() < end:
        s = screen(page)
        if s != last:
            last, since = s, time.time()
        elif time.time() - since >= secs:
            return s
        time.sleep(0.3)
    return last


def pod_shot(p):
    """The pod is see-through: grab the screen over a canvas-coloured backing window."""
    import tkinter as tk
    l, t, r, b = frame(p)
    pad = 24
    bg = tk.Tk()
    bg.overrideredirect(True)
    bg.configure(bg=CANVAS)
    bg.geometry("%dx%d+%d+%d" % (r - l + 2 * pad, b - t + 2 * pad, l - pad, t - pad))
    bg.attributes("-topmost", True)
    bg.update()
    time.sleep(0.3)
    u32.SetWindowPos(W.HWND(p), W.HWND(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # TOPMOST, no move/size/activate
    time.sleep(0.5)
    img = ImageGrab.grab(bbox=(l - pad, t - pad, r + pad, b + pad), all_screens=True)
    u32.SetWindowPos(W.HWND(p), W.HWND(-2), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)
    bg.destroy()
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    # run from inside a Claude Code session, its markers would reach the demo's engines (e.g. "transcript saving is off")
    for k in [k for k in os.environ if k.startswith(("CLAUDECODE", "CLAUDE_CODE_", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_AUTOCOMPACT"))]:
        del os.environ[k]
    make_kiln()
    root, home, bin_ = make_home()
    before = set(glob.glob(os.path.join(CLAUDE_PROJECTS, "*", "*.jsonl")))
    t, seen, c = None, set(), None
    try:
        t = guihome.Tauri(root, port=PORT, exe=os.path.join(bin_, "Reidcc.exe"), cwd=KILN)
        time.sleep(2.0)
        t.js("__reid.selectRow(%d)" % t.js("__reid.state().names").index("main"))
        time.sleep(0.8)

        # ---- the launcher, settings, and three sizes
        as_installed(t)
        img = guihome.client_shot(t.hwnd)
        save(img, "launcher", 1000)
        thumb(img, "size-main")
        t.js("__reid.button('settings')")
        wait(lambda: t.js("__reid.settings().open"), 3)
        time.sleep(0.8)
        as_installed(t)
        # cut above plugins: it would list this PC's installed Claude Code plugins
        cut = t.js("""(() => { const s = document.querySelector('#settings .slist')?.closest('.ssec');
            return s ? Math.floor(s.getBoundingClientRect().top) : innerHeight; })()""")
        img = guihome.client_shot(t.hwnd)
        save(img.crop((0, 0, img.width, min(cut, img.height))), "settings", 1000)
        t.js("__reid.button('← back')")
        if not wait(lambda: not t.js("__reid.settings().open"), 3):
            raise RuntimeError("settings didn't close")
        time.sleep(0.6)
        resize_inner(t, 500, 836)
        time.sleep(0.8)
        as_installed(t)
        thumb(guihome.client_shot(t.hwnd), "size-medium")
        key(t, "Digit2", alt=True)
        time.sleep(1.0)
        as_installed(t)
        thumb(guihome.client_shot(t.hwnd), "size-small")
        key(t, "Digit1", alt=True)
        time.sleep(1.0)

        # ---- one chat: a Claude turn that writes a file (Read, Read, Write fold into one line)
        t.js("__reid.button('open chat')")
        c = Chat(chat_target())
        ch = guihome.find_window(t.proc.pid, title="chat · main")
        resize_window(ch, *CHAT_SIZE)
        r = c.turn(CHAT_PROMPT, timeout=240)
        print("chat  tools=%d changed=%s text=%r" % (len(r.get("tools", [])), r.get("changed"), r.get("text", "")[:80]))
        wait(lambda: c.js("!!document.querySelector('.changed')"), 20)
        c.js("document.querySelector('.changed .head').click()")  # open: the file it wrote shows
        c.js("document.activeElement && document.activeElement.blur()")
        time.sleep(0.8)
        save(guihome.client_shot(ch), "chat", CHAT_SIZE[0])
        c.js("__chat.click('#close')")
        time.sleep(1.0)

        # ---- a session window, the launcher beside it (RC). Its Claude skips this PC's user settings: their
        # plugins, hooks and status line would be on screen. Set now, after the launcher's shots show main's command.
        cfgp = os.path.join(home, "reid.json")
        cfg = json.load(open(cfgp, encoding="utf-8"))
        cfg["profiles"]["main"]["args"] = ["--setting-sources", "project,local", "--permission-mode", "default"]
        json.dump(cfg, open(cfgp, "w", encoding="utf-8"), indent=2)
        title = "claude · main"
        press(t, "main")
        wait(lambda: visible(find(t.proc.pid, title)), 15)
        h = find(t.proc.pid, title)
        page = Page(session_target(seen, timeout=20))
        resize_window(h, *SESSION_SIZE)
        s = settled(page, 3.0, 60)
        if "trust this folder" in (s or ""):
            # Claude's folder-trust question (a new demo folder): its cursor starts on "No, exit"
            sess_write(page, "\x1b[B")
            time.sleep(0.5)
            sess_write(page, "\r")
            settled(page, 3.0, 30)
        sess_write(page, SESSION_PROMPT)
        time.sleep(0.8)
        sess_write(page, "\r")
        time.sleep(4)
        s = settled(page, 5.0, 150)
        print("sess  %r" % (s or "")[-300:])
        save(guihome.client_shot(h), "session-window", SESSION_SIZE[0])
        page.js("document.getElementById('mark').click()")
        wait(lambda: t.js("__reid.docked()") == "beside", 5)
        time.sleep(1.0)
        save(guihome.client_shot(h), "beside", 1120)
        page.js("document.getElementById('mark').click()")
        wait(lambda: t.js("__reid.docked()") == "full", 5)
        page.js("document.getElementById('mark').click()")
        wait(lambda: not t.js("__reid.docked()"), 5)
        time.sleep(0.8)

        # ---- the pod, with that session in its slot
        key(t, "Digit3", alt=True)
        wait(lambda: visible(pod_hwnd(t)), 5)
        time.sleep(1.5)
        thumb(pod_shot(pod_hwnd(t)), "size-pod")
        return 0
    finally:
        if t:
            t.close()
        for p in ours(bin_):
            try:
                p.kill()
            except psutil.Error:
                pass
        time.sleep(1.0)
        gone = 0
        for f in set(glob.glob(os.path.join(CLAUDE_PROJECTS, "*", "*.jsonl"))) - before:
            if "kiln" in os.path.basename(os.path.dirname(f)).lower():
                os.remove(f)
                shutil.rmtree(f[:-6], ignore_errors=True)
                gone += 1
        print("      removed %d demo session file(s)" % gone)
        os.rmdir(os.path.join(home, "assets"))  # the junction, never what it points at
        shutil.rmtree(root, ignore_errors=True)
        empty_kiln()


if __name__ == "__main__":
    sys.exit(main())
