// The chat window (vision\Spec\SPEC-unified-interface.md Part 6): one folder, one composer over Claude
// Code and Codex. Each turn is `reid --stream` (rs\app\src\chat.rs); its events land here as they come.
import { invoke, Channel } from "@tauri-apps/api/core";
import { getCurrentWindow } from "@tauri-apps/api/window";

type Info = { folder: string; shown: string; profile: string; profiles: [string, string][] };
type Ev = { type: string; [k: string]: unknown };
type Out = { kind: "event"; event: Ev } | { kind: "exit"; rc: number; stopped: boolean; err: string };
type FileStat = { path: string; added: number | null; removed: number | null };
type Changed = { from: string; to: string; files: FileStat[] };

const id = Number(new URLSearchParams(location.search).get("id"));
const win = getCurrentWindow();
const $ = <T extends HTMLElement = HTMLElement>(s: string) => document.getElementById(s) as T;
function el<K extends keyof HTMLElementTagNameMap>(tag: K, cls = "", text = ""): HTMLElementTagNameMap[K] {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text) e.textContent = text;
  return e;
}

const col = $("col"), stream = $("stream"), field = $<HTMLTextAreaElement>("field"), pick = $<HTMLSelectElement>("pick");
const go = $<HTMLButtonElement>("go"), ro = $("ro"), note = $("note");

let info: Info = { folder: "", shown: "", profile: "", profiles: [] };
const engines: Record<string, string> = {};
/** the profile the conversation is with; the picker can point elsewhere (then send is a switch) */
let cur = "";
/** each profile's session in this window: the next turn with it continues that one */
const sids: Record<string, string> = {};
let turns = 0, readOnly = false, running = false, began = 0, tick = 0;
let context: number | null | undefined, cost = 0;
/** the held session the note is waiting on, and its poll */
let waitSid = "", poll = 0;
const engine = (p: string) => engines[p] ?? "claude";

// ---------------------------------------------------------------- the bar ---
const pad = (n: number) => String(n).padStart(2, "0");
const ctxText = () => context == null ? "context unknown" : `context ${Math.round(context)}%`;
function bar(): void {
  const where = $("where");
  where.replaceChildren(el("b", "", info.shown), document.createTextNode(`  ${cur} · ${engine(cur)}${readOnly ? " · read-only" : ""}`));
  const m = $("meters");
  if (running) {
    const s = Math.floor((Date.now() - began) / 1000);
    const live = el("span", "live", `● ${pad(Math.floor(s / 60))}:${pad(s % 60)}`);
    m.replaceChildren(live, document.createTextNode(" · "), meterCtx());
  } else {
    m.replaceChildren(document.createTextNode("ready · "), meterCtx());
  }
}
function meterCtx(): HTMLSpanElement {
  const c = el("span", context != null && context >= 90 ? "hot" : context != null && context >= 75 ? "warn" : "", ctxText());
  return c;
}
$("min").onclick = () => win.minimize();
$("max").onclick = () => win.toggleMaximize();
$("close").onclick = () => win.close();

// ------------------------------------------------------------- the stream ---
const atBottom = () => stream.scrollHeight - stream.scrollTop - stream.clientHeight < 40;
function keep(f: () => void): void {
  const stick = atBottom();
  f();
  if (stick) stream.scrollTop = stream.scrollHeight;
}

/** the turn being drawn */
let t: { reply: HTMLElement; tools: HTMLElement; text: HTMLElement | null; caret: HTMLElement; sawText: boolean; ro: boolean; undo: () => void } | null = null;

function ask(profile: string, q: string, undo: () => void): void {
  col.querySelector(".empty")?.remove();
  const a = el("div", "ask");
  a.append(el("span", "who", `${profile} · ${engine(profile)} ›`), el("span", "q", q));
  const reply = el("div", "reply");
  const tools = el("div", "tools");
  const caret = el("span", "caret");
  reply.append(tools, caret);
  keep(() => col.append(a, reply));
  t = { reply, tools, text: null, caret, sawText: false, ro: readOnly, undo };
}

