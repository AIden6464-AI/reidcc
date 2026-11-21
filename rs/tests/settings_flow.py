"""The settings page in the Rust GUI: the `settings` button opens it, its choices write reid.json (and the
default removes the key again), the default engine reaches `new profile`, plugins load, `back` returns.
Runs against a temp Reidcc folder; checks the real reid.json stays untouched. Saves two shots.

    python rs\\tests\\settings_flow.py      (needs rs\\target\\release\\Reidcc.exe built)
"""
import os, sys, json, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import guihome

OUT = os.path.join(HERE, "gui_shots")
fails = []


def check(ok, what):
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        fails.append(what)


def wait(cond, s=30):
    end = time.time() + s
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.2)
    return False


def main():
    real = os.path.join(guihome.REIDCC, "reid.json")
    real_before = open(real, "rb").read()
    root, home = guihome.make_home()
    cfg_path = os.path.join(home, "reid.json")
    cfg = lambda: json.load(open(cfg_path, encoding="utf-8"))
    t = guihome.Tauri(root)
    try:
        time.sleep(1)
        check(t.js("__reid.button('settings')"), "settings button exists and opens the page")
        check(t.js("__reid.settings().open"), "page is open")
        text = lambda: t.js("__reid.settings().text")
        for s in ["sessions open in", "default engine", "updates", "plugins", "locations", home]:
            check(s in text(), "page shows %r" % s)
        check(wait(lambda: "loading…" not in text()), "plugins finished loading")
        print("      plugins:", [l for l in text().splitlines() if "·" in l][:3])
        os.makedirs(OUT, exist_ok=True)
        guihome.client_shot(t.hwnd).save(os.path.join(OUT, "settings.png"))

        def radio(label):  # click a radio by its text
            return t.js("""(() => { const r = [...document.querySelectorAll('#settings .check')].find(c => c.textContent.trim() === %s);
                           if (!r) return false; r.click(); return true; })()""" % json.dumps(label))
        check(radio("Windows Terminal"), "click Windows Terminal")
        check(wait(lambda: cfg().get("open_in") == "terminal", 5), "open_in = terminal in reid.json")
        check(radio("Reidcc session window"), "click Reidcc session window")
        check(wait(lambda: "open_in" not in cfg(), 5), "default removes open_in again")
        check(radio("codex"), "click codex")
        check(wait(lambda: cfg().get("default_engine") == "codex", 5), "default_engine = codex in reid.json")
        check(not radio("dev releases") or "updates" not in cfg(), "dev releases is disabled (writes nothing)")

        t.js("document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
        t.js("window.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}))")
        check(wait(lambda: not t.js("__reid.settings().open"), 3), "Escape returns to the launcher")
        before = set(cfg()["profiles"])
        t.js("__reid.button('new profile')")
        check(wait(lambda: len(cfg()["profiles"]) > len(before), 5), "new profile made")
        new = [n for n in cfg()["profiles"] if n not in before]
        check(new and cfg()["profiles"][new[0]] == {"engine": "codex"}, "new profile starts on codex: %s" % (new and cfg()["profiles"][new[0]]))

        t.js("__reid.button('settings')")
        check(radio("claude"), "back to claude")
        check(wait(lambda: "default_engine" not in cfg(), 5), "default removes default_engine")
        t.js("__reid.button('back')")
        check(not t.js("__reid.settings().open"), "back returns to the launcher")
        guihome.client_shot(t.hwnd).save(os.path.join(OUT, "settings_button.png"))
    finally:
        t.close()
        guihome.remove_home(root)
    check(open(real, "rb").read() == real_before, "real reid.json untouched")
    print("\n%d failed" % len(fails))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
