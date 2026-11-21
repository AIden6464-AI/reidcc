// The settings page: app-wide choices only (vision: "Direction from Reid" in reidcc_design_motion_system.md).
// It takes the launcher's place in the same window; `back` (or Escape) returns. Profile fields never come here.
import { invoke } from "@tauri-apps/api/core";
import { C, Check, button, el, label } from "./widgets";

type View = { open_in: string; engine: string; version: string; installed: boolean; home: string; temp: string; ai_temp: string };
type Plugin = { id: string; version: string; enabled: boolean };

export class Settings {
  root = el("div");
  radios: Record<string, [string, Check][]> = {};
  paths: Record<string, HTMLDivElement> = {};
  version = label("", "text2", "mono");
  plugins = el("div", "slist");
  bBack: HTMLButtonElement;

  constructor(private back: () => void) {
    this.root.id = "settings";
    const head = el("div", "shead");
    this.bBack = button("back", () => this.back());
    const spacer = el("div");
    spacer.style.flex = "1";
    head.append(label("settings", "text", "title"), spacer, this.bBack);
    const body = el("div", "sbody");
    body.append(
      this.section("sessions open in", this.choice("open_in", [["reidcc", "Reidcc session window"], ["terminal", "Windows Terminal"]])),
      this.section("default engine", this.choice("engine", [["claude", "claude"], ["codex", "codex"]]),
        this.note("new profile starts on this engine")),
      this.section("updates", this.updates()),
      this.section("plugins", this.plugins, this.note("Claude Code's installed plugins. Turn them on or off with /plugin in a session.")),
      this.section("locations", this.path("local data", "home"), this.path("temp files", "temp"), this.path("ai temp work", "ai_temp"),
        this.note("Changing these comes later.")),
    );
    this.root.append(head, el("div", "hair"), body);
  }

  section(title: string, ...rows: HTMLElement[]) {
    const s = el("div", "ssec");
    s.append(label(title, "text3", "label"), ...rows);
    return s;
  }

  note(text: string) {
    const n = label(text, "text3", "tag");
    n.classList.add("snote");
    return n;
  }

  choice(key: string, opts: [string, string][]) {
    const row = el("div", "srow");
    this.radios[key] = opts.map(([value, text]) => {
      const r = new Check(text, true);
      r.onClick = () => this.set(key, value);
      r.root.style.marginRight = "24px";
      row.append(r.root);
      return [value, r] as [string, Check];
    });
    return row;
  }

  updates() {
    const row = el("div", "srow");
    const b = button("check for updates", () => invoke("update_check"));
    b.style.marginLeft = "16px";
    row.append(this.version, b);
    const ch = el("div", "srow");
    const stable = new Check("stable releases", true);
    stable.set(true);
    const dev = new Check("dev releases", true);
    dev.setDisabled(true);
    stable.root.style.marginRight = "24px";
    ch.append(stable.root, dev.root);
    const wrap = el("div");
    wrap.append(row, ch, this.note("Dev releases aren't published yet."));
    return wrap;
  }

  path(name: string, which: string) {
    const row = el("div", "srow");
    const l = label(name, "text2", "label");
    l.style.width = "120px";
    this.paths[which] = label("", "text2", "mono");
    this.paths[which].classList.add("spath");
    const b = button("open", () => invoke("settings_open", { which }));
    row.append(l, this.paths[which], b);
    return row;
  }

  paint(v: View) {
    for (const [key, cur] of [["open_in", v.open_in], ["engine", v.engine]]) for (const [val, r] of this.radios[key]) r.set(val === cur);
    this.version.textContent = `Reidcc ${v.version}${v.installed ? "" : " · not the installed copy"}`;
    this.paths.home.textContent = v.home;
    this.paths.temp.textContent = v.temp;
    this.paths.ai_temp.textContent = v.ai_temp + "  (Claude Code)";
  }

  async set(key: string, value: string) { this.paint(await invoke<View>("settings_set", { key, value })); }

  async open() {
    document.body.dataset.view = "settings";
    this.bBack.focus();
    this.paint(await invoke<View>("settings_get"));
    this.plugins.replaceChildren(label("loading…", "text3", "mono"));
    try {
      const list = await invoke<Plugin[]>("settings_plugins");
      this.plugins.replaceChildren(...(list.length ? list.map((p) => {
        const r = el("div", "mrow");
        const dot = el("span", "dot", "●");
        dot.style.cssText = `color:${p.enabled ? C.emerald : C.text3};margin:0 8px 0 0`;
        r.append(dot, el("span", "name", p.id), el("span", "st", `${p.version} · ${p.enabled ? "on" : "off"}`));
        return r;
      }) : [label("No plugins installed.", "text3", "mono")]));
    } catch (e) {
      this.plugins.replaceChildren(label(`Can't list plugins: ${e}`, "oxide", "mono"));
    }
  }

  close() { delete document.body.dataset.view; }

  get isOpen() { return document.body.dataset.view === "settings"; }
}
