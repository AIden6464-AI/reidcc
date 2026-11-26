//! StreamEngine (SPEC-unified-interface, Milestone 1): one headless turn of Claude Code
//! (`-p --output-format stream-json`) or Codex (`exec --json`), as one event stream. Read-only is
//! enforced by each CLI's own switches (checked against the installed claude and codex), never by
//! asking the model nicely.

use crate::engines::{self, engine_of};
use crate::{locks, profiles, proxy, remember_session, session, Ctx, Obj, ReidError};
use serde_json::{json, Value};
use std::io::{BufRead, Read, Write};
use std::process::{Command, Stdio};

#[derive(Clone, Copy, PartialEq, Debug)]
pub enum Mode {
    Write,
    ReadOnly,
}

#[derive(Debug, PartialEq)]
pub enum EngineError {
    /// The engine reported it (Claude's result is_error, Codex's turn.failed / error).
    Engine { message: String },
    /// Reid stopped the turn before it ran: a lock, a bad profile, a session that isn't there.
    Refused { message: String },
    /// The engine ended badly without saying why: its exit code and the end of its stderr.
    Unknown { exit_code: i32, raw: String },
}

#[derive(Debug, PartialEq)]
pub enum Event {
    Started { session_id: String },
    TextDelta { text: String },
    ToolCall { name: String, summary: String },
    /// None means the engine didn't say: shown as unknown, never as 0%.
    Usage { context_pct: Option<u8>, cost_usd: Option<f64> },
    Done { exit_code: i32 },
    Error(EngineError),
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
            Event::Usage { context_pct, cost_usd } => json!({"type": "usage", "context_pct": context_pct, "cost_usd": cost_usd}),
            Event::Done { exit_code } => json!({"type": "done", "exit_code": exit_code}),
            Event::Error(EngineError::Engine { message }) => json!({"type": "error", "kind": "engine", "message": message}),
            Event::Error(EngineError::Refused { message }) => json!({"type": "error", "kind": "refused", "message": message}),
            Event::Error(EngineError::Unknown { exit_code, raw }) => json!({"type": "error", "kind": "unknown", "exit_code": exit_code, "raw": raw}),
        }
    }
}

/// Claude Code tools that change files or run commands: gone from a read-only session (subagents too).
pub const CLAUDE_WRITE_TOOLS: [&str; 6] = ["Write", "Edit", "NotebookEdit", "Bash", "PowerShell", "EnterWorktree"];

/// One line of a tool call: the path, command or query it acts on.
fn summary(v: &Value) -> String {
    let s = ["file_path", "command", "pattern", "path", "url", "query", "description"].iter()
        .find_map(|k| v.get(*k).and_then(Value::as_str).map(String::from))
        .or_else(|| v.as_str().map(String::from))
        .unwrap_or_else(|| if v.is_null() { String::new() } else { v.to_string() });
    let line = s.lines().next().unwrap_or_default();
    if line.chars().count() > 200 { line.chars().take(199).collect::<String>() + "…" } else { line.to_string() }
}

/// Turns an engine's JSON lines into events.
pub struct Parser {
    claude: bool,
    context_tokens: Option<u64>, // Claude: what the last request sent, i.e. what's in the context now
}

impl Parser {
    pub fn new(engine: &str) -> Parser {
        Parser { claude: engine == "claude", context_tokens: None }
    }

    pub fn line(&mut self, line: &str) -> Vec<Event> {
        let Ok(v) = serde_json::from_str::<Value>(line) else { return vec![] }; // banners, warnings
        let s = |v: &Value| v.as_str().unwrap_or_default().to_string();
        if self.claude { self.claude_line(&v, s) } else { codex_line(&v, s) }
    }

