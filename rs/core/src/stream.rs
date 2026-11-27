//! StreamEngine (SPEC-unified-interface, Milestone 1): one headless turn of Claude Code
//! (`-p --output-format stream-json`), Codex (`exec --json`) or OpenCode (`run --format json`), as one
//! event stream. Read-only is
//! enforced by each CLI's own switches (checked against the installed claude and codex), never by
//! asking the model nicely.

use crate::engines::{self, engine_of};
use crate::{locks, profiles, proxy, remember_session, session, transcript, Ctx, Obj, ReidError};
use serde_json::{json, Value};
use std::cell::Cell;
use std::io::{BufRead, Read, Write};
use std::process::{Command, Stdio};
use windows_sys::Win32::System::Threading::{CREATE_NO_WINDOW, CREATE_SUSPENDED};

/// A tool line is one line on screen: longer ones end in "…".
const MAX_SUMMARY_CHARS: usize = 200;
/// How much of an engine's stderr an unexplained failure carries: its end, where the error is.
const MAX_STDERR_TAIL_CHARS: usize = 2000;

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Mode {
    Write,
    ReadOnly,
}

#[derive(Clone, Debug, PartialEq)]
pub enum EngineError {
    /// The engine reported it (Claude's result is_error, Codex's turn.failed / error).
    Engine { message: String },
    /// Reid stopped the turn before it ran: a lock, a bad profile, a session that isn't there.
    Refused { message: String },
    /// The engine ended badly without saying why: its exit code and the end of its stderr.
    Unknown { exit_code: i32, raw: String },
}

#[derive(Clone, Debug, PartialEq)]
pub enum Event {
    Started { session_id: String },
    TextDelta { text: String },
    ToolCall { name: String, summary: String },
    /// The end of a tool's output (`transcript::tool_tail`), for the chat's transcript only: `run` keeps it
    /// out of the stream. `tool` is its call's place among the turn's tool calls.
    ToolOutput { tool: usize, text: String },
    /// None means the engine didn't say: shown as unknown, never as 0%.
    Usage { context_pct: Option<u8>, cost_usd: Option<f64>, tokens: Option<Tokens> },
    Done { exit_code: i32 },
    Error(EngineError),
    /// One line for the chat about the turn itself (how a switch carried the conversation).
    Note { text: String },
}

/// Token counts as the engine reports them. Codex's turn.completed usage is the thread's running total:
/// a resumed turn counts the turns before it too.
#[derive(Clone, Debug, PartialEq)]
pub struct Tokens {
    /// everything sent, cached part included
    pub input: u64,
    /// the part of `input` served from the prompt cache, when the engine says
    pub cached: Option<u64>,
    pub output: u64,
}

impl Tokens {
    /// Codex's `usage` object; None unless it has both input and output counts.
    fn from_codex(usage: &Value) -> Option<Tokens> {
        Some(Tokens {
            input: usage["input_tokens"].as_u64()?,
            cached: usage["cached_input_tokens"].as_u64(),
            output: usage["output_tokens"].as_u64()?,
        })
    }

    fn to_json(&self) -> Value {
        json!({"in": self.input, "cached": self.cached, "out": self.output})
    }
}

impl From<ReidError> for EngineError {
    fn from(e: ReidError) -> Self {
        EngineError::Refused { message: e.0 }
    }
}

impl Event {
    pub fn to_json(&self) -> Value {
        match self {
            Event::Started { session_id } => json!({"type": "started", "session_id": session_id}),
            Event::TextDelta { text } => json!({"type": "text_delta", "text": text}),
            Event::ToolCall { name, summary } => json!({"type": "tool_call", "name": name, "summary": summary}),
            Event::ToolOutput { tool, text } => json!({"type": "tool_output", "tool": tool, "text": text}),
            Event::Usage { context_pct, cost_usd, tokens } => json!({"type": "usage", "context_pct": context_pct, "cost_usd": cost_usd,
                "tokens": tokens.as_ref().map(Tokens::to_json)}),
            Event::Done { exit_code } => json!({"type": "done", "exit_code": exit_code}),
            Event::Note { text } => json!({"type": "note", "text": text}),
            Event::Error(EngineError::Engine { message }) => json!({"type": "error", "kind": "engine", "message": message}),
            Event::Error(EngineError::Refused { message }) => json!({"type": "error", "kind": "refused", "message": message}),
            Event::Error(EngineError::Unknown { exit_code, raw }) => json!({"type": "error", "kind": "unknown", "exit_code": exit_code, "raw": raw}),
        }
    }
}

/// Claude Code tools that change files or run commands: gone from a read-only session (subagents too).
/// `mcp__*` takes every MCP server's tools with them, even ones the settings allow: deny wins over allow
/// (checked on claude 2.1.332: an allowed MCP tool that writes a file no longer exists in the turn).
pub const CLAUDE_WRITE_TOOLS: [&str; 7] = ["Write", "Edit", "NotebookEdit", "Bash", "PowerShell", "EnterWorktree", "mcp__*"];

/// One line of a tool call: the path, command or query it acts on.
fn summary(input: &Value) -> String {
    let full = ["file_path", "filePath", "command", "pattern", "path", "url", "query", "description"].iter()
        .find_map(|key| input.get(*key).and_then(Value::as_str).map(String::from))
        .or_else(|| input.as_str().map(String::from))
        .unwrap_or_else(|| if input.is_null() { String::new() } else { input.to_string() });
    let line = full.lines().next().unwrap_or_default();
    let mut chars = line.chars();
    let head: String = chars.by_ref().take(MAX_SUMMARY_CHARS - 1).collect();
    let rest = chars.as_str();
    // one char over would be no shorter with "…" in its place
    if rest.chars().nth(1).is_some() { head + "…" } else { head + rest }
}

/// A JSON string field as text; anything else (missing, null) is "".
fn text_of(value: &Value) -> String {
    value.as_str().unwrap_or_default().to_string()
}

/// The command a shell wrapper runs: `"…\pwsh.exe" -NoProfile -Command "git status"` -> `git status`.
/// Anything that isn't a known shell comes back as it was.
fn unwrap_shell(cmd: &str) -> String {
    let cmd = cmd.trim();
    let (exe, rest) = match cmd.strip_prefix('"') {
        Some(q) => match q.find('"') { Some(i) => (&q[..i], &q[i + 1..]), None => return cmd.into() },
        None => cmd.split_once(' ').unwrap_or((cmd, "")),
    };
    let name = exe.rsplit(['\\', '/']).next().unwrap_or(exe).to_lowercase();
    if !["pwsh", "pwsh.exe", "powershell", "powershell.exe", "cmd", "cmd.exe", "bash", "bash.exe", "sh", "zsh"].contains(&name.as_str()) {
        return cmd.into();
    }
    let mut command = rest.trim_start();
    loop {
        let (token, after) = command.split_once(' ').unwrap_or((command, ""));
        let flag = token.to_lowercase();
        if ["-command", "-c", "/c", "-lc"].contains(&flag.as_str()) {
            command = after.trim();
            break;
        }
        if !(flag.starts_with('-') || flag.starts_with('/')) || after.is_empty() {
            return cmd.into(); // not a form we know: show it whole
        }
        command = after.trim_start();
    }
    // its quotes; a cut-off or here-string command may have lost the closing one
    match command.chars().next() {
        Some(quote @ ('"' | '\'')) => {
            let inner = &command[1..];
            inner.strip_suffix(quote).unwrap_or(inner).to_string()
        }
        _ => command.to_string(),
    }
}

