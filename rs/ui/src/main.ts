// The launcher's one screen, 1:1 with `App` in python\reid_gui.py: folder -> profile -> open gate.
// Layout follows App._build_* (Tk pack/grid) at the sizes Tk gives them; every data change goes to
// Rust (rs\app\src\model.rs), which loads reid.json fresh, saves, and answers with screen operations.
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { Gate, Meta } from "./gate";
import { Settings } from "./settings";
import { C, Check, Combo, Listbox, button, closePopups, el, entry, label, measure, setMetrics, wrap } from "./widgets";

const PAD = 40;
/** vision v1 §1: smaller than this (CSS px), the launcher folds into the mini pod */
const POD_BELOW: [number, number] = [340, 240];
const MODES: [string, string][] = [["append", "add to Claude Code's prompt"], ["replace", "replace Claude Code's prompt"]];
/** The form (vision\Spec\SPEC-form.md): narrower or shorter than full, at least the old launcher's minsize. */
const FORM_MIN: [number, number] = [480, 720];
/** The form's checkbox rows: each switch with a sentence saying what it does (what claude.rs does with it). */
const SENTENCES: [string, string, string][] = [
  ["memory", "memory", "add your memory file to the session"],
  ["chrome", "chrome", "let Claude Code use Chrome"],
  ["connectors", "connectors", "use your claude.ai connectors"],
  ["safe", "safe mode", "no CLAUDE.md files, only the MCP servers set here"],
];
type Size = "full" | "form" | "medium";
const RANK: Record<Size, number> = { full: 0, form: 1, medium: 2 };
const REDUCED = matchMedia("(prefers-reduced-motion: reduce)");

type Op =
  | { op: "say"; text: string; kind: string; actions: [string, string][]; seconds: number | null; focus: number | null }
  | { op: "clear" }
  | { op: "clear_if"; text: string }
  | { op: "list"; items: string[]; names: string[] }
  | { op: "select"; index: number }
  | ({ op: "fields" } & Fields)
  | ({ op: "refresh" } & Refresh)
  | { op: "var"; key: string; value: string }
  | { op: "persona_choice"; value: string }
  | { op: "recheck" }
  | { op: "focus"; target: string };

interface Fields {
  name: string; engine: string; model: string; auth: string; persona: string; mode: string; proxy: string;
  tools: string; mcp: string; args: string; memory: boolean; chrome: boolean; connectors: boolean; safe: boolean;
  engines: string[]; models: string[]; auths: string[]; personas: string[]; proxies: string[];
  tools_choices: string[]; mcps: string[];
}
interface Refresh {
  title: string; tags: string; mode_texts: [string, string]; mode_disabled: boolean;
  disabled: Record<string, boolean>; codex: boolean; ready: boolean; status: string; preview: string;
}

class App {
  root = document.getElementById("root")!;
  names: string[] = [];
  mode = "append";
  msgText = "";
  msgTimer = 0;
  recheck = 0;
  previewText = "";
  gate: Gate | null = null;
  emblem: Gate | null = null; // the form's opening (SPEC-hand.md): the emblem grows and the view zooms into the emerald
  opening: Gate | null = null; // the one playing now
  settings!: Settings;
  /** vision v1 §1: the window's size is its mode */
  size: Size = "full";
  fullMin: [number, number] = [960, 820];
  /** Alt+1/2's size while its eased resize runs: the sizes it passes through don't get a layout */
  target: Size = "full";
  targetUntil = 0;
  pushGhost: HTMLElement | null = null;
  /** the form's own widgets; the shared ones move in (`put`) and back (`unplace`) */
  undo: (() => void)[] = [];
  cells: Record<string, HTMLDivElement> = {};
  folderBox!: HTMLDivElement;
  profCombo!: Combo;
  defCheck!: Check;
  promptCombo!: Combo;
  modeTexts = MODES.map((m) => m[1]);
  modeDisabled = false;
  fPick!: HTMLButtonElement;
  fBar!: HTMLDivElement;
  folderRow!: HTMLDivElement;
  folderHair!: HTMLDivElement;
  mSessions!: HTMLDivElement;
  mCombos!: HTMLDivElement;
  sessTimer = 0;
  foldTimer = 0;

  // widgets
  statusText!: HTMLDivElement;
  statusDot!: HTMLDivElement;
  updateText!: HTMLDivElement;
  msgLabel!: HTMLDivElement;
  msgActions!: HTMLDivElement;
  eFolder!: HTMLInputElement;
  bPick!: HTMLButtonElement;
  bRecent!: HTMLButtonElement;
  lb!: Listbox;
  pTitle!: HTMLDivElement;
  tags!: HTMLDivElement;
  eName!: HTMLInputElement;
  cb: Record<string, Combo> = {};
  bBrowse!: HTMLButtonElement;
  bOpenPersona!: HTMLButtonElement;
  radios: Check[] = [];
  checks: Record<string, Check> = {};
  eArgs!: HTMLInputElement;
  preview!: HTMLDivElement;
  bGo!: HTMLButtonElement;
  bResume!: HTMLButtonElement;

  constructor() {
    // Built in Tk's creation order, so Tab moves the way Tk's traversal does; `order` places them.
    this.buildFooter();
    this.buildMsgbar();
    this.buildMain();
    this.buildMedium();
    this.buildForm();
    this.settings = new Settings(() => this.closeSettings());
    this.root.append(this.settings.root);
    this.keys();
    new ResizeObserver(() => { this.fit(); this.wrapTexts(); }).observe(document.body);
  }

