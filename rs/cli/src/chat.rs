//! The TUI's chat view (vision\Spec\SPEC-unified-interface.md Part 6, Milestone 2B): ui\src\chat.ts in
//! text. One folder, one composer over Claude Code and Codex. Each turn is a `reid --stream` child, as in
//! the chat window: stop kills it and its job takes the engine down; a crashed turn can't take the TUI.

use super::{clen, fit, getkey, rep, Stop, Tui, B, DIM, EMERALD, LINE, RULE, T, VAL};
use crate::console;
use reidcc::term::{BRONZE, OXIDE, R, TEXT, TEXT2, TEXT3};
use reidcc::{changes, load_config, locks, profiles, show_path};
use serde_json::Value;
use std::collections::HashMap;
use std::io::{BufRead, Read, Write};
use std::os::windows::process::CommandExt;
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{channel, Receiver};
use std::time::{Duration, Instant};

const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const CREATE_NEW_CONSOLE: u32 = 0x10;
const CODE: &str = "\x1b[48;2;23;21;19m"; // --s2 under inline code
const UNDER: &str = "\x1b[4m";

enum Msg {
    Event(Value),
    /// stdout ended; `err` is the end of reid's stderr
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
    ro: bool,
    stopped: bool,
    refused: bool,
    saw_text: bool,
    /// the folder before a write turn (a git tree), for its diff
    before: Option<String>,
    /// how to take the turn back if reid refuses it: the profile talked to, and the stream's length
    undo: (String, usize),
}

struct Chat {
    folder: String,
    profiles: Vec<(String, String)>,
    cur: String,
    pick: usize,
    sids: HashMap<String, String>,
    turns: usize,
    ro: bool,
    field: String,
    blocks: Vec<Block>,
    note: Note,
    polled: Instant,
    turn: Option<Turn>,
    context: Option<u8>,
    cost: f64,
    scroll: i64,
    terminal: Option<Child>,
    flash: String,
}

impl Drop for Chat {
    fn drop(&mut self) {
        if let Some(t) = self.turn.as_mut() {
            let _ = t.child.kill(); // leaving (or Ctrl+C) ends a running turn; a terminal window stays
        }
    }
}

/// Engine text for the screen: no control characters (an escape sequence in a reply must not drive
/// the terminal), tabs as spaces.
pub(super) fn clean(s: &str) -> String {
    s.chars().flat_map(|c| match c {
        '\t' => vec![' '; 4],
        '\n' => vec!['\n'],
        c if c.is_control() => vec![],
        c => vec![c],
    }).collect()
}

/// One markdown line outside a fence as styled pieces: `code`, **bold**, [text](target) -> text.
fn inline(line: &str) -> Vec<(String, String)> {
    let mut out = vec![];
    if let Some(h) = line.trim_start().strip_prefix('#') {
        let h = h.trim_start_matches('#');
        if h.starts_with(' ') {
            return inline(h.trim()).into_iter().map(|(st, t)| (format!("{B}{st}"), t)).collect();
        }
    }
    let parts: Vec<&str> = line.split('`').collect();
    let closed = parts.len() % 2 == 1; // an odd count of pieces: every ` has its pair
    for (i, part) in parts.iter().enumerate() {
        if i % 2 == 1 && (closed || i < parts.len() - 1) {
            out.push((format!("{CODE}{TEXT}"), part.to_string()));
            continue;
        }
        let part = if i % 2 == 1 { format!("`{part}") } else { part.to_string() }; // the unclosed one
        let bold: Vec<&str> = part.split("**").collect();
        let paired = bold.len() % 2 == 1;
        for (j, b) in bold.iter().enumerate() {
            if j % 2 == 1 && (paired || j < bold.len() - 1) {
                out.push((format!("{B}{TEXT}"), b.to_string()));
            } else {
                let b = if j % 2 == 1 { format!("**{b}") } else { b.to_string() };
                links(&b, &mut out);
            }
        }
    }
    out
}

