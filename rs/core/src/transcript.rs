//! The full context switch (SPEC-0.2.6 Part 2): Reidcc keeps one transcript per chat, and a switch writes
//! it into the next engine's own session format as a new session, so that engine resumes the whole chat
//! as its own history. Plain code, no model: the same transcript always gives the same session.

use crate::stream::Event;
use crate::{engines, err, py, session, Ctx, Env, R};
use serde_json::{json, Map, Value};
use std::io::{BufRead, Write};
use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

/// The carried conversation fits in this share of the target engine's window...
const WINDOW_SHARE_PCT: usize = 60;
/// ...counted at this many characters per token.
const CHARS_PER_TOKEN: usize = 4;
const ASK_TIMEOUT: Duration = Duration::from_secs(15);
/// Claude Code names a folder's session folder after its path up to this length, and its own way past it.
const CLAUDE_SLUG_MAX: usize = 200;

/// `<REIDCC_HOME>\chats\<chat>.jsonl`. The id is checked like a session id: it becomes a file name.
fn path(ctx: &Ctx, chat: &str) -> R<String> {
    if !crate::locks::valid_id(chat) {
        return err(format!("{chat} isn't a chat id."));
    }
    Ok(py::join(&ctx.home, &["chats", &format!("{chat}.jsonl")]))
}

/// A new chat's id (each chat window makes one).
pub fn new_chat_id() -> String {
    uuid::Uuid::new_v4().to_string()
}

/// Add records to the chat's transcript.
pub fn append(ctx: &Ctx, chat: &str, records: &[Value]) -> R<()> {
    let path = path(ctx, chat)?;
    std::fs::create_dir_all(py::dirname(&path)).map_err(engines::io)?;
    let mut file = std::fs::OpenOptions::new().create(true).append(true).open(&path).map_err(engines::io)?;
    let lines: String = records.iter().map(|r| format!("{r}\n")).collect();
    file.write_all(lines.as_bytes()).map_err(engines::io)
}

/// The chat's records, oldest first; none when there's no transcript yet.
pub fn read(ctx: &Ctx, chat: &str) -> Vec<Value> {
    let Ok(path) = path(ctx, chat) else { return vec![] };
    std::fs::read_to_string(path).unwrap_or_default().lines().filter_map(|l| serde_json::from_str(l).ok()).collect()
}

fn record(role: &str, profile: &str, engine: &str, model: &str, body: (&str, Value)) -> Value {
    let mut r = Map::new();
    for (k, v) in [("role", role), ("profile", profile), ("engine", engine), ("model", model)] {
        r.insert(k.into(), v.into());
    }
    r.insert(body.0.into(), body.1);
    Value::Object(r)
}

/// What was asked. Written when the engine starts, so a turn that's stopped mid-way keeps its ask.
pub fn ask_record(profile: &str, engine: &str, model: &str, ask: &str) -> Value {
    record("user", profile, engine, model, ("text", ask.into()))
}

/// One turn's reply as the stream saw it: its text and tool lines, in order.
#[derive(Default)]
pub struct Recorder {
    parts: Vec<Value>,
    pub ran: bool,
}

impl Recorder {
    pub fn push(&mut self, event: &Event) {
        match event {
            Event::Started { .. } => self.ran = true,
            Event::TextDelta { text } => match self.parts.last_mut().and_then(|p| p.get_mut("text")) {
                Some(Value::String(last)) => last.push_str(text),
                _ => self.parts.push(json!({"text": text})),
            },
            Event::ToolCall { name, summary } => self.parts.push(json!({"tool": name, "summary": summary})),
            Event::ToolOutput { tool, text } => {
                if let Some(part) = self.parts.iter_mut().filter(|p| p.get("tool").is_some()).nth(*tool) {
                    part["output"] = json!(text);
                }
            }
            _ => {}
        }
    }

    /// The reply, written when the turn ends.
    pub fn reply_record(self, profile: &str, engine: &str, model: &str) -> Value {
        record("assistant", profile, engine, model, ("parts", Value::Array(self.parts)))
    }
}