/// `text` with `folder\` taken off every path in it (either slash, any case): `read src\calc.py`.
fn relative(text: &str, folder: &str) -> String {
    let folder = folder.trim_end_matches(['\\', '/']);
    if folder.is_empty() {
        return text.into();
    }
    // ASCII-only folding keeps byte offsets equal between `text` and `hay`
    let fold = |path: &str| path.to_ascii_lowercase().replace('/', "\\");
    let (hay, needle) = (fold(text), fold(folder));
    let mut out = String::new();
    let mut i = 0;
    while let Some(at) = hay[i..].find(&needle).map(|a| a + i) {
        let end = at + needle.len();
        // only the whole folder: a slash after it goes too; a name going on (work -> workshop) isn't it
        match hay.as_bytes().get(end) {
            Some(b'\\') => { out.push_str(&text[i..at]); i = end + 1; }
            Some(next) if next.is_ascii_alphanumeric() || matches!(next, b'_' | b'-' | b'.') => { out.push_str(&text[i..end]); i = end; }
            _ => { out.push_str(&text[i..at]); out.push('.'); i = end; }
        }
    }
    out.push_str(&text[i..]);
    out
}

/// Turns an engine's JSON lines into events.
pub struct Parser {
    engine: String,
    /// the turn's folder: tool lines show paths inside it relative to it
    folder: String,
    context_tokens: Option<u64>, // Claude: what the last request sent, i.e. what's in the context now
    /// OpenCode: the turn's token and cost totals so far (each step_finish is one request)
    steps: (Tokens, f64),
    started: bool,
    /// the ids of the turn's tool calls, in order: an output finds its call by id (parallel calls can
    /// finish in any order)
    tools: Vec<String>,
}

impl Parser {
    pub fn new(engine: &str, folder: &str) -> Parser {
        Parser { engine: engine.into(), folder: folder.into(), context_tokens: None,
                 steps: (Tokens { input: 0, cached: Some(0), output: 0 }, 0.0), started: false, tools: vec![] }
    }

    pub fn line(&mut self, line: &str) -> Vec<Event> {
        let Ok(json) = serde_json::from_str::<Value>(line) else { return vec![] }; // banners, warnings
        let mut events = match self.engine.as_str() {
            "claude" => self.claude_line(&json),
            "opencode" => self.opencode_line(&json),
            _ => codex_line(&json, &mut self.tools),
        };
        for event in &mut events {
            if let Event::ToolCall { summary, .. } = event {
                *summary = relative(summary, &self.folder);
            }
        }
        events
    }

    fn claude_line(&mut self, json: &Value) -> Vec<Event> {
        match json["type"].as_str().unwrap_or_default() {
            "system" if json["subtype"] == "init" => vec![Event::Started { session_id: text_of(&json["session_id"]) }],
            "stream_event" if json["event"]["delta"]["type"] == "text_delta" => {
                vec![Event::TextDelta { text: text_of(&json["event"]["delta"]["text"]) }]
            }
            "assistant" => {
                let usage = &json["message"]["usage"];
                if usage.is_object() {
                    let tokens = |key: &str| usage[key].as_u64().unwrap_or(0);
                    self.context_tokens = Some(tokens("input_tokens") + tokens("cache_creation_input_tokens") + tokens("cache_read_input_tokens"));
                }
                json["message"]["content"].as_array().into_iter().flatten().filter(|block| block["type"] == "tool_use")
                    .map(|block| {
                        self.tools.push(text_of(&block["id"]));
                        Event::ToolCall { name: text_of(&block["name"]), summary: summary(&block["input"]) }
                    }).collect()
            }
            "user" => json["message"]["content"].as_array().into_iter().flatten().filter(|block| block["type"] == "tool_result")
                .filter_map(|block| {
                    let content = &block["content"]; // a string, or text blocks
                    let text = content.as_str().map(String::from).unwrap_or_else(|| {
                        content.as_array().into_iter().flatten().map(|b| text_of(&b["text"])).collect::<Vec<_>>().join("\n")
                    });
                    tool_output(&self.tools, &text_of(&block["tool_use_id"]), &text)
                }).collect(),
            "result" => {
                let window = json["modelUsage"].as_object().into_iter().flat_map(|models| models.values())
                    .filter_map(|model| model["contextWindow"].as_u64()).max().filter(|size| *size > 0);
                let context_pct = self.context_tokens.zip(window)
                    .map(|(used, size)| ((used as f64 * 100.0 / size as f64).round() as u64).min(100) as u8);
                let mut out = vec![Event::Usage { context_pct, cost_usd: json["total_cost_usd"].as_f64(), tokens: None }];
                if json["is_error"].as_bool() == Some(true) {
                    let message = Some(text_of(&json["result"])).filter(|message| !message.is_empty())
                        .or_else(|| json["errors"].as_array().map(|errors| errors.iter().map(text_of).collect::<Vec<_>>().join("; ")))
                        .filter(|message| !message.is_empty()).unwrap_or_else(|| text_of(&json["subtype"]));
                    out.push(Event::Error(EngineError::Engine { message }));
                }
                out
            }
            _ => vec![],
        }
    }

