// The Tk widgets the launcher uses, drawn the way Tk (clam theme) draws them on Windows:
// tk.Label, tk.Button, tk.Entry, tk.Listbox + ttk Scrollbar, ttk Combobox with its drop-down,
// ttk Checkbutton / Radiobutton. Sizes are Tk's (python\reid_gui.py at 1000x880).

export const C = {
  canvas: "#040404", s1: "#0E0D0C", s2: "#171513", stone: "#292723",
  line: "#2A2724", line2: "#4A4540", linework: "#928A82",
  text: "#D6D0C8", text2: "#9F978E", text3: "#746F69",
  emerald: "#00C463", bronze: "#C99A45", oxide: "#C0584B",
};

export const FONT = {
  title: "20px " + "var(--ui)", head: "16px var(--ui)", body: "14px var(--ui)", btn: "13px var(--ui)",
  label: "13px var(--ui)", mono: "12px var(--mono)", tag: "11px var(--mono)",
};

const UI_FAMS = 'Inter, Geist, "Segoe UI Variable Text", "Segoe UI", Helvetica, "Lucida Sans Unicode", sans-serif';
const MONO_FAMS = '"Geist Mono", "JetBrains Mono", "Cascadia Mono", Consolas, Menlo, monospace';
const ctx2d = document.createElement("canvas").getContext("2d")!;

type Role = keyof typeof FONT;
let GDI: Record<string, Record<string, number>> | null = null;

function dwWidth(text: string, role: Role): number {
  const px = FONT[role].split("px")[0];
  ctx2d.font = `${px}px ${FONT[role].includes("mono") ? MONO_FAMS : UI_FAMS}`;
  return ctx2d.measureText(text).width;
}

/** Text width in px for a font role, as Tk's `font measure` gives it: GDI's whole-pixel advances. */
export function measure(text: string, role: Role): number {
  const t = GDI?.[role];
  if (!t) return Math.round(dwWidth(text, role));
  let w = 0;
  for (const ch of text) w += t[ch] ?? Math.round(dwWidth(ch, role));
  return w;
}

const ROLE_BY_SIZE: Record<string, Role> = { "20": "title", "16": "head", "14": "body", "13": "btn", "12": "mono", "11": "tag" };

/** Put each character of a UI-font text where Tk puts it: WebView2 lays text out with DirectWrite's
 *  fractional advances, Tk with GDI's whole-pixel ones (no kerning). Each character gets a box as wide
 *  as its GDI advance, so every glyph starts on Tk's pixel. (Mono text only needs one fixed
 *  letter-spacing per size, set in CSS.) The text itself (textContent) stays the same. */
function fit(e: HTMLElement) {
  if (e.classList.contains("ch")) return;
  const text = e.textContent || "";
  if (!text) return; // nothing to fit; an emptied row may hold the form's place-markers (main.ts put())
  if (e.dataset.fit === text && e.querySelector(":scope > .ch")) return; // already done
  if (e.children.length && !e.querySelector(":scope > .ch")) return;     // not a text leaf
  const cs = getComputedStyle(e);
  const role = ROLE_BY_SIZE[parseFloat(cs.fontSize).toString()];
  if (!role || role === "mono" || role === "tag" || cs.fontFamily.includes("Mono")) return;
  const frag = document.createDocumentFragment();
  for (const ch of text) {
    if (ch === "\n") { frag.append("\n"); continue; }
    const s = document.createElement("span");
    s.className = "ch";
    s.textContent = ch;
    s.style.width = measure(ch, role) + "px";
    frag.append(s);
  }
  e.dataset.fit = text;
  e.replaceChildren(frag);
}

/** Tk centres a widget in its cell with whole-pixel (floor) maths; CSS centring can leave it on a
 *  half pixel, which the text then rounds down a row. Pull such widgets up the half pixel. */
export function snap() {
  document.querySelectorAll<HTMLElement>("#root .lbl, #root .check, #root .btn, #root .combo, #root input").forEach((e) => {
    const cur = parseFloat(e.style.top || "0");
    const frac = (((e.getBoundingClientRect().top - cur) % 1) + 1) % 1;
    const want = Math.abs(frac - 0.5) < 0.01 ? -0.5 : 0;
    if (want !== cur) {
      e.style.position = want ? "relative" : "";
      e.style.top = want ? want + "px" : "";
    }
  });
  // tk.Button centres its text with whole-pixel maths too: leave the odd pixel right and below
  document.querySelectorAll<HTMLElement>(".btn").forEach((e) => {
    const r = (e.clientWidth - measure(e.textContent || "", "btn")) % 2 ? "1px" : "";
    const b = (e.clientHeight - 17) % 2 ? "1px" : "";
    if (e.style.paddingRight !== r) e.style.paddingRight = r;
    if (e.style.paddingBottom !== b) e.style.paddingBottom = b;
  });
}