function onEvent(e: Ev, profile: string): void {
  if (!t) return;
  const tt = t;
  keep(() => {
    switch (e.type) {
      case "started":
        sids[profile] = String(e.session_id);
        field.value = "";
        sideSessions();
        break;
      case "text_delta":
        if (!tt.text) {
          tt.text = el("div", "text");
          tt.reply.insertBefore(tt.text, tt.caret);
        }
        tt.text.textContent += String(e.text ?? "");
        tt.sawText = true;
        break;
      case "tool_call": {
        // a tool after text starts a new paragraph below it
        if (tt.text) {
          tt.tools = el("div", "tools");
          tt.reply.insertBefore(tt.tools, tt.caret);
          tt.text = null;
        }
        const line = el("div", "tool");
        line.append(el("b", "", String(e.name ?? "").toLowerCase()), el("span", "", String(e.summary ?? "")));
        tt.tools.append(line);
        break;
      }
      case "usage":
        context = e.context_pct as number | null;
        if (typeof e.cost_usd === "number") cost = e.cost_usd;
        sideContext();
        bar();
        break;
      case "error":
        onError(e);
        break;
    }
  });
}

/** reid's errors: a lock refusal becomes the composer's note; the rest go in the stream */
function onError(e: Ev): void {
  const msg = String(e.message ?? e.raw ?? "");
  if (e.kind === "refused") {
    if (/open in another window/.test(msg)) {
      const sid = sids[pickedProfile()] ?? "";
      showNote("in terminal", "This session is open in a terminal.", [["focus terminal", focusTerminal]]);
      if (sid) waitFree(sid);
    } else if (/window is open in this folder/.test(msg)) {
      showNote("locked", "A Reidcc window is open in this folder.", [["focus window", focusTerminal], ["send read-only", sendReadOnly]]);
    } else if (/turn is writing/i.test(msg)) {
      showNote("locked", "Another turn is writing in this folder.", [["send read-only", sendReadOnly]]);
    } else {
      showNote("refused", msg, []);
    }
    // nothing ran: the ask stays in the field, and a refused switch isn't one
    t?.reply.previousElementSibling?.remove();
    t?.reply.remove();
    t?.undo();
    t = null;
    bar();
    sideSessions();
    return;
  }
  if (t) t.reply.insertBefore(el("div", "fail", e.kind === "unknown" ? `${engine(cur)} ended (${e.exit_code}).${msg ? "\n" + msg : ""}` : msg), t.caret);
}

function showNote(lbl: string, text: string, acts: [string, () => void][]): void {
  const parts: HTMLElement[] = [el("span", "lbl", lbl), el("span", "", text)];
  for (const [label, f] of acts) {
    const b = el("button", "act", label);
    b.onclick = f;
    parts.push(b);
  }
  note.replaceChildren(...parts);
  note.hidden = false;
}
function clearNote(): void {
  note.hidden = true;
  note.replaceChildren();
  waitSid = "";
  clearInterval(poll);
}

/** the session is held by another window: the note stays until it lets go */
function waitFree(sid: string): void {
  clearInterval(poll);
  waitSid = sid;
  poll = window.setInterval(async () => {
    if (waitSid !== sid) return;
    if (!(await invoke("chat_holder", { sid }))) clearNote();
  }, 1500);
}

async function focusTerminal(): Promise<void> {
  await invoke("chat_focus", { id });
}
function sendReadOnly(): void {
  setReadOnly(true);
  clearNote();
  void send();
}