    /// OpenCode's run --format json: every line has type, sessionID and part. There's no end line: the
    /// turn ends when the process does.
    fn opencode_line(&mut self, json: &Value) -> Vec<Event> {
        let part = &json["part"];
        match json["type"].as_str().unwrap_or_default() {
            "step_start" if !self.started => {
                self.started = true;
                vec![Event::Started { session_id: text_of(&json["sessionID"]) }]
            }
            "text" => vec![Event::TextDelta { text: text_of(&part["text"]) }],
            "tool_use" => {
                let state = &part["state"];
                self.tools.push(text_of(&part["id"]));
                let output = [&state["output"], &state["error"]].into_iter().map(text_of).find(|t| !t.is_empty()).unwrap_or_default();
                let text = transcript::tool_tail(&output);
                let mut out = vec![Event::ToolCall { name: text_of(&part["tool"]), summary: summary(&state["input"]) }];
                out.extend((!text.is_empty()).then(|| Event::ToolOutput { tool: self.tools.len() - 1, text }));
                out
            }
            "step_finish" => {
                let t = &part["tokens"];
                if !t.is_object() {
                    return vec![Event::Usage { context_pct: None, cost_usd: None, tokens: None }];
                }
                let count = |v: &Value| v.as_u64().unwrap_or(0);
                let cached = count(&t["cache"]["read"]);
                let (sum, cost) = &mut self.steps;
                sum.input += count(&t["input"]) + cached + count(&t["cache"]["write"]);
                sum.cached = Some(sum.cached.unwrap_or(0) + cached);
                sum.output += count(&t["output"]) + count(&t["reasoning"]);
                *cost += part["cost"].as_f64().unwrap_or(0.0);
                let tokens = Tokens { input: sum.input, cached: sum.cached, output: sum.output };
                vec![Event::Usage { context_pct: None, cost_usd: part["cost"].as_f64().map(|_| *cost), tokens: Some(tokens) }]
            }
            "error" => {
                let error = &json["error"];
                let message = [&error["message"], &error["data"]["message"], &error["type"]].into_iter()
                    .map(text_of).find(|m| !m.is_empty()).unwrap_or_default();
                vec![Event::Error(EngineError::Engine { message })]
            }
            _ => vec![],
        }
    }
}

/// The end of tool call `id`'s output as an event; None for a call this turn didn't make, or no output.
fn tool_output(tools: &[String], id: &str, output: &str) -> Option<Event> {
    let tool = tools.iter().position(|t| t == id).filter(|_| !id.is_empty())?;
    let text = transcript::tool_tail(output);
    (!text.is_empty()).then_some(Event::ToolOutput { tool, text })
}

fn codex_line(json: &Value, tools: &mut Vec<String>) -> Vec<Event> {
    let item = &json["item"];
    let kind = (json["type"].as_str().unwrap_or_default(), item["type"].as_str().unwrap_or_default());
    if matches!(kind, ("item.started", "command_execution" | "file_change" | "mcp_tool_call") | ("item.completed", "web_search")) {
        tools.push(text_of(&item["id"])); // every tool call, so an output's place counts right
    }
    let event = match kind {
        ("thread.started", _) => Event::Started { session_id: text_of(&json["thread_id"]) },
        ("item.completed", "agent_message") => Event::TextDelta { text: text_of(&item["text"]) },
        ("item.started", "command_execution") => Event::ToolCall {
            name: "shell".into(),
            summary: summary(&Value::String(unwrap_shell(&text_of(&item["command"])))),
        },
        ("item.started", "file_change") => Event::ToolCall {
            name: "patch".into(),
            summary: item["changes"].as_array().into_iter().flatten()
                .map(|change| format!("{} {}", text_of(&change["kind"]), text_of(&change["path"]))).collect::<Vec<_>>().join(", "),
        },
        ("item.started", "mcp_tool_call") => Event::ToolCall {
            name: format!("{}.{}", text_of(&item["server"]), text_of(&item["tool"])),
            summary: summary(&item["arguments"]),
        },
        ("item.completed", "web_search") => Event::ToolCall { name: "web_search".into(), summary: text_of(&item["query"]) },
        ("item.completed", "command_execution") => return tool_output(tools, &text_of(&item["id"]), &text_of(&item["aggregated_output"])).into_iter().collect(),
        // exec --json has token counts (the thread's total so far), but no context window or cost
        ("turn.completed", _) => Event::Usage { context_pct: None, cost_usd: None, tokens: Tokens::from_codex(&json["usage"]) },
        ("turn.failed", _) => Event::Error(EngineError::Engine { message: text_of(&json["error"]["message"]) }),
        ("error", _) => Event::Error(EngineError::Engine { message: text_of(&json["message"]) }),
        _ => return vec![],
    };
    vec![event]
}

pub struct Turn<'a> {
    pub profile: &'a str,
    pub folder: &'a str,
    pub prompt: &'a str,
    pub mode: Mode,
    /// A session id to continue; None starts a new one.
    pub resume: Option<&'a str>,
    /// Switch: `.reid\handoff.md`, written and put before the prompt once the turn holds its locks
    /// (a refused switch writes nothing)
    pub switch: Option<crate::handoff::Switch<'a>>,
    /// The chat this turn belongs to: the turn goes in its transcript, and a switch carries the
    /// transcript into a new session of this turn's engine (SPEC-0.2.6 Part 2).
    pub chat: Option<&'a str>,
}

/// Run one turn, sending each event to `emit`. Ok(exit code) once the engine ran (its failures come
/// as events); Err when it was refused before starting.
pub fn run(ctx: &Ctx, cfg: &Obj, turn: &Turn, emit: &mut dyn FnMut(&Event)) -> Result<i32, EngineError> {
    let empty = Obj::new();
    let prof = profiles(cfg).get(turn.profile).and_then(Value::as_object).unwrap_or(&empty);
    let engine = engine_of(prof, turn.profile)?;
    if let Some(id) = turn.resume.filter(|id| !locks::valid_id(id)) {
        return refuse(format!("{id} isn't a session id."));
    }
    if let Some(id) = turn.chat.filter(|id| !locks::valid_id(id)) {
        return refuse(format!("{id} isn't a chat id."));
    }
    // read-only can't trust a profile that turns the engine's own guards off
    let own = crate::args(prof);
    if let Some(arg) = own.iter().find(|arg| own_guards(arg, engine)).filter(|_| turn.mode == Mode::ReadOnly) {
        return refuse(format!("Read-only can't run {} with {arg} in its args. Take it out, or use another profile.", turn.profile));
    }
    let mut launch = engines::build(ctx, cfg, turn.profile, &[], Some(turn.folder), true)?;
    let mut said = transcript::Recorder::default();
    let model = prof.get("model").and_then(Value::as_str).unwrap_or_default();
    let save = |records: &[Value], emit: &mut dyn FnMut(&Event)| {
        if let Some(Err(e)) = turn.chat.map(|chat| transcript::append(ctx, chat, records)) {
            emit(&Event::Note { text: format!("the chat transcript wasn't saved: {}", e.0) });
        }
    };
    // the ask once the engine starts (a refused turn leaves no trace, a stopped one keeps its ask), the
    // reply at the end
    let res = launch_turn(ctx, prof, turn, engine, &mut launch, &own, &mut |e: &Event| {
        if matches!(e, Event::Started { .. }) && !said.ran {
            save(&[transcript::ask_record(turn.profile, engine, model, turn.prompt)], emit);
        }
        said.push(e);
        if !matches!(e, Event::ToolOutput { .. }) {
            emit(e)
        }
    });
    launch.remove_temps();
    if said.ran {
        save(&[said.reply_record(turn.profile, engine, model)], emit);
    }
    res
}

