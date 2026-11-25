// The Reidcc session window (vision\SPEC-vision-v1.md §2): the real engine (reid.exe <profile> in a
// ConPTY, rs\app\src\session.rs) drawn by xterm.js under the Telemetry Bar (design doc §5, Zone 1).
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import { WebglAddon } from "@xterm/addon-webgl";
import "@xterm/xterm/css/xterm.css";
import { invoke, Channel } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { bindDock } from "./dock";

type Info = { engine: string; profile: string; folder: string; persona: string; elapsed_ms: number };
type Msg = { kind: "data"; text: string } | { kind: "exit"; rc: number; back: boolean };
type Obj = Record<string, unknown>;
type Meters = { context?: number; limit?: number | null; context_window?: Obj; rate_limits?: Obj };

const id = Number(new URLSearchParams(location.search).get("id"));
const win = getCurrentWindow();
const $ = (s: string) => document.getElementById(s)!;

function span(cls: string, text: string): HTMLSpanElement {
  const e = document.createElement("span");
  e.className = cls;
  e.textContent = text;
  return e;
}
const sep = () => span("sep", " · ");

// ---------------------------------------------------------------- terminal ---
let size = 13;
const term = new Terminal({
  fontFamily: '"Cascadia Mono", Consolas, monospace',
  fontSize: size,
  cursorBlink: true,
  scrollback: 10000,
  windowsPty: { backend: "conpty", buildNumber: 26200 },
  theme: { background: "#040404", foreground: "#D6D0C8", cursor: "#D6D0C8", cursorAccent: "#040404",
           selectionBackground: "#292723" },
});
(window as unknown as { __term: Terminal }).__term = term; // rs\tests\session_flow.py reads the screen
const fit = new FitAddon();
term.loadAddon(fit);
term.open($("xt")); // the gutter is on #term: FitAddon measures this host and counts no padding of its own
try {
  const gl = new WebglAddon();
  gl.onContextLoss(() => gl.dispose());
  term.loadAddon(gl);
} catch { /* the DOM renderer draws instead */ }

const send = (data: string) => invoke("sess_write", { id, data });
term.onData(send);
term.onResize(({ cols, rows }) => invoke("sess_resize", { id, cols, rows }));
new ResizeObserver(() => fit.fit()).observe($("xt"));

function copy() {
  const t = term.getSelection();
  if (t) navigator.clipboard.writeText(t).catch(() => {});
  term.clearSelection();
}
async function paste(raw: boolean) {
  const t = await invoke<string>("clip_text");
  if (t) term.paste(t);
  else if (raw) send("\x16"); // no text: let the engine look for an image (Claude reads the clipboard itself)
}
function zoom(by: number) {
  size = by === 0 ? 13 : Math.max(9, Math.min(24, size + by));
  term.options.fontSize = size;
  fit.fit();
}

let failed = false;
term.attachCustomKeyEventHandler((e) => {
  if (e.type !== "keydown") return true;
  if (failed) { close(null); return false; } // after a failure any key closes
  const k = e.key.toLowerCase(), plain = e.ctrlKey && !e.altKey && !e.shiftKey;
  const take = (fn: () => void) => { e.preventDefault(); fn(); return false; };
  if (e.ctrlKey && e.shiftKey && k === "c") return take(copy);
  if (e.ctrlKey && e.shiftKey && k === "v") return take(() => paste(false));
  if (plain && k === "c" && term.hasSelection()) return take(copy);
  if (plain && k === "v") return take(() => paste(true));
  if (plain && (k === "=" || k === "+")) return take(() => zoom(1));
  if (plain && k === "-") return take(() => zoom(-1));
  if (plain && k === "0") return take(() => zoom(0));
  return true;
});

// ----------------------------------------------------------- telemetry bar ---
let info: Info = { engine: "", profile: "", folder: "", persona: "", elapsed_ms: 0 };
let t0 = performance.now();
let meters: Meters = {};
let state = ""; // "" while running, then "finished" / "failed · code N"
let hover = "";

function drawWhere() {
  const w = $("where");
  w.replaceChildren(span("path", info.folder));
  const tags: [string, string][] = [["PROFILE", info.profile]];
  if (info.persona) tags.push(["PERSONA", info.persona]);
  tags.push(["ENGINE", info.engine]);
  for (const [k, v] of tags) w.append(sep(), span("tag", `${k} · ${v}`));
}