function meta(stopped: boolean, rc: number): void {
  if (!t) return;
  const s = Math.round((Date.now() - began) / 1000);
  const bits = stopped ? ["stopped"] : [`${pad(Math.floor(s / 60))}:${pad(s % 60)}`, ctxText()];
  if (!stopped && cost > 0) bits.push(`$${cost.toFixed(cost < 1 ? 3 : 2)}`);
  if (!stopped) bits.push(t.ro ? "read-only" : "edit-only");
  if (!stopped && rc !== 0 && !t.reply.querySelector(".fail")) bits.push(`exit ${rc}`);
  t.reply.append(el("div", "meta", bits.join(" · ")));
}

async function changedBlock(reply: HTMLElement): Promise<void> {
  const c = await invoke<Changed | null>("chat_changed", { id }).catch(() => null);
  if (!c || !c.files.length) return;
  const box = el("div", "changed shut");
  const add = c.files.reduce((n, f) => n + (f.added ?? 0), 0), del = c.files.reduce((n, f) => n + (f.removed ?? 0), 0);
  const head = el("button", "head");
  head.append(el("span", "", `changed · ${c.files.length} file${c.files.length === 1 ? "" : "s"}`),
              el("span", "plus", `+${add}`), el("span", "minus", `−${del}`), el("span", "tw", "▸"));
  head.onclick = () => {
    box.classList.toggle("shut");
    head.lastElementChild!.textContent = box.classList.contains("shut") ? "▸" : "▾";
  };
  box.append(head);
  for (const f of c.files) {
    const row = el("button", "file");
    const n = el("span", "n");
    n.append(el("span", "plus", f.added == null ? "bin" : `+${f.added}`), document.createTextNode(" "),
             el("span", "minus", f.removed == null ? "" : `−${f.removed}`));
    row.append(el("span", "", f.path), n);
    let d: HTMLElement | null = null;
    row.onclick = async () => {
      if (d) { d.remove(); d = null; return; }
      const text = await invoke<string>("chat_file_diff", { id, from: c.from, to: c.to, path: f.path }).catch(String);
      d = el("div", "diff");
      for (const line of text.split("\n")) {
        d.append(el("div", line.startsWith("@@") ? "h" : line.startsWith("+") ? "a" : line.startsWith("-") ? "d" : "", line || " "));
      }
      row.after(d);
    };
    box.append(row);
  }
  keep(() => reply.insertBefore(box, reply.querySelector(".meta")));
}

function divider(from: string, to: string): HTMLElement {
  const d = el("div", "switch");
  const link = el("button", "link", ".reid/handoff.md");
  link.onclick = () => invoke("chat_handoff", { id });
  d.append(el("span", "", `switch · ${engine(from)} → ${engine(to)}`), el("span", "t3", "·"), link);
  keep(() => col.append(d));
  $("hsec").hidden = false;
  const h = el("button", "link", "open");
  h.onclick = () => invoke("chat_handoff", { id });
  const row = el("div", "kv");
  row.append(el("span", "", `${from} → ${to}`), el("span", "r t3"), h);
  $("handoff").replaceChildren(row);
  return d;
}

// ----------------------------------------------------------- the sidebar ---
function sideSessions(): void {
  const rows = info.profiles.filter(([p]) => sids[p] || p === cur).map(([p, e]) => {
    const r = el("div", p === cur ? "row sel" : "row");
    r.append(el("span", "", `${p} · ${e}`), el("span", "r", sids[p] ? sids[p].slice(0, 8) : "new"));
    return r;
  });
  $("sessions").replaceChildren(...rows);
}
function sideContext(): void {
  const kv = (k: string, v: string) => {
    const r = el("div", "kv");
    r.append(el("span", "", k), el("span", "r", v));
    return r;
  };
  $("context").replaceChildren(kv("context", context == null ? "unknown" : `${Math.round(context)}%`),
                               kv("cost", cost > 0 ? `$${cost.toFixed(3)}` : "—"), kv("turns", String(turns)));
}

