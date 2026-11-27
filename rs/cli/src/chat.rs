//! The TUI's chat view (vision\Spec\SPEC-unified-interface.md Part 6, Milestone 2B): ui\src\chat.ts in
//! text. One folder, one composer over Claude Code and Codex. Each turn is a `reid --stream` child, as in
//! the chat window: stop kills it and its job takes the engine down; a crashed turn can't take the TUI.

use super::{clen, fit, getkey, rep, strip_sgr, Stop, Tui, B, DIM, EMERALD, LINE, RULE, T, VAL};
use crate::console;
use reidcc::term::{BRONZE, OXIDE, R, TEXT, TEXT2, TEXT3};
use reidcc::engines::tuning::{self, Choices};
use reidcc::{changes, load_config, locks, profiles, show_path, Obj};
use serde_json::Value;
use std::collections::HashMap;
use std::io::{BufRead, Read, Write};
use std::os::windows::process::CommandExt;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{channel, Receiver};
use std::time::{Duration, Instant};
use windows_sys::Win32::System::Threading::{CREATE_NEW_CONSOLE, CREATE_NO_WINDOW};

const CODE: &str = "\x1b[48;2;23;21;19m"; // --s2 under inline code
const UNDER: &str = "\x1b[4m";
/// When reid fails before streaming anything, this much of its stderr's end says why.
const MAX_STDERR_TAIL_CHARS: usize = 600;
/// Lines of one file's diff shown under ctrl+d.
const MAX_DIFF_LINES: usize = 200;
/// The composer shows the end of a long prompt, this many rows.
const FIELD_ROWS: usize = 3;
const TOOL_NAME_WIDTH: i64 = 6;
/// the bar's fixed text around the path: " RC  ", the two spaces after it, and at least one space before the meters
const BAR_FIXED: i64 = 8;
/// How often a session held by a terminal is checked for being free again.
const HOLDER_POLL: Duration = Duration::from_millis(1500);
/// How long the loop sleeps with no key waiting; the running turn's timer redraws every second.
const KEY_POLL: Duration = Duration::from_millis(30);
const TIMER_REDRAW: Duration = Duration::from_secs(1);

// console::getkey() gives control keys as their characters
const TAB: &str = "\t";
const CTRL_D: &str = "\x04";
const CTRL_E: &str = "\x05";
const CTRL_O: &str = "\x0f";
const CTRL_R: &str = "\x12";
const CTRL_T: &str = "\x14";

enum Msg {
    Event(Value),
    /// stdout ended; the text is the end of reid's stderr
    Eof(String),
}

enum Block {
    Info(String),
    Ask { who: String, text: String },
    Tool { name: String, summary: String },
    Text(String),
    Fail(String),
    Meta(String),
    Changed { from: String, to: String, files: Vec<changes::FileStat>, diffs: Option<Vec<String>> },
    Switch { from: String, to: String },
}

enum Note {
    None,
    /// the session is held by another window: cleared when it lets go
    InTerminal(String),
    /// a write turn can't have the folder: ctrl+r sends it read-only
    Locked(String),
    Refused(String),
}

struct Turn {
    child: Child,
    rx: Receiver<Msg>,
    began: Instant,
    profile: String,
    prompt: String,
    read_only: bool,
    stopped: bool,
    refused: bool,
    saw_text: bool,
    /// the folder before a write turn (a git tree), for its diff
    before: Option<String>,
    /// how to take the turn back if reid refuses it: the profile talked to, and the stream's length
    undo: (String, usize),
}

/// A row of the tune panel (ctrl+e): this chat's model, effort, MCP servers and plugins for a profile.
#[derive(Clone, PartialEq)]
enum TuneRow {
    Model,
    Effort,
    Mcp(String),
    Plugin(String),
}

struct Chat {
    folder: String,
    /// reid.json, for each profile's own model / effort / MCP / plugins
    cfg: Obj,
    /// what this chat changed per profile (SPEC-unified-interface Milestone 2C): `reid --stream --with`
    tunes: HashMap<String, Obj>,
    choices: HashMap<String, Choices>,
    /// the models the tune panel steps through, per engine: OpenCode's list takes a second to read
    models: HashMap<String, Vec<String>>,
    /// the tune panel's selected row while it's open
    tuning: Option<usize>,
    profiles: Vec<(String, String)>,
    cur: String,
    pick: usize,
    sids: HashMap<String, String>,
    /// this chat's transcript (`reid --stream --chat`): a switch carries it into the next engine
    chat: String,
    turns: usize,
    read_only: bool,
    field: String,
    blocks: Vec<Block>,
    note: Note,
    polled: Instant,
    turn: Option<Turn>,
    context: Option<u8>,
    cost: f64,
    /// "19.9k in · 5 out": the thread's token counts so far, when the engine reports them (Codex does), never zeros
    tokens: Option<String>,
    scroll: i64,
    terminal: Option<Child>,
    flash: String,
}

impl Drop for Chat {
    fn drop(&mut self) {
        if let Some(turn) = self.turn.as_mut() {
            let _ = turn.child.kill(); // leaving (or Ctrl+C) ends a running turn; a terminal window stays
        }
    }
}

/// Engine text for the screen: no control characters (an escape sequence in a reply must not drive
/// the terminal), tabs as spaces.
pub(super) fn clean(text: &str) -> String {
    text.chars().flat_map(|c| match c {
        '\t' => vec![' '; 4],
        '\n' => vec!['\n'],
        c if c.is_control() => vec![],
        c => vec![c],
    }).collect()
}