/** Load Tk's GDI widths (from Rust) and keep every UI-font text spaced to them. Call before building. */
export function setMetrics(m: { widths: Record<string, Record<string, number>> }) {
  GDI = m.widths;
  // mono: one fixed correction per size (every glyph has the same advance), for inputs too
  const root = document.documentElement.style;
  root.setProperty("--ls12", (measure("0", "mono") - dwWidth("0", "mono")).toFixed(4) + "px");
  root.setProperty("--ls11", (measure("0", "tag") - dwWidth("0", "tag")).toFixed(4) + "px");
  const todo = new Set<HTMLElement>();
  let queued = false;
  const flush = () => { queued = false; todo.forEach((e) => e.isConnected && fit(e)); todo.clear(); snap(); };
  const add = (n: Node | null) => {
    const e = n instanceof HTMLElement ? n : n?.parentElement;
    if (!e) return;
    todo.add(e);
    e.querySelectorAll<HTMLElement>("*").forEach((c) => { if (c.firstChild instanceof Text) todo.add(c); });
    if (!queued) { queued = true; queueMicrotask(flush); }
  };
  new MutationObserver((ms) => ms.forEach((m) => {
    if (m.type === "characterData") add(m.target);
    else { add(m.target); m.addedNodes.forEach(add); }
  })).observe(document.body, { subtree: true, childList: true, characterData: true });
  window.addEventListener("resize", () => requestAnimationFrame(snap));
}

/** Tk's word wrap for a label with -wraplength: break at spaces; a word longer than the line
 *  breaks where it stops fitting. Returns the lines joined with \n. */
export function wrap(text: string, width: number, role: Role): string {
  const out: string[] = [];
  for (const para of text.split("\n")) {
    let line = "";
    const words = para.split(/(?<= )/); // keep the space with the word before it
    for (const w of words) {
      if (line && measure((line + w).trimEnd(), role) > width) {
        out.push(line.trimEnd());
        line = "";
      }
      let word = w;
      while (!line && measure(word.trimEnd(), role) > width && word.trimEnd().length > 1) {
        let n = word.length - 1;
        while (n > 1 && measure(word.slice(0, n), role) > width) n--;
        out.push(word.slice(0, n));
        word = word.slice(n);
      }
      line += word;
    }
    out.push(line.trimEnd());
  }
  return out.join("\n");
}

export function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text = ""): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}

/** tk.Label */
export function label(text: string, fg: keyof typeof C = "text", font: keyof typeof FONT = "body", widthChars = 0): HTMLDivElement {
  const d = el("div", `lbl f-${font} c-${fg}`, text);
  if (widthChars) d.style.width = widthChars * measure("0", font) + 6 + "px"; // width= is in average chars
  return d;
}

/** tk.Button: width = text + 2*padx + 5 (Tk's inset on Windows), 34 px tall. */
export function button(text: string, cmd: () => void, primary = false): HTMLButtonElement {
  const b = el("button", "btn" + (primary ? " primary" : ""), text);
  b.style.width = measure(text, "btn") + 2 * (primary ? 22 : 12) + 5 + "px";
  b.addEventListener("mousedown", (e) => e.preventDefault()); // Tk buttons don't take focus on click
  b.addEventListener("click", () => cmd());
  return b;
}

/** tk.Entry (mono) */
export function entry(): HTMLInputElement {
  const e = el("input", "entry");
  e.spellcheck = false;
  e.autocomplete = "off";
  return e;
}

// ------------------------------------------------------------------ listbox ---
export const ROW = 17; // Tk listbox line: linespace 16 + 1