/// A switch in a chat: the chat's transcript as a new session of `engine`, so the turn resumes the whole
/// conversation. Some(id) when the engine took it. The text is the conversation to put before the prompt
/// when it didn't, or when the engine won't resume it after all (empty when there's nothing to carry).
/// Never fails the turn.
fn carry(ctx: &Ctx, chat: &str, engine: &str, folder: &str, env: &crate::Env, emit: &mut dyn FnMut(&Event),
         native: impl Fn(&str, &[transcript::Turn], &str, &crate::Env) -> crate::R<String>) -> (Option<String>, String) {
    let all = transcript::turns(&transcript::read(ctx, chat));
    if all.is_empty() {
        return (None, String::new());
    }
    let (n, turns) = (all.len(), transcript::fit(all, transcript::budget(engine)));
    let text = format!("The conversation so far (from Reidcc's chat transcript; other agents' replies are labelled):\n\n{}\n---\n\n",
                       transcript::as_text(&turns));
    match native(engine, &turns, folder, env) {
        Ok(id) => {
            let turns = if n == 1 { "1 turn".to_string() } else { format!("{n} turns") };
            emit(&Event::Note { text: format!("context carried: {turns} in a new {engine} session") });
            (Some(id), text)
        }
        Err(e) => {
            emit(&Event::Note { text: format!("context passed as text: {engine} didn't take the session ({})", e.0) });
            (None, text)
        }
    }
}

/// A carried session's turn. Its events wait until the engine answers (text or a tool call). The engine
/// didn't resume the session when it ends first with an error, or when it names another session as it
/// starts (Codex starts an empty thread for an id it can't load: then `stop` ends it there, before it
/// does anything). Then the events are dropped (the chat never sees the dead session's id) and `retry`
/// runs the turn once, as a new session with the conversation as text. Nothing ran in the first try, so
/// nothing runs twice; a failure in the retry (sign-in, network) is the turn's own and shows as usual.
fn resume_or_retry<S>(state: &mut S, emit: &mut dyn FnMut(&Event), engine: &str, carried: &str,
                      first: impl FnOnce(&mut S, &mut dyn FnMut(&Event), &Cell<bool>) -> Result<i32, EngineError>,
                      retry: impl FnOnce(&mut S, &mut dyn FnMut(&Event)) -> Result<i32, EngineError>) -> Result<i32, EngineError> {
    let mut held = Some(vec![]);
    let stop = Cell::new(false);
    let res = first(state, &mut |e: &Event| {
        if matches!(e, Event::Started { session_id } if session_id != carried) && held.is_some() {
            stop.set(true);
        }
        if !matches!(e, Event::TextDelta { .. } | Event::ToolCall { .. }) {
            if let Some(events) = held.as_mut() {
                events.push(e.clone());
                return;
            }
        }
        for h in held.take().unwrap_or_default() {
            emit(&h);
        }
        emit(e);
    }, &stop);
    let Some(events) = held else { return res }; // it answered: everything went out as it came
    let error = events.iter().find_map(|e| if let Event::Error(error) = e { Some(Event::Error(error.clone()).to_json()) } else { None });
    let why = if stop.get() {
        "it started a new session instead".to_string()
    } else if let Some(error) = error.filter(|_| res.is_ok()) {
        error["message"].as_str().or(error["raw"].as_str()).unwrap_or_default().lines().next().unwrap_or_default().to_string()
    } else {
        for e in &events {
            emit(e);
        }
        return res;
    };
    emit(&Event::Note { text: format!("context passed as text: {engine} didn't resume the session ({why})") });
    retry(state, emit)
}

fn refuse(message: String) -> Result<i32, EngineError> {
    Err(EngineError::Refused { message })
}

/// The engine's argv for this turn, its locks and proxy, the handoff on a switch; then the turn.
fn launch_turn(ctx: &Ctx, prof: &Obj, turn: &Turn, engine: &'static str, launch: &mut engines::Launch, own: &[String],
               emit: &mut dyn FnMut(&Event)) -> Result<i32, EngineError> {
    // a switch in a chat resumes the session it carries the chat into, not the profile's old one
    let carrying = turn.chat.is_some() && turn.switch.is_some();
    // that session is new, so the folder goes first: a busy folder refuses before anything is written
    // shortcut: a proxy that fails to start after this leaves the carried session unused; it's an
    // ordinary session the engine lists, so nothing breaks
    let early_folder = if carrying && turn.mode == Mode::Write { Some(locks::folder(ctx, turn.folder, None)?) } else { None };
    let (carried, text) = match (turn.chat, &turn.switch) {
        (Some(chat), Some(_)) => carry(ctx, chat, engine, turn.folder, &launch.env, emit, transcript::native),
        _ => (None, String::new()),
    };
    // test hook, debug builds only: an engine that won't resume the carried session (switch_flow part 9)
    #[cfg(debug_assertions)]
    let carried = carried.map(|id| if std::env::var_os("REIDCC_TEST_DEAD_RESUME").is_some() { format!("{id}0") } else { id });
    let resume = if carrying { carried.as_deref() } else { turn.resume };
    if let Some(id) = resume.filter(|_| !carrying) { // a carried session was checked as it was written
        let there = match engine {
            "claude" => session::session_exists(id),
            "opencode" => engines::opencode::session_exists(&launch.env, turn.folder, id),
            _ => engines::codex::thread_exists(&launch.env, id),
        };
        if !there {
            return refuse(format!("There's no {engine} session {id} to continue."));
        }
    }
    let mode = if turn.mode == Mode::ReadOnly { "read-only" } else { "write" };
    if engine == "opencode" {
        engines::opencode::turn_agent(&mut launch.env, turn.mode == Mode::ReadOnly);
    }
    launch.env.insert("REID_PROFILE".into(), turn.profile.into());
    let base = launch.argv.clone();
    let mut sid = engine_args(prof, turn, engine, own, launch, resume);

    // the session first: "open in another window" says more than "someone's writing here"
    let lock = |sid: &Option<String>| -> Result<Option<locks::Lock>, EngineError> {
        match sid {
            Some(id) => Ok(Some(locks::session(ctx, &locks::record(id, engine, turn.profile, turn.folder, mode))?)),
            None => Ok(None), // a new Codex thread: locked once Codex names it
        }
    };
    let mut session_lock = lock(&sid)?;
    let folder_lock = match early_folder {
        Some(lock) => Some(lock),
        None if turn.mode == Mode::Write => Some(locks::folder(ctx, turn.folder, sid.as_deref())?),
        None => None,
    };
    let mut running_proxy = match proxy::plan(ctx, prof)? {
        Some(plan) => {
            let started = proxy::start(ctx, turn.profile, &plan)?;
            launch.env.extend(proxy::env(&started, engine != "claude"));
            Some(started)
        }
        None => None,
    };
    let handoff = match &turn.switch {
        Some(switch) => Some(crate::handoff::write(switch)?.1),
        None => None,
    };
    let prompt = |before: &str| {
        let ask = format!("{before}{}", turn.prompt);
        match &handoff {
            Some(md) => crate::handoff::prompt(md, &ask),
            None => ask,
        }
    };
    let go_on = Cell::new(false);
    let title_env = (engine == "opencode").then(|| launch.env.clone());
    let res = if let Some(id) = &carried {
        let mut state = (launch, sid, session_lock);
        let res = resume_or_retry(&mut state, emit, engine, id,
            |(launch, sid, session_lock), emit, stop| spawn(ctx, turn, &prompt(""), engine, launch, sid, session_lock, emit, stop),
            |(launch, sid, session_lock), emit| {
                *session_lock = None; // the dead session's
                launch.argv = base.clone();
                *sid = engine_args(prof, turn, engine, own, launch, None);
                *session_lock = lock(sid)?;
                spawn(ctx, turn, &prompt(&text), engine, launch, sid, session_lock, emit, &go_on)
            });
        (_, sid, session_lock) = state;
        res
    } else {
        spawn(ctx, turn, &prompt(&text), engine, launch, &mut sid, &mut session_lock, emit, &go_on)
    };
    proxy::stop(running_proxy.as_mut());
    drop((folder_lock, session_lock));
    let _ = remember_session(ctx, turn.profile, turn.folder, sid.as_deref(), engine);
    // a new OpenCode session (not a resumed or carried one, which has its name) is named after its ask
    if let (Some(env), Some(id), Ok(_)) = (&title_env, sid.as_deref().filter(|id| Some(*id) != resume), &res) {
        engines::opencode::set_title(env, turn.folder, id, turn.prompt);
    }
    res
}