const level = (p: number) => (p >= 90 ? "m hot" : p >= 75 ? "m warn" : "m");
const num = (v: unknown) => (typeof v === "number" && isFinite(v) ? v : null);
const k = (n: number) => (n >= 1000 ? `${Math.round(n / 1000)}k` : `${Math.round(n)}`);

function clock(ms: number): string {
  const s = Math.floor(ms / 1000), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), r = s % 60;
  const two = (n: number) => String(n).padStart(2, "0");
  return h ? `${h}:${two(m)}:${two(r)}` : `${two(m)}:${two(r)}`;
}

/** `84k / 200k` for context, `resets in 3h 12m` for the limit, when the statusline gave the numbers. */
function detail(which: string): string | null {
  if (which === "context") {
    const sz = num(meters.context_window?.["context_window_size"]), p = num(meters.context);
    return sz && p !== null ? `${k((sz * p) / 100)} / ${k(sz)}` : null;
  }
  let best: Obj | null = null, top = -1;
  for (const w of ["five_hour", "seven_day"]) {
    const o = meters.rate_limits?.[w] as Obj | undefined, p = num(o?.["used_percentage"]);
    if (o && p !== null && p > top) { best = o; top = p; }
  }
  const at = best?.["resets_at"];
  const when = typeof at === "number" ? at * (at < 1e12 ? 1000 : 1) : typeof at === "string" ? Date.parse(at) : NaN;
  if (!isFinite(when)) return null;
  const mins = Math.max(0, Math.round((when - Date.now()) / 60000));
  return `resets in ${Math.floor(mins / 60)}h ${mins % 60}m`;
}

function drawMeters() {
  const m = $("meters");
  const parts: HTMLElement[] = [];
  const meter = (which: string, p: number) => {
    const d = hover === which ? detail(which) : null;
    const e = span(level(p) + (detail(which) ? " detail" : ""), d ?? `${which} ${p}%`);
    e.addEventListener("mouseenter", () => { hover = which; drawMeters(); });
    e.addEventListener("mouseleave", () => { hover = ""; drawMeters(); });
    parts.push(e);
  };
  if (num(meters.context) !== null) meter("context", meters.context!);
  if (num(meters.limit) !== null) meter("limit", meters.limit!);
  if (state) parts.push(span(state === "finished" ? "m" : "m failed", state));
  else parts.push(span("m", clock(performance.now() - t0)));
  m.replaceChildren();
  parts.forEach((p, i) => { if (i) m.append(sep()); m.append(p); });
}

// ------------------------------------------------------------------ ending ---
function close(note: string | null) {
  invoke("sess_close", { id, note });
}

function ended(rc: number, back: boolean) {
  const codex = info.engine === "codex";
  if (back) return close("Back from the session.");
  if (rc === 0) {
    state = "finished";
    drawMeters();
    setTimeout(() => close(codex ? "Back from Codex." : "Back from the session."), 1500);
    return;
  }
  state = `failed · code ${rc >>> 0} · any key closes`;
  failed = true;
  drawMeters();
}

// ------------------------------------------------------- window and shimmer ---
$("close").addEventListener("click", () => close(null));
bindDock();

let still = 0, resized = 0;
win.onResized(() => { resized = performance.now(); });
win.onMoved(() => {
  if (document.body.classList.contains("grouped") || performance.now() - resized < 60) return;
  document.body.classList.add("moving");
  clearTimeout(still);
  still = window.setTimeout(() => document.body.classList.remove("moving"), 150);
});
win.onFocusChanged(({ payload }) => { if (payload) term.focus(); });

// ------------------------------------------------------------------- start ---
async function start() {
  const ch = new Channel<Msg>();
  ch.onmessage = (m) => (m.kind === "data" ? term.write(m.text) : ended(m.rc, m.back));
  fit.fit();
  const got = await invoke<Info | null>("sess_attach", { id, chan: ch });
  if (!got) return close(null);
  info = got;
  t0 = performance.now() - info.elapsed_ms;
  drawWhere();
  drawMeters();
  invoke("sess_resize", { id, cols: term.cols, rows: term.rows });
  term.focus();
  setInterval(() => { if (!state) drawMeters(); }, 1000);
  setInterval(async () => {
    if (state) return;
    const m = await invoke<Meters | null>("sess_meters", { id });
    if (m) { meters = m; drawMeters(); }
  }, 500);
}
start();