/// How much of a tool's output the transcript keeps: the end, where the errors and failed tests are.
pub const TOOL_TAIL: usize = 2048;

/// A tool's output for the transcript: terminal escapes (colours, a shell profile's sixel logo) and control
/// characters out, each line as it was last redrawn (`\r` progress bars), then its last TOOL_TAIL bytes, cut
/// on a char boundary.
pub fn tool_tail(output: &str) -> String {
    let mut plain = String::new();
    let mut chars = output.chars().peekable();
    while let Some(c) = chars.next() {
        match c {
            '\u{1b}' => match chars.next() {
                Some('[') => {
                    for c in chars.by_ref() {
                        if ('@'..='~').contains(&c) {
                            break; // a CSI ends on its final byte
                        }
                    }
                }
                Some(']' | 'P' | 'X' | '^' | '_') => {
                    // a string (OSC, DCS: sixel): up to BEL or ST (ESC \)
                    while let Some(c) = chars.next() {
                        if c == '\u{7}' || (c == '\u{1b}' && chars.next_if_eq(&'\\').is_some()) {
                            break;
                        }
                    }
                }
                _ => {}
            },
            '\n' | '\r' | '\t' => plain.push(c),
            c if c.is_control() => {}
            c => plain.push(c),
        }
    }
    let lines: Vec<&str> = plain.split('\n')
        .map(|line| line.strip_suffix('\r').unwrap_or(line).rsplit('\r').next().unwrap_or_default().trim_end()).collect();
    let text = lines.join("\n");
    let text = text.trim();
    if text.len() <= TOOL_TAIL {
        return text.to_string();
    }
    let mut cut = text.len() - TOOL_TAIL;
    while !text.is_char_boundary(cut) {
        cut += 1;
    }
    format!("…{}", text[cut..].trim_start())
}

/// A turn to carry: what was asked, and the reply as text another engine can read.
pub type Turn = (String, String);

/// The transcript as turns. A reply starts with where it came from (`[codex · gpt-5.5]`) and keeps its tool
/// calls as text lines (`[ran in codex] shell: npm test`): tool names and ids differ per engine.
pub fn turns(records: &[Value]) -> Vec<Turn> {
    let mut out: Vec<Turn> = vec![];
    for record in records {
        let text = |key: &str| record[key].as_str().unwrap_or_default().to_string();
        match record["role"].as_str() {
            Some("user") => out.push((text("text"), String::new())),
            Some("assistant") => {
                let (engine, model) = (text("engine"), text("model"));
                let mut reply = if model.is_empty() { format!("[{engine}]") } else { format!("[{engine} · {model}]") };
                let mut said = false;
                for part in record["parts"].as_array().into_iter().flatten() {
                    match (part["text"].as_str(), part["tool"].as_str()) {
                        (Some(t), _) if !t.trim().is_empty() => {
                            reply += &format!("\n{}", t.trim());
                            said = true;
                        }
                        (_, Some(tool)) => {
                            reply += &format!("\n[ran in {engine}] {tool}: {}", part["summary"].as_str().unwrap_or_default());
                            for line in part["output"].as_str().unwrap_or_default().lines() {
                                reply += &format!("\n    {line}"); // its output's end, indented under it
                            }
                        }
                        _ => {}
                    }
                }
                if !said {
                    reply += "\n(no reply text)";
                }
                match out.last_mut() {
                    Some(turn) if turn.1.is_empty() => turn.1 = reply,
                    _ => out.push((String::new(), reply)), // a reply with no ask before it: keep it anyway
                }
            }
            _ => {}
        }
    }
    for turn in &mut out {
        if turn.1.is_empty() {
            turn.1 = "(no reply: the turn was stopped)".into(); // and every native format wants a reply
        }
    }
    out
}

/// How many characters of conversation `engine` takes: WINDOW_SHARE_PCT of its window.
/// shortcut: one window per engine, not per model; read the model's own window when a small one matters.
pub fn budget(engine: &str) -> usize {
    let window_tokens = match engine { "codex" => 272_000, "opencode" => 128_000, _ => 200_000 };
    window_tokens * WINDOW_SHARE_PCT / 100 * CHARS_PER_TOKEN
}