/// The turn's flags on the engine's argv, resuming `resume` or starting a new session; the session's id
/// when it's known before the engine starts (a new Codex thread is named by Codex).
fn engine_args(prof: &Obj, turn: &Turn, engine: &str, own: &[String], launch: &mut engines::Launch, resume: Option<&str>) -> Option<String> {
    let argv = &mut launch.argv;
    match engine {
        "opencode" => {
            argv.insert(1, "run".into()); // right after the exe: --standalone and the profile's flags follow
            argv.extend(["--format", "json", "--agent", engines::opencode::TURN_AGENT].map(String::from));
            argv.extend(engines::opencode::turn_args(prof, &launch.env, turn.folder));
            if turn.mode == Mode::Write {
                argv.push("--auto".into()); // run can't ask: what the turn's agent doesn't deny is allowed
            }
            let id = resume.map(String::from).unwrap_or_else(engines::opencode::new_session_id);
            argv.extend(["--session".into(), id.clone()]); // the prompt comes on stdin
            Some(id)
        }
        "claude" => {
            argv.extend(["-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages"].map(String::from));
            if turn.mode == Mode::ReadOnly {
                argv.extend(["--permission-mode".into(), "default".into(), "--disallowedTools".into()]);
                argv.extend(CLAUDE_WRITE_TOOLS.map(String::from));
            } else {
                if !own.iter().any(|arg| arg.starts_with("--permission-mode") || arg.contains("dangerously")) {
                    argv.extend(["--permission-mode".into(), "acceptEdits".into()]); // -p can't ask, so edits are allowed up front
                }
                // edit-only (Part 6), whatever permission mode the profile brings: shell goes through open terminal,
                // so the composer's `edits · no shell` holds
                argv.extend(["--disallowedTools", "Bash", "PowerShell"].map(String::from));
            }
            let (flag, id) = match resume {
                Some(id) => ("--resume", id.to_string()),
                None => ("--session-id", uuid::Uuid::new_v4().to_string()),
            };
            argv.extend([flag.into(), id.clone()]);
            Some(id)
        }
        _ => {
            argv.extend(["exec", "--json", "--skip-git-repo-check"].map(String::from));
            let sandbox = if turn.mode == Mode::ReadOnly { Some("read-only") }
                          else if own.iter().any(|arg| own_guards(arg, "codex")) { None } // the profile chose its own
                          else { Some("workspace-write") };
            if let Some(sandbox) = sandbox {
                argv.extend(["-c".into(), format!("sandbox_mode=\"{sandbox}\"")]);
            }
            if turn.mode == Mode::ReadOnly {
                // with approvals on, Codex's auto-reviewer can wave a patch past the read-only sandbox
                argv.extend(["-c".into(), "approval_policy=\"never\"".into()]);
            }
            if let Some(id) = resume {
                argv.extend(["resume".into(), id.into()]);
            }
            argv.push("-".into()); // the prompt comes on stdin
            resume.map(String::from)
        }
    }
}

/// A profile arg that sets the engine's own permission guards (or turns them off). Matched loosely on
/// purpose: any spelling of a guard flag (`--sandbox`, `-c sandbox_mode=…`) counts. OpenCode's guards
/// are the turn's agent, so picking another agent counts too.
fn own_guards(arg: &str, engine: &str) -> bool {
    let arg = arg.to_lowercase();
    arg.contains("dangerously") || match engine {
        "claude" => arg == "bypasspermissions",
        "opencode" => arg == "--auto" || arg.starts_with("--agent"),
        _ => arg.contains("sandbox") || arg.contains("approval") || ["--yolo", "--full-auto", "-s", "-a"].contains(&arg.as_str()),
    }
}