    fn claude_line(&mut self, v: &Value, s: impl Fn(&Value) -> String) -> Vec<Event> {
        match v["type"].as_str().unwrap_or_default() {
            "system" if v["subtype"] == "init" => vec![Event::Started { session_id: s(&v["session_id"]) }],
            "stream_event" if v["event"]["delta"]["type"] == "text_delta" => vec![Event::TextDelta { text: s(&v["event"]["delta"]["text"]) }],
            "assistant" => {
                let u = &v["message"]["usage"];
                if u.is_object() {
                    let n = |k: &str| u[k].as_u64().unwrap_or(0);
                    self.context_tokens = Some(n("input_tokens") + n("cache_creation_input_tokens") + n("cache_read_input_tokens"));
                }
                v["message"]["content"].as_array().into_iter().flatten().filter(|b| b["type"] == "tool_use")
                    .map(|b| Event::ToolCall { name: s(&b["name"]), summary: summary(&b["input"]) }).collect()
            }
            "result" => {
                let window = v["modelUsage"].as_object().into_iter().flat_map(|m| m.values())
                    .filter_map(|m| m["contextWindow"].as_u64()).max().filter(|w| *w > 0);
                let context_pct = self.context_tokens.zip(window)
                    .map(|(t, w)| ((t as f64 * 100.0 / w as f64).round() as u64).min(100) as u8);
                let mut out = vec![Event::Usage { context_pct, cost_usd: v["total_cost_usd"].as_f64() }];
                if v["is_error"].as_bool() == Some(true) {
                    let message = Some(s(&v["result"])).filter(|m| !m.is_empty())
                        .or_else(|| v["errors"].as_array().map(|e| e.iter().map(|x| s(x)).collect::<Vec<_>>().join("; ")))
                        .filter(|m| !m.is_empty()).unwrap_or_else(|| s(&v["subtype"]));
                    out.push(Event::Error(EngineError::Engine { message }));
                }
                out
            }
            _ => vec![],
        }
    }
}

fn codex_line(v: &Value, s: impl Fn(&Value) -> String) -> Vec<Event> {
    let item = &v["item"];
    let ev = match (v["type"].as_str().unwrap_or_default(), item["type"].as_str().unwrap_or_default()) {
        ("thread.started", _) => Event::Started { session_id: s(&v["thread_id"]) },
        ("item.completed", "agent_message") => Event::TextDelta { text: s(&item["text"]) },
        ("item.started", "command_execution") => Event::ToolCall { name: "shell".into(), summary: summary(&item["command"]) },
        ("item.started", "file_change") => Event::ToolCall {
            name: "patch".into(),
            summary: item["changes"].as_array().into_iter().flatten()
                .map(|c| format!("{} {}", s(&c["kind"]), s(&c["path"]))).collect::<Vec<_>>().join(", "),
        },
        ("item.started", "mcp_tool_call") => Event::ToolCall { name: format!("{}.{}", s(&item["server"]), s(&item["tool"])), summary: summary(&item["arguments"]) },
        ("item.completed", "web_search") => Event::ToolCall { name: "web_search".into(), summary: s(&item["query"]) },
        // exec --json has no context or cost figures
        ("turn.completed", _) => Event::Usage { context_pct: None, cost_usd: None },
        ("turn.failed", _) => Event::Error(EngineError::Engine { message: s(&v["error"]["message"]) }),
        ("error", _) => Event::Error(EngineError::Engine { message: s(&v["message"]) }),
        _ => return vec![],
    };
    vec![ev]
}

pub struct Turn<'a> {
    pub profile: &'a str,
    pub folder: &'a str,
    pub prompt: &'a str,
    pub mode: Mode,
    /// A session id to continue; None starts a new one.
    pub resume: Option<&'a str>,
}

/// Run one turn, sending each event to `emit`. Ok(exit code) once the engine ran (its failures come
/// as events); Err when it was refused before starting.
pub fn run(ctx: &Ctx, cfg: &Obj, t: &Turn, emit: &mut dyn FnMut(&Event)) -> Result<i32, EngineError> {
    let empty = Obj::new();
    let prof = profiles(cfg).get(t.profile).and_then(Value::as_object).unwrap_or(&empty);
    let engine = engine_of(prof, t.profile)?;
    let claude = engine == "claude";
    if let Some(r) = t.resume.filter(|r| !locks::valid_id(r)) {
        return refuse(format!("{r} isn't a session id."));
    }
    // read-only can't trust a profile that turns the engine's own guards off
    let own = crate::args(prof);
    if let Some(a) = own.iter().find(|a| own_guards(a, claude)).filter(|_| t.mode == Mode::ReadOnly) {
        return refuse(format!("Read-only can't run {} with {a} in its args. Take it out, or use another profile.", t.profile));
    }
    let mut launch = engines::build(ctx, cfg, t.profile, &[], Some(t.folder), true)?;
    let res = turn(ctx, prof, t, engine, &mut launch, &own, emit);
    launch.remove_temps();
    res
}

