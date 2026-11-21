// The gate (SPEC-gate.md), as reid_gui.py's `Gate` draws it, but as a layer in the launcher
// window instead of Tk's separate layered window:
// - ghost: the gate's blueprint lines at GHOST strength, see-through and click-through, on hover;
// - gate: the full art, which rises out of its lines, ignites and opens while the session starts;
//   the view pushes through the lit passage into the dark, and the session window appears there.
import { invoke } from "@tauri-apps/api/core";
import { C, el } from "./widgets";

export interface Meta { size: [number, number]; bg: string; key: string; tag: [number, number]; steps: [string, number, number, number][] }

const GHOST = 0.14;
export const PACE = 1.375; // the opening's speed: 10% slower, then 25% slower again (Reid, 2026-11-17)
const ASSETS = "http://reid.localhost/assets/";

function ease(t: number) { return 1 - (1 - t) ** 3; } // fast start, soft stop, no overshoot

export interface Host {
  say(text: string, kind: string, seconds?: number): void;
  focusList(): void;
}

export class Gate {
  root = el("div");
  canvas = el("canvas");
  tag = el("div", "gtxt f-tag");
  head = el("div", "gtxt f-mono");
  subhead = el("div", "gtxt f-tag");
  g = this.canvas.getContext("2d")!;
  images = new Map<string, ImageBitmap | null>();
  loading = new Map<string, Promise<ImageBitmap | null>>();
  flags = new Map<string, boolean>();
  timers: number[] = [];
  alpha = 0;
  mode: "ghost" | "gate" | null = null;
  current = "";
  active = false;
  done = false;
  usesWt = false;
  found = false;
  dark = false;
  note = "";
  title = "";
  sub = "";
  t0 = 0;
  x0 = 0;
  y0 = 0;
  private fadeJob = 0;
  private hoverJob = 0;
  private gen = 0;

  constructor(public meta: Meta, private host: Host) {
    this.root.id = "gate";
    this.head.style.color = C.text2;
    this.subhead.style.color = C.text3;
    this.root.append(this.canvas, this.tag, this.head, this.subhead);
    document.body.append(this.root);
    this.root.addEventListener("mousedown", () => this.skip());
    new ResizeObserver(() => this.place()).observe(document.body);
    window.addEventListener("blur", () => this.calm());
    document.addEventListener("visibilitychange", () => { if (document.hidden) this.calm(); });
    this.setMode("ghost");
    this.place();
    setTimeout(() => this.resident().forEach((n) => this.load(n)), 250);
  }

  // -- frames
  frames(step: string): string[] {
    const n = this.meta.steps.find((s) => s[0] === step)![1];
    return Array.from({ length: n }, (_, i) => step + String(i).padStart(2, "0"));
  }

  /** The ghost, the closed gate and the steps before the last stay loaded; the last step's frames
   *  load while the gate is hovered or the first steps play, and are freed after. */
  resident(): string[] {
    return ["ghost", "gate", ...this.meta.steps.slice(0, -1).flatMap((s) => this.frames(s[0]))];
  }

  warm() {
    const gen = this.gen;
    for (const n of this.frames(this.meta.steps[this.meta.steps.length - 1][0])) if (gen === this.gen) this.load(n);
  }

  cool() {
    this.gen++;
    for (const n of this.frames(this.meta.steps[this.meta.steps.length - 1][0])) {
      this.images.get(n)?.close();
      this.images.delete(n);
      this.loading.delete(n);
    }
  }

  load(name: string): Promise<ImageBitmap | null> {
    if (this.images.has(name)) return Promise.resolve(this.images.get(name)!);
    const busy = this.loading.get(name);
    if (busy) return busy;
    const rel = name === "ghost" ? "gate_ghost.png" : name === "gate" ? "gate.png" : `gate_${name.slice(0, -2)}/${name.slice(-2)}.png`;
    const gen = this.gen;
    const p = fetch(ASSETS + rel).then((r) => (r.ok ? r.blob() : null)).then(async (b) => {
      if (!b) return null;
      let bmp = await createImageBitmap(b);
      if (name === "ghost") bmp = await this.keyed(bmp); // the key colour is see-through
      return bmp;
    }).catch(() => null).then((bmp) => {
      if (gen === this.gen || !name.startsWith("open")) this.images.set(name, bmp);
      this.loading.delete(name);
      if (this.current === name) this.draw(name);
      return bmp;
    });
    this.loading.set(name, p);
    return p;
  }