/// One markdown line outside a fence as styled pieces: `code`, **bold**, [text](target) -> text.
fn inline(line: &str) -> Vec<(String, String)> {
    if let Some(heading) = line.trim_start().strip_prefix('#') {
        let heading = heading.trim_start_matches('#');
        if heading.starts_with(' ') {
            return inline(heading.trim()).into_iter().map(|(style, text)| (format!("{B}{style}"), text)).collect();
        }
    }
    let mut out = vec![];
    let mut rest = line;
    while let Some((open, mid, close)) = next_link(rest) {
        code_and_bold(&rest[..open], "", &mut out);
        code_and_bold(&rest[open + 1..mid], UNDER, &mut out);
        rest = &rest[close + 1..];
    }
    code_and_bold(rest, "", &mut out);
    out
}

/// The first whole `[text](target)` as byte offsets of `[`, `](` and `)`. Left to right: a closed `code`
/// span is skipped, so its text never turns into a link, while a link's text may hold code.
fn next_link(text: &str) -> Option<(usize, usize, usize)> {
    let bytes = text.as_bytes();
    let skip_code = |at: usize| text[at + 1..].find('`').map(|end| at + 1 + end);
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'`' => i = skip_code(i).unwrap_or(i),
            b'[' => {
                let mut j = i + 1;
                while j < bytes.len() && bytes[j] != b']' && bytes[j] != b'[' {
                    j = if bytes[j] == b'`' { skip_code(j).unwrap_or(j) } else { j } + 1;
                }
                if text[j..].starts_with("](") {
                    if let Some(close) = text[j + 2..].find(')').map(|at| j + 2 + at) {
                        let target = &text[j + 2..close];
                        if !target.is_empty() && !target.contains(char::is_whitespace) {
                            return Some((i, j, close));
                        }
                    }
                }
            }
            _ => {}
        }
        i += 1;
    }
    None
}

/// `code` and **bold** pieces of plain text, each style after `under` (a link's underline, or "").
fn code_and_bold(text: &str, under: &str, out: &mut Vec<(String, String)>) {
    let parts: Vec<&str> = text.split('`').collect();
    let closed = parts.len() % 2 == 1; // an odd count of pieces: every ` has its pair
    for (i, part) in parts.iter().enumerate() {
        if i % 2 == 1 && (closed || i < parts.len() - 1) {
            out.push((format!("{under}{CODE}{TEXT}"), part.to_string()));
            continue;
        }
        let part = if i % 2 == 1 { format!("`{part}") } else { part.to_string() }; // the unclosed one
        let pieces: Vec<&str> = part.split("**").collect();
        let paired = pieces.len() % 2 == 1;
        for (j, piece) in pieces.iter().enumerate() {
            if j % 2 == 1 && (paired || j < pieces.len() - 1) {
                out.push((format!("{under}{B}{TEXT}"), piece.to_string()));
            } else {
                let piece = if j % 2 == 1 { format!("**{piece}") } else { piece.to_string() };
                out.push((format!("{under}{TEXT}"), piece));
            }
        }
    }
}

/// Styled pieces wrapped at `width` columns; a line's leading spaces (a list's indent) stay on its first row.
fn wrap(pieces: &[(String, String)], width: i64) -> Vec<String> {
    let width = width.max(8);
    let (mut lines, mut row, mut row_width, mut first) = (vec![], String::new(), 0i64, true);
    for (style, text) in pieces {
        // runs of spaces and runs of everything else
        let mut tokens: Vec<String> = vec![];
        for c in text.chars() {
            match tokens.last_mut() {
                Some(token) if (c == ' ') == token.starts_with(' ') => token.push(c),
                _ => tokens.push(c.to_string()),
            }
        }
        for mut token in tokens {
            let token_width = clen(&token);
            if token.starts_with(' ') {
                if row_width == 0 && !first {
                    continue;
                }
                if row_width + token_width > width {
                    lines.push(std::mem::take(&mut row));
                    (row_width, first) = (0, false);
                    continue;
                }
            } else if row_width + token_width > width && row_width > 0 {
                lines.push(std::mem::take(&mut row));
                (row_width, first) = (0, false);
            }
            while clen(&token) > width {
                // a word longer than the line: cut it
                let head: String = token.chars().take((width - row_width).max(1) as usize).collect();
                token = token.chars().skip(head.chars().count()).collect();
                row += &format!("{style}{head}{R}");
                lines.push(std::mem::take(&mut row));
                (row_width, first) = (0, false);
            }
            row_width += clen(&token);
            row += &format!("{style}{token}{R}");
        }
    }
    if !row.is_empty() || lines.is_empty() {
        lines.push(row);
    }
    lines
}

/// A reply as screen lines (the chat window's md.ts rules). A fence still open (the text is
/// streaming) is code to the end.
pub(super) fn md_lines(text: &str, width: i64) -> Vec<String> {
    let mut out = vec![];
    let mut code = false;
    for line in clean(text).split('\n') {
        if line.trim_start().starts_with("```") && line.len() - line.trim_start().len() <= 3 {
            code = !code;
            continue;
        }
        if code {
            out.push(format!("{VAL}{TEXT} {} {R}", super::ljust(&fit(line, width - 2), width - 2)));
        } else if line.trim().is_empty() {
            out.push(String::new());
        } else {
            out.extend(wrap(&inline(line), width));
        }
    }
    out
}

/// `+3` in bone, `−3` in oxide; a zero is muted, and a binary file has no count.
fn count(sign: char, lines: Option<u64>) -> String {
    match lines {
        None => format!("{TEXT3}bin{R}"),
        Some(0) => format!("{TEXT3}{sign}0{R}"),
        Some(lines) => format!("{}{sign}{lines}{R}", if sign == '+' { TEXT } else { OXIDE }),
    }
}

fn mmss(elapsed: Duration) -> String {
    let secs = elapsed.as_secs();
    format!("{:02}:{:02}", secs / 60, secs % 60)
}