fn refuse(message: String) -> Result<i32, EngineError> {
    Err(EngineError::Refused { message })
}

fn turn(ctx: &Ctx, prof: &Obj, t: &Turn, engine: &'static str, launch: &mut engines::Launch, own: &[String],
        emit: &mut dyn FnMut(&Event)) -> Result<i32, EngineError> {
    let claude = engine == "claude";
    let mut sid = t.resume.map(String::from);
    if let Some(r) = t.resume {
        let there = if claude { session::session_exists(r) } else { engines::codex::thread_exists(&launch.env, r) };
        if !there {
            return refuse(format!("There's no {engine} session {r} to continue."));
        }
    }
    let argv = &mut launch.argv;
    let mode = if t.mode == Mode::ReadOnly { "read-only" } else { "write" };
    if claude {
        argv.extend(["-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages"].map(String::from));
        if t.mode == Mode::ReadOnly {
            argv.extend(["--permission-mode".into(), "default".into(), "--disallowedTools".into()]);
            argv.extend(CLAUDE_WRITE_TOOLS.map(String::from));
        } else if !own.iter().any(|a| a.starts_with("--permission-mode") || a.contains("dangerously")) {
            argv.extend(["--permission-mode".into(), "acceptEdits".into()]); // -p can't ask, so edits are allowed up front
        }
        match t.resume {
            Some(r) => argv.extend(["--resume".into(), r.into()]),
            None => {
                let id = uuid::Uuid::new_v4().to_string();
                argv.extend(["--session-id".into(), id.clone()]);
                sid = Some(id);
            }
        }
    } else {
        argv.extend(["exec", "--json", "--skip-git-repo-check"].map(String::from));
        let sandbox = if t.mode == Mode::ReadOnly { Some("read-only") }
                      else if own.iter().any(|a| own_guards(a, false)) { None } // the profile chose its own
                      else { Some("workspace-write") };
        if let Some(sb) = sandbox {
            argv.extend(["-c".into(), format!("sandbox_mode=\"{sb}\"")]);
        }
        if t.mode == Mode::ReadOnly {
            // with approvals on, Codex's auto-reviewer can wave a patch past the read-only sandbox
            argv.extend(["-c".into(), "approval_policy=\"never\"".into()]);
        }
        if let Some(r) = t.resume {
            argv.extend(["resume".into(), r.into()]);
        }
        argv.push("-".into()); // the prompt comes on stdin
    }
    launch.env.insert("REID_PROFILE".into(), t.profile.into());

    // the session first: "open in another window" says more than "someone's writing here"
    let mut session_lock = match &sid {
        Some(id) => Some(locks::session(ctx, &locks::record(id, engine, t.profile, t.folder, mode))?),
        None => None, // a new Codex thread: locked once Codex names it
    };
    let folder_lock = if t.mode == Mode::Write { Some(locks::folder(ctx, t.folder, sid.as_deref())?) } else { None };
    let mut px = match proxy::plan(ctx, prof)? {
        Some(plan) => {
            let p = proxy::start(ctx, t.profile, &plan)?;
            launch.env.extend(proxy::env(&p, !claude));
            Some(p)
        }
        None => None,
    };
    let res = spawn(ctx, t, engine, launch, &mut sid, &mut session_lock, emit);
    proxy::stop(px.as_mut());
    drop((folder_lock, session_lock));
    let _ = remember_session(ctx, t.profile, t.folder, sid.as_deref(), engine);
    res
}

/// A profile arg that sets the engine's own permission guards (or turns them off).
fn own_guards(a: &str, claude: bool) -> bool {
    let a = a.to_lowercase();
    a.contains("dangerously") || if claude { a == "bypasspermissions" }
        else { a.contains("sandbox") || a.contains("approval") || ["--yolo", "--full-auto", "-s", "-a"].contains(&a.as_str()) }
}