  /** Tk's -transparentcolor: pixels of exactly the key colour vanish. */
  private async keyed(bmp: ImageBitmap): Promise<ImageBitmap> {
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const g = c.getContext("2d")!;
    g.drawImage(bmp, 0, 0);
    const d = g.getImageData(0, 0, bmp.width, bmp.height);
    const k = parseInt(this.meta.key.slice(1), 16), kr = k >> 16, kg = (k >> 8) & 255, kb = k & 255;
    for (let i = 0; i < d.data.length; i += 4) {
      if (d.data[i] === kr && d.data[i + 1] === kg && d.data[i + 2] === kb) d.data[i + 3] = 0;
    }
    g.putImageData(d, 0, 0);
    return createImageBitmap(c);
  }

  draw(name: string) {
    this.current = name;
    const bmp = this.images.get(name);
    if (bmp === undefined) { this.load(name); return; }
    this.g.clearRect(0, 0, this.canvas.width, this.canvas.height);
    if (bmp) this.g.drawImage(bmp, this.x0, this.y0);
  }

  // -- drawing
  setMode(mode: "ghost" | "gate") {
    if (mode === this.mode) return;
    this.mode = mode;
    this.root.classList.toggle("solid", mode === "gate");
    if (mode === "ghost") {
      this.draw("ghost");
      for (const t of [this.tag, this.head, this.subhead]) t.textContent = "";
    } else this.draw("gate");
  }

  place() {
    const w = document.documentElement.clientWidth, h = document.documentElement.clientHeight;
    if (this.canvas.width !== w || this.canvas.height !== h) { this.canvas.width = w; this.canvas.height = h; }
    const [iw, ih] = this.meta.size;
    this.x0 = Math.floor((w - iw) / 2);
    this.y0 = Math.floor((h - ih) / 2);
    // canvas text anchor "e": right edge at x, centred on y (one 15 px line)
    this.tag.style.right = w - (this.x0 + this.meta.tag[0]) + "px";
    // Tk: anchor e centres the 15 px line with whole pixels (y - 7); GDI sets Cascadia Mono a pixel lower than WebView2
    this.tag.style.top = this.y0 + this.meta.tag[1] - 7 + 1 + "px";
    this.head.style.left = "24px"; this.head.style.top = "21px"; // where the terminal's first line will be
    this.subhead.style.left = "24px"; this.subhead.style.top = "45px"; // 20 / 44 in Tk, +1 as above
    if (this.current) this.draw(this.current);
  }

  setTag(text: string, color: string) {
    this.tag.textContent = text;
    this.tag.style.color = color;
  }

  setAlpha(a: number) {
    this.alpha = a;
    this.root.style.opacity = String(a);
    this.root.style.display = a > 0 ? "block" : "none";
  }

  fade(to: number, ms: number, then?: () => void) {
    cancelAnimationFrame(this.fadeJob);
    this.fadeJob = 0;
    const start = this.alpha, t0 = performance.now();
    const step = () => {
      const t = ms > 0 ? Math.min(1, (performance.now() - t0) / ms) : 1;
      this.setAlpha(start + (to - start) * ease(t));
      if (t < 1) this.fadeJob = requestAnimationFrame(step);
      else { this.fadeJob = 0; then?.(); }
    };
    step();
  }

  // -- the ghost
  /** key: which control (pointer or focus on open gate / resume). Ghost while any is on. */
  hover(key: string, on: boolean) {
    if (this.active) return;
    this.flags.set(key, on);
    clearTimeout(this.hoverJob);
    this.hoverJob = 0;
    if ([...this.flags.values()].some(Boolean)) {
      this.hoverJob = window.setTimeout(() => { // sweeping past the button doesn't flash it
        this.hoverJob = 0;
        this.setMode("ghost");
        this.place();
        this.fade(GHOST, 140);
        this.warm(); // a press is likely: get the opening ready
      }, 60);
    } else this.fade(0, 120);
  }

  /** The launcher lost focus (alt-tab, a dialog): no ghost left hanging over it. */
  calm() {
    if (this.active) return;
    this.flags.clear();
    this.cool();
    clearTimeout(this.hoverJob);
    this.hoverJob = 0;
    this.fade(0, 120);
  }