/// 5, 19.9k, 120k: the same short counts as the window's chat
fn short_count(n: u64) -> String {
    match n {
        0..=999 => n.to_string(),
        1_000..=99_949 => format!("{:.1}k", n as f64 / 1000.0),
        _ => format!("{}k", (n as f64 / 1000.0).round()),
    }
}

/// `/model sonnet` -> ("model", Some("sonnet")), `/effort` -> ("effort", None); anything else is a message.
fn slash_tune(prompt: &str) -> Option<(&'static str, Option<&str>)> {
    let mut words = prompt.split_whitespace();
    let key = match words.next()? {
        "/model" => "model",
        "/effort" => "effort",
        _ => return None,
    };
    let value = words.next();
    words.next().is_none().then_some((key, value))
}

/// A string field of a `reid --stream` event, cleaned for the screen.
fn field_of(event: &Value, key: &str) -> String {
    clean(event[key].as_str().unwrap_or_default())
}

impl Chat {
    fn engine(&self, profile: &str) -> String {
        self.profiles.iter().find(|(name, _)| name == profile).map(|(_, engine)| engine.clone())
            .unwrap_or_else(|| "claude".into())
    }

    fn picked(&self) -> String {
        self.profiles[self.pick].0.clone()
    }

    fn switching(&self) -> bool {
        self.picked() != self.cur && self.turns > 0
    }

    /// context only when the engine reported it; Codex doesn't, and "context unknown" said nothing
    fn ctx_text(&self) -> Option<String> {
        self.context.map(|pct| format!("context {pct}%"))
    }

    /// what the next turn may do: Claude and OpenCode turns have no shell, Codex keeps its sandboxed one
    fn capability(&self, profile: &str) -> String {
        let shell = if self.engine(profile) == "codex" { "shell" } else { "no shell" }; // OpenCode: the turn agent denies bash
        format!("{} · {shell}", if self.read_only { "read-only" } else { "edits" })
    }

