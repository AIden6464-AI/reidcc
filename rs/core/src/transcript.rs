//! The full context switch (SPEC-0.2.6 Part 2): Reidcc keeps one transcript per chat, and a switch writes
//! it into the next engine's own session format as a new session, so that engine resumes the whole chat
//! as its own history. Plain code, no model: the same transcript always gives the same session.

use crate::stream::Event;
use crate::{engines, err, py, session, Ctx, Env, R};
use serde_json::{json, Value};
use std::io::Write;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

/// The carried conversation fits in this share of the target engine's window...
const WINDOW_SHARE_PCT: usize = 60;
/// ...counted at this many characters per token.
const CHARS_PER_TOKEN: usize = 4;
const ASK_TIMEOUT: Duration = Duration::from_secs(15);

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
            _ => {}
        }
    }

    /// The turn's two records: what was asked, and the reply.
    pub fn records(self, profile: &str, engine: &str, model: &str, ask: &str) -> [Value; 2] {
        let who = json!({"profile": profile, "engine": engine, "model": model});
        let mut user = json!({"role": "user", "text": ask});
        let mut reply = json!({"role": "assistant", "parts": self.parts});
        for record in [&mut user, &mut reply] {
            record.as_object_mut().unwrap().extend(who.as_object().unwrap().clone());
        }
        [user, reply]
    }
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
                        (_, Some(tool)) => reply += &format!("\n[ran in {engine}] {tool}: {}", part["summary"].as_str().unwrap_or_default()),
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
            turn.1 = "(no reply)".into(); // a turn that never answered: every native format wants a reply
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

/// Now, as engines write it: 2026-11-27T10:15:00.123Z (UTC).
fn utc_now() -> (String, u64) {
    let ms = SystemTime::now().duration_since(UNIX_EPOCH).map_or(0, |d| d.as_millis() as u64);
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
    (format!("{year:04}-{month:02}-{day:02}T{h:02}:{m:02}:{s:02}.{milli:03}Z"), ms)
}

/// The installed CLI's version (its first word that starts with a digit), for the session's own field.
fn version(argv: Vec<String>, env: &Env, fallback: &str) -> String {
    engines::codex::run_capture(&argv, env, None, ASK_TIMEOUT)
        .and_then(|(_, out, _)| out.split_whitespace().find(|w| w.starts_with(|c: char| c.is_ascii_digit())).map(String::from))
        .unwrap_or_else(|| fallback.into())
}

fn write_lines(path: &std::path::Path, lines: &[Value]) -> R<()> {
    std::fs::create_dir_all(path.parent().unwrap_or(path)).map_err(engines::io)?;
    let body: String = lines.iter().map(|l| format!("{l}\n")).collect();
    std::fs::write(path, body).map_err(engines::io)
}

/// Claude Code: `projects\<folder slug>\<id>.jsonl`, user and assistant records chained by parentUuid
/// (verified on 2.1.332: `claude -p --resume <id>` answers from it).
fn claude(turns: &[Turn], folder: &str) -> R<String> {
    let id = uuid::Uuid::new_v4().to_string();
    let slug: String = folder.chars().map(|c| if c.is_ascii_alphanumeric() { c } else { '-' }).collect();
    let file = std::path::Path::new(&session::claude_dir()).join("projects").join(slug).join(format!("{id}.jsonl"));
    let exe = engines::claude::find_claude()?;
    let version = version(vec![exe, "--version".into()], &crate::environ(), "2.1.332");
    let (stamp, _) = utc_now();
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
    write_lines(&file, &lines)?;
    if !session::session_exists(&id) {
        return err("Claude Code doesn't list the session Reidcc wrote.");
    }
    Ok(id)
}