  // ---------------------------------------------------------------- layout ---
  buildFooter() {
    const f = el("div");
    f.id = "footer";
    f.append(el("div", "hair"));
    const row = el("div");
    row.style.cssText = `display:flex;align-items:center;padding:9px ${PAD}px`;
    this.statusDot = label("●", "emerald", "mono");
    this.statusText = label("", "text2", "mono");
    const spacer = el("div");
    spacer.style.flex = "1";
    this.statusDot.style.marginRight = "6px";
    const hint = label("folder → profile → open gate", "text3", "mono");
    hint.classList.add("hint");
    // the updater's line takes the status's place while it has something to say (SPEC-github-repo.md 4a)
    this.updateText = label("", "text2", "mono");
    this.updateText.addEventListener("click", () => { if (this.updateText.dataset.click) invoke("update_install"); });
    this.updateText.addEventListener("mouseenter", () => { if (this.updateText.dataset.click) this.updateText.style.color = C.text; });
    this.updateText.addEventListener("mouseleave", () => { this.updateText.style.color = ""; });
    row.append(hint, spacer, this.statusDot, this.statusText, this.updateText);
    const foot = (f: { text: string; click: boolean }) => {
      this.updateText.textContent = f.text;
      this.updateText.style.cursor = f.click ? "pointer" : "";
      if (f.click) this.updateText.dataset.click = "1"; else delete this.updateText.dataset.click;
      for (const e of [this.statusDot, this.statusText]) e.style.display = f.text ? "none" : "";
    };
    listen<{ text: string; click: boolean }>("update", (e) => foot(e.payload));
    invoke<{ text: string; click: boolean }>("update_foot").then(foot);
    f.append(row);
    this.root.append(f);
  }

  buildMsgbar() {
    const m = el("div");
    m.id = "msgbar";
    this.msgLabel = label("", "text", "body");
    this.msgLabel.style.margin = `0 12px 0 ${PAD}px`;
    this.msgActions = el("div");
    this.msgActions.style.cssText = "display:flex;flex:none";
    m.append(this.msgLabel, this.msgActions);
    this.root.append(m);
  }