/** A vertical ttk scrollbar for a row list. */
export class Scrollbar {
  root = el("div", "sb");
  thumb = el("div", "thumb");
  constructor(private onScroll: (delta: number, page?: boolean, frac?: number) => void) {
    const up = el("div", "up"), down = el("div", "down");
    up.append(el("i")); down.append(el("i"));
    this.root.append(up, this.thumb, down);
    up.addEventListener("mousedown", (e) => { e.preventDefault(); this.onScroll(-1); });
    down.addEventListener("mousedown", (e) => { e.preventDefault(); this.onScroll(1); });
    this.root.addEventListener("mousedown", (e) => {
      if (e.target !== this.root) return;
      e.preventDefault();
      const r = this.thumb.getBoundingClientRect();
      this.onScroll(e.clientY < r.top ? -1 : 1, true);
    });
    this.thumb.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const y0 = e.clientY, top0 = this.thumb.offsetTop;
      const move = (ev: MouseEvent) => {
        const trough = this.root.clientHeight - 2 * 14;
        this.onScroll(0, false, (top0 - 14 + ev.clientY - y0) / trough);
      };
      const up = () => { window.removeEventListener("mousemove", move); window.removeEventListener("mouseup", up); };
      window.addEventListener("mousemove", move);
      window.addEventListener("mouseup", up);
    });
  }
  /** first/last as fractions, like Tk's `set first last` */
  set(first: number, last: number) {
    const h = this.root.clientHeight; // inside the 1 px border
    const trough = h - 2 * 14; // between the arrow boxes (their borders overlap ours)
    const top = 14 + Math.round(first * trough), bot = 14 + Math.round(last * trough);
    this.thumb.style.top = top - 1 + "px";
    this.thumb.style.height = Math.max(bot - top + 2, 10) + "px";
  }
}

/** tk.Listbox (browse mode) with its scrollbar: whole-row scrolling, Tk's `see`. */
export class Listbox {
  box = el("div");
  root = el("div", "lb");
  rows = el("div", "rows");
  sb: Scrollbar;
  items: string[] = [];
  sel = -1;
  top = 0;
  onSelect: (i: number) => void = () => {};

  constructor(cls = "") {
    if (cls) this.root.classList.add(cls);
    this.box.style.cssText = "display:flex;flex:1;min-height:0";
    this.root.tabIndex = 0;
    this.root.append(this.rows);
    this.sb = new Scrollbar((d, page, frac) => {
      if (frac !== undefined) this.scrollTo(Math.round(frac * this.items.length));
      else this.scrollTo(this.top + d * (page ? this.fullLines() : 1));
    });
    this.box.append(this.root, this.sb.root);
    this.root.addEventListener("mousedown", (e) => {
      this.root.focus();
      const pick = (ev: MouseEvent) => {
        const r = this.rows.getBoundingClientRect();
        const i = this.top + Math.floor((ev.clientY - r.top) / ROW);
        if (i >= 0 && i < this.items.length && i !== this.sel) { this.select(i); this.onSelect(i); }
      };
      pick(e);
      const up = () => { window.removeEventListener("mousemove", pick); window.removeEventListener("mouseup", up); };
      window.addEventListener("mousemove", pick);
      window.addEventListener("mouseup", up);
    });
    this.root.addEventListener("wheel", (e) => { e.preventDefault(); this.scrollTo(this.top + Math.sign(e.deltaY) * 4); });
    this.root.addEventListener("keydown", (e) => {
      const n = this.items.length;
      let i = -1;
      if (e.key === "ArrowUp") i = Math.max(0, this.sel - 1);
      else if (e.key === "ArrowDown") i = Math.min(n - 1, this.sel + 1);
      else if (e.key === "Home" && e.ctrlKey) i = 0;
      else if (e.key === "End" && e.ctrlKey) i = n - 1;
      else if (e.key === "PageUp" || e.key === "PageDown") {
        this.scrollTo(this.top + (e.key === "PageUp" ? -1 : 1) * this.fullLines());
        e.preventDefault();
        return;
      }
      if (i >= 0 && n) {
        e.preventDefault();
        this.see(i);
        if (i !== this.sel) { this.select(i); this.onSelect(i); }
      }
    });
    new ResizeObserver(() => this.paint()).observe(this.root);
  }

  fullLines() { return Math.max(1, Math.floor(this.root.clientHeight / ROW)); }

  set(items: string[]) {
    this.items = items;
    this.sel = -1;
    this.rows.replaceChildren(...items.map((t) => el("div", "row", t)));
    this.paint();
  }

  select(i: number) {
    this.sel = i;
    [...this.rows.children].forEach((r, k) => r.classList.toggle("sel", k === i));
  }

  scrollTo(top: number) {
    this.top = top;
    this.paint();
  }