// ----------------------------------------------------------- the composer ---
const pickedProfile = () => pick.value || cur;
const switching = () => pickedProfile() !== cur && turns > 0;
function setReadOnly(on: boolean): void {
  readOnly = on;
  ro.querySelector(".m")!.textContent = on ? "✓" : "·";
  bar();
}
function primary(): void {
  if (running) {
    go.textContent = "stop";
    go.className = "btn stop";
    go.disabled = false;
  } else {
    go.textContent = switching() ? `switch → ${engine(pickedProfile())}` : "send";
    go.className = "btn primary";
    go.disabled = !field.value.trim();
  }
  pick.disabled = running;
  field.placeholder = `Ask ${pickedProfile()}…`;
}

async function send(): Promise<void> {
  const prompt = field.value.trim();
  if (running || !prompt) return;
  const profile = pickedProfile();
  const from = switching() ? cur : null;
  clearNote();
  running = true;
  began = Date.now();
  context = undefined;
  cost = 0;
  const prev = cur, div = from ? divider(from, profile) : null;
  cur = profile;
  ask(profile, prompt, () => { cur = prev; div?.remove(); });
  const turnRo = readOnly;
  primary();
  bar();
  tick = window.setInterval(bar, 1000);
  const chan = new Channel<Out>();
  chan.onmessage = (m) => {
    if (m.kind === "event") return onEvent(m.event, profile);
    void finish(m, turnRo);
  };
  try {
    await invoke("chat_send", { id, profile, prompt, readOnly: turnRo, resume: sids[profile] ?? null, switchFrom: from, chan });
  } catch (e) {
    void finish({ kind: "exit", rc: 1, stopped: false, err: String(e) }, turnRo);
  }
}

async function finish(m: Extract<Out, { kind: "exit" }>, turnRo: boolean): Promise<void> {
  clearInterval(tick);
  const reply = t?.reply;
  if (t) {
    t.caret.remove();
    // reid itself failed (bad args, a crash): nothing streamed, so its stderr says why
    if (m.err && !m.stopped && !t.sawText && !t.reply.querySelector(".fail")) t.reply.insertBefore(el("div", "fail", m.err), t.tools.nextSibling);
    meta(m.stopped, m.rc);
    turns++;
  }
  t = null;
  if (reply && !turnRo) await changedBlock(reply); // still running till then: the turn ends with its diff
  running = false;
  sideSessions();
  sideContext();
  primary();
  bar();
  field.focus();
}

go.onclick = () => (running ? void invoke("chat_stop", { id }) : void send());
ro.onclick = () => setReadOnly(!readOnly);
pick.onchange = () => primary();
field.oninput = () => primary();
field.onkeydown = (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    void send();
  }
};
$("term").onclick = () => invoke("chat_terminal", { id, profile: pickedProfile(), sid: sids[pickedProfile()] ?? null });

// ------------------------------------------------------------------ start ---
(async () => {
  info = await invoke<Info>("chat_info", { id });
  for (const [p, e] of info.profiles) {
    engines[p] = e;
    const o = el("option", "", `${p} · ${e}`);
    o.value = p;
    pick.append(o);
  }
  cur = info.profile;
  pick.value = cur;
  document.title = `chat · ${info.shown}`;
  col.append(el("div", "empty", `${info.shown} · ask ${cur} anything. Write turns are edit-only; open terminal for shell and tests.`));
  sideSessions();
  sideContext();
  primary();
  bar();
  field.focus();
})();

// rs\tests\chat_flow.py drives and reads the window through this
(window as unknown as { __chat: object }).__chat = {
  state: () => ({ cur, sids: { ...sids }, turns, running, readOnly, context, note: note.hidden ? "" : note.textContent,
                  primary: go.textContent, picked: pickedProfile() }),
  type: (s: string) => { field.value = s; primary(); },
  pick: (p: string) => { pick.value = p; primary(); },
  readOnly: (on: boolean) => setReadOnly(on),
  click: (sel: string) => (document.querySelector(sel) as HTMLElement | null)?.click(),
};