#[allow(clippy::too_many_arguments)]
/// `stop`, once `emit` sets it, ends the engine where it is (a carried session it didn't resume).
fn spawn(ctx: &Ctx, turn: &Turn, prompt: &str, engine: &'static str, launch: &engines::Launch, sid: &mut Option<String>,
         session_lock: &mut Option<locks::Lock>, emit: &mut dyn FnMut(&Event), stop: &Cell<bool>) -> Result<i32, EngineError> {
    use std::os::windows::io::AsRawHandle;
    use std::os::windows::process::CommandExt;
    let mut child = Command::new(&launch.argv[0]).args(&launch.argv[1..]).env_clear().envs(&launch.env)
        .current_dir(turn.folder).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .creation_flags(CREATE_SUSPENDED | CREATE_NO_WINDOW).spawn().map_err(engines::io)?;
    // the engine and everything it starts die with this process, however it ends: no orphan
    // holding a session the lock says is free
    let job = crate::win::job_kill_on_close(child.as_raw_handle() as _);
    let mut stderr = child.stderr.take().expect("piped");
    let tail = std::thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = stderr.read_to_end(&mut buf);
        let text = String::from_utf8_lossy(&buf).trim().to_string();
        let start = text.char_indices().rev().nth(MAX_STDERR_TAIL_CHARS - 1).map_or(0, |(at, _)| at);
        text[start..].to_string()
    });
    // on its own thread, after the readers exist: a pipe holds ~4 KB, and an engine that writes
    // before it has read a long prompt would otherwise wait on us while we wait on it
    if let Some(mut stdin) = child.stdin.take() {
        let prompt = prompt.to_owned();
        std::thread::spawn(move || {
            let _ = stdin.write_all(prompt.as_bytes()); // fails only if the engine already quit: its exit says why
            drop(stdin); // EOF: the prompt is complete
        });
    }
    let mut parser = Parser::new(engine, turn.folder);
    let mut failed = false;
    'read: for line in std::io::BufReader::new(child.stdout.take().expect("piped")).split(b'\n').map_while(Result::ok) {
        for event in parser.line(&String::from_utf8_lossy(&line)) {
            match &event {
                Event::Started { session_id } => {
                    if sid.is_none() && locks::valid_id(session_id) {
                        *sid = Some(session_id.clone());
                        // a brand-new thread: nobody else can have it, so this can't fail
                        *session_lock = locks::session(ctx, &locks::record(session_id, engine, turn.profile, turn.folder,
                            if turn.mode == Mode::ReadOnly { "read-only" } else { "write" })).ok();
                    }
                    let _ = remember_session(ctx, turn.profile, turn.folder, sid.as_deref(), engine); // reid --resume finds it now
                }
                Event::Error(_) => failed = true,
                _ => {}
            }
            emit(&event);
            if stop.get() {
                let _ = child.kill(); // the job takes anything it started with it, below
                break 'read;
            }
        }
    }
    let code = child.wait().map_err(engines::io)?.code().unwrap_or(1);
    if let Some(job) = job {
        crate::win::job_kill(job); // anything the engine left running
    }
    let raw = tail.join().unwrap_or_default();
    if code != 0 && !failed {
        emit(&Event::Error(EngineError::Unknown { exit_code: code, raw }));
    }
    emit(&Event::Done { exit_code: code });
    Ok(code)
}