    // ------------------------------------------------------------- turns ---
    fn send(&mut self) {
        let prompt = self.field.trim().to_string();
        if self.turn.is_some() || prompt.is_empty() {
            return;
        }
        if let Some((key, value)) = slash_tune(&prompt) {
            return self.tune_typed(key, value);
        }
        let profile = self.picked();
        let from = self.switching().then(|| self.cur.clone());
        self.note = Note::None;
        self.flash.clear();
        let undo = (self.cur.clone(), self.blocks.len());
        if let Some(from) = &from {
            self.blocks.push(Block::Switch { from: self.engine(from), to: self.engine(&profile) });
        }
        self.cur = profile.clone();
        self.blocks.push(Block::Ask { who: format!("{profile} · {}", self.engine(&profile)), text: prompt.clone() });
        (self.context, self.cost, self.tokens, self.scroll) = (None, 0.0, None, 0);
        let mut args = vec!["--stream".to_string(), profile.clone(), "--chat".into(), self.chat.clone()];
        if self.read_only {
            args.push("--read-only".into());
        }
        if let Some(sid) = self.sids.get(&profile) {
            args.extend(["--resume".into(), sid.clone()]);
        }
        if let Some(tune) = self.tunes.get(&profile).filter(|tune| !tune.is_empty()) {
            args.extend(["--with".into(), Value::Object(tune.clone()).to_string()]);
        }
        if let Some(from) = from {
            args.extend(["--switch-from".into(), from]);
        }
        args.push("-".into()); // the prompt on stdin: no length limit, nothing in the process list
        let before = if self.read_only { None } else { changes::snapshot(&self.folder) };
        let spawned = std::env::current_exe().and_then(|exe| Command::new(exe).args(&args).current_dir(&self.folder)
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).creation_flags(CREATE_NO_WINDOW).spawn());
        let mut child = match spawned {
            Ok(child) => child,
            Err(error) => {
                self.blocks.push(Block::Fail(format!("Couldn't start reid ({error}).")));
                return;
            }
        };
        let (mut stdin, stdout, mut stderr) = (child.stdin.take().unwrap(), child.stdout.take().unwrap(), child.stderr.take().unwrap());
        let input = prompt.clone();
        std::thread::spawn(move || {
            let _ = stdin.write_all(input.as_bytes());
        }); // dropped there: EOF
        let tail = std::thread::spawn(move || {
            let mut text = String::new();
            let _ = stderr.read_to_string(&mut text);
            let text = text.trim();
            let start = text.char_indices().rev().nth(MAX_STDERR_TAIL_CHARS - 1).map_or(0, |(at, _)| at);
            text[start..].to_string()
        });
        let (tx, rx) = channel();
        std::thread::spawn(move || {
            for line in std::io::BufReader::new(stdout).lines().map_while(Result::ok) {
                if let Ok(event) = serde_json::from_str::<Value>(&line) {
                    let _ = tx.send(Msg::Event(event));
                }
            }
            let _ = tx.send(Msg::Eof(tail.join().unwrap_or_default()));
        });
        self.turn = Some(Turn { child, rx, began: Instant::now(), profile, prompt, read_only: self.read_only, stopped: false,
                                refused: false, saw_text: false, before, undo });
    }

    fn stop(&mut self) {
        if let Some(turn) = self.turn.as_mut() {
            turn.stopped = true;
            let _ = turn.child.kill();
        }
    }

    /// The running turn's news; true when something changed.
    fn pump(&mut self) -> bool {
        let Some(turn) = self.turn.as_ref() else { return false };
        let messages: Vec<Msg> = turn.rx.try_iter().collect();
        let any = !messages.is_empty();
        for message in messages {
            match message {
                Msg::Event(event) => self.event(&event),
                Msg::Eof(stderr_tail) => self.finish(stderr_tail),
            }
        }
        any
    }

    fn event(&mut self, event: &Value) {
        let Some(turn) = self.turn.as_mut() else { return };
        match event["type"].as_str().unwrap_or_default() {
            "started" => {
                self.sids.insert(turn.profile.clone(), field_of(event, "session_id"));
                if self.field.trim() == turn.prompt {
                    self.field.clear(); // it's on its way; what you typed since stays
                }
            }
            "text_delta" => {
                turn.saw_text = true;
                let text = field_of(event, "text");
                match self.blocks.last_mut() {
                    Some(Block::Text(reply)) => reply.push_str(&text),
                    _ => self.blocks.push(Block::Text(text)),
                }
            }
            "note" => self.blocks.push(Block::Info(field_of(event, "text"))),
            "tool_call" => self.blocks.push(Block::Tool {
                name: field_of(event, "name").to_lowercase(),
                summary: field_of(event, "summary"),
            }),
            "usage" => {
                self.context = event["context_pct"].as_u64().map(|pct| pct as u8);
                if let Some(cost) = event["cost_usd"].as_f64() {
                    self.cost = cost;
                }
                let tokens = &event["tokens"];
                self.tokens = tokens["in"].as_u64().zip(tokens["out"].as_u64())
                    .map(|(input, output)| format!("{} in · {} out", short_count(input), short_count(output)));
            }
            "error" if event["kind"] == "refused" => {
                let message = field_of(event, "message");
                turn.refused = true;
                // nothing ran: the ask stays in the field, and a refused switch isn't one
                let (prev, len) = turn.undo.clone();
                let profile = turn.profile.clone();
                self.blocks.truncate(len);
                self.cur = prev;
                self.note = if message.contains("open in another window") {
                    Note::InTerminal(self.sids.get(&profile).cloned().unwrap_or_default())
                } else if message.contains("window is open in this folder") {
                    Note::Locked("A Reidcc window is open in this folder.".into())
                } else if message.to_lowercase().contains("turn is writing") {
                    Note::Locked("Another turn is writing in this folder.".into())
                } else {
                    Note::Refused(message)
                };
                self.polled = Instant::now();
            }
            "error" => {
                let profile = turn.profile.clone();
                let message = if event["kind"] == "unknown" {
                    let raw = field_of(event, "raw");
                    let raw = if raw.is_empty() { raw } else { format!("\n{raw}") };
                    format!("{} ended ({}).{raw}", self.engine(&profile), event["exit_code"])
                } else {
                    field_of(event, "message")
                };
                self.blocks.push(Block::Fail(message));
            }
            _ => {}
        }
    }

    fn finish(&mut self, stderr_tail: String) {
        let Some(mut turn) = self.turn.take() else { return };
        let exit_code = turn.child.wait().ok().and_then(|status| status.code()).unwrap_or(1);
        if turn.refused {
            return;
        }
        let failed = self.blocks[turn.undo.1..].iter().any(|block| matches!(block, Block::Fail(_)));
        if !stderr_tail.is_empty() && !turn.stopped && !turn.saw_text && !failed {
            self.blocks.push(Block::Fail(clean(&stderr_tail))); // reid itself failed: nothing streamed, its stderr says why
        }
        if !turn.read_only {
            if let Some((from, to)) = turn.before.take().zip(changes::snapshot(&self.folder)) {
                let files = changes::changed(&self.folder, &from, &to);
                if !files.is_empty() {
                    self.blocks.push(Block::Changed { from, to, files, diffs: None });
                }
            }
        }
        let meta = if turn.stopped { "stopped".to_string() } else {
            let mut bits = vec![mmss(turn.began.elapsed())];
            bits.extend(self.ctx_text());
            if self.cost > 0.0 {
                bits.push(if self.cost < 1.0 { format!("${:.3}", self.cost) } else { format!("${:.2}", self.cost) });
            }
            bits.extend(self.tokens.clone());
            bits.push(if turn.read_only { "read-only" } else { "edits" }.into());
            if exit_code != 0 && !failed {
                bits.push(format!("exit {exit_code}"));
            }
            bits.join(" · ")
        };
        self.blocks.push(Block::Meta(meta));
        self.turns += 1;
    }

    /// A held session: is it free yet?
    fn poll(&mut self, tui: &Tui) -> bool {
        let Note::InTerminal(sid) = &self.note else { return false };
        if self.polled.elapsed() < HOLDER_POLL {
            return false;
        }
        self.polled = Instant::now();
        if locks::holder(tui.ctx, sid).is_none() {
            self.note = Note::None;
            return true;
        }
        false
    }

    /// ctrl+t: the picked profile's session (`reid --resume <profile> --id <id>`) in a console of its own.
    fn terminal(&mut self) {
        if let Some(terminal) = self.terminal.as_mut() {
            if matches!(terminal.try_wait(), Ok(None)) {
                self.flash = "The terminal is open in its own window.".into();
                return;
            }
        }
        let profile = self.picked();
        let args: Vec<String> = match self.sids.get(&profile) {
            Some(sid) => vec!["--resume".into(), profile.clone(), "--id".into(), sid.clone()],
            None => vec![profile.clone()],
        };
        match std::env::current_exe().and_then(|exe| Command::new(exe).args(&args).current_dir(&self.folder)
            .creation_flags(CREATE_NEW_CONSOLE).spawn()) {
            Ok(child) => {
                self.terminal = Some(child);
                self.flash = format!("{profile} opened in a terminal window.");
            }
            Err(error) => self.flash = format!("Couldn't open a terminal ({error})."),
        }
    }

    fn toggle_diff(&mut self) {
        let folder = self.folder.clone();
        let last_changed = self.blocks.iter_mut().rev().find(|block| matches!(block, Block::Changed { .. }));
        let Some(Block::Changed { from, to, files, diffs }) = last_changed else {
            self.flash = "No changes to show yet.".into();
            return;
        };
        *diffs = match diffs {
            Some(_) => None,
            None => Some(files.iter().map(|file| clean(&changes::file_diff(&folder, from, to, &file.path, MAX_DIFF_LINES))).collect()),
        };
    }

    fn open_handoff(&mut self) {
        let path = Path::new(&self.folder).join(reidcc::handoff::DIR).join("handoff.md");
        if path.exists() {
            crate::open_file(&path.to_string_lossy());
        } else {
            self.flash = "No handoff here yet.".into();
        }
    }

    // ------------------------------------------------------------ tuning ---
    fn own(&self, profile: &str) -> Obj {
        profiles(&self.cfg).get(profile).and_then(Value::as_object).cloned().unwrap_or_default()
    }

    /// The profile's value for `key` with this chat's change over it.
    fn tuned(&self, profile: &str, key: &str) -> Option<Value> {
        self.tunes.get(profile).and_then(|tune| tune.get(key)).cloned().or_else(|| self.own(profile).get(key).cloned())
    }

    fn open_tune(&mut self) {
        let profile = self.picked();
        self.load_choices(&profile);
        self.tuning = Some(0);
    }

    fn load_choices(&mut self, profile: &str) {
        if !self.choices.contains_key(profile) {
            self.choices.insert(profile.into(), tuning::choices(&self.own(profile), &self.folder));
        }
        let engine = self.engine(profile);
        if !self.models.contains_key(&engine) {
            self.models.insert(engine.clone(), tuning::models(&self.cfg, &engine));
        }
    }

    fn tune_rows(&self) -> Vec<TuneRow> {
        let Some(choices) = self.choices.get(&self.picked()) else { return vec![] };
        let mut rows = vec![TuneRow::Model, TuneRow::Effort];
        rows.extend(choices.mcp.iter().cloned().map(TuneRow::Mcp));
        rows.extend(choices.plugins.iter().map(|plugin| TuneRow::Plugin(plugin.id.clone())));
        rows
    }

    /// <-/-> on model or effort: the next value ("" is the profile's own); on a server or plugin, flip it.
    fn tune_change(&mut self, step: i64) {
        let (Some(row), profile) = (self.tuning, self.picked()) else { return };
        let Some(which) = self.tune_rows().get(row).cloned() else { return };
        let mut tune = self.tunes.get(&profile).cloned().unwrap_or_default();
        match &which {
            TuneRow::Model | TuneRow::Effort => {
                let (key, values) = if which == TuneRow::Model {
                    ("model", self.models.get(&self.engine(&profile)).cloned().unwrap_or_default())
                } else {
                    ("effort", self.choices.get(&profile).map(|c| c.efforts.clone()).unwrap_or_default())
                };
                // from the profile's own value; landing on it again (or on "default") is no change
                let own = reidcc::text(&self.own(&profile), key);
                let mut all = if own.is_empty() { vec![String::new()] } else { vec![] };
                all.extend(values);
                if !own.is_empty() && !all.contains(&own) {
                    all.insert(0, own.clone());
                }
                let now = tune.get(key).and_then(Value::as_str).map(String::from).unwrap_or_else(|| own.clone());
                let at = all.iter().position(|value| *value == now).unwrap_or(0) as i64;
                let next = all[(at + step).rem_euclid(all.len() as i64) as usize].clone();
                if next.is_empty() || next == own {
                    tune.remove(key);
                } else {
                    tune.insert(key.into(), Value::String(next));
                }
            }
            TuneRow::Mcp(server) => {
                let mut off: Vec<Value> = self.tuned(&profile, "mcp_off").and_then(|v| v.as_array().cloned()).unwrap_or_default();
                match off.iter().position(|name| name.as_str() == Some(server)) {
                    Some(at) => {
                        off.remove(at);
                    }
                    None => off.push(Value::String(server.clone())),
                }
                tune.insert("mcp_off".into(), Value::Array(off));
            }
            TuneRow::Plugin(id) => {
                let on = self.plugin_on(&profile, id);
                let mut switches = match self.tuned(&profile, "plugins") {
                    Some(Value::Object(map)) => map,
                    _ => Obj::new(),
                };
                switches.insert(id.clone(), Value::Bool(!on));
                tune.insert("plugins".into(), Value::Object(switches));
            }
        }
        self.tunes.insert(profile, tune);
    }

    /// `/model sonnet`, `/effort high`, `/effort default`: the tune panel's choice typed in the box; alone, it opens the panel.
    fn tune_typed(&mut self, key: &'static str, value: Option<&str>) {
        let Some(value) = value else {
            self.field.clear();
            return self.open_tune();
        };
        let profile = self.picked();
        self.load_choices(&profile);
        let efforts = self.choices.get(&profile).map(|c| c.efforts.clone()).unwrap_or_default();
        if key == "effort" && value != "default" && !efforts.iter().any(|e| e == value) {
            self.flash = format!("effort is one of default · {}", efforts.join(" · "));
            return;
        }
        let own = reidcc::text(&self.own(&profile), key);
        let tune = self.tunes.entry(profile.clone()).or_default();
        if value == "default" || value == own {
            tune.remove(key);
        } else {
            tune.insert(key.into(), Value::String(value.into()));
        }
        let now = match tune.get(key).and_then(Value::as_str) {
            Some(chosen) => chosen.to_string(),
            None if own.is_empty() => "default".into(),
            None => format!("{own} (the profile's)"),
        };
        self.field.clear();
        self.flash = format!("{profile} · {key} {now} · from the next turn, this chat only");
    }

    fn plugin_on(&self, profile: &str, id: &str) -> bool {
        let chat = self.tunes.get(profile).and_then(|tune| tune.get("plugins")).and_then(|p| p.get(id)).and_then(Value::as_bool);
        chat.unwrap_or_else(|| self.choices.get(profile).and_then(|c| c.plugins.iter().find(|p| p.id == id)).is_some_and(|p| p.on))
    }

    fn mcp_on(&self, profile: &str, server: &str) -> bool {
        !self.tuned(profile, "mcp_off").and_then(|v| v.as_array().cloned()).unwrap_or_default().iter().any(|v| v.as_str() == Some(server))
    }

    /// `haiku · high · tools changed`: what this chat changed for a profile, for the controls line.
    fn tune_summary(&self, profile: &str) -> String {
        let Some(tune) = self.tunes.get(profile) else { return String::new() };
        let mut parts: Vec<String> = ["model", "effort"].iter().filter_map(|key| tune.get(*key).and_then(Value::as_str).map(String::from)).collect();
        if tune.contains_key("mcp_off") || tune.contains_key("plugins") {
            parts.push("tools changed".into());
        }
        parts.join(" · ")
    }

    fn tune_lines(&self) -> Vec<String> {
        let profile = self.picked();
        let own = self.own(&profile);
        let mut out = vec![format!("{B}{TEXT}tune {profile} · {}{R}  {TEXT3}this chat only · reid.json stays as it is{R}", self.engine(&profile)),
                           String::new()];
        let tick = |on: bool| if on { format!("{TEXT}✓{R}") } else { format!("{TEXT3}·{R}") };
        let rows = self.tune_rows();
        for (i, row) in rows.iter().enumerate() {
            let mark = if self.tuning == Some(i) { format!("{TEXT}›{R}") } else { " ".into() };
            let (label, value) = match row {
                TuneRow::Model | TuneRow::Effort => {
                    let key = if *row == TuneRow::Model { "model" } else { "effort" };
                    let chat = self.tunes.get(&profile).and_then(|tune| tune.get(key)).and_then(Value::as_str);
                    let profile_value = reidcc::text(&own, key);
                    let value = match chat {
                        Some(value) => format!("{TEXT}‹ {value} ›{R}"),
                        None if !profile_value.is_empty() => format!("{TEXT2}‹ {profile_value} ›{R} {TEXT3}the profile's{R}"),
                        None => format!("{TEXT2}‹ default ›{R}"),
                    };
                    (key, value)
                }
                TuneRow::Mcp(server) => ("mcp", format!("{} {TEXT2}{server}{R}", tick(self.mcp_on(&profile, server)))),
                TuneRow::Plugin(id) => ("plugin", format!("{} {TEXT2}{id}{R}", tick(self.plugin_on(&profile, id)))),
            };
            out.push(format!("{mark} {TEXT3}{}{R}{value}", super::ljust(label, 8))); // short rows: fit() would count the colours
        }
        if rows.len() == 2 {
            out.push(format!("  {TEXT3}No MCP servers or plugins found for this profile.{R}"));
        }
        out
    }

    // ----------------------------------------------------------- drawing ---
    fn lines(&self, width: i64) -> Vec<String> {
        let mut out: Vec<String> = vec![];
        for block in &self.blocks {
            match block {
                Block::Info(text) => out.extend(wrap(&[(DIM.into(), text.clone())], width)),
                Block::Ask { who, text } => {
                    if !out.is_empty() {
                        out.push(String::new());
                    }
                    let pieces = [(TEXT3.to_string(), format!("{who} › ")), (TEXT.into(), clean(text).replace('\n', " "))];
                    out.extend(wrap(&pieces, width).into_iter().map(|line| format!("{LINE}▏{R}{line}")));
                    out.push(String::new());
                }
                Block::Tool { name, summary } => out.push(format!("{TEXT2}{}{R} {TEXT3}{}{R}", super::ljust(name, TOOL_NAME_WIDTH),
                                                                  fit(summary, (width - TOOL_NAME_WIDTH - 1).max(1)))),
                Block::Text(reply) => out.extend(md_lines(reply, width)),
                Block::Fail(text) => out.extend(wrap(&[(OXIDE.into(), text.clone())], width)),
                Block::Meta(text) => out.push(format!("{TEXT3}{text}{R}")),
                Block::Changed { files, diffs, .. } => {
                    let (added, removed) = files.iter().fold((0, 0), |(added, removed), file| {
                        (added + file.added.unwrap_or(0), removed + file.removed.unwrap_or(0))
                    });
                    let n = files.len();
                    let hint = if diffs.is_some() { "ctrl+d closes" } else { "ctrl+d shows the diff" };
                    out.push(format!("{TEXT2}changed · {n} file{}{R}  {} {}   {TEXT3}{hint}{R}", if n == 1 { "" } else { "s" },
                                     count('+', Some(added)), count('−', Some(removed))));
                    for (i, file) in files.iter().enumerate() {
                        let path = clean(&file.path);
                        out.push(format!("  {TEXT}{}{R}  {} {}", fit(&path, (width - 16).max(4)), count('+', file.added),
                                         count('−', file.removed)));
                        let Some(diffs) = diffs else { continue };
                        for line in diffs[i].lines() {
                            let color = if line.starts_with("@@") { TEXT3 } else if line.starts_with('+') { TEXT }
                                        else if line.starts_with('-') { OXIDE } else { TEXT2 };
                            out.push(format!("  {RULE}│{R} {color}{}{R}", fit(line, (width - 4).max(1))));
                        }
                    }
                }
                Block::Switch { from, to } => {
                    let label = format!(" switch · {from} → {to} · .reid/handoff.md ");
                    let side = ((width - clen(&label)) / 2).max(2);
                    out.push(String::new());
                    out.push(format!("{RULE}{}{R}{LINE}{label}{R}{RULE}{}{R}", rep("─", side), rep("─", (width - side - clen(&label)).max(0))));
                    out.push(String::new());
                }
            }
        }
        if let Some(turn) = &self.turn {
            if !turn.refused {
                out.push(format!("{TEXT2}▍{R}")); // the caret: the turn is still going
            }
        }
        out
    }

    fn draw(&mut self, tui: &Tui) {
        let (width, height) = tui.size();
        let body_width = width - 4;
        // the bar: where and who on the left, the meters on the right (emerald only while a turn runs)
        let state = match &self.turn {
            Some(turn) => format!("{EMERALD}● {}{R}", mmss(turn.began.elapsed())),
            None => format!("{TEXT2}ready{R}"),
        };
        let right = match self.ctx_text() {
            Some(context) => format!("{state} {TEXT2}· {context}{R} "),
            None => format!("{state} "),
        };
        let who = format!("{} · {}{}", self.cur, self.engine(&self.cur), if self.read_only { " · read-only" } else { "" });
        // the path gives way first, so who and the meters stay on the bar's one line
        let path_room = width - BAR_FIXED - clen(&who) - shown_len(&right);
        let left = format!(" {LINE}RC{R}  {TEXT}{}{R}  {TEXT2}{who}{R}", fit(&show_path(&self.folder), (width / 2).min(path_room).max(10)));
        let mut screen = vec![format!("{left}{}{right}", rep(" ", (width - shown_len(&left) - shown_len(&right)).max(1))), tui.rule()];

        // the composer: note, field, controls, keys
        let mut composer = vec![tui.rule()];
        let note = match &self.note {
            Note::None => None,
            Note::InTerminal(_) => Some(format!("{BRONZE}in terminal{R}  {TEXT2}This session is open in a terminal. It clears when that closes.{R}")),
            Note::Locked(message) => Some(format!("{BRONZE}locked{R}  {TEXT2}{message}{R}  {TEXT}ctrl+r sends it read-only{R}")),
            Note::Refused(message) => Some(format!("{BRONZE}refused{R}  {TEXT2}{}{R}", fit(message, (width - 14).max(4)))),
        };
        if let Some(note) = note {
            composer.push(format!(" {note}"));
        } else if !self.flash.is_empty() {
            composer.push(format!(" {TEXT2}{}{R}", fit(&self.flash, width - 2)));
        }
        let shown = if self.field.is_empty() && self.turn.is_none() { format!("{TEXT3}Ask {}…{R}", self.picked()) }
                    else { self.field.clone() };
        let field = wrap(&[(TEXT.into(), shown)], body_width - 2);
        let start = field.len().saturating_sub(FIELD_ROWS);
        for (i, line) in field[start..].iter().enumerate() {
            let cursor = if i + start == field.len() - 1 && self.turn.is_none() { "\x1b[7m \x1b[27m" } else { "" };
            composer.push(format!(" {TEXT3}{}{R} {line}{cursor}", if i == 0 { "›" } else { " " }));
        }
        let profile = self.picked();
        let primary = if self.turn.is_some() { format!("{OXIDE}esc stop{R}") }
                      else if self.switching() { format!("{TEXT}↵ switch → {}{R}", self.engine(&profile)) }
                      else { format!("{TEXT}↵ send{R}") };
        let summary = self.tune_summary(&profile);
        let summary = if summary.is_empty() { String::new() } else { format!(" {TEXT2}· {summary}{R}") };
        let controls = format!(" {TEXT}{profile} · {}{R}{summary}   {TEXT}{}{R} {TEXT2}read-only{R}", self.engine(&profile),
                               if self.read_only { "✓" } else { "·" });
        // what the turn may do sits before the key, when the line has room for it
        let with_capability = format!("{TEXT2}{}{R}   {primary}", self.capability(&profile));
        let primary = if shown_len(&controls) + shown_len(&with_capability) + 2 <= width { with_capability } else { primary };
        composer.push(format!("{controls}{}{primary} ", rep(" ", (width - shown_len(&controls) - shown_len(&primary) - 1).max(1))));
        let back = if self.turn.is_some() { "" } else { " · esc back" };
        if self.tuning.is_some() {
            composer.push(tui.help("↑↓ choose · ←→ change · space switch · ^e or esc done"));
        } else {
            composer.push(tui.help(&format!("tab profile · ^e tune · ^r read-only · ^t terminal · ^d diff · ^o handoff · pgup/pgdn{back}")));
        }

        let room = (height - 1 - screen.len() as i64 - composer.len() as i64).max(1);
        let all = if self.tuning.is_some() { self.tune_lines() } else { self.lines(body_width) };
        let total = all.len() as i64;
        self.scroll = self.scroll.clamp(0, (total - room).max(0));
        let end = total - self.scroll;
        let first = (end - room).max(0);
        let mut body: Vec<String> = all[first as usize..end as usize].iter().map(|line| format!("  {line}")).collect();
        if self.scroll > 0 {
            if let Some(last) = body.last_mut() {
                *last = format!("  {TEXT3}↓ {} more lines · end jumps there{R}", self.scroll);
            }
        }
        while (body.len() as i64) < room {
            body.push(String::new());
        }
        screen.extend(body);
        screen.extend(composer);
        tui.paint(&screen);
    }
}