  buildMain() {
    const m = el("div");
    m.id = "main";
    const banner = el("img");
    banner.src = "http://reid.localhost/assets/banner.png";
    banner.style.cssText = "display:block;margin:14px auto 0;width:720px;height:176px;flex:none";
    banner.onerror = () => banner.remove();
    m.append(banner);
    const col = el("div");
    col.style.cssText = `flex:1 1 auto;min-height:0;display:flex;flex-direction:column;padding:0 ${PAD}px`;
    m.append(col);
    const title = label("Open a folder. Start coding.", "text", "title");
    title.style.cssText = "margin:12px 0 2px;align-self:flex-start";
    const sub = label("Pick a project and a profile. Your persona, memory and settings are already there.", "text2", "body");
    sub.style.alignSelf = "flex-start";
    col.append(title, sub);

    // 1. folder
    const fr = el("div");
    fr.style.cssText = "display:flex;align-items:center;margin:16px 0 14px;flex:none";
    this.eFolder = entry();
    this.eFolder.style.cssText = "flex:1;height:32px";
    this.eFolder.addEventListener("input", () => invoke("folder_text", { text: this.eFolder.value }));
    this.eFolder.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.ctrlKey) { e.preventDefault(); e.stopPropagation(); this.action("commit_folder"); }
    });
    this.bPick = button("pick folder", () => this.pickFolder());
    this.bRecent = button("open recent ▾", () => this.openRecent());
    this.bPick.style.marginLeft = this.bRecent.style.marginLeft = "8px";
    const fl = label("folder", "text3", "label", 8);
    fl.classList.add("flabel");
    fr.append(fl, this.eFolder, this.bPick, this.bRecent);
    this.folderRow = fr;
    this.folderHair = el("div", "hair");
    col.append(fr, this.folderHair);

    // 2. profile: list on the left, the selected profile's fields on the right
    const panel = el("div");
    panel.style.cssText = "display:flex;margin-top:12px;flex:1 0 auto;min-height:0";
    this.buildProfileList(panel);
    const div = el("div");
    div.style.cssText = `width:1px;background:${C.line};margin:0 18px;flex:none`;
    panel.append(div);
    this.buildFields(panel);
    col.append(panel);

    // 3. go
    const h = el("div", "hair");
    h.style.marginTop = "10px";
    const act = el("div");
    act.style.cssText = "display:flex;margin:10px 0 4px;flex:0 1 34px;min-height:0;overflow:hidden";
    const spacer = el("div");
    spacer.style.flex = "1";
    this.bGo = button("open gate", () => this.go(false), true);
    this.bResume = button("resume", () => this.go(true));
    this.bResume.style.marginRight = "8px";
    const bConfig = button("open reid.json", () => this.action("open_config"));
    bConfig.style.marginLeft = "8px";
    // DOM order = Tk's creation order (open gate before resume); placed with `order`
    const bMem = button("open memory", () => this.action("open_memory"));
    // the way into the settings page (Reid, 2026-11-21): after open reid.json, same quiet style
    const bSettings = button("settings", () => this.openSettings());
    bSettings.style.marginLeft = "8px";
    for (const [b, o] of [[bMem, 1], [bConfig, 2], [bSettings, 3], [this.bGo, 6], [this.bResume, 5]] as const) b.style.order = String(o);
    spacer.style.order = "4";
    for (const b of [bMem, bConfig, bSettings, this.bGo, this.bResume]) b.style.height = "auto";
    act.append(bMem, bConfig, bSettings, spacer, this.bGo, this.bResume);
    col.append(h, act);
    this.root.append(m);
  }

  buildProfileList(panel: HTMLElement) {
    const left = el("div");
    left.style.cssText = "display:flex;flex-direction:column;flex:none";
    const l = label("profiles", "text3", "label");
    l.style.cssText = "margin-bottom:6px;align-self:flex-start";
    this.lb = new Listbox();
    this.lb.onSelect = (i) => this.select(this.names[i]);
    const g = el("div");
    g.style.cssText = "display:grid;grid-template-columns:1fr 1fr;margin-top:8px;flex:none";
    const cmds: [string, () => void][] = [["new profile", () => this.action("new")], ["duplicate", () => this.action("dup")],
      ["delete", () => this.action("delete")], ["make default", () => this.action("default")]];
    // grid uniform columns: each as wide as the widest button (+ the 6 px gap on the left one)
    const w = Math.max(...cmds.map(([t]) => measure(t, "btn") + 29));
    g.style.gridTemplateColumns = `${w}px ${w}px`;
    cmds.forEach(([t, fn], i) => {
      const b = button(t, fn);
      b.style.width = "auto";
      b.style.margin = i % 2 === 0 ? "0 6px 6px 0" : "0 0 6px 0";
      g.append(b);
    });
    left.append(l, this.lb.box, g);
    panel.append(left);
  }

  buildFields(panel: HTMLElement) {
    const right = el("div");
    right.style.cssText = "display:flex;flex-direction:column;flex:1;min-width:0";
    const head = el("div");
    head.style.cssText = "display:flex;align-items:center;height:27px;margin-bottom:6px;flex:none";
    this.pTitle = label("", "text", "head");
    this.tags = label("", "text2", "tag");
    this.tags.style.marginLeft = "12px";
    head.append(this.pTitle, this.tags);

    const form = el("div");
    form.style.cssText = "display:grid;grid-template-columns:auto 1fr auto auto;align-items:center;flex:none";
    let r = 1;
    const row = (text: string, widget: HTMLElement, extra: HTMLElement[] = [], span = 1) => {
      const l = label(text, "text3", "label");
      l.style.cssText += `;grid-row:${r};grid-column:1;margin:2px 14px 2px 0;justify-self:start`;
      widget.style.gridRow = String(r);
      widget.style.gridColumn = `2 / span ${span}`;
      widget.style.margin = "2px 0";
      form.append(l, widget);
      extra.forEach((w, i) => {
        w.style.gridRow = String(r);
        w.style.gridColumn = String(3 + i);
        w.style.margin = "2px 0 2px 6px";
        form.append(w);
      });
      r++;
    };
    this.eName = entry();
    this.eName.addEventListener("keydown", (e) => { if (e.key === "Enter") this.rename(); });
    this.eName.addEventListener("blur", () => this.rename());
    // engine: on the name row, right above model, so the form keeps its height
    const ef = el("div");
    ef.style.cssText = "display:flex;align-items:center";
    const engLabel = label("engine", "text3", "label");
    engLabel.style.marginRight = "8px";
    const combo = (key: string, readonly: boolean, short = false) => {
      const c = new Combo(readonly, short);
      c.onChange = () => this.apply();
      this.cb[key] = c;
      return c;
    };
    const eng = combo("engine", true, true);
    eng.root.style.width = 8 * measure("0", "mono") + 33 + "px"; // width=8 chars
    ef.append(engLabel, eng.root);
    row("name", this.eName, [ef]);
    ef.style.gridColumn = "3 / span 2";
    ef.style.justifySelf = "start";
    row("model", combo("model", false).root);
    row("sign-in", combo("auth", true).root);
    this.bBrowse = button("browse", () => this.browsePersona());
    this.bOpenPersona = button("open persona", () => this.openPersona());
    row("persona", combo("persona", true).root, [this.bBrowse, this.bOpenPersona]);
    const mf = el("div");
    mf.style.cssText = "display:flex";
    for (const [mode, txt] of MODES) {
      const rb = new Check(txt, true);
      rb.root.style.marginRight = "16px";
      rb.onClick = () => { this.mode = mode; this.paintModes(); this.apply(); };
      this.radios.push(rb);
      mf.append(rb.root);
    }
    row("persona mode", mf, [], 3);
    row("proxy", combo("proxy", true).root);
    row("tools", combo("tools", false).root);
    row("mcp", combo("mcp", true).root);
    const sf = el("div");
    sf.style.cssText = "display:flex";
    for (const [k, txt] of [["memory", "memory"], ["chrome", "chrome"], ["connectors", "connectors"], ["safe", "safe mode"]]) {
      const c = new Check(txt);
      c.root.style.marginRight = "16px";
      c.onClick = () => { c.set(!c.on); this.apply(); };
      this.checks[k] = c;
      sf.append(c.root);
    }
    row("switches", sf, [], 3);
    this.eArgs = entry();
    this.eArgs.addEventListener("input", () => this.apply());
    row("extra args", this.eArgs);

    const cmdf = el("div");
    cmdf.style.cssText = "display:flex;flex-direction:column;margin-top:8px;flex:none";
    const cl = label("command", "text3", "label");
    cl.style.alignSelf = "flex-start";
    this.preview = label("", "text3", "tag");
    cmdf.append(cl, this.preview);
    right.append(head, form, cmdf);
    panel.append(right);
  }

  // ---------------------------------------------------------------- sizes ---
  /** Medium (vision v1 §1): the folder, the sessions that run, and combos (1–9 opens a profile's gate). */
  buildMedium() {
    const m = el("div");
    m.id = "medium";
    const head = (text: string) => {
      const l = label(text, "text3", "label");
      l.style.cssText += ";margin:10px 0 4px;align-self:flex-start";
      return l;
    };
    this.mSessions = el("div", "mlist");
    this.mCombos = el("div", "mlist mcombos");
    m.append(head("sessions"), this.mSessions, el("div", "hair"), head("combos"), this.mCombos);
    this.root.append(m);
  }

  /** The form (vision\Spec\SPEC-form.md): 0.2.0's main screen laid out like the old launcher. One row per
   *  setting, a sentence beside each checkbox, word buttons on the right. Its own widgets are the head, the
   *  profile / default / prompt rows and the buttons; the rest are full's widgets, moved in by placeForm(). */
  buildForm() {
    const f = el("div");
    f.id = "form";
    const head = el("div", "fhead");
    const hl = el("div");
    const sub = label("Open a folder. Start coding.", "text2", "body");
    sub.classList.add("fsub");
    hl.append(el("div", "wordmark", "Reidcc"), sub);
    head.append(hl, button("settings", () => this.openSettings()));

    const grid = el("div", "fgrid");
    const cell = (key: string) => (this.cells[key] = el("div", "fcell"));
    const row = (text: string, field: HTMLElement, btns: HTMLElement[] = []) => {
      grid.append(label(text, "text2", "body"), field);
      if (!btns.length) { field.classList.add("fwide"); return; }
      const b = el("div", "fbtns");
      b.append(...btns);
      grid.append(b);
    };
    this.folderBox = el("div", "combo short");
    const arrow = el("div", "arrow");
    arrow.append(el("i"));
    arrow.addEventListener("mousedown", (e) => { if (e.button === 0) { e.preventDefault(); this.openRecent(this.folderBox); } });
    this.folderBox.append(arrow);
    this.eFolder.addEventListener("focus", () => this.folderBox.classList.add("focus"));
    this.eFolder.addEventListener("blur", () => this.folderBox.classList.remove("focus"));
    this.fPick = button("browse", () => this.pickFolder());
    row("folder", this.folderBox, [this.fPick]);

    this.profCombo = new Combo(true, true);
    this.profCombo.onChange = () => {
      const i = this.names.indexOf(this.profCombo.value);
      if (i >= 0 && i !== this.lb.sel) { this.lb.select(i); this.lb.see(i); this.lb.onSelect(i); }
    };
    row("profile", this.profCombo.root, [button("new", () => this.action("new")), button("delete", () => this.action("delete"))]);
    row("name", cell("name"), [button("duplicate", () => this.action("dup"))]);
    this.defCheck = new Check("the profile reid uses when you don't name one");
    this.defCheck.onClick = () => { if (!this.defCheck.on) this.action("default"); }; // default moves, it can't be unset
    row("default", this.defCheck.root);
    row("engine", cell("engine"));
    row("model", cell("model"));
    row("sign-in", cell("auth"));
    row("persona", cell("persona"), [button("browse", () => this.browsePersona()), button("edit", () => this.openPersona())]);
    this.promptCombo = new Combo(true, true);
    this.promptCombo.onChange = () => {
      const i = this.modeTexts.indexOf(this.promptCombo.value);
      if (i >= 0 && MODES[i][0] !== this.mode) { this.mode = MODES[i][0]; this.paintModes(); this.apply(); }
    };
    row("prompt", this.promptCombo.root);
    row("proxy", cell("proxy"));
    row("tools", cell("tools"));
    row("mcp", cell("mcp"));
    for (const [k, text] of SENTENCES) row(text, cell(k));
    row("extra args", cell("args"));

    // no command preview here (Reid, 2026-11-22: "can we remove this"); the wide layout keeps its own
    const body = el("div", "sbody fbody");
    body.append(grid);
    this.fBar = el("div", "fbar");
    this.fBar.append(button("open memory", () => this.action("open_memory")), button("open reid.json", () => this.action("open_config")));
    f.append(head, body, this.fBar);
    this.root.append(f);
  }

  /** Move one of full's widgets into the form; unplace() puts it back as it was. */
  put(w: HTMLElement, parent: HTMLElement, cls = "") {
    const a = document.createComment(""), css = w.style.cssText, add = !!cls && !w.classList.contains(cls);
    w.before(a);
    for (const p of ["grid-row", "grid-column", "margin", "margin-left", "margin-right", "order", "flex", "height", "justify-self"]) w.style.removeProperty(p);
    if (!(w instanceof HTMLButtonElement)) w.style.removeProperty("width");
    if (add) w.classList.add(cls);
    parent.append(w);
    this.undo.push(() => { a.replaceWith(w); w.style.cssText = css; if (add) w.classList.remove(cls); });
  }

  unplace() { while (this.undo.length) this.undo.pop()!(); }

  placeForm() {
    const c = this.cells;
    this.put(this.eFolder, this.folderBox);
    this.put(this.eName, c.name);
    for (const k of ["engine", "model", "auth", "persona", "proxy", "tools", "mcp"]) this.put(this.cb[k].root, c[k], "short");
    for (const [k, , sentence] of SENTENCES) {
      const ch = this.checks[k], old = ch.txt.textContent || "";
      this.put(ch.root, c[k]);
      ch.text = sentence;
      this.undo.push(() => { ch.text = old; });
    }
    this.put(this.eArgs, c.args);
    this.put(this.bResume, this.fBar);
    this.put(this.bGo, this.fBar);
  }

  sizeFor(): Size {
    if (innerWidth >= this.fullMin[0] && innerHeight >= this.fullMin[1]) return "full";
    return innerWidth >= FORM_MIN[0] && innerHeight >= FORM_MIN[1] ? "form" : "medium";
  }

  /** The layout for the window's size: full when the full layout fits, the form when it's narrower or
   *  shorter (down to the old launcher's minsize), medium below that. Alt+1/2 push; dragging cuts. */
  fit() {
    // Dragged smaller than the pod threshold: fold into the mini pod once the drag ends.
    clearTimeout(this.foldTimer);
    if (innerWidth < POD_BELOW[0] || innerHeight < POD_BELOW[1]) this.foldTimer = window.setTimeout(() => this.foldWhenLetGo(), 350);
    const size = this.sizeFor(), keyed = performance.now() < this.targetUntil;
    if (size === this.size || (keyed && size !== this.target)) return;
    if (keyed && !this.settings?.isOpen) this.push(this.view(), RANK[size] > RANK[this.size] ? 1 : -1, () => this.layout(size));
    else this.layout(size);
  }

  layout(size: Size) {
    this.size = size;
    closePopups();
    if (!this.opening?.active) this.calm(); // no ghost of the other size's opening left over
    document.body.dataset.size = size;
    this.unplace();
    this.folderHair.before(this.folderRow);
    clearInterval(this.sessTimer);
    if (size === "medium") {
      document.getElementById("medium")!.prepend(this.folderRow);
      this.drawCombos();
      this.drawSessions();
      this.sessTimer = window.setInterval(() => this.drawSessions(), 1000);
    } else if (size === "form") this.placeForm();
    this.wrapTexts();
  }

  /** The view on screen: settings, or the launcher's layout for the size. */
  view(): HTMLElement {
    return this.settings?.isOpen ? this.settings.root : document.getElementById(this.size === "full" ? "main" : this.size)!;
  }

  /** "slide in to the other veiw not just switch" (Reid, 2026-11-22): a push. A still copy of the old view
   *  slides out while the new one slides in from the other side (`dir` 1: in from the right). 240 ms on the
   *  design curve, no fade; a cut with reduced motion. */
  push(out: HTMLElement, dir: 1 | -1, change: () => void) {
    this.pushGhost?.remove();
    if (REDUCED.matches) { change(); return; }
    const r = out.getBoundingClientRect();
    const ghost = out.cloneNode(true) as HTMLElement;
    const live = out.querySelectorAll("input"), copy = ghost.querySelectorAll("input");
    live.forEach((x, i) => { copy[i].value = x.value; }); // a clone keeps attributes, not typed values
    change();
    ghost.style.cssText += `;display:flex;position:fixed;left:${r.left}px;top:${r.top}px;width:${r.width}px;height:${r.height}px;pointer-events:none;z-index:5`;
    document.body.append(ghost);
    this.pushGhost = ghost;
    const o = { duration: 240, easing: "cubic-bezier(0.16, 1, 0.3, 1)" };
    ghost.animate([{ transform: "none" }, { transform: `translateX(${-100 * dir}%)` }], o).onfinish = () => {
      ghost.remove();
      if (this.pushGhost === ghost) this.pushGhost = null;
    };
    this.view().animate([{ transform: `translateX(${100 * dir}%)` }, { transform: "none" }], o);
  }

  /** Where focus goes for "the profile list": the list, or the form's profile combo. */
  listFocus(): HTMLElement { return this.size === "form" ? this.profCombo.input : this.lb.root; }

  /** The form's own widgets follow the state full's widgets show. */
  paintForm() {
    if (!this.profCombo) return;
    this.profCombo.values = this.names;
    this.profCombo.value = this.names[this.lb.sel] ?? "";
    this.defCheck.set(!!this.lb.items[this.lb.sel]?.endsWith("●")); // model.rs marks the default "  ●"
    this.promptCombo.values = this.modeTexts;
    this.promptCombo.value = this.modeTexts[MODES.findIndex((m) => m[0] === this.mode)] ?? "";
    this.promptCombo.setDisabled(this.modeDisabled);
  }

  async foldWhenLetGo() {
    if (innerWidth >= POD_BELOW[0] && innerHeight >= POD_BELOW[1]) return;
    if (!(await invoke<boolean>("pod_fold", { drag: true }))) this.foldTimer = window.setTimeout(() => this.foldWhenLetGo(), 200);
  }

  drawCombos() {
    this.mCombos.replaceChildren(...this.names.slice(0, 9).map((n, i) => {
      const r = el("div", "mrow");
      r.append(el("span", "k", String(i + 1)), el("span", "", n));
      if (i === this.lb.sel) r.classList.add("cur");
      r.addEventListener("click", () => this.combo(i));
      return r;
    }));
  }

  /** A combo: that profile, then open gate on the current folder. */
  async combo(i: number) {
    if (i >= Math.min(9, this.names.length) || this.opening?.active) return;
    this.lb.select(i);
    await this.select(this.names[i]);
    this.drawCombos();
    await this.go(false);
  }

  async drawSessions() {
    type Row = { id: number; engine: string; profile: string; folder: string; elapsed_ms: number; rc: number | null };
    const rows = await invoke<Row[]>("sess_list");
    if (!rows.length) {
      this.mSessions.replaceChildren(label("No sessions running.", "text3", "mono"));
      return;
    }
    const clock = (ms: number) => {
      const t = Math.floor(ms / 1000), h = Math.floor(t / 3600), mm = String(Math.floor(t / 60) % 60).padStart(2, "0");
      return (h ? h + ":" : "") + mm + ":" + String(t % 60).padStart(2, "0");
    };
    this.mSessions.replaceChildren(...rows.map((s) => {
      const r = el("div", "mrow");
      r.title = s.folder;
      const state = s.rc === null ? "running" : s.rc === 0 ? "finished" : `failed · code ${s.rc}`;
      const dot = el("span", "dot", "●");
      dot.style.color = s.rc === null ? C.emerald : s.rc === 0 ? C.text3 : C.oxide;
      const right = el("span", "st", ` ${state} · ${clock(s.elapsed_ms)}`);
      r.append(el("span", "name", `${s.engine} · ${s.profile}`), dot, right);
      // on press: the 1 s redraw can replace the row before a click lands
      r.addEventListener("mousedown", (e) => { if (e.button === 0) invoke("sess_focus", { id: s.id }); });
      return r;
    }));
  }

  paintModes() { this.radios.forEach((rb, i) => rb.set(MODES[i][0] === this.mode)); this.paintForm(); }

  wrapTexts() {
    const w = document.documentElement.clientWidth;
    this.preview.textContent = wrap(this.previewText, Math.max(300, w - 2 * PAD - 300), "tag");
    const msgW = this.size === "form" ? w - 40 - 20 : Math.max(300, w - 2 * PAD - 260);
    this.msgLabel.textContent = wrap(this.msgText, msgW, "body");
  }

  keys() {
    window.addEventListener("keydown", (e) => {
      if (this.opening?.active) { // while the gate plays, every key skips it instead
        e.preventDefault();
        e.stopPropagation();
        this.opening.skip();
        return;
      }
      if (this.settings.isOpen) { // the launcher's keys stay with the launcher
        if (e.key === "Escape") { e.preventDefault(); this.closeSettings(); }
        else if (e.key === "Enter" && document.activeElement instanceof HTMLButtonElement) { e.preventDefault(); document.activeElement.click(); }
        return;
      }
      if (e.key === "Enter" && e.ctrlKey) { e.preventDefault(); this.go(false); }
      else if (e.key === "Enter") this.onReturn(e);
      else if (e.key === "Escape") this.clearMsg();
      else if (e.ctrlKey && !e.shiftKey && !e.altKey && e.key === "o") { e.preventDefault(); this.pickFolder(); }
      else if (e.ctrlKey && !e.shiftKey && !e.altKey && e.key === "r") { e.preventDefault(); this.go(true); }
      else if (e.altKey && !e.ctrlKey && (e.code === "Digit1" || e.code === "Digit2")) {
        e.preventDefault();
        this.target = e.code === "Digit1" ? "full" : "medium";
        this.targetUntil = performance.now() + 500; // the eased resize takes 160 ms
        invoke("set_size", { size: this.target });
      }
      else if (e.altKey && !e.ctrlKey && e.code === "Digit3") { e.preventDefault(); closePopups(); invoke("pod_fold", { drag: false }); }
      else if (this.size === "medium" && /^Digit[1-9]$/.test(e.code) && !e.altKey && !e.ctrlKey && !e.metaKey
               && !(document.activeElement instanceof HTMLInputElement)) {
        e.preventDefault();
        this.combo(Number(e.code.slice(5)) - 1);
      }
    }, true);
  }

  /** Enter: a focused button presses itself; on the profile list (or nothing) it means go. */
  onReturn(e: KeyboardEvent) {
    const w = document.activeElement;
    if (w instanceof HTMLButtonElement) { e.preventDefault(); w.click(); }
    else if (!w || w === document.body || w === this.lb.root) { e.preventDefault(); this.go(false); }
  }

  // -------------------------------------------------------------- messages ---
  /** kind: info (bone), error (oxide), quiet (muted). actions: [label, action id]. */
  say(text: string, kind = "info", actions: [string, string][] = [], seconds: number | null = null): HTMLButtonElement[] {
    clearTimeout(this.msgTimer);
    this.msgTimer = 0;
    this.msgText = text;
    this.msgLabel.style.color = kind === "error" ? C.oxide : kind === "quiet" ? C.text3 : C.text;
    this.wrapTexts();
    this.msgActions.replaceChildren();
    const btns = actions.map(([t, id]) => {
      const b = button(t, () => { this.clearMsg(); this.run(id); });
      b.style.marginRight = "8px";
      this.msgActions.append(b);
      return b;
    });
    if (seconds) this.msgTimer = window.setTimeout(() => this.clearMsg(), seconds * 1000);
    return btns;
  }

  clearMsg() {
    if (this.msgText || this.msgActions.children.length) this.say("");
  }

  run(id: string) {
    if (id === "pick_folder") this.pickFolder();
    else if (id === "go") this.go(false);
    else if (id === "go_resume") this.go(true);
    else if (id !== "keep") this.action(id);
  }

  // ------------------------------------------------------------------ ops ---
  ops(list: Op[]) {
    for (const o of list) {
      switch (o.op) {
        case "say": {
          const b = this.say(o.text, o.kind, o.actions, o.seconds);
          if (o.focus !== null && b[o.focus]) b[o.focus].focus();
          break;
        }
        case "clear": this.clearMsg(); break;
        case "clear_if": if (this.msgText === o.text) this.clearMsg(); break;
        case "list": this.names = o.names; this.lb.set(o.items); if (this.size === "medium") this.drawCombos(); break;
        case "select": this.lb.select(o.index); this.lb.see(o.index); break;
        case "fields": this.setFields(o); break;
        case "refresh": this.refresh(o); break;
        case "var": this.setVar(o.key, o.value); break;
        case "persona_choice": this.cb.persona.values = [...this.cb.persona.values, o.value]; break;
        case "recheck":
          clearTimeout(this.recheck);
          this.recheck = window.setTimeout(() => { this.recheck = 0; this.action("retry"); }, 3000);
          break;
        case "focus":
          (o.target === "pick" ? (this.size === "form" ? this.fPick : this.bPick) : o.target === "name" ? this.eName : this.listFocus()).focus();
          break;
      }
    }
    this.paintForm();
  }

  setFields(f: Fields) {
    this.eName.value = f.name;
    const set = (k: string, v: string, vals: string[]) => { this.cb[k].values = vals; this.cb[k].value = v; };
    set("engine", f.engine, f.engines);
    set("model", f.model, f.models);
    set("auth", f.auth, f.auths);
    set("persona", f.persona, f.personas);
    set("proxy", f.proxy, f.proxies);
    set("tools", f.tools, f.tools_choices);
    set("mcp", f.mcp, f.mcps);
    this.mode = f.mode;
    this.paintModes();
    this.eArgs.value = f.args;
    for (const k of ["memory", "chrome", "connectors", "safe"] as const) this.checks[k].set(f[k]);
  }

  setVar(key: string, value: string) {
    if (key === "auths") this.cb.auth.values = JSON.parse(value);
    else if (key === "folder") { this.eFolder.value = value; }
    else if (key === "name") this.eName.value = value;
    else if (key === "persona_set") { this.cb.persona.value = value; this.apply(); }
    else if (this.cb[key]) this.cb[key].value = value;
  }

  /** Header, tags, greyed fields, status tag and command preview for the selected profile. */
  refresh(r: Refresh) {
    this.pTitle.textContent = r.title;
    this.tags.textContent = r.tags;
    this.radios.forEach((rb, i) => { rb.text = r.mode_texts[i]; rb.setDisabled(r.mode_disabled); });
    this.modeTexts = r.mode_texts;
    this.modeDisabled = r.mode_disabled;
    // Claude-only fields stay on screen for a Codex profile, disabled while they're off
    for (const k of ["proxy", "tools", "mcp"]) {
      this.cb[k].setDisabled(r.disabled[k]);
      this.cb[k].setReadonly(k !== "tools");
    }
    for (const k of ["safe", "chrome", "connectors"]) this.checks[k].setDisabled(r.disabled[k]);
    this.bResume.classList.toggle("dim", r.codex);
    this.statusDot.style.color = r.ready ? C.emerald : C.oxide;
    this.statusText.textContent = r.status;
    this.previewText = r.preview;
    this.preview.style.color = r.ready ? C.text3 : C.oxide;    this.wrapTexts();
  }

  vars() {
    const c = this.checks;
    return {
      engine: this.cb.engine.value, model: this.cb.model.value, auth: this.cb.auth.value, persona: this.cb.persona.value,
      mode: this.mode, proxy: this.cb.proxy.value, tools: this.cb.tools.value, mcp: this.cb.mcp.value,
      args: this.eArgs.value, memory: c.memory.on, chrome: c.chrome.on, connectors: c.connectors.on, safe: c.safe.on,
    };
  }

  // -------------------------------------------------------------- actions ---
  async call(cmd: string, args: Record<string, unknown> = {}) { this.ops(await invoke<Op[]>(cmd, args)); }
  apply() { return this.call("apply", { vars: this.vars() }); }
  select(name: string) { return this.call("select", { name, typed: this.eName.value }); }
  rename() { return this.call("rename", { typed: this.eName.value }); }
  action(name: string) { return this.call("action", { name }); }
  openPersona() { return this.call("open_persona", { persona: this.cb.persona.value }); }

  async pickFolder() {
    this.calm();
    await this.call("pick_folder");
  }

  async browsePersona() {
    this.calm();
    await this.call("browse_persona", { choices: this.cb.persona.values });
  }

  async openRecent(anchor: HTMLElement = this.bRecent) {
    const r = await invoke<{ dirs: [string, string][]; ops: Op[] }>("recent");
    this.ops(r.ops);
    if (!r.dirs.length) return;
    closePopups();
    const menu = el("div", "menu");
    const head = el("div", "item off", "recent");
    menu.append(head);
    const close = () => { menu.remove(); window.removeEventListener("mousedown", out, true); window.removeEventListener("keydown", esc, true); };
    for (const [show, d] of r.dirs) {
      const it = el("div", "item", show);
      it.addEventListener("mouseup", () => { close(); this.call("set_folder", { path: d }); });
      menu.append(it);
    }
    const b = anchor.getBoundingClientRect();
    menu.style.left = b.left + "px";
    menu.style.top = b.bottom + "px";
    document.body.append(menu);
    const out = (e: MouseEvent) => { if (!menu.contains(e.target as Node)) { e.stopPropagation(); close(); } };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") { e.stopPropagation(); e.preventDefault(); close(); } };
    setTimeout(() => window.addEventListener("mousedown", out, true));
    window.addEventListener("keydown", esc, true);
  }

  openSettings() {
    closePopups();
    this.clearMsg();
    if (!this.settings.isOpen) this.push(this.view(), 1, () => this.settings.open());
  }

  closeSettings() {
    if (this.settings.isOpen) this.push(this.settings.root, -1, () => this.settings.close());
    this.listFocus().focus();
  }

  async go(resume: boolean) {
    if (this.opening?.active || this.settings.isOpen) return; // one session per press
    type Go = { kind: "ops"; ops: Op[] } | { kind: "gate"; note: string; uses_wt: boolean; found: boolean; title: string; sub: string; ops: Op[] };
    // The gate plays in the full layout, the emblem in the form; medium opens the session window straight away.
    const g = this.opener();
    const r = await invoke<Go>("go", { resume, gateOk: !!g });
    this.ops(r.ops);
    if (r.kind !== "gate" || !g) return;
    this.opening = g;
    g.open(r.note, r.uses_wt, r.title, r.sub);
    if (r.found) g.windowFound(false); // a Reidcc session window: it exists already, hidden
  }

  /** This size's opening: the gate (full), the emblem (form), none (medium). */
  opener(): Gate | null { return this.size === "full" ? this.gate : this.size === "form" ? this.emblem : null; }

  calm() { this.gate?.calm(); this.emblem?.calm(); }

  // ------------------------------------------------------------------ gate ---
  buildGate(meta: Meta | null, emblem: Meta | null) {
    const host = { say: (t: string, k: string, s?: number) => this.say(t, k, [], s), focusList: () => this.listFocus().focus() };
    if (meta) this.gate = new Gate(meta, host);
    if (emblem) this.emblem = new Gate(emblem, host, "emblem");
    // the ghost is this size's opening; medium has none, so there the buttons just open the session
    for (const [key, b] of [["go", this.bGo], ["resume", this.bResume]] as const) {
      const on = (k: string) => this.opener()?.hover(k, true);
      const off = (k: string) => { this.gate?.hover(k, false); this.emblem?.hover(k, false); };
      b.addEventListener("mouseenter", () => on(key + ":ptr"));
      b.addEventListener("mouseleave", () => off(key + ":ptr"));
      b.addEventListener("focus", () => on(key + ":focus"));
      b.addEventListener("blur", () => off(key + ":focus"));
    }
    listen<boolean>("gate-found", (e) => this.opening?.windowFound(e.payload));
    listen("gate-timeout", () => this.opening?.timeout());
  }
}