/// The turns that fit in `budget` characters: the first one, then the newest that fit, with one line
/// where the gap is. A single message longer than a quarter of the budget is cut.
pub fn fit(turns: Vec<Turn>, budget: usize) -> Vec<Turn> {
    let cap = (budget / 4).max(1);
    let cut = |text: String| -> String {
        let n = text.chars().count();
        if n <= cap { text } else { format!("{}… [{} characters cut]", text.chars().take(cap).collect::<String>(), n - cap) }
    };
    let mut turns: Vec<Turn> = turns.into_iter().map(|(a, b)| (cut(a), cut(b))).collect();
    let size = |t: &Turn| t.0.len() + t.1.len();
    if turns.iter().map(size).sum::<usize>() <= budget {
        return turns;
    }
    let first = turns.remove(0);
    let mut left = budget.saturating_sub(size(&first) + 100);
    let mut newest = vec![];
    while let Some(turn) = turns.pop() {
        if size(&turn) > left {
            turns.push(turn);
            break;
        }
        left -= size(&turn);
        newest.push(turn);
    }
    newest.reverse();
    let gap = format!("[{} earlier turns left out: they're in Reidcc's chat transcript]", turns.len());
    match newest.first_mut() {
        Some(next) => next.0 = format!("{gap}\n\n{}", next.0),
        None => newest.push((gap, "ok".into())),
    }
    std::iter::once(first).chain(newest).collect()
}

/// The turns as plain text, for an engine that didn't take the session.
pub fn as_text(turns: &[Turn]) -> String {
    turns.iter().map(|(ask, reply)| format!("User: {ask}\n\nAssistant: {reply}\n")).collect::<Vec<_>>().join("\n")
}

/// Write `turns` as a new session of `engine` in `folder` (never touching one that's there), check the
/// engine can see it, and return its id.
pub fn native(engine: &str, turns: &[Turn], folder: &str, env: &Env) -> R<String> {
    match engine {
        "codex" => codex(turns, folder, env),
        "opencode" => opencode(turns, folder, env),
        _ => claude(turns, folder),
    }
}

/// 2026-11-27T10:15:00.123Z for milliseconds since 1970 (UTC), as the engines write their times.
fn iso_utc(ms: u64) -> String {
    let (days, rest) = ((ms / 86_400_000) as i64, ms % 86_400_000);
    // civil date from days since 1970-01-01 (Howard Hinnant's algorithm)
    let z = days + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + i64::from(month <= 2);
    let (h, m, s, milli) = (rest / 3_600_000, rest / 60_000 % 60, rest / 1000 % 60, rest % 1000);
    format!("{year:04}-{month:02}-{day:02}T{h:02}:{m:02}:{s:02}.{milli:03}Z")
}

fn now_ms() -> u64 {
    SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |d| d.as_millis() as u64)
}

/// The installed CLI's version (its first word that starts with a digit), for the session's own field.
fn version(argv: Vec<String>, env: &Env, fallback: &str) -> String {
    engines::codex::run_capture(&argv, env, None, ASK_TIMEOUT)
        .and_then(|(_, out, _)| out.split_whitespace().find(|w| w.starts_with(|c: char| c.is_ascii_digit())).map(String::from))
        .unwrap_or_else(|| fallback.into())
}

fn write_lines(path: &Path, lines: &[Value]) -> R<()> {
    std::fs::create_dir_all(path.parent().unwrap_or(path)).map_err(engines::io)?;
    let body: String = lines.iter().map(|l| format!("{l}\n")).collect();
    std::fs::write(path, body).map_err(engines::io)
}