/// `[text](target)` shows its text, underlined; anything else is plain.
fn links(s: &str, out: &mut Vec<(String, String)>) {
    let mut rest = s;
    while let Some(a) = rest.find('[') {
        let found = rest[a..].find("](").map(|m| a + m).and_then(|m| {
            let close = rest[m + 2..].find(')').map(|c| m + 2 + c)?;
            let target = &rest[m + 2..close];
            (!target.is_empty() && !target.contains(char::is_whitespace) && !rest[a + 1..m].contains('[')).then_some((m, close))
        });
        match found {
            Some((m, close)) => {
                out.push((TEXT.into(), rest[..a].into()));
                out.push((format!("{UNDER}{TEXT}"), rest[a + 1..m].into()));
                rest = &rest[close + 1..];
            }
            None => {
                out.push((TEXT.into(), rest[..=a].into()));
                rest = &rest[a + 1..];
            }
        }
    }
    out.push((TEXT.into(), rest.into()));
}

/// Styled pieces wrapped at `w` columns; a line's leading spaces (a list's indent) stay on its first row.
fn wrap(pieces: &[(String, String)], w: i64) -> Vec<String> {
    let w = w.max(8);
    let (mut lines, mut cur, mut cw, mut first) = (vec![], String::new(), 0i64, true);
    for (style, text) in pieces {
        let mut tokens: Vec<String> = vec![];
        for c in text.chars() {
            match tokens.last_mut() {
                Some(t) if (c == ' ') == t.starts_with(' ') => t.push(c),
                _ => tokens.push(c.to_string()),
            }
        }
        for tok in tokens {
            let tw = clen(&tok);
            if tok.starts_with(' ') {
                if cw == 0 && !first {
                    continue;
                }
                if cw + tw > w {
                    lines.push(std::mem::take(&mut cur));
                    (cw, first) = (0, false);
                    continue;
                }
            } else if cw + tw > w && cw > 0 {
                lines.push(std::mem::take(&mut cur));
                (cw, first) = (0, false);
            }
            let mut tok = tok;
            while clen(&tok) > w {
                // a word longer than the line: cut it
                let head: String = tok.chars().take((w - cw).max(1) as usize).collect();
                tok = tok.chars().skip(head.chars().count()).collect();
                cur += &format!("{style}{head}{R}");
                lines.push(std::mem::take(&mut cur));
                (cw, first) = (0, false);
            }
            cw += clen(&tok);
            cur += &format!("{style}{tok}{R}");
        }
    }
    if !cur.is_empty() || lines.is_empty() {
        lines.push(cur);
    }
    lines
}

/// A reply as screen lines (the chat window's md.ts rules). A fence still open (the text is
/// streaming) is code to the end.
pub(super) fn md_lines(text: &str, w: i64) -> Vec<String> {
    let mut out = vec![];
    let mut code = false;
    for line in clean(text).split('\n') {
        if line.trim_start().starts_with("```") && line.len() - line.trim_start().len() <= 3 {
            code = !code;
            continue;
        }
        if code {
            out.push(format!("{VAL}{TEXT} {} {R}", super::ljust(&fit(line, w - 2), w - 2)));
        } else if line.trim().is_empty() {
            out.push(String::new());
        } else {
            out.extend(wrap(&inline(line), w));
        }
    }
    out
}

fn count(sign: char, n: Option<u64>) -> String {
    match n {
        None => format!("{TEXT3}bin{R}"),
        Some(0) => format!("{TEXT3}{sign}0{R}"),
        Some(n) => format!("{}{sign}{n}{R}", if sign == '+' { TEXT } else { OXIDE }),
    }
}

fn mmss(d: Duration) -> String {
    let s = d.as_secs();
    format!("{:02}:{:02}", s / 60, s % 60)
}

impl Chat {
    fn engine(&self, p: &str) -> String {
        self.profiles.iter().find(|(n, _)| n == p).map(|(_, e)| e.clone()).unwrap_or_else(|| "claude".into())
    }

    fn picked(&self) -> String {
        self.profiles[self.pick].0.clone()
    }

    fn switching(&self) -> bool {
        self.picked() != self.cur && self.turns > 0
    }