async function start() {
  setMetrics(await invoke("metrics"));
  const app = new App();
  const init = await invoke<{ ops: Op[]; folder: string; gate: Meta | null; emblem: Meta | null; test: boolean; full_min: [number, number] }>("init").catch(() => null);
  if (!init) return;
  app.fullMin = init.full_min;
  app.fit();
  app.eFolder.value = init.folder;
  app.buildGate(init.gate, init.emblem);
  listen("login-done", () => app.action("login_done"));
  listen<string>("session-note", (e) => app.say(e.payload, "quiet", [], 4)); // back from a session window
  app.ops(init.ops);
  if (init.test) (window as unknown as { __reid: unknown }).__reid = testHooks(app);
  requestAnimationFrame(() => requestAnimationFrame(() => invoke("show")));
}

/** For rs\tests\gui_parity.py and gui_shots.py (only with REIDCC_GUI_TEST=1): the same paths
 *  a click, a pick or a key takes, plus a read of what the screen shows. */
function testHooks(app: App) {
  return {
    state: () => ({
      names: app.names, sel: app.lb.sel, msg: app.msgText, title: app.pTitle.textContent, tags: app.tags.textContent,
      status: app.statusText.textContent, preview: app.previewText, name: app.eName.value, vars: app.vars(),
      choices: Object.fromEntries(Object.entries(app.cb).map(([k, c]) => [k, c.values])),
      disabled: { ...Object.fromEntries(Object.entries(app.cb).map(([k, c]) => [k, c.disabled])),
        ...Object.fromEntries(Object.entries(app.checks).map(([k, c]) => [k, c.disabled])), mode: app.radios[0].disabled },
      actions: [...app.msgActions.children].map((b) => b.textContent),
    }),
    pick: (key: string, value: string) => app.cb[key].choose(value),
    type: (key: string, value: string) => {
      const input = key === "args" ? app.eArgs : app.cb[key].input;
      input.value = value;
      input.dispatchEvent(new Event("input"));
    },
    check: (key: string) => app.checks[key].root.click(),
    radio: (i: number) => app.radios[i].root.click(),
    selectRow: (i: number) => { app.lb.select(i); app.lb.see(i); app.lb.onSelect(i); },
    rename: (text: string) => {
      app.eName.focus();
      app.eName.value = text;
      app.eName.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    },
    button: (text: string) => {
      const b = [...document.querySelectorAll<HTMLButtonElement>("button")].find((x) => x.textContent === text);
      b?.click();
      return !!b;
    },
    login: (status: string | null) => app.call("test_login", { status }),
    // this size's opening: the gate in full, the emblem in the form
    ghost: () => (app.opener() ?? app.gate)!.showGhost(),
    gateAt: (ms: number) => (app.opener() ?? app.gate)!.showAt(ms),
    dark: (title: string, sub: string) => (app.opener() ?? app.gate)!.showDark(title, sub),
    gateOff: () => { for (const g of [app.gate, app.emblem]) { g?.setAlpha(0); g?.setMode("ghost"); } },
    opening: () => app.opening && { name: app.opening.name, active: app.opening.active },
    ghostOf: () => [app.gate, app.emblem].find((g) => g && g.alpha > 0)?.name ?? null,
    hover: (on: boolean) => app.bGo.dispatchEvent(new MouseEvent(on ? "mouseenter" : "mouseleave")),
    focusList: () => app.lb.root.focus(),
    size: () => app.size,
    folderIn: (id: string) => document.getElementById(id)!.contains(app.eFolder),
    sessions: () => app.mSessions.textContent,
    combos: () => [...app.mCombos.children].map((r) => r.textContent),
    settings: () => ({ open: app.settings.isOpen, text: app.settings.root.innerText }),
  };
}

start();