/// The folder Claude Code keeps `folder`'s sessions in: its path with every other character a dash. Past
/// CLAUDE_SLUG_MAX characters Claude shortens the name its own way, so there it's known only once Claude
/// has made it: the folder whose sessions say they ran in `folder`. None until then.
fn claude_project(projects: &Path, folder: &str) -> Option<PathBuf> {
    let slug: String = folder.chars().map(|c| if c.is_ascii_alphanumeric() { c } else { '-' }).collect();
    if slug.len() <= CLAUDE_SLUG_MAX {
        return Some(projects.join(slug));
    }
    let ran_here = |file: PathBuf| -> bool {
        let Ok(f) = std::fs::File::open(file) else { return false };
        std::io::BufReader::new(f).lines().take(5).map_while(Result::ok)
            .filter_map(|l| serde_json::from_str::<Value>(&l).ok())
            .any(|r| r["cwd"].as_str().is_some_and(|cwd| cwd.eq_ignore_ascii_case(folder)))
    };
    std::fs::read_dir(projects).ok()?.flatten()
        .filter(|d| d.file_name().to_string_lossy().starts_with(&slug[..CLAUDE_SLUG_MAX]))
        .map(|d| d.path())
        .find(|dir| std::fs::read_dir(dir).into_iter().flatten().flatten().map(|f| f.path())
            .any(|f| f.extension().is_some_and(|e| e == "jsonl") && ran_here(f)))
}

/// Claude Code's session records: user and assistant chained by parentUuid.
fn claude_lines(turns: &[Turn], folder: &str, id: &str, version: &str, stamp: &str) -> Vec<Value> {
    let mut parent = Value::Null;
    let mut lines = vec![];
    for (ask, reply) in turns {
        for (role, message) in [("user", json!({"role": "user", "content": ask})),
                                ("assistant", json!({"role": "assistant", "type": "message", "model": "reidcc",
                                    "content": [{"type": "text", "text": reply}], "stop_reason": "end_turn"}))] {
            let uuid = uuid::Uuid::new_v4().to_string();
            lines.push(json!({"parentUuid": parent, "isSidechain": false, "userType": "external", "cwd": folder,
                              "sessionId": id, "version": version, "type": role, "message": message,
                              "uuid": uuid, "timestamp": stamp}));
            parent = Value::String(uuid);
        }
    }
    lines
}

/// Claude Code: `projects\<folder slug>\<id>.jsonl` (verified on 2.1.332: `claude -p --resume <id>`
/// answers from it).
fn claude(turns: &[Turn], folder: &str) -> R<String> {
    let id = uuid::Uuid::new_v4().to_string();
    let projects = Path::new(&session::claude_dir()).join("projects");
    let Some(dir) = claude_project(&projects, folder) else {
        return err("Claude Code names this folder's sessions its own way (the path is long), and has none here yet.");
    };
    let version = version(vec![engines::claude::find_claude()?, "--version".into()], &crate::environ(), "2.1.332");
    let file = dir.join(format!("{id}.jsonl"));
    write_lines(&file, &claude_lines(turns, folder, &id, &version, &iso_utc(now_ms())))?;
    if !session::session_exists(&id) {
        return err("Claude Code doesn't list the session Reidcc wrote.");
    }
    Ok(id)
}

/// Codex's rollout: a session_meta line, then one response_item per message.
fn codex_lines(turns: &[Turn], folder: &str, id: &str, version: &str, stamp: &str) -> Vec<Value> {
    let line = |kind: &str, payload: Value| json!({"timestamp": stamp, "type": kind, "payload": payload});
    let message = |role: &str, kind: &str, text: &str| json!({"type": "message", "role": role, "content": [{"type": kind, "text": text}]});
    let mut lines = vec![line("session_meta", json!({"id": id, "timestamp": stamp, "cwd": folder, "originator": "codex_exec",
                                                     "cli_version": version, "source": "exec", "model_provider": "openai"}))];
    for (ask, reply) in turns {
        lines.push(line("response_item", message("user", "input_text", ask)));
        lines.push(line("response_item", message("assistant", "output_text", reply)));
    }
    lines
}