  // -- opening the gate
  /** The session already started (Rust launched it); play the opening over it. */
  open(note: string, usesWt: boolean, title: string, sub: string) {
    clearTimeout(this.hoverJob);
    cancelAnimationFrame(this.fadeJob);
    this.hoverJob = this.fadeJob = 0;
    this.flags.clear();
    this.note = note; this.usesWt = usesWt; this.title = title; this.sub = sub;
    this.active = true; this.done = false; this.found = false; this.dark = false;
    this.t0 = performance.now();
    (document.activeElement as HTMLElement | null)?.blur(); // keys now skip instead of typing into a field
    const steps = this.meta.steps; // rise, ignite, open: [name, frames, start ms, ms]
    this.warm(); // if not hovered first: loads while rise and ignite play
    this.setMode("gate");
    this.draw(this.frames(steps[0][0])[0]);
    this.place();
    this.setTag("REIDCC · OPENING", C.bronze);
    this.fade(1, steps[0][3] * PACE); // 1. the window solidifies while the gate rises
    for (const [name, , start, dur] of steps) this.play(this.frames(name), start, dur); // 2. ignite, 3. open
    const end = steps[steps.length - 1][2] + steps[steps.length - 1][3];
    if (usesWt) this.at(end, () => this.inTheDark()); // 4. the session window appears in the dark
    else {
      this.at(end, () => this.setTag("REIDCC · READY", C.text2));
      this.at(end + 300, () => this.fade(0, 180 * PACE, () => this.finish()));
    }
  }

  /** Run fn at ms (design timing, scaled by PACE) after the press, on schedule even if a frame ran late. */
  at(ms: number, fn: () => void) {
    const delay = ms * PACE - (performance.now() - this.t0);
    this.timers.push(window.setTimeout(fn, Math.max(0, Math.floor(delay))));
  }

  play(names: string[], start: number, dur: number) {
    names.forEach((n, i) => this.at(start + (dur * i) / names.length, () => this.draw(n)));
  }

  /** The watcher found the new terminal window (READY is real: the window exists). */
  windowFound(handed: boolean) {
    this.found = true;
    if (handed || !this.active) return;
    this.setTag("REIDCC · READY", C.text2);
    this.maybeHandoff();
  }

  inTheDark() {
    this.dark = true;
    if (!this.found) {
      this.head.textContent = this.title + " · opening…";
      this.subhead.textContent = this.sub;
    }
    this.maybeHandoff();
  }

  /** 5. The real terminal window is shown over the launcher, out of the dark. */
  maybeHandoff() {
    if (!(this.active && this.dark && this.found) || this.done) return;
    this.done = true;
    this.handOver();
    this.timers.push(window.setTimeout(() => this.fade(0, 180 * PACE, () => this.finish()), Math.floor(150 * PACE))); // 6. return
  }

  timeout() {
    if (!this.active) return;
    this.fade(0, 180 * PACE, () => this.finish("The session window didn't appear. It may still be starting.", "info"));
  }

  /** Any key or click: straight to the end. Exactly one session either way. */
  skip() {
    if (!this.active) return;
    if (this.found) this.host.focusList();
    invoke("gate_skip");
    this.done = true;
    this.finish();
  }

  finish(note?: string, kind = "quiet") {
    if (!this.active) return;
    this.active = false;
    for (const t of this.timers) clearTimeout(t);
    this.timers = [];
    cancelAnimationFrame(this.fadeJob);
    this.fadeJob = 0;
    this.setAlpha(0);
    this.setMode("ghost");
    this.cool();
    invoke("gate_finish");
    this.host.say(note || this.note, kind, 4);
    if (!this.found) this.host.focusList();
  }

  /** The session window to the front. Focus moves first: focusing afterwards would pull the
   *  keyboard back to the launcher. */
  handOver() {
    this.host.focusList();
    invoke("gate_handover");
  }

  // -- test hooks (gui_shots.py): the opening as it looks at `ms` after the press, held still
  async showAt(ms: number, ghostFirst = true) {
    for (const n of [...this.resident(), ...this.frames(this.meta.steps[this.meta.steps.length - 1][0])]) await this.load(n);
    const steps = this.meta.steps;
    this.setMode("gate");
    this.place();
    const t = ms / PACE; // design time
    let frame = this.frames(steps[0][0])[0];
    for (const [name, n, start, dur] of steps) {
      for (let i = 0; i < n; i++) if (start + (dur * i) / n <= t) frame = this.frames(name)[i];
    }
    this.draw(frame);
    const end = steps[steps.length - 1][2] + steps[steps.length - 1][3];
    const rise = steps[0][3] * PACE, from = ghostFirst ? GHOST : 0;
    this.setAlpha(from + (1 - from) * ease(Math.min(1, ms / rise)));
    this.setTag(t >= end ? "REIDCC · READY" : "REIDCC · OPENING", t >= end ? C.text2 : C.bronze);
  }

  showDark(title: string, sub: string) {
    this.showAt((this.meta.steps[2][2] + this.meta.steps[2][3]) * PACE, true).then(() => {
      this.setTag("REIDCC · OPENING", C.bronze);
      this.head.textContent = title + " · opening…";
      this.subhead.textContent = sub;
    });
  }

  async showGhost() {
    await this.load("ghost");
    this.setMode("ghost");
    this.place();
    this.setAlpha(GHOST);
  }
}