fn spawn(ctx: &Ctx, t: &Turn, engine: &'static str, launch: &engines::Launch, sid: &mut Option<String>,
         session_lock: &mut Option<locks::Lock>, emit: &mut dyn FnMut(&Event)) -> Result<i32, EngineError> {
    use std::os::windows::io::AsRawHandle;
    use std::os::windows::process::CommandExt;
    const CREATE_SUSPENDED: u32 = 0x4;
    const CREATE_NO_WINDOW: u32 = 0x0800_0000;
    let mut child = Command::new(&launch.argv[0]).args(&launch.argv[1..]).env_clear().envs(&launch.env)
        .current_dir(t.folder).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .creation_flags(CREATE_SUSPENDED | CREATE_NO_WINDOW).spawn().map_err(engines::io)?;
    // the engine and everything it starts die with this process, however it ends: no orphan
    // holding a session the lock says is free
    let job = crate::win::job_kill_on_close(child.as_raw_handle() as _);
    let mut stderr = child.stderr.take().expect("piped");
    let tail = std::thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = stderr.read_to_end(&mut buf);
        let text = String::from_utf8_lossy(&buf).trim().to_string();
        let skip = text.chars().count().saturating_sub(2000);
        text.chars().skip(skip).collect::<String>()
    });
    // on its own thread, after the readers exist: a pipe holds ~4 KB, and an engine that writes
    // before it has read a long prompt would otherwise wait on us while we wait on it
    if let Some(mut stdin) = child.stdin.take() {
        let prompt = t.prompt.to_owned();
        std::thread::spawn(move || {
            let _ = stdin.write_all(prompt.as_bytes()); // fails only if the engine already quit: its exit says why
            drop(stdin); // EOF: the prompt is complete
        });
    }
    let mut parser = Parser::new(engine);
    let mut failed = false;
    for line in std::io::BufReader::new(child.stdout.take().expect("piped")).split(b'\n').map_while(Result::ok) {
        for ev in parser.line(&String::from_utf8_lossy(&line)) {
            match &ev {
                Event::Started { session_id } => {
                    if sid.is_none() && locks::valid_id(session_id) {
                        *sid = Some(session_id.clone());
                        // a brand-new thread: nobody else can have it, so this can't fail
                        *session_lock = locks::session(ctx, &locks::record(session_id, engine, t.profile, t.folder,
                            if t.mode == Mode::ReadOnly { "read-only" } else { "write" })).ok();
                    }
                    let _ = remember_session(ctx, t.profile, t.folder, sid.as_deref(), engine); // reid --resume finds it now
                }
                Event::Error(_) => failed = true,
                _ => {}
            }
            emit(&ev);
        }
    }
    let code = child.wait().map_err(engines::io)?.code().unwrap_or(1);
    if let Some(j) = job {
        crate::win::job_kill(j); // anything the engine left running
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
        let mut s = String::new();
        let _ = std::io::stdin().read_to_string(&mut s);
        return s;
    }
    args.join(" ")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn run(engine: &str, lines: &[&str]) -> Vec<Event> {
        let mut p = Parser::new(engine);
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
            Event::ToolCall { name: "Write".into(), summary: "C:\\w\\hello.txt".into() },
            Event::Usage { context_pct: Some(15), cost_usd: Some(0.0053) },
        ]);
        // no window size, no figure: unknown, never 0%
        let ev = run("claude", &[r#"{"type":"result","is_error":true,"subtype":"error_during_execution","errors":["boom"]}"#]);
        assert_eq!(ev, vec![Event::Usage { context_pct: None, cost_usd: None }, Event::Error(EngineError::Engine { message: "boom".into() })]);
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
            r#"{"type":"turn.completed","usage":{"input_tokens":88905,"output_tokens":305}}"#,
            r#"{"type":"turn.failed","error":{"message":"stream disconnected"}}"#,
        ]);
        assert_eq!(ev, vec![
            Event::Started { session_id: "019d-abc".into() },
            Event::ToolCall { name: "shell".into(), summary: "pwsh -Command \"git diff\"".into() },
            Event::ToolCall { name: "patch".into(), summary: "add C:\\w\\a.txt".into() },
            Event::TextDelta { text: "Looks fine.".into() },
            Event::Usage { context_pct: None, cost_usd: None },
            Event::Error(EngineError::Engine { message: "stream disconnected".into() }),
        ]);
        assert_eq!(Event::Usage { context_pct: None, cost_usd: None }.to_json().to_string(),
                   r#"{"type":"usage","context_pct":null,"cost_usd":null}"#);
    }
}