    fn ctx_text(&self) -> String {
        match self.context {
            Some(c) => format!("context {c}%"),
            None => "context unknown".into(),
        }
    }

    // ------------------------------------------------------------- turns ---
    fn send(&mut self) {
        let prompt = self.field.trim().to_string();
        if self.turn.is_some() || prompt.is_empty() {
            return;
        }
        let profile = self.picked();
        let from = self.switching().then(|| self.cur.clone());
        self.note = Note::None;
        self.flash.clear();
        let undo = (self.cur.clone(), self.blocks.len());
        if let Some(f) = &from {
            self.blocks.push(Block::Switch { from: self.engine(f), to: self.engine(&profile) });
        }
        self.cur = profile.clone();
        self.blocks.push(Block::Ask { who: format!("{profile} · {}", self.engine(&profile)), text: prompt.clone() });
        (self.context, self.cost, self.scroll) = (None, 0.0, 0);
        let mut args = vec!["--stream".to_string(), profile.clone()];
        if self.ro {
            args.push("--read-only".into());
        }
        if let Some(s) = self.sids.get(&profile) {
            args.extend(["--resume".into(), s.clone()]);
        }
        if let Some(f) = from {
            args.extend(["--switch-from".into(), f]);
        }
        args.push("-".into()); // the prompt on stdin: no length limit, nothing in the process list
        let before = if self.ro { None } else { changes::snapshot(&self.folder) };
        let spawned = std::env::current_exe().and_then(|exe| Command::new(exe).args(&args).current_dir(&self.folder)
            .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).creation_flags(CREATE_NO_WINDOW).spawn());
        let mut child = match spawned {
            Ok(c) => c,
            Err(e) => {
                self.blocks.push(Block::Fail(format!("Couldn't start reid ({e}).")));
                return;
            }
        };
        let (mut stdin, stdout, mut stderr) = (child.stdin.take().unwrap(), child.stdout.take().unwrap(), child.stderr.take().unwrap());
        let p = prompt.clone();
        std::thread::spawn(move || {
            let _ = stdin.write_all(p.as_bytes());
        }); // dropped there: EOF
        let tail = std::thread::spawn(move || {
            let mut s = String::new();
            let _ = stderr.read_to_string(&mut s);
            let s = s.trim().to_string();
            s.chars().skip(s.chars().count().saturating_sub(600)).collect::<String>()
        });
        let (tx, rx) = channel();
        std::thread::spawn(move || {
            for line in std::io::BufReader::new(stdout).lines().map_while(Result::ok) {
                if let Ok(v) = serde_json::from_str::<Value>(&line) {
                    let _ = tx.send(Msg::Event(v));
                }
            }
            let _ = tx.send(Msg::Eof(tail.join().unwrap_or_default()));
        });
        self.turn = Some(Turn { child, rx, began: Instant::now(), profile, prompt, ro: self.ro, stopped: false, refused: false,
                                saw_text: false, before, undo });
    }

    fn stop(&mut self) {
        if let Some(t) = self.turn.as_mut() {
            t.stopped = true;
            let _ = t.child.kill();
        }
    }

    /// The running turn's news; true when something changed.
    fn pump(&mut self) -> bool {
        let Some(t) = self.turn.as_ref() else { return false };
        let msgs: Vec<Msg> = t.rx.try_iter().collect();
        let any = !msgs.is_empty();
        for m in msgs {
            match m {
                Msg::Event(e) => self.event(&e),
                Msg::Eof(err) => self.finish(err),
            }
        }
        any
    }

    fn event(&mut self, e: &Value) {
        let s = |k: &str| clean(e[k].as_str().unwrap_or_default());
        let Some(t) = self.turn.as_mut() else { return };
        match e["type"].as_str().unwrap_or_default() {
            "started" => {
                self.sids.insert(t.profile.clone(), s("session_id"));
                if self.field.trim() == t.prompt {
                    self.field.clear(); // it's on its way; what you typed since stays
                }
            }
            "text_delta" => {
                t.saw_text = true;
                match self.blocks.last_mut() {
                    Some(Block::Text(x)) => x.push_str(&s("text")),
                    _ => self.blocks.push(Block::Text(s("text"))),
                }
            }
            "tool_call" => self.blocks.push(Block::Tool { name: s("name").to_lowercase(), summary: s("summary") }),
            "usage" => {
                self.context = e["context_pct"].as_u64().map(|c| c as u8);
                if let Some(c) = e["cost_usd"].as_f64() {
                    self.cost = c;
                }
            }
            "error" if e["kind"] == "refused" => {
                let msg = s("message");
                t.refused = true;
                // nothing ran: the ask stays in the field, and a refused switch isn't one
                let (prev, len) = t.undo.clone();
                let profile = t.profile.clone();
                self.blocks.truncate(len);
                self.cur = prev;
                self.note = if msg.contains("open in another window") {
                    Note::InTerminal(self.sids.get(&profile).cloned().unwrap_or_default())
                } else if msg.contains("window is open in this folder") {
                    Note::Locked("A Reidcc window is open in this folder.".into())
                } else if msg.to_lowercase().contains("turn is writing") {
                    Note::Locked("Another turn is writing in this folder.".into())
                } else {
                    Note::Refused(msg)
                };
                self.polled = Instant::now();
            }
            "error" => {
                let profile = t.profile.clone();
                let msg = if e["kind"] == "unknown" {
                    format!("{} ended ({}).{}", self.engine(&profile), e["exit_code"], Some(s("raw")).filter(|r| !r.is_empty())
                        .map(|r| format!("\n{r}")).unwrap_or_default())
                } else {
                    s("message")
                };
                self.blocks.push(Block::Fail(msg));
            }
            _ => {}
        }
    }

    fn finish(&mut self, err: String) {
        let Some(mut t) = self.turn.take() else { return };
        let rc = t.child.wait().ok().and_then(|s| s.code()).unwrap_or(1);
        if t.refused {
            return;
        }
        let failed = self.blocks[t.undo.1..].iter().any(|b| matches!(b, Block::Fail(_)));
        if !err.is_empty() && !t.stopped && !t.saw_text && !failed {
            self.blocks.push(Block::Fail(clean(&err))); // reid itself failed: nothing streamed, its stderr says why
        }
        if !t.ro {
            if let Some((from, to)) = t.before.take().zip(changes::snapshot(&self.folder)) {
                let files = changes::changed(&self.folder, &from, &to);
                if !files.is_empty() {
                    self.blocks.push(Block::Changed { from, to, files, diffs: None });
                }
            }
        }
        let meta = if t.stopped { "stopped".to_string() } else {
            let mut bits = vec![mmss(t.began.elapsed()), self.ctx_text()];
            if self.cost > 0.0 {
                bits.push(if self.cost < 1.0 { format!("${:.3}", self.cost) } else { format!("${:.2}", self.cost) });
            }
            bits.push(if t.ro { "read-only" } else { "edit-only" }.into());
            if rc != 0 && !failed {
                bits.push(format!("exit {rc}"));
            }
            bits.join(" · ")
        };
        self.blocks.push(Block::Meta(meta));
        self.turns += 1;
    }

    /// A held session: is it free yet? (every 1.5 s)
    fn poll(&mut self, tui: &Tui) -> bool {
        let Note::InTerminal(sid) = &self.note else { return false };
        if self.polled.elapsed() < Duration::from_millis(1500) {
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
        if let Some(t) = self.terminal.as_mut() {
            if matches!(t.try_wait(), Ok(None)) {
                self.flash = "The terminal is open in its own window.".into();
                return;
            }
        }
        let p = self.picked();
        let args: Vec<String> = match self.sids.get(&p) {
            Some(s) => vec!["--resume".into(), p.clone(), "--id".into(), s.clone()],
            None => vec![p.clone()],
        };
        match std::env::current_exe().and_then(|exe| Command::new(exe).args(&args).current_dir(&self.folder)
            .creation_flags(CREATE_NEW_CONSOLE).spawn()) {
            Ok(c) => {
                self.terminal = Some(c);
                self.flash = format!("{p} opened in a terminal window.");
            }
            Err(e) => self.flash = format!("Couldn't open a terminal ({e})."),
        }
    }

    fn toggle_diff(&mut self) {
        let folder = self.folder.clone();
        let Some(Block::Changed { from, to, files, diffs }) = self.blocks.iter_mut().rev().find(|b| matches!(b, Block::Changed { .. })) else {
            self.flash = "No changes to show yet.".into();
            return;
        };
        *diffs = match diffs {
            Some(_) => None,
            None => Some(files.iter().map(|f| clean(&changes::file_diff(&folder, from, to, &f.path, 200))).collect()),
        };
    }

    // ----------------------------------------------------------- drawing ---
    fn lines(&self, w: i64) -> Vec<String> {
        let mut out: Vec<String> = vec![];
        for b in &self.blocks {
            match b {
                Block::Info(s) => out.extend(wrap(&[(DIM.into(), s.clone())], w)),
                Block::Ask { who, text } => {
                    if !out.is_empty() {
                        out.push(String::new());
                    }
                    let mut pieces = vec![(TEXT3.to_string(), format!("{who} › "))];
                    pieces.push((TEXT.into(), clean(text).replace('\n', " ")));
                    out.extend(wrap(&pieces, w).into_iter().map(|l| format!("{LINE}▏{R}{l}")));
                    out.push(String::new());
                }
                Block::Tool { name, summary } => out.push(format!("{TEXT2}{}{R} {TEXT3}{}{R}", super::ljust(name, 6),
                                                                  fit(summary, (w - 7).max(1)))),
                Block::Text(t) => out.extend(md_lines(t, w)),
                Block::Fail(s) => out.extend(wrap(&[(OXIDE.into(), s.clone())], w)),
                Block::Meta(s) => {
                    out.push(format!("{TEXT3}{s}{R}"));
                }
                Block::Changed { files, diffs, .. } => {
                    let (a, d) = files.iter().fold((0, 0), |(a, d), f| (a + f.added.unwrap_or(0), d + f.removed.unwrap_or(0)));
                    let n = files.len();
                    let hint = if diffs.is_some() { "ctrl+d closes" } else { "ctrl+d shows the diff" };
                    out.push(format!("{TEXT2}changed · {n} file{}{R}  {} {}   {TEXT3}{hint}{R}", if n == 1 { "" } else { "s" },
                                     count('+', Some(a)), count('−', Some(d))));
                    for (i, f) in files.iter().enumerate() {
                        let path = clean(&f.path);
                        out.push(format!("  {TEXT}{}{R}  {} {}", fit(&path, (w - 16).max(4)), count('+', f.added), count('−', f.removed)));
                        if let Some(ds) = diffs {
                            for l in ds[i].lines() {
                                let col = if l.starts_with("@@") { TEXT3 } else if l.starts_with('+') { TEXT }
                                          else if l.starts_with('-') { OXIDE } else { TEXT2 };
                                out.push(format!("  {RULE}│{R} {col}{}{R}", fit(l, (w - 4).max(1))));
                            }
                        }
                    }
                }
                Block::Switch { from, to } => {
                    let mid = format!(" switch · {from} → {to} · .reid/handoff.md ");
                    let side = ((w - clen(&mid)) / 2).max(2);
                    out.push(String::new());
                    out.push(format!("{RULE}{}{R}{LINE}{mid}{R}{RULE}{}{R}", rep("─", side), rep("─", (w - side - clen(&mid)).max(0))));
                    out.push(String::new());
                }
            }
        }
        if let Some(t) = &self.turn {
            if !t.refused {
                out.push(format!("{TEXT2}▍{R}")); // the caret: the turn is still going
            }
        }
        out
    }

    fn draw(&mut self, tui: &Tui) {
        let (w, h) = tui.size();
        let ww = w - 4;
        // the bar: where and who on the left, the meters on the right (emerald only while a turn runs)
        let left = format!(" {LINE}RC{R}  {TEXT}{}{R}  {TEXT2}{} · {}{}{R}", fit(&show_path(&self.folder), (w / 2).max(10)), self.cur,
                           self.engine(&self.cur), if self.ro { " · read-only" } else { "" });
        let right = match &self.turn {
            Some(t) => format!("{EMERALD}● {}{R} {TEXT2}· {}{R} ", mmss(t.began.elapsed()), self.ctx_text()),
            None => format!("{TEXT2}ready · {}{R} ", self.ctx_text()),
        };
        let mut top = vec![format!("{left}{}{right}", rep(" ", (w - clen(&left) - clen(&right)).max(1))), tui.rule()];

        // the composer: note, field, controls, keys
        let mut bottom = vec![tui.rule()];
        let note = match &self.note {
            Note::None => None,
            Note::InTerminal(_) => Some(format!("{BRONZE}in terminal{R}  {TEXT2}This session is open in a terminal. It clears when that closes.{R}")),
            Note::Locked(m) => Some(format!("{BRONZE}locked{R}  {TEXT2}{m}{R}  {TEXT}ctrl+r sends it read-only{R}")),
            Note::Refused(m) => Some(format!("{BRONZE}refused{R}  {TEXT2}{}{R}", fit(m, (w - 14).max(4)))),
        };
        if let Some(n) = note {
            bottom.push(format!(" {n}"));
        } else if !self.flash.is_empty() {
            bottom.push(format!(" {TEXT2}{}{R}", fit(&self.flash, w - 2)));
        }
        let shown = if self.field.is_empty() && self.turn.is_none() { format!("{TEXT3}Ask {}…{R}", self.picked()) } else { self.field.clone() };
        let field = wrap(&[(TEXT.into(), shown)], ww - 2);
        let start = field.len().saturating_sub(3);
        for (i, l) in field[start..].iter().enumerate() {
            let cursor = if i + start == field.len() - 1 && self.turn.is_none() { "\x1b[7m \x1b[27m" } else { "" };
            bottom.push(format!(" {TEXT3}{}{R} {l}{cursor}", if i == 0 { "›" } else { " " }));
        }
        let p = self.picked();
        let primary = if self.turn.is_some() { format!("{OXIDE}esc stop{R}") }
                      else if self.switching() { format!("{TEXT}↵ switch → {}{R}", self.engine(&p)) }
                      else { format!("{TEXT}↵ send{R}") };
        let ctl = format!(" {TEXT}{p} · {}{R}   {TEXT}{}{R} {TEXT2}read-only{R}", self.engine(&p), if self.ro { "✓" } else { "·" });
        bottom.push(format!("{ctl}{}{primary} ", rep(" ", (w - clen(&ctl) - clen(&primary) - 1).max(1))));
        let back = if self.turn.is_some() { "" } else { " · esc back" };
        bottom.push(tui.help(&format!("tab profile · ctrl+r read-only · ctrl+t terminal · ctrl+d diff · ctrl+o handoff · pgup/pgdn scroll{back}")));

        let room = (h - 1 - top.len() as i64 - bottom.len() as i64).max(1);
        let all = self.lines(ww);
        let n = all.len() as i64;
        self.scroll = self.scroll.clamp(0, (n - room).max(0));
        let end = n - self.scroll;
        let first = (end - room).max(0);
        let mut body: Vec<String> = all[first as usize..end as usize].iter().map(|l| format!("  {l}")).collect();
        if self.scroll > 0 {
            if let Some(last) = body.last_mut() {
                *last = format!("  {TEXT3}↓ {} more lines · end jumps there{R}", self.scroll);
            }
        }
        while (body.len() as i64) < room {
            body.push(String::new());
        }
        top.extend(body);
        top.extend(bottom);
        tui.paint(&top);
    }
}

