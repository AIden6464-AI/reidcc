// The settings page: app-wide choices only (vision: "Direction from Reid" in reidcc_design_motion_system.md).
// It takes the launcher's place in the same window; `← back` (or Escape) returns. Profile fields never come here.
// Layout: vision\Spec\SPEC-one-look.md Part 5 (title column in bone, control column, help under the control).
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Check, button, el, label } from "./widgets";

type View = { open_in: string; engine: string; start_size: string; colors: string; version: string; installed: boolean; home: string; temp: string; ai_temp: string };
type Plugin = { id: string; version: string; enabled: boolean };
type Foot = { text: string; click: boolean };

export class Settings {
  root = el("div");
  radios: Record<string, [string, Check][]> = {};
  paths: Record<string, HTMLDivElement> = {};
  version = label("", "text", "mono");
  update = label("", "text2", "mono");
  locNote = this.note(""); // what the last `change` did
  plugins = el("div", "slist");
  bBack: HTMLButtonElement;

  constructor(private back: () => void) {
    this.root.id = "settings";
    const head = el("div", "shead");
    this.bBack = button("← back", () => this.back());
    head.append(this.bBack, label("settings", "text", "title"));
    const body = el("div", "sbody");
    body.append(
      this.section("sessions open in", this.choice("open_in", [["reidcc", "Reidcc session window"], ["terminal", "Windows Terminal"]])),
      this.section("terminal colours", this.choice("colors", [["reidcc", "Reidcc palette"], ["engine", "the engine's own · no translate"]]),
        this.note("Session windows move Claude Code's colours into Reidcc's palette. Sessions opened after a change use it.")),
      this.section("default engine", this.choice("engine", [["claude", "claude"], ["codex", "codex"]]),
        this.note("a new profile starts on this engine")),
      this.section("default size", this.choice("start_size", [["main", "main"], ["medium", "medium"], ["small", "small"]]),
        this.note("Reidcc opens at this size. Alt+1 and Alt+2 still switch while it's open.")),
      this.section("updates", this.updates()),
      this.section("locations", this.path("local data", "home"), this.path("temp files", "temp"), this.path("ai temp work", "ai_temp"), this.locNote),
      this.section("plugins", this.plugins, this.note("Claude Code's installed plugins. Turn them on or off with /plugin in a session.")),
    );
    this.root.append(head, el("div", "hair"), body);
    // the updater's answer lands here while settings is open (the launcher's status bar is hidden)
    const foot = (f: Foot) => {
      this.update.textContent = f.text;
      this.update.classList.toggle("slink", f.click);
    };
    this.update.addEventListener("click", () => { if (this.update.classList.contains("slink")) invoke("update_install"); });
    listen<Foot>("update", (e) => foot(e.payload));
    invoke<Foot>("update_foot").then(foot);
  }

  section(title: string, ...rows: HTMLElement[]) {
    const s = el("div", "ssec");
    const ctl = el("div", "sctl");
    ctl.append(...rows);
    s.append(label(title, "text", "body"), ctl);
    return s;
  }

  note(text: string) {
    const n = label(text, "text2", "tag");
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
    b.style.margin = "0 16px";
    row.append(this.version, b, this.update);
    return row;
  }

  path(name: string, which: string) {
    const row = el("div", "srow");
    const l = label(name, "text2", "label");
    l.style.width = "120px";
    this.paths[which] = label("", "text2", "mono");
    this.paths[which].classList.add("spath");
    const change = button("change", () => this.change(which));
    change.style.marginRight = "6px";
    row.append(l, this.paths[which], change, button("open", () => invoke("settings_open", { which })));
    return row;
  }

  paint(v: View) {
    for (const [key, cur] of [["open_in", v.open_in], ["colors", v.colors], ["engine", v.engine], ["start_size", v.start_size]]) for (const [val, r] of this.radios[key]) r.set(val === cur);
    this.version.textContent = `Reidcc ${v.version}`;
    if (!v.installed && !this.update.textContent) this.update.textContent = "updates come with the installed copy";
    this.paths.home.textContent = v.home;
    this.paths.temp.textContent = v.temp;
    this.paths.ai_temp.textContent = v.ai_temp + "  (Claude Code)";
  }

  /** `change`: pick a folder (the backend opens the dialog), then show what that did. */
  async change(which: string) {
    const r = await invoke<{ view: View; note: string }>("settings_change", { which });
    this.paint(r.view);
    if (r.note) this.locNote.textContent = r.note;
  }

  async set(key: string, value: string) { this.paint(await invoke<View>("settings_set", { key, value })); }

  /** One plugin row: `name  marketplace · version`, `on`/`off` at the right; a commit-hash version shows 7 characters. */
  plugin(p: Plugin) {
    const r = el("div", "mrow");
    const at = p.id.lastIndexOf("@"), name = at > 0 ? p.id.slice(0, at) : p.id, market = at > 0 ? p.id.slice(at + 1) : "";
    const hash = /^[0-9a-f]{12,}$/i.test(p.version);
    const n = el("span", "name", name);
    n.style.flex = "none";
    r.append(n);
    if (market) r.append(el("span", "dim", `  ${market}`));
    r.append(el("span", "sep", " · "), el("span", hash ? "dim" : "", hash ? p.version.slice(0, 7) : p.version || "?"));
    const spacer = el("span");
    spacer.style.flex = "1";
    r.append(spacer, el("span", p.enabled ? "st" : "st dim", p.enabled ? "on" : "off"));
    return r;
  }

  async open() {
    document.body.dataset.view = "settings";
    this.bBack.focus();
    this.locNote.textContent = "local data: from Reidcc's next start. Temp folders: for sessions opened after a change.";
    this.paint(await invoke<View>("settings_get"));
    this.plugins.replaceChildren(label("loading…", "text3", "mono"));
    try {
      const list = await invoke<Plugin[]>("settings_plugins");
      this.plugins.replaceChildren(...(list.length ? list.map((p) => this.plugin(p)) : [label("No plugins installed.", "text2", "mono")]));
    } catch (e) {
      this.plugins.replaceChildren(label(`Can't list plugins: ${e}`, "oxide", "mono"));
    }
  }

  close() { delete document.body.dataset.view; }

  get isOpen() { return document.body.dataset.view === "settings"; }
}
