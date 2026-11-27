//! StreamEngine (SPEC-unified-interface, Milestone 1): one headless turn of Claude Code
//! (`-p --output-format stream-json`) or Codex (`exec --json`), as one event stream. Read-only is
//! enforced by each CLI's own switches (checked against the installed claude and codex), never by
//! asking the model nicely.

use crate::engines::{self, engine_of};
use crate::{locks, profiles, proxy, remember_session, session, Ctx, Obj, ReidError};
use serde_json::{json, Value};
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
fn summary(input: &Value) -> String {
    let full = ["file_path", "command", "pattern", "path", "url", "query", "description"].iter()
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
    claude: bool,
    /// the turn's folder: tool lines show paths inside it relative to it
    folder: String,
    context_tokens: Option<u64>, // Claude: what the last request sent, i.e. what's in the context now
}

impl Parser {
    pub fn new(engine: &str, folder: &str) -> Parser {
        Parser { claude: engine == "claude", folder: folder.into(), context_tokens: None }
    }

    pub fn line(&mut self, line: &str) -> Vec<Event> {
        let Ok(json) = serde_json::from_str::<Value>(line) else { return vec![] }; // banners, warnings
        let mut events = if self.claude { self.claude_line(&json) } else { codex_line(&json) };
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
                    .map(|block| Event::ToolCall { name: text_of(&block["name"]), summary: summary(&block["input"]) }).collect()
            }
            "result" => {
                let window = json["modelUsage"].as_object().into_iter().flat_map(|models| models.values())
                    .filter_map(|model| model["contextWindow"].as_u64()).max().filter(|size| *size > 0);
                let context_pct = self.context_tokens.zip(window)
                    .map(|(used, size)| ((used as f64 * 100.0 / size as f64).round() as u64).min(100) as u8);
                let mut out = vec![Event::Usage { context_pct, cost_usd: json["total_cost_usd"].as_f64() }];
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
}

fn codex_line(json: &Value) -> Vec<Event> {
    let item = &json["item"];
    let event = match (json["type"].as_str().unwrap_or_default(), item["type"].as_str().unwrap_or_default()) {
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
        // exec --json has no context or cost figures
        ("turn.completed", _) => Event::Usage { context_pct: None, cost_usd: None },
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
}

/// Run one turn, sending each event to `emit`. Ok(exit code) once the engine ran (its failures come
/// as events); Err when it was refused before starting.
pub fn run(ctx: &Ctx, cfg: &Obj, turn: &Turn, emit: &mut dyn FnMut(&Event)) -> Result<i32, EngineError> {
    let empty = Obj::new();
    let prof = profiles(cfg).get(turn.profile).and_then(Value::as_object).unwrap_or(&empty);
    let engine = engine_of(prof, turn.profile)?;
    let claude = engine == "claude";
    if let Some(id) = turn.resume.filter(|id| !locks::valid_id(id)) {
        return refuse(format!("{id} isn't a session id."));
    }
    // read-only can't trust a profile that turns the engine's own guards off
    let own = crate::args(prof);
    if let Some(arg) = own.iter().find(|arg| own_guards(arg, claude)).filter(|_| turn.mode == Mode::ReadOnly) {
        return refuse(format!("Read-only can't run {} with {arg} in its args. Take it out, or use another profile.", turn.profile));
    }
    let mut launch = engines::build(ctx, cfg, turn.profile, &[], Some(turn.folder), true)?;
    let res = launch_turn(ctx, prof, turn, engine, &mut launch, &own, emit);
    launch.remove_temps();
    res
}

fn refuse(message: String) -> Result<i32, EngineError> {
    Err(EngineError::Refused { message })
}

/// The engine's argv for this turn, its locks and proxy, the handoff on a switch; then the turn.
fn launch_turn(ctx: &Ctx, prof: &Obj, turn: &Turn, engine: &'static str, launch: &mut engines::Launch, own: &[String],
               emit: &mut dyn FnMut(&Event)) -> Result<i32, EngineError> {
    let claude = engine == "claude";
    let mut sid = turn.resume.map(String::from);
    if let Some(id) = turn.resume {
        let there = if claude { session::session_exists(id) } else { engines::codex::thread_exists(&launch.env, id) };
        if !there {
            return refuse(format!("There's no {engine} session {id} to continue."));
        }
    }
    let argv = &mut launch.argv;
    let mode = if turn.mode == Mode::ReadOnly { "read-only" } else { "write" };
    if claude {
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
        match turn.resume {
            Some(id) => argv.extend(["--resume".into(), id.into()]),
            None => {
                let id = uuid::Uuid::new_v4().to_string();
                argv.extend(["--session-id".into(), id.clone()]);
                sid = Some(id);
            }
        }
    } else {
        argv.extend(["exec", "--json", "--skip-git-repo-check"].map(String::from));
        let sandbox = if turn.mode == Mode::ReadOnly { Some("read-only") }
                      else if own.iter().any(|arg| own_guards(arg, false)) { None } // the profile chose its own
                      else { Some("workspace-write") };
        if let Some(sandbox) = sandbox {
            argv.extend(["-c".into(), format!("sandbox_mode=\"{sandbox}\"")]);
        }
        if turn.mode == Mode::ReadOnly {
            // with approvals on, Codex's auto-reviewer can wave a patch past the read-only sandbox
            argv.extend(["-c".into(), "approval_policy=\"never\"".into()]);
        }
        if let Some(id) = turn.resume {
            argv.extend(["resume".into(), id.into()]);
        }
        argv.push("-".into()); // the prompt comes on stdin
    }
    launch.env.insert("REID_PROFILE".into(), turn.profile.into());

    // the session first: "open in another window" says more than "someone's writing here"
    let mut session_lock = match &sid {
        Some(id) => Some(locks::session(ctx, &locks::record(id, engine, turn.profile, turn.folder, mode))?),
        None => None, // a new Codex thread: locked once Codex names it
    };
    let folder_lock = if turn.mode == Mode::Write { Some(locks::folder(ctx, turn.folder, sid.as_deref())?) } else { None };
    let mut running_proxy = match proxy::plan(ctx, prof)? {
        Some(plan) => {
            let started = proxy::start(ctx, turn.profile, &plan)?;
            launch.env.extend(proxy::env(&started, !claude));
            Some(started)
        }
        None => None,
    };
    let prompt = match &turn.switch {
        Some(switch) => crate::handoff::prompt(&crate::handoff::write(switch)?.1, turn.prompt),
        None => turn.prompt.to_string(),
    };
    let res = spawn(ctx, turn, &prompt, engine, launch, &mut sid, &mut session_lock, emit);
    proxy::stop(running_proxy.as_mut());
    drop((folder_lock, session_lock));
    let _ = remember_session(ctx, turn.profile, turn.folder, sid.as_deref(), engine);
    res
}

/// A profile arg that sets the engine's own permission guards (or turns them off). Matched loosely on
/// purpose: any spelling of a guard flag (`--sandbox`, `-c sandbox_mode=…`) counts.
fn own_guards(arg: &str, claude: bool) -> bool {
    let arg = arg.to_lowercase();
    arg.contains("dangerously") || if claude { arg == "bypasspermissions" }
        else { arg.contains("sandbox") || arg.contains("approval") || ["--yolo", "--full-auto", "-s", "-a"].contains(&arg.as_str()) }
}

#[allow(clippy::too_many_arguments)]
fn spawn(ctx: &Ctx, turn: &Turn, prompt: &str, engine: &'static str, launch: &engines::Launch, sid: &mut Option<String>,
         session_lock: &mut Option<locks::Lock>, emit: &mut dyn FnMut(&Event)) -> Result<i32, EngineError> {
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
    for line in std::io::BufReader::new(child.stdout.take().expect("piped")).split(b'\n').map_while(Result::ok) {
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
            Event::ToolCall { name: "shell".into(), summary: "git diff".into() },
            Event::ToolCall { name: "patch".into(), summary: "add a.txt".into() },
            Event::TextDelta { text: "Looks fine.".into() },
            Event::Usage { context_pct: None, cost_usd: None },
            Event::Error(EngineError::Engine { message: "stream disconnected".into() }),
        ]);
        assert_eq!(Event::Usage { context_pct: None, cost_usd: None }.to_json().to_string(),
                   r#"{"type":"usage","context_pct":null,"cost_usd":null}"#);
    }
}