/// Codex: `sessions\YYYY\MM\DD\rollout-<time>-<id>.jsonl`, a session_meta line and one response_item per
/// message (verified on 0.172.0: `codex exec resume <id>` answers from it).
fn codex(turns: &[Turn], folder: &str, env: &Env) -> R<String> {
    let id = uuid::Uuid::new_v4().to_string();
    let (stamp, _) = utc_now();
    let (exe, _) = engines::codex::find_codex()?;
    let version = version(vec![exe, "--version".into()], env, "0.172.0");
    let day = std::path::Path::new(&engines::codex::codex_home(env)).join("sessions").join(&stamp[..4]).join(&stamp[5..7]).join(&stamp[8..10]);
    let file = day.join(format!("rollout-{}-{id}.jsonl", stamp[..19].replace(':', "-")));
    let line = |kind: &str, payload: Value| json!({"timestamp": stamp, "type": kind, "payload": payload});
    let message = |role: &str, kind: &str, text: &str| json!({"type": "message", "role": role, "content": [{"type": kind, "text": text}]});
    let mut lines = vec![line("session_meta", json!({"id": id, "timestamp": stamp, "cwd": folder, "originator": "codex_exec",
                                                     "cli_version": version, "source": "exec", "model_provider": "openai"}))];
    for (ask, reply) in turns {
        lines.push(line("response_item", message("user", "input_text", ask)));
        lines.push(line("response_item", message("assistant", "output_text", reply)));
    }
    write_lines(&file, &lines)?;
    if !engines::codex::thread_exists(env, &id) {
        return err("Codex doesn't list the session Reidcc wrote.");
    }
    Ok(id)
}

/// OpenCode: `opencode session import` of an export-shaped file. The import needs the folder's project id,
/// which only OpenCode knows: an empty session made through its API names it, then goes again.
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
    let (_, ms) = utc_now();
    let mut messages = vec![];
    for (i, (ask, reply)) in turns.iter().enumerate() {
        let t = ms + 2 * i as u64;
        messages.push(json!({"id": format!("msg_{}", uuid::Uuid::new_v4().simple()), "time": {"created": t}, "type": "user",
                             "text": ask, "files": []}));
        messages.push(json!({"id": format!("msg_{}", uuid::Uuid::new_v4().simple()), "time": {"created": t + 1, "completed": t + 1},
                             "type": "assistant", "agent": "build", "model": {"id": "reidcc", "providerID": "reidcc"},
                             "content": [{"type": "text", "text": reply}]}));
    }
    let export = json!({"info": {"id": id, "projectID": project, "agent": "build", "cost": 0,
                                 "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}},
                                 "outcome": "succeeded", "time": {"created": ms, "updated": ms}, "location": {"directory": folder}},
                        "messages": messages});
    // the pid in the name tells sweep_temps the file belongs to a running reid
    let file = py::mkstemp(&format!("reid_import_{}_", std::process::id()), ".json", &export.to_string()).map_err(engines::io)?;
    let imported = run(&["session", "import", &file, "--standalone"]);
    let _ = std::fs::remove_file(&file);
    match imported {
        Some((0, _, _)) => Ok(id),
        Some((_, out, errs)) => err(format!("OpenCode didn't import the session: {}", (out + &errs).lines().next().unwrap_or_default())),
        None => err("OpenCode didn't import the session in time."),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn records() -> Vec<Value> {
        let mut rec = Recorder::default();
        for e in [Event::Started { session_id: "s".into() }, Event::TextDelta { text: "Look".into() },
                  Event::TextDelta { text: "ing.".into() }, Event::ToolCall { name: "shell".into(), summary: "npm test".into() },
                  Event::TextDelta { text: "Passes.".into() }] {
            rec.push(&e);
        }
        assert!(rec.ran);
        let mut all = rec.records("cx", "codex", "gpt-5.5", "run the tests").to_vec();
        all.extend(Recorder::default().records("cl", "claude", "", "and now?"));
        all
    }

    #[test]
    fn transcript_turns_label_the_source_and_keep_tools_as_text() {
        assert_eq!(turns(&records()), vec![
            ("run the tests".to_string(), "[codex · gpt-5.5]\nLooking.\n[ran in codex] shell: npm test\nPasses.".to_string()),
            ("and now?".to_string(), "[claude]\n(no reply text)".to_string()),
        ]);
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
        let huge = fit(vec![("a".repeat(5000), "b".into())], 400);
        assert!(huge[0].0.ends_with("[4900 characters cut]"), "{}", &huge[0].0[90..]);
    }

    #[test]
    fn utc_dates_are_right() {
        let (stamp, ms) = utc_now();
        assert_eq!(stamp.len(), 24);
        assert!(stamp.ends_with('Z') && ms > 1_700_000_000_000);
    }
}