  /** Tk's ListboxSeeCmd: near the view -> scroll the least; far -> centre it. */
  see(i: number) {
    const full = this.fullLines();
    let diff = this.top - i;
    if (diff > 0) this.top = diff <= Math.floor(full / 3) ? i : i - Math.floor((full - 1) / 2);
    else {
      diff = i - (this.top + full - 1);
      if (diff > 0) this.top = diff <= Math.floor(full / 3) ? this.top + diff : i - Math.floor((full - 1) / 2);
    }
    this.paint();
  }

  paint() {
    const n = this.items.length, full = this.fullLines();
    this.top = Math.max(0, Math.min(this.top, n - full));
    this.rows.style.top = -this.top * ROW + "px";
    this.sb.set(n ? this.top / n : 0, n ? Math.min(1, (this.top + full) / n) : 1);
  }
}

// ----------------------------------------------------------------- combobox ---
let openPop: { close: () => void } | null = null;
export function closePopups() { openPop?.close(); }

/** A floating list under a widget (the combobox drop-down): Tk's popdown, up to 10 rows. */
function popdown(anchor: HTMLElement, values: string[], current: string, choose: (v: string) => void, onClose: () => void) {
  closePopups();
  const r = anchor.getBoundingClientRect();
  const pop = el("div", "popdown");
  const lb = new Listbox();
  lb.root.style.border = "0";
  lb.root.style.background = C.s2;
  lb.root.tabIndex = -1;
  const shown = Math.min(values.length, 10);
  const h = shown * ROW + 2;
  pop.style.left = r.left + "px";
  pop.style.width = r.width + "px";
  pop.style.height = h + "px";
  pop.style.top = (r.bottom + h > window.innerHeight && r.top - h >= 0 ? r.top - h : r.bottom) + "px";
  pop.append(lb.box);
  if (values.length <= 10) lb.sb.root.style.display = "none";
  document.body.append(pop);
  lb.set(values);
  const i = values.indexOf(current);
  if (i >= 0) { lb.select(i); lb.see(i); }
  // Tk's popdown follows the pointer with its selection, and a click picks
  lb.root.addEventListener("mousemove", (e) => {
    const k = lb.top + Math.floor((e.clientY - lb.rows.getBoundingClientRect().top) / ROW);
    if (k >= 0 && k < values.length) lb.select(k);
  });
  lb.onSelect = () => {};
  const close = () => {
    pop.remove();
    window.removeEventListener("mousedown", outside, true);
    window.removeEventListener("keydown", keys, true);
    openPop = null;
    onClose();
  };
  lb.root.addEventListener("mouseup", () => { const v = values[lb.sel]; close(); if (v !== undefined) choose(v); });
  const outside = (e: MouseEvent) => { if (!pop.contains(e.target as Node)) { e.stopPropagation(); e.preventDefault(); close(); } };
  const keys = (e: KeyboardEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (e.key === "Escape") close();
    else if (e.key === "Enter" || e.key === "Tab") { const v = values[lb.sel]; close(); if (v !== undefined) choose(v); }
    else if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      const k = Math.max(0, Math.min(values.length - 1, lb.sel + (e.key === "ArrowDown" ? 1 : -1)));
      lb.select(k); lb.see(k);
    }
  };
  setTimeout(() => window.addEventListener("mousedown", outside, true));
  window.addEventListener("keydown", keys, true);
  openPop = { close };
}

/** ttk.Combobox: readonly (pick only) or editable (type or pick). */
export class Combo {
  root = el("div", "combo");
  input = el("input");
  values: string[] = [];
  readonly: boolean;
  disabled = false;
  onChange: () => void = () => {};

  constructor(readonly: boolean, short = false) {
    this.readonly = readonly;
    if (short) this.root.classList.add("short");
    const arrow = el("div", "arrow");
    arrow.append(el("i"));
    this.input.spellcheck = false;
    this.input.autocomplete = "off";
    this.root.append(this.input, arrow);
    this.setReadonly(readonly);
    this.input.addEventListener("focus", () => this.root.classList.add("focus"));
    this.input.addEventListener("blur", () => this.root.classList.remove("focus"));
    this.input.addEventListener("input", () => this.onChange()); // Tk: every write of the variable saves
    const post = (e: MouseEvent) => {
      if (this.disabled || e.button !== 0) return;
      e.preventDefault();
      this.input.focus();
      if (openPop) { closePopups(); return; }
      this.post();
    };
    arrow.addEventListener("mousedown", post);
    this.input.addEventListener("mousedown", (e) => { if (this.readonly) post(e); });
    this.input.addEventListener("keydown", (e) => {
      if (this.disabled) return;
      if (e.key === "ArrowDown" && !openPop) { e.preventDefault(); this.post(); }
    });
    // ttk::combobox::Scroll: the wheel steps through the values
    this.root.addEventListener("wheel", (e) => {
      e.preventDefault();
      if (this.disabled) return;
      const max = this.values.length;
      const cur = this.values.indexOf(this.input.value) + Math.sign(e.deltaY);
      if (max !== 0 && cur >= 0 && cur < max) this.choose(this.values[cur]);
    });
  }