/// the width a line takes on screen: its characters without the colour escapes
fn shown_len(line: &str) -> i64 {
    clen(&strip_sgr(line))
}

/// The chat view on `profile` in the TUI's folder; back to the caller when you leave it (esc).

pub(super) fn run(tui: &mut Tui, profile: &str) -> T<()> {
    let cfg = load_config(tui.ctx)?;
    let all: Vec<(String, String)> = profiles(&cfg).iter()
        .map(|(name, prof)| (name.clone(), super::engine_str(prof.as_object().unwrap_or(&Default::default())))).collect();
    let Some(pick) = all.iter().position(|(name, _)| name == profile) else {
        return Err(Stop::Err(reidcc::ReidError(format!("No profile named {profile}."))));
    };
    let mut chat = Chat {
        folder: tui.cwd.clone(), cfg: cfg.clone(), tunes: HashMap::new(), choices: HashMap::new(), models: HashMap::new(), tuning: None,
        cur: profile.into(), pick, profiles: all, sids: HashMap::new(), chat: reidcc::transcript::new_chat_id(), turns: 0, read_only: false,
        field: String::new(), blocks: vec![], note: Note::None, polled: Instant::now(), turn: None, context: None, cost: 0.0, tokens: None,
        scroll: 0, terminal: None, flash: String::new(),
    };
    chat.blocks.push(Block::Info(format!("{} · ask {profile} anything. Turns make edits, or only read with read-only on; ctrl+t opens a terminal for shell and tests.",
                                         show_path(&chat.folder))));
    let (mut dirty, mut drawn, mut size) = (true, Instant::now(), tui.size());
    loop {
        if console::interrupted() {
            return Err(Stop::Int);
        }
        dirty |= chat.pump() | chat.poll(tui) | (tui.size() != size);
        if dirty || (chat.turn.is_some() && drawn.elapsed() >= TIMER_REDRAW) {
            size = tui.size();
            chat.draw(tui);
            (dirty, drawn) = (false, Instant::now());
        }
        if !console::kbhit() {
            std::thread::sleep(KEY_POLL);
            continue;
        }
        let key = getkey()?;
        dirty = true;
        let page = (tui.size().1 / 2).max(3);
        if let Some(row) = chat.tuning {
            let rows = chat.tune_rows().len();
            match key.as_str() {
                "esc" | CTRL_E => chat.tuning = None,
                "up" => chat.tuning = Some(row.saturating_sub(1)),
                "down" => chat.tuning = Some((row + 1).min(rows.saturating_sub(1))),
                "left" => chat.tune_change(-1),
                "right" | " " | "enter" => chat.tune_change(1),
                _ => {}
            }
            continue;
        }
        match key.as_str() {
            CTRL_E if chat.turn.is_none() => chat.open_tune(),
            "esc" if chat.turn.is_some() => chat.stop(),
            "esc" => return Ok(()),
            // shortcut: a pasted line break sends, like Enter; a multi-line paste needs the chat window
            "enter" => chat.send(),
            "backspace" => {
                chat.field.pop();
            }
            TAB if chat.turn.is_none() => chat.pick = (chat.pick + 1) % chat.profiles.len(),
            CTRL_R if chat.turn.is_none() => {
                if matches!(chat.note, Note::Locked(_)) {
                    (chat.read_only, chat.note) = (true, Note::None);
                    chat.send();
                } else {
                    chat.read_only = !chat.read_only;
                }
            }
            CTRL_T => chat.terminal(),
            CTRL_D => chat.toggle_diff(),
            CTRL_O => chat.open_handoff(),
            "pgup" | "up" => chat.scroll += page,
            "pgdn" | "down" => chat.scroll = (chat.scroll - page).max(0),
            "end" => chat.scroll = 0,
            typed if typed.chars().count() == 1 && !typed.chars().next().is_some_and(char::is_control) => chat.field.push_str(typed),
            _ => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::strip_sgr;
    use super::*;

    #[test]
    fn token_counts_stay_short() {
        assert_eq!([5, 999, 19_881, 99_949, 99_999, 120_400].map(short_count), ["5", "999", "19.9k", "99.9k", "100k", "120k"]);
    }

    #[test]
    fn slash_model_and_effort_are_tune_not_messages() {
        assert_eq!(slash_tune("/model sonnet"), Some(("model", Some("sonnet"))));
        assert_eq!(slash_tune("/effort"), Some(("effort", None)));
        assert_eq!(slash_tune("/effort high please"), None);
        assert_eq!(slash_tune("/models"), None);
        assert_eq!(slash_tune("set /model sonnet"), None);
    }

    #[test]
    fn replies_render_like_the_chat_window() {
        let plain = |text: &str| md_lines(text, 60).iter().map(|line| strip_sgr(line).trim_end().to_string()).collect::<Vec<_>>();
        assert_eq!(plain("Use `Option<T>` and **care**, see [calc.py](C:/w/calc.py:9)."),
                   vec!["Use Option<T> and care, see calc.py."]);
        // a fence still streaming is code already, its ``` hidden
        assert_eq!(plain("Here:\n```rust\nfn x() {"), vec!["Here:", " fn x() {"]);
        assert!(md_lines("```\nfn x() {", 60)[0].contains(VAL));
        assert_eq!(plain("## Title\nan unclosed `tick and **star"), vec!["Title", "an unclosed `tick and **star"]);
        assert_eq!(plain("a [b] (c) [d](e f)"), vec!["a [b] (c) [d](e f)"]);
        // a link's text can hold code (Codex: [The `--version` check](path)); code never becomes a link
        let pieces = inline("see [The `--version` check](C:/w/reid.py:2173).");
        assert_eq!(pieces.iter().map(|(_, text)| text.as_str()).collect::<String>(), "see The --version check.");
        assert!(pieces.iter().any(|(style, text)| text == "--version" && style.contains(UNDER) && style.contains(CODE)));
        assert_eq!(plain("`arr[0](x)` and [a](b)"), vec!["arr[0](x) and a"]);
        assert!(inline("`arr[0](x)`").iter().all(|(style, _)| !style.contains(UNDER)));
        // engine text can't drive the terminal
        assert_eq!(clean("hi\x1b[2Jthere\x07\tx"), "hi[2Jthere    x");
        // wrapped at the width, indents only on a line's first row
        assert_eq!(plain("  - one two three four five six seven eight nine ten eleven twelve thirteen"),
                   vec!["  - one two three four five six seven eight nine ten eleven", "twelve thirteen"]);
    }
}