/// The chat view on `profile` in the TUI's folder; back to the caller when you leave it (esc).
pub(super) fn run(tui: &mut Tui, profile: &str) -> T<()> {
    let cfg = load_config(tui.ctx)?;
    let profs: Vec<(String, String)> = profiles(&cfg).iter()
        .map(|(n, p)| (n.clone(), super::engine_str(p.as_object().unwrap_or(&Default::default())))).collect();
    let Some(pick) = profs.iter().position(|(n, _)| n == profile) else {
        return Err(Stop::Err(reidcc::ReidError(format!("No profile named {profile}."))));
    };
    let mut c = Chat {
        folder: tui.cwd.clone(), cur: profile.into(), pick, profiles: profs, sids: HashMap::new(), turns: 0, ro: false,
        field: String::new(), blocks: vec![], note: Note::None, polled: Instant::now(), turn: None, context: None, cost: 0.0,
        scroll: 0, terminal: None, flash: String::new(),
    };
    c.blocks.push(Block::Info(format!("{} · ask {profile} anything. Write turns are edit-only; ctrl+t opens a terminal for shell and tests.",
                                      show_path(&c.folder))));
    let (mut dirty, mut drawn, mut size) = (true, Instant::now(), tui.size());
    loop {
        if console::interrupted() {
            return Err(Stop::Int);
        }
        dirty |= c.pump() | c.poll(tui) | (tui.size() != size);
        if dirty || (c.turn.is_some() && drawn.elapsed() >= Duration::from_secs(1)) {
            size = tui.size();
            c.draw(tui);
            (dirty, drawn) = (false, Instant::now());
        }
        if !console::kbhit() {
            std::thread::sleep(Duration::from_millis(30));
            continue;
        }
        let k = getkey()?;
        dirty = true;
        let page = (tui.size().1 / 2).max(3);
        match k.as_str() {
            "esc" if c.turn.is_some() => c.stop(),
            "esc" => return Ok(()),
            // shortcut: a pasted line break sends, like Enter; a multi-line paste needs the chat window
            "enter" => c.send(),
            "backspace" => {
                c.field.pop();
            }
            "\t" if c.turn.is_none() => c.pick = (c.pick + 1) % c.profiles.len(),
            "\x12" if c.turn.is_none() => {
                if matches!(c.note, Note::Locked(_)) {
                    (c.ro, c.note) = (true, Note::None);
                    c.send();
                } else {
                    c.ro = !c.ro;
                }
            }
            "\x14" => c.terminal(),
            "\x04" => c.toggle_diff(),
            "\x0f" => {
                let p = reidcc::py::join(&c.folder, &[reidcc::handoff::DIR, "handoff.md"]);
                if reidcc::py::exists(&p) { crate::open_file(&p) } else { c.flash = "No handoff here yet.".into() }
            }
            "pgup" | "up" => c.scroll += page,
            "pgdn" | "down" => c.scroll = (c.scroll - page).max(0),
            "end" => c.scroll = 0,
            k if k.chars().count() == 1 && !k.chars().next().is_some_and(char::is_control) => c.field.push_str(k),
            _ => {}
        }
    }
}