/// A turn's prompt typed as args, or stdin when there are none (or just "-").
pub fn prompt_from(args: &[String]) -> String {
    if args.is_empty() || args == ["-"] {
        let mut prompt = String::new();
        let _ = std::io::stdin().read_to_string(&mut prompt);
        return prompt;
    }
    args.join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tool_lines_unwrap_shells_and_drop_the_folder() {
        assert_eq!(unwrap_shell(r#""C:\\Program Files\\PowerShell\\7\\pwsh.exe" -NoProfile -Command "git status --short""#), "git status --short");
        assert_eq!(unwrap_shell("pwsh -Command \"@'"), "@'"); // a here-string: no closing quote
        assert_eq!(unwrap_shell("bash -lc 'ls -la'"), "ls -la");
        assert_eq!(unwrap_shell("cmd.exe /c dir"), "dir");
        assert_eq!(unwrap_shell("git diff"), "git diff");
        assert_eq!(unwrap_shell("pwsh script.ps1"), "pwsh script.ps1");
        assert_eq!(relative(r"C:\W\work\src\calc.py", r"C:\w\work"), r"src\calc.py");
        assert_eq!(relative("rg x C:/w/work/src C:/w/workshop", r"C:\w\work\"), "rg x src C:/w/workshop");
        assert_eq!(relative(r"cd C:\w\work", r"C:\w\work"), "cd .");
        assert_eq!(relative(r"Set-Location 'C:\w\work'; ls", r"C:\w\work"), "Set-Location '.'; ls");
        assert_eq!(relative("café C:\\w\\a", "C:\\w"), "café a");
    }

    fn run(engine: &str, lines: &[&str]) -> Vec<Event> {
        let mut p = Parser::new(engine, "C:\\w");
        lines.iter().flat_map(|l| p.line(l)).collect()
    }

    #[test]
    fn claude_stream_json_becomes_events() {
        let ev = run("claude", &[
            r#"{"type":"system","subtype":"hook_started","session_id":"s1"}"#,
            r#"{"type":"system","subtype":"init","session_id":"s1","tools":[]}"#,
            r#"{"type":"stream_event","event":{"type":"content_block_delta","index":0,"delta":{"type":"thinking_delta","thinking":"hm"}}}"#,
            r#"{"type":"stream_event","event":{"type":"content_block_delta","index":1,"delta":{"type":"text_delta","text":"Hi "}}}"#,
            r#"{"type":"assistant","message":{"content":[{"type":"text","text":"Hi "}],"usage":{"input_tokens":2,"cache_creation_input_tokens":410,"cache_read_input_tokens":29588}}}"#,
            r#"{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Write","input":{"file_path":"C:\\w\\hello.txt","content":"x"}}],"usage":{"input_tokens":2,"cache_creation_input_tokens":410,"cache_read_input_tokens":29588}}}"#,
            "not json",
            r#"{"type":"result","subtype":"success","is_error":false,"total_cost_usd":0.0053,"modelUsage":{"claude-haiku-5-5":{"contextWindow":200000}}}"#,
        ]);
        assert_eq!(ev, vec![
            Event::Started { session_id: "s1".into() },
            Event::TextDelta { text: "Hi ".into() },
            Event::ToolCall { name: "Write".into(), summary: "hello.txt".into() },
            Event::Usage { context_pct: Some(15), cost_usd: Some(0.0053), tokens: None },
        ]);
        // no window size, no figure: unknown, never 0%
        let ev = run("claude", &[r#"{"type":"result","is_error":true,"subtype":"error_during_execution","errors":["boom"]}"#]);
        assert_eq!(ev, vec![Event::Usage { context_pct: None, cost_usd: None, tokens: None },
                            Event::Error(EngineError::Engine { message: "boom".into() })]);
    }

    #[test]
    fn a_switch_the_engine_refuses_passes_the_chat_as_text() {
        let home = tempfile_dir();
        let ctx = Ctx::at(&home);
        let env = crate::Env::new();
        let mut notes = vec![];
        let mut emit = |e: &Event| notes.push(e.to_json()["text"].as_str().unwrap_or_default().to_string());
        // nothing in the chat yet: nothing to carry, no note
        let none = carry(&ctx, "c1", "codex", &home, &env, &mut emit, |_, _, _, _| unreachable!());
        assert_eq!(none, (None, String::new()));
        let mut rec = transcript::Recorder::default();
        rec.push(&Event::TextDelta { text: "PERIWINKLE".into() });
        transcript::append(&ctx, "c1", &[transcript::ask_record("cl", "claude", "opus", "remember the codeword"),
                                         rec.reply_record("cl", "claude", "opus")]).unwrap();
        let refused = carry(&ctx, "c1", "codex", &home, &env, &mut emit, |_, _, _, _| crate::err("format changed"));
        assert_eq!(refused.0, None);
        assert!(refused.1.contains("User: remember the codeword\n\nAssistant: [claude · opus]\nPERIWINKLE"), "{}", refused.1);
        let took = carry(&ctx, "c1", "codex", &home, &env, &mut emit, |engine, turns, _, _| Ok(format!("{engine}-{}", turns.len())));
        assert_eq!(took, (Some("codex-1".into()), refused.1.clone()), "the text comes either way: a retry needs it");
        assert_eq!(notes, ["context passed as text: codex didn't take the session (format changed)",
                           "context carried: 1 turn in a new codex session"]);
        let _ = std::fs::remove_dir_all(home);
    }

    fn tempfile_dir() -> String {
        let dir = std::env::temp_dir().join(format!("reid_carry_{}", uuid::Uuid::new_v4().simple()));
        std::fs::create_dir_all(&dir).unwrap();
        dir.to_string_lossy().into_owned()
    }

    /// One scripted try: these events, then this result.
    fn tried(events: Vec<Event>, res: Result<i32, EngineError>) -> impl FnOnce(&mut u32, &mut dyn FnMut(&Event), &Cell<bool>) -> Result<i32, EngineError> {
        move |tries, emit, stop| {
            *tries += 1;
            for e in &events {
                emit(e);
                if stop.get() {
                    return Ok(1); // spawn kills the engine there
                }
            }
            res
        }
    }

    fn started(id: &str) -> Event {
        Event::Started { session_id: id.into() }
    }

    fn failed(message: &str) -> Event {
        Event::Error(EngineError::Engine { message: message.into() })
    }

    /// (what the chat saw, as JSON types and ids, how many tries, the result)
    fn retried(first: Vec<Event>, first_res: Result<i32, EngineError>, retry: Vec<Event>, retry_res: Result<i32, EngineError>)
               -> (Vec<String>, u32, Result<i32, EngineError>) {
        let (mut seen, mut tries) = (vec![], 0);
        let res = resume_or_retry(&mut tries, &mut |e: &Event| {
            let j = e.to_json();
            seen.push(format!("{} {}", j["type"].as_str().unwrap(), j["session_id"].as_str().or(j["text"].as_str()).or(j["message"].as_str()).unwrap_or_default()));
        }, "codex", "carried", tried(first, first_res), |tries, emit| tried(retry, retry_res)(tries, emit, &Cell::new(false)));
        (seen, tries, res)
    }

    #[test]
    fn a_carried_session_that_answers_streams_as_it_comes() {
        let (seen, tries, res) = retried(
            vec![started("carried"), Event::TextDelta { text: "hi".into() }, failed("later"), Event::Done { exit_code: 1 }], Ok(1),
            vec![], Ok(0));
        assert_eq!(seen, ["started carried", "text_delta hi", "error later", "done "], "an error after it answered is the turn's own");
        assert_eq!((tries, res), (1, Ok(1)));
        // no text at all but no error (an empty reply): it went fine, nothing to retry
        let (seen, tries, _) = retried(vec![started("carried"), Event::Done { exit_code: 0 }], Ok(0), vec![], Ok(0));
        assert_eq!((seen, tries), (vec!["started carried".to_string(), "done ".to_string()], 1));
        // a tool call counts as answering too
        let (seen, tries, _) = retried(vec![started("carried"), Event::ToolCall { name: "read".into(), summary: "a".into() }], Ok(0), vec![], Ok(0));
        assert_eq!((seen.len(), tries), (2, 1));
    }

    #[test]
    fn a_carried_session_the_engine_wont_resume_runs_once_more_as_text() {
        let (seen, tries, res) = retried(
            vec![started("carried"), failed("session not found\nmore"), Event::Done { exit_code: 1 }], Ok(1),
            vec![started("fresh"), Event::TextDelta { text: "ok".into() }, Event::Done { exit_code: 0 }], Ok(0));
        // the dead session's id never reaches the chat: its next turn resumes the fresh one
        assert_eq!(seen, ["note context passed as text: codex didn't resume the session (session not found)",
                          "started fresh", "text_delta ok", "done "]);
        assert_eq!((tries, res), (2, Ok(0)));
        // the retry fails too (signed out, offline): one retry only, and its error shows
        let (seen, tries, res) = retried(vec![started("carried"), failed("offline"), Event::Done { exit_code: 1 }], Ok(1),
                                         vec![failed("offline"), Event::Done { exit_code: 1 }], Ok(1));
        assert_eq!(seen[1..], ["error offline".to_string(), "done ".to_string()]);
        assert_eq!((tries, res), (2, Ok(1)));
        // reid couldn't start the engine at all: no retry, what it said goes out
        let (seen, tries, res) = retried(vec![started("carried")], Err(EngineError::Refused { message: "no".into() }), vec![], Ok(0));
        assert_eq!((seen, tries, res), (vec!["started carried".to_string()], 1, Err(EngineError::Refused { message: "no".into() })));
        // Codex can't load the thread and starts an empty one instead: stopped at its first event, before it
        // answers or runs anything, then run once more as text
        let (seen, tries, res) = retried(
            vec![started("empty-thread"), Event::ToolCall { name: "shell".into(), summary: "rm x".into() }, Event::TextDelta { text: "Unknown".into() }], Ok(0),
            vec![started("fresh"), Event::TextDelta { text: "ok".into() }], Ok(0));
        assert_eq!(seen, ["note context passed as text: codex didn't resume the session (it started a new session instead)",
                          "started fresh", "text_delta ok"]);
        assert_eq!((tries, res), (2, Ok(0)));
    }

    #[test]
    fn opencode_run_json_becomes_events() {
        // OpenCode 2.3.0's real shapes (2026-11-27), trimmed
        let ev = run("opencode", &[
            r#"{"type":"step_start","sessionID":"ses_ab","part":{"type":"step-start"}}"#,
            r#"{"type":"tool_use","sessionID":"ses_ab","part":{"tool":"read","state":{"status":"completed","input":{"path":"C:\\w\\a.txt"},"output":"x"}}}"#,
            r#"{"type":"tool_use","sessionID":"ses_ab","part":{"tool":"edit","state":{"status":"completed","input":{"filePath":"C:\\w\\b.txt"}}}}"#,
            r#"{"type":"step_finish","sessionID":"ses_ab","part":{"reason":"tool-calls","cost":0.25,"tokens":{"input":9607,"output":39,"reasoning":1,"cache":{"read":1664,"write":0}}}}"#,
            r#"{"type":"step_start","sessionID":"ses_ab","part":{"type":"step-start"}}"#,
            r#"{"type":"text","sessionID":"ses_ab","part":{"text":"Done."}}"#,
            r#"{"type":"step_finish","sessionID":"ses_ab","part":{"reason":"stop","cost":0.5,"tokens":{"input":71,"output":3,"reasoning":0,"cache":{"read":11264,"write":0}}}}"#,
            r#"{"type":"error","sessionID":"","error":{"type":"unknown","message":"Variant unavailable"}}"#,
        ]);
        assert_eq!(ev, vec![
            Event::Started { session_id: "ses_ab".into() },
            Event::ToolCall { name: "read".into(), summary: "a.txt".into() },
            Event::ToolOutput { tool: 0, text: "x".into() },
            Event::ToolCall { name: "edit".into(), summary: "b.txt".into() },
            Event::Usage { context_pct: None, cost_usd: Some(0.25), tokens: Some(Tokens { input: 11271, cached: Some(1664), output: 40 }) },
            Event::TextDelta { text: "Done.".into() },
            // the turn's totals: every step is a request
            Event::Usage { context_pct: None, cost_usd: Some(0.75), tokens: Some(Tokens { input: 22606, cached: Some(12928), output: 43 }) },
            Event::Error(EngineError::Engine { message: "Variant unavailable".into() }),
        ]);
        assert!(own_guards("--agent=build", "opencode") && own_guards("--auto", "opencode") && !own_guards("--auto", "claude"));
    }

    #[test]
    fn tool_output_finds_its_call() {
        // Claude: two calls in one message, results back in the other order (real shape, 2026-11-27)
        let ev = run("claude", &[
            r#"{"type":"assistant","message":{"content":[{"type":"tool_use","id":"tu_a","name":"Bash","input":{"command":"npm test"}},{"type":"tool_use","id":"tu_b","name":"Read","input":{"file_path":"C:\\w\\a.txt"}}]}}"#,
            r#"{"type":"user","message":{"role":"user","content":[{"tool_use_id":"tu_b","type":"tool_result","content":[{"type":"text","text":"line one"}]}]}}"#,
            r#"{"type":"user","message":{"role":"user","content":[{"tool_use_id":"tu_a","type":"tool_result","content":"FAIL x.test\n1 failed","is_error":true}]}}"#,
            r#"{"type":"user","message":{"role":"user","content":[{"tool_use_id":"tu_gone","type":"tool_result","content":"not this turn's"}]}}"#,
        ]);
        assert_eq!(ev[2..], [Event::ToolOutput { tool: 1, text: "line one".into() }, Event::ToolOutput { tool: 0, text: "FAIL x.test\n1 failed".into() }]);
        // Codex: the output on item.completed, a profile's escapes gone; an empty output is no event
        let ev = run("codex", &[
            r#"{"type":"item.completed","item":{"id":"w","type":"web_search","query":"rust"}}"#,
            r#"{"type":"item.started","item":{"id":"item_2","type":"command_execution","command":"cargo test","aggregated_output":"","status":"in_progress"}}"#,
            r#"{"type":"item.completed","item":{"id":"item_2","type":"command_execution","command":"cargo test","aggregated_output":"\u001bP0;0;0q\"1;1#0~-\u001b\\\u001b[100m   \u001b[m\r\ntest result: FAILED\r\n","exit_code":101,"status":"completed"}}"#,
            r#"{"type":"item.started","item":{"id":"item_3","type":"command_execution","command":"true"}}"#,
            r#"{"type":"item.completed","item":{"id":"item_3","type":"command_execution","command":"true","aggregated_output":"","exit_code":0}}"#,
        ]);
        assert_eq!(ev, vec![
            Event::ToolCall { name: "web_search".into(), summary: "rust".into() },
            Event::ToolCall { name: "shell".into(), summary: "cargo test".into() },
            Event::ToolOutput { tool: 1, text: "test result: FAILED".into() },
            Event::ToolCall { name: "shell".into(), summary: "true".into() },
        ]);
        // OpenCode: a failed tool keeps its error
        let ev = run("opencode", &[r#"{"type":"tool_use","part":{"id":"c1","tool":"shell","state":{"status":"error","input":{"command":"x"},"error":"not found"}}}"#]);
        assert_eq!(ev[1], Event::ToolOutput { tool: 0, text: "not found".into() });
    }

    #[test]
    fn codex_exec_json_becomes_events() {
        let ev = run("codex", &[
            r#"{"type":"thread.started","thread_id":"019d-abc"}"#,
            r#"{"type":"item.completed","item":{"id":"i0","type":"error","message":"a config warning"}}"#,
            r#"{"type":"turn.started"}"#,
            r#"{"type":"item.started","item":{"type":"command_execution","command":"pwsh -Command \"git diff\"","status":"in_progress"}}"#,
            r#"{"type":"item.started","item":{"type":"file_change","changes":[{"path":"C:\\w\\a.txt","kind":"add"}]}}"#,
            r#"{"type":"item.completed","item":{"type":"agent_message","text":"Looks fine."}}"#,
            // codex-cli 0.172's real shape (2026-11-26)
            r#"{"type":"turn.completed","usage":{"input_tokens":19881,"cached_input_tokens":15488,"cache_write_input_tokens":0,"output_tokens":5,"reasoning_output_tokens":0}}"#,
            r#"{"type":"turn.completed","usage":{"input_tokens":88905,"output_tokens":305}}"#,
            r#"{"type":"turn.completed"}"#,
            r#"{"type":"turn.failed","error":{"message":"stream disconnected"}}"#,
        ]);
        assert_eq!(ev, vec![
            Event::Started { session_id: "019d-abc".into() },
            Event::ToolCall { name: "shell".into(), summary: "git diff".into() },
            Event::ToolCall { name: "patch".into(), summary: "add a.txt".into() },
            Event::TextDelta { text: "Looks fine.".into() },
            Event::Usage { context_pct: None, cost_usd: None, tokens: Some(Tokens { input: 19881, cached: Some(15488), output: 5 }) },
            Event::Usage { context_pct: None, cost_usd: None, tokens: Some(Tokens { input: 88905, cached: None, output: 305 }) },
            // no usage object: no counts, never zeros
            Event::Usage { context_pct: None, cost_usd: None, tokens: None },
            Event::Error(EngineError::Engine { message: "stream disconnected".into() }),
        ]);
        assert_eq!(Event::Usage { context_pct: None, cost_usd: None, tokens: None }.to_json().to_string(),
                   r#"{"type":"usage","context_pct":null,"cost_usd":null,"tokens":null}"#);
        let counted = Event::Usage { context_pct: None, cost_usd: None, tokens: Some(Tokens { input: 19881, cached: Some(15488), output: 5 }) };
        assert_eq!(counted.to_json().to_string(),
                   r#"{"type":"usage","context_pct":null,"cost_usd":null,"tokens":{"in":19881,"cached":15488,"out":5}}"#);
    }
}