/// Codex: `sessions\YYYY\MM\DD\rollout-<time>-<id>.jsonl` (verified on 0.172.0: `codex exec resume <id>`
/// answers from it).
fn codex(turns: &[Turn], folder: &str, env: &Env) -> R<String> {
    let id = uuid::Uuid::new_v4().to_string();
    let stamp = iso_utc(now_ms());
    let (exe, _) = engines::codex::find_codex()?;
    let version = version(vec![exe, "--version".into()], env, "0.172.0");
    let day = Path::new(&engines::codex::codex_home(env)).join("sessions").join(&stamp[..4]).join(&stamp[5..7]).join(&stamp[8..10]);
    let file = day.join(format!("rollout-{}-{id}.jsonl", stamp[..19].replace(':', "-")));
    write_lines(&file, &codex_lines(turns, folder, &id, &version, &stamp))?;
    if !engines::codex::thread_exists(env, &id) {
        return err("Codex doesn't list the session Reidcc wrote.");
    }
    Ok(id)
}

/// OpenCode's `session import` file: the shape `session export` prints.
fn opencode_export(turns: &[Turn], folder: &str, id: &str, project: &str, ms: u64) -> Value {
    let mut messages = vec![];
    for (i, (ask, reply)) in turns.iter().enumerate() {
        let t = ms + 2 * i as u64; // in order, a millisecond apart
        messages.push(json!({"id": format!("msg_{}", uuid::Uuid::new_v4().simple()), "time": {"created": t}, "type": "user",
                             "text": ask, "files": []}));
        messages.push(json!({"id": format!("msg_{}", uuid::Uuid::new_v4().simple()), "time": {"created": t + 1, "completed": t + 1},
                             "type": "assistant", "agent": "build", "model": {"id": "reidcc", "providerID": "reidcc"},
                             "content": [{"type": "text", "text": reply}]}));
    }
    json!({"info": {"id": id, "projectID": project, "agent": "build", "cost": 0,
                    "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}},
                    "outcome": "succeeded", "time": {"created": ms, "updated": ms}, "location": {"directory": folder}},
           "messages": messages})
}