  post() { popdown(this.root, this.values, this.input.value, (v) => this.choose(v), () => {}); }

  choose(v: string) {
    this.input.value = v;
    this.onChange();
  }

  get value() { return this.input.value; }
  set value(v: string) { this.input.value = v; }

  setReadonly(on: boolean) {
    this.readonly = on;
    this.input.readOnly = on || this.disabled;
    this.root.classList.toggle("readonly", on);
  }

  setDisabled(on: boolean) {
    this.disabled = on;
    this.input.readOnly = on || this.readonly;
    this.input.tabIndex = on ? -1 : 0;
    this.root.classList.toggle("disabled", on);
  }
}

// ------------------------------------------------------ check / radio boxes ---
// The clam indicators, pixel for pixel (11x11): a = border, b = indicator background, f = mark.
const CHECK = [
  "aaaaaaaaaaa", "abbbbbbbbba", "abffbbbffba", "abfffbfffba", "abbfffffbba", "abbbfffbbba",
  "abbfffffbba", "abfffbfffba", "abffbbbffba", "abbbbbbbbba", "aaaaaaaaaaa",
];
const RADIO = [
  "....aaa....", "..aabbbaa..", ".abbbbbbba.", ".abbfffbbba", "abbfffffbba", "abbfffffbba",
  "abbfffffbba", ".abbfffbba.", ".abbbbbbba.", "..abbbbaa..", "...aaaa....",
];

function indicator(pat: string[], a: string, b: string, f: string): string {
  let rects = "";
  pat.forEach((row, y) => [...row].forEach((ch, x) => {
    const c = ch === "a" ? a : ch === "b" ? b : ch === "f" ? f : "";
    if (c) rects += `<rect x="${x}" y="${y}" width="1" height="1" fill="${c}"/>`;
  }));
  return `url("data:image/svg+xml,${encodeURIComponent(`<svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" shape-rendering="crispEdges">${rects}</svg>`)}")`;
}

/** ttk.Checkbutton or ttk.Radiobutton, styled as reid_gui.py's _style() maps them. */
export class Check {
  root = el("div", "check");
  ind = el("div", "ind");
  txt = el("span", "txt");
  on = false;
  disabled = false;
  hover = false;
  onClick: () => void = () => {};

  constructor(text: string, private radio = false) {
    this.txt.textContent = text;
    this.root.tabIndex = 0;
    this.root.append(this.ind, this.txt);
    this.root.addEventListener("click", () => { if (!this.disabled) this.onClick(); });
    this.root.addEventListener("keydown", (e) => {
      if (e.key === " " && !this.disabled) { e.preventDefault(); this.onClick(); }
    });
    this.root.addEventListener("mouseenter", () => { this.hover = true; this.paint(); });
    this.root.addEventListener("mouseleave", () => { this.hover = false; this.paint(); });
    this.paint();
  }

  set text(t: string) { this.txt.textContent = t; }

  set(on: boolean) { this.on = on; this.paint(); }

  setDisabled(on: boolean) {
    this.disabled = on;
    this.root.tabIndex = on ? -1 : 0;
    this.root.classList.toggle("disabled", on);
    this.paint();
  }

  paint() {
    const d = this.disabled, s = this.on;
    // indicatorbackground: disabled+selected line2, disabled canvas, selected text, active s2, else s1
    const b = d && s ? C.line2 : d ? C.canvas : s ? C.text : this.hover ? C.s2 : C.s1;
    // indicatorforeground: disabled+selected s1, selected canvas, else s1
    const f = d && s ? C.s1 : s ? C.canvas : C.s1;
    const a = d ? C.line : C.line2;
    this.ind.style.background = indicator(this.radio ? RADIO : CHECK, a, b, f);
  }
}