#[cfg(test)]
mod tests {
    use super::super::strip_sgr;
    use super::*;

    #[test]
    fn replies_render_like_the_chat_window() {
        let plain = |t: &str| md_lines(t, 60).iter().map(|l| strip_sgr(l).trim_end().to_string()).collect::<Vec<_>>();
        assert_eq!(plain("Use `Option<T>` and **care**, see [calc.py](C:/w/calc.py:9)."),
                   vec!["Use Option<T> and care, see calc.py."]);
        // a fence still streaming is code already, its ``` hidden
        assert_eq!(plain("Here:\n```rust\nfn x() {"), vec!["Here:", " fn x() {"]);
        assert!(md_lines("```\nfn x() {", 60)[0].contains(VAL));
        assert_eq!(plain("## Title\nan unclosed `tick and **star"), vec!["Title", "an unclosed `tick and **star"]);
        assert_eq!(plain("a [b] (c) [d](e f)"), vec!["a [b] (c) [d](e f)"]);
        // engine text can't drive the terminal
        assert_eq!(clean("hi\x1b[2Jthere\x07\tx"), "hi[2Jthere    x");
        // wrapped at the width, indents only on a line's first row
        assert_eq!(plain("  - one two three four five six seven eight nine ten eleven twelve thirteen"),
                   vec!["  - one two three four five six seven eight nine ten eleven", "twelve thirteen"]);
    }
}