/// OpenCode: `opencode session import`. The import needs the folder's project id, which only OpenCode
/// knows: an empty session made through its API names it, then goes again.
fn opencode(turns: &[Turn], folder: &str, env: &Env) -> R<String> {
    let exe = engines::opencode::find_opencode()?;
    let mut env = env.clone();
    env.insert("PWD".into(), folder.into()); // OpenCode's folder (see opencode::build)
    let run = |args: &[&str]| {
        let mut argv = vec![exe.clone()];
        argv.extend(args.iter().map(|a| a.to_string()));
        engines::codex::run_capture(&argv, &env, Some(folder), ASK_TIMEOUT)
    };
    let made = run(&["api", "--standalone", "session.create", "-d", "{}"]).filter(|(code, _, _)| *code == 0)
        .and_then(|(_, out, _)| serde_json::from_str::<Value>(&out).ok());
    let (Some(empty), Some(project)) = (made.as_ref().and_then(|m| m["data"]["id"].as_str()),
                                        made.as_ref().and_then(|m| m["data"]["projectID"].as_str())) else {
        return err("OpenCode didn't make a session to read the project from.");
    };
    let _ = run(&["session", "delete", empty, "--standalone"]);
    let id = engines::opencode::new_session_id();
    let export = opencode_export(turns, folder, &id, project, now_ms());
    // the pid in the name tells sweep_temps the file belongs to a running reid
    let file = py::mkstemp(&format!("reid_import_{}_", std::process::id()), ".json", &export.to_string()).map_err(engines::io)?;
    let imported = run(&["session", "import", &file, "--standalone"]);
    let _ = std::fs::remove_file(&file);
    match imported {
        Some((0, _, _)) if engines::opencode::session_exists(&env, folder, &id) => Ok(id),
        Some((0, _, _)) => err("OpenCode doesn't list the session Reidcc imported."),
        Some((_, out, errs)) => err(format!("OpenCode didn't import the session: {}", (out + &errs).lines().next().unwrap_or_default())),
        None => err("OpenCode didn't import the session in time."),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn turn(a: &str, b: &str) -> Turn {
        (a.to_string(), b.to_string())
    }

    fn records() -> Vec<Value> {
        let mut rec = Recorder::default();
        for e in [Event::Started { session_id: "s".into() }, Event::TextDelta { text: "Look".into() },
                  Event::TextDelta { text: "ing.".into() }, Event::ToolCall { name: "shell".into(), summary: "npm test".into() },
                  Event::ToolOutput { tool: 0, text: "12 passed\n0 failed".into() }, Event::ToolOutput { tool: 5, text: "no such call".into() },
                  Event::TextDelta { text: "Passes.".into() }] {
            rec.push(&e);
        }
        assert!(rec.ran);
        vec![ask_record("cx", "codex", "gpt-5.5", "run the tests"), rec.reply_record("cx", "codex", "gpt-5.5"),
             ask_record("cl", "claude", "", "and now?"), Recorder::default().reply_record("cl", "claude", ""),
             ask_record("cl", "claude", "", "stopped one")] // stopped: the engine started, no reply was written
    }

    #[test]
    fn transcript_turns_label_the_source_and_keep_tools_as_text() {
        assert_eq!(turns(&records()), vec![
            turn("run the tests", "[codex · gpt-5.5]\nLooking.\n[ran in codex] shell: npm test\n    12 passed\n    0 failed\nPasses."),
            turn("and now?", "[claude]\n(no reply text)"),
            turn("stopped one", "(no reply: the turn was stopped)"),
        ]);
        // a reply with no ask before it, a blank text part, a tool with no summary, an unknown role
        let odd = [json!({"role": "assistant", "engine": "opencode", "model": "", "parts": [{"text": "  "}, {"tool": "read"}]}),
                   json!({"role": "system", "text": "ignored"})];
        assert_eq!(turns(&odd), vec![turn("", "[opencode]\n[ran in opencode] read: \n(no reply text)")]);
    }

    #[test]
    fn tool_output_keeps_its_plain_end() {
        assert_eq!(tool_tail(""), "");
        assert_eq!(tool_tail("\u{1b}[31mred\u{1b}[0m ok\r\n"), "red ok");
        assert_eq!(tool_tail("\u{1b}]0;title\u{7}a\u{1b}P0;0q\"1#0~-\u{1b}\\b\u{0}\u{8}"), "ab");
        assert_eq!(tool_tail("10%\r50%\r100%\ndone"), "100%\ndone"); // a progress bar as last drawn
        // long: the end, cut on a char boundary, whatever the bytes around the cut are
        for pad in 0..4 {
            let out = format!("{}{}{}", "x".repeat(pad), "─é".repeat(1000), "\nFAILED: 1 test");
            let tail = tool_tail(&out);
            assert!(tail.starts_with('…') && tail.ends_with("FAILED: 1 test"), "{pad}");
            assert!(tail.len() <= TOOL_TAIL + '…'.len_utf8() && tail.len() > TOOL_TAIL - 4, "{pad}: {}", tail.len());
        }
        // an escape cut off at the end eats nothing after it, and never panics
        assert_eq!(tool_tail("ok\u{1b}["), "ok");
        assert_eq!(tool_tail("ok\u{1b}P unterminated"), "ok");
    }

    #[test]
    fn a_transcript_round_trips_through_its_file() {
        let home = std::env::temp_dir().join(format!("reid_tr_{}", uuid::Uuid::new_v4().simple()));
        let ctx = Ctx::at(&home.to_string_lossy());
        assert!(read(&ctx, "c").is_empty());
        append(&ctx, "c", &records()[..2]).unwrap();
        append(&ctx, "c", &records()[2..]).unwrap();
        assert_eq!(read(&ctx, "c"), records());
        // a chat id becomes a file name: nothing that leaves the chats folder
        for bad in ["..\\x", "a/b", "", "c:x"] {
            assert!(append(&ctx, bad, &records()).is_err(), "{bad}");
            assert!(read(&ctx, bad).is_empty());
        }
        let _ = std::fs::remove_dir_all(home);
    }

    #[test]
    fn fit_keeps_the_first_turn_and_the_newest_with_a_gap_line() {
        let all: Vec<Turn> = (0..10).map(|i| (format!("ask {i} {}", "x".repeat(90)), format!("reply {i}"))).collect();
        assert_eq!(fit(all.clone(), 100_000), all); // fits: unchanged
        let kept = fit(all.clone(), 450);
        assert_eq!(kept[0], all[0]);
        assert_eq!(kept.last().unwrap(), all.last().unwrap());
        assert!(kept[1].0.starts_with("[7 earlier turns left out"), "{kept:?}");
        assert_eq!(fit(all.clone(), 450), kept); // deterministic
        // one huge message is cut, not dropped
        let huge = fit(vec![turn(&"a".repeat(5000), "b")], 400);
        assert!(huge[0].0.ends_with("[4900 characters cut]"), "{}", &huge[0].0[90..]);
        // the first turn fills it: only the gap line follows, as a turn of its own
        let full = fit(vec![turn(&"a".repeat(90), &"b".repeat(90)), turn(&"c".repeat(90), "d")], 200);
        assert_eq!(full.len(), 2);
        assert_eq!(full[1], turn("[1 earlier turns left out: they're in Reidcc's chat transcript]", "ok"));
        // cut on characters, never inside one
        let wide = fit(vec![turn(&"é".repeat(300), "ü")], 400);
        assert!(wide[0].0.starts_with(&"é".repeat(100)) && wide[0].0.ends_with("[200 characters cut]"));
    }

    #[test]
    fn fit_holds_for_any_mix_of_sizes() {
        // a small linear congruential generator: the same cases every run
        let mut seed = 42u64;
        let mut next = |m: u64| {
            seed = seed.wrapping_mul(6_364_136_223_846_793_005).wrapping_add(1_442_695_040_888_963_407);
            (seed >> 33) % m
        };
        for _ in 0..300 {
            let budget = 200 + next(20_000) as usize;
            let n = 1 + next(60) as usize;
            let all: Vec<Turn> = (0..n).map(|i| (format!("ask {i} {}", "x".repeat(next(3000) as usize)),
                                                format!("reply {i} {}", "y".repeat(next(3000) as usize)))).collect();
            let kept = fit(all.clone(), budget);
            let size: usize = kept.iter().map(|t| t.0.len() + t.1.len()).sum();
            let gap = kept.iter().any(|t| t.0.contains("earlier turns left out"));
            assert!(size <= budget + 200, "budget {budget}, got {size}"); // the gap line and cut marks are the slack
            assert!(kept[0].0.starts_with("ask 0 "), "the first ask always comes");
            assert_eq!(kept, fit(all.clone(), budget), "deterministic");
            if gap {
                let left: usize = kept.iter().find_map(|t| t.0.split(' ').next().and_then(|w| w.strip_prefix('[')).and_then(|w| w.parse().ok())).unwrap();
                let carried = kept.len() - 1 - usize::from(kept.last().unwrap().1 == "ok");
                assert_eq!(1 + left + carried, n, "every turn is kept or counted in the gap line");
                // the newest turns, in order, right up to the end
                if carried > 0 {
                    assert!(kept.last().unwrap().0.contains(&format!("ask {} ", n - 1)));
                }
            } else {
                assert_eq!(kept.len(), n);
            }
        }
    }

    #[test]
    fn utc_dates_are_right() {
        assert_eq!(iso_utc(0), "1970-01-01T00:00:00.000Z");
        assert_eq!(iso_utc(951_782_400_000), "2000-02-29T00:00:00.000Z"); // a leap day in a century leap year
        assert_eq!(iso_utc(4_107_542_399_999), "2100-02-28T23:59:59.999Z"); // 2100 isn't a leap year
        assert_eq!(iso_utc(1_795_775_415_123), "2026-11-27T10:30:15.123Z");
        assert!(iso_utc(now_ms()).starts_with("20"));
    }

    #[test]
    fn claude_sessions_chain_their_messages() {
        let lines = claude_lines(&[turn("hi", "[codex]\nhello"), turn("and?", "[codex]\nso")], r"C:\w", "sid", "2.1.332", "t");
        assert_eq!(lines.len(), 4);
        assert_eq!(lines[0]["parentUuid"], Value::Null);
        for pair in lines.windows(2) {
            assert_eq!(pair[1]["parentUuid"], pair[0]["uuid"]);
        }
        let roles: Vec<&str> = lines.iter().map(|l| l["type"].as_str().unwrap()).collect();
        assert_eq!(roles, ["user", "assistant", "user", "assistant"]);
        assert!(lines.iter().all(|l| l["sessionId"] == "sid" && l["cwd"] == r"C:\w" && l["isSidechain"] == false));
        assert_eq!(lines[0]["message"]["content"], "hi");
        assert_eq!(lines[1]["message"]["content"][0]["text"], "[codex]\nhello");
    }

    #[test]
    fn claude_project_folders_follow_claudes_names() {
        let projects = std::env::temp_dir().join(format!("reid_cp_{}", uuid::Uuid::new_v4().simple()));
        assert_eq!(claude_project(&projects, r"C:\Users\me\my app"), Some(projects.join("C--Users-me-my-app")));
        // a long path: unknown until Claude has made the folder, then found by its sessions' cwd
        let long = format!(r"C:\w\{}", "deep\\".repeat(45));
        assert_eq!(claude_project(&projects, &long), None);
        let slug: String = long.chars().map(|c| if c.is_ascii_alphanumeric() { c } else { '-' }).collect();
        let other = projects.join(format!("{}-other", &slug[..CLAUDE_SLUG_MAX]));
        let theirs = projects.join(format!("{}-1a2b3c", &slug[..CLAUDE_SLUG_MAX]));
        for (dir, cwd) in [(&other, format!("{long}x")), (&theirs, long.to_uppercase())] {
            std::fs::create_dir_all(dir).unwrap();
            std::fs::write(dir.join("s.jsonl"), format!("{}\n", json!({"type": "summary"})) + &format!("{}\n", json!({"cwd": cwd}))).unwrap();
        }
        assert_eq!(claude_project(&projects, &long), Some(theirs));
        let _ = std::fs::remove_dir_all(projects);
    }

    #[test]
    fn codex_rollouts_start_with_their_meta() {
        let lines = codex_lines(&[turn("hi", "hello")], r"C:\w", "019d", "0.172.0", "2026-11-27T10:30:15.123Z");
        assert_eq!(lines.len(), 3);
        assert_eq!(lines[0]["type"], "session_meta");
        assert_eq!(lines[0]["payload"]["id"], "019d");
        assert_eq!(lines[0]["payload"]["cwd"], r"C:\w");
        assert_eq!(lines[1]["payload"]["content"][0], json!({"type": "input_text", "text": "hi"}));
        assert_eq!(lines[2]["payload"]["role"], "assistant");
        assert_eq!(lines[2]["payload"]["content"][0], json!({"type": "output_text", "text": "hello"}));
    }

    #[test]
    fn opencode_exports_keep_order_and_every_required_field() {
        let e = opencode_export(&[turn("hi", "hello"), turn("and?", "so")], r"C:\w", "ses_x", "prj", 1000);
        for key in ["id", "projectID", "agent", "cost", "tokens", "outcome", "time", "location"] {
            assert!(!e["info"][key].is_null(), "info.{key}");
        }
        let msgs = e["messages"].as_array().unwrap();
        let times: Vec<u64> = msgs.iter().map(|m| m["time"]["created"].as_u64().unwrap()).collect();
        assert_eq!(times, [1000, 1001, 1002, 1003]);
        assert_eq!(msgs.iter().map(|m| m["type"].as_str().unwrap()).collect::<Vec<_>>(), ["user", "assistant", "user", "assistant"]);
        assert_eq!(msgs[3]["content"][0]["text"], "so");
        let ids: std::collections::HashSet<&str> = msgs.iter().map(|m| m["id"].as_str().unwrap()).collect();
        assert_eq!(ids.len(), 4, "message ids are unique");
    }
}
