// The pod (vision\SPEC-vision-v1.md §1): the launcher folded into a capsule. Each running session
// is a slot in one row: engine mark, profile, ●, elapsed time and (Claude) its own ctx % and lim %;
// clicking one brings its window forward. The pod grows sideways with its slots. Alt+1 / Alt+2 or a double-click unfold it; dragging the capsule moves it.
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

type Row = {
  id: number; engine: string; profile: string; folder: string; elapsed_ms: number;
  rc: number | null; context: number | null; limit: number | null;
};

const C = { emerald: "#00C463", oxide: "#C0584B", text3: "#7F7A73" };
const MARK: Record<string, string> = { claude: "CL", codex: "CX", opencode: "OC" };
const $ = (id: string) => document.getElementById(id)!;
const cap = $("cap"), dock = $("dock"), usage = $("usage");
let rows: Row[] = [];
let width = 0;

function clock(ms: number) {
  const t = Math.floor(ms / 1000), h = Math.floor(t / 3600), m = String(Math.floor(t / 60) % 60).padStart(2, "0");
  return (h ? h + ":" : "") + m + ":" + String(t % 60).padStart(2, "0");
}

/** A slot's details: elapsed time, then Claude's context % and limit % once its statusline has written
 *  them (Codex and OpenCode don't report usage), or the exit code when it failed. */
function details(r: Row) {
  const parts = [clock(r.elapsed_ms)];
  if (r.context !== null) parts.push(`ctx ${r.context}%`);
  if (r.limit !== null) parts.push(`lim ${r.limit}%`);
  if (r.rc !== null && r.rc !== 0) parts.push(`code ${r.rc}`);
  return parts.join(" · ");
}

const span = (cls: string, text: string) => {
  const e = document.createElement("span");
  e.className = cls;
  e.textContent = text;
  return e;
};

function draw() {
  dock.replaceChildren(...rows.map((r) => {
    const s = document.createElement("div");
    s.className = "slot";
    s.title = r.folder;
    const dot = span("dot", "●");
    dot.style.color = r.rc === null ? C.emerald : r.rc === 0 ? C.text3 : C.oxide;
    s.append(span("mark", MARK[r.engine] ?? r.engine.slice(0, 2).toUpperCase()), span("name", r.profile), dot, span("st", details(r)));
    // a slot is a button, not a handle; on press, since the redraw can replace it before a click lands
    s.addEventListener("mousedown", (e) => { e.stopPropagation(); if (e.button === 0) invoke("sess_focus", { id: r.id }); });
    return s;
  }));
  usage.textContent = rows.length ? "" : "No sessions running.";
  // grow sideways with the slots, inside the round ends
  const want = Math.ceil(52 + dock.scrollWidth + (rows.length ? 0 : measure(usage.textContent) + 24));
  if (want !== width) {
    width = want;
    invoke("pod_fit", { width });
  }
}

const ctx = document.createElement("canvas").getContext("2d")!;
function measure(text: string) {
  ctx.font = getComputedStyle(usage).font;
  return ctx.measureText(text).width;
}

/** `force`: poll even while hidden (on load, and on fold, which emits before it shows the pod). */
async function poll(force = false) {
  if (document.hidden && !force) return; // folded away: nothing to show
  rows = await invoke<Row[]>("sess_list").catch(() => rows);
  draw();
}

// Drag to move; a second press soon after the first unfolds instead.
let lastDown = 0;
cap.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  const now = performance.now();
  if (now - lastDown < 350) {
    lastDown = 0;
    invoke("pod_unfold", { size: "main" });
    return;
  }
  lastDown = now;
  invoke("pod_drag");
});

window.addEventListener("keydown", (e) => {
  if (e.altKey && !e.ctrlKey && (e.code === "Digit1" || e.code === "Digit2")) {
    e.preventDefault();
    invoke("pod_unfold", { size: e.code === "Digit1" ? "main" : "small" });
  }
});

// Fold in: fade the capsule up (the design doc's 150 ms, no bounce).
listen("pod-shown", () => {
  cap.classList.add("in");
  poll(true);
  requestAnimationFrame(() => requestAnimationFrame(() => cap.classList.remove("in")));
});

poll(true);
setInterval(poll, 1000);
(window as unknown as { __pod: unknown }).__pod = { rows: () => rows, usage: () => usage.textContent, slots: () => dock.children.length, details };
