//! The Reidcc TUI: a direct port of `class TUI` in python\reid.py (vision\Spec\SPEC-rust-tui-gui.md,
//! part 1). Same screens, words, colours, keys and files written; the same ANSI strings and the
//! same full-screen repaint. Method names follow the Python so the two can be read side by side.

use crate::console::{self, Interrupt};
use reidcc::engines::{self, codex, is_codex, ENGINES};
use reidcc::term::{is_tty, write, BRONZE, OXIDE, R, TEXT, TEXT2, TEXT3};
use reidcc::{load_config, load_state, memory_path, on, profile, profiles, proxy, py, pyjson, save_json, session,
             show_path, text, Ctx, Obj, ReidError, BASE_MODELS};
use serde_json::Value;
use std::collections::HashMap;
use std::time::{Duration, Instant};

const LINE: &str = "\x1b[38;2;146;138;130m"; // #928A82, the art's engraved lines
const EMERALD: &str = "\x1b[38;2;0;196;99m"; // #00C463
const ACC: &str = TEXT; // labels you act on
const DIM: &str = TEXT3; // hints, separators, detail
const WARN: &str = TEXT; // flash messages
const SEL: &str = "\x1b[48;2;41;39;35m\x1b[38;2;214;208;200m"; // stone-dark row, bone text
const B: &str = "\x1b[1m";

const CODEX_TAG: &str = "CODEX · GREYED FIELDS ARE CLAUDE'S";
const CODEX_REPLACE_HINT: &str = "replace drops Codex's own instructions; add is the safe one.";
const CORE_TOOLS: [&str; 6] = ["Read", "Edit", "Write", "Glob", "Grep", "Bash"];
const WEB_TOOLS: [&str; 2] = ["WebSearch", "WebFetch"];

// ------------------------------------------------------- python strings ---
fn clen(s: &str) -> i64 {
    s.chars().count() as i64
}

fn rep(s: &str, n: i64) -> String {
    if n > 0 { s.repeat(n as usize) } else { String::new() }
}

fn fdiv(a: i64, b: i64) -> i64 {
    a.div_euclid(b) // Python's // for a positive divisor
}

pub fn fit(s: &str, w: i64) -> String {
    if clen(s) <= w {
        return s.to_string();
    }
    s.chars().take((w - 1).max(0) as usize).collect::<String>() + "…"
}

fn ljust(s: &str, w: i64) -> String {
    format!("{s}{}", rep(" ", w - clen(s)))
}

/// str.center, with CPython's rule for where the odd space goes.
fn center(s: &str, w: i64) -> String {
    let marg = w - clen(s);
    if marg <= 0 {
        return s.to_string();
    }
    let left = marg / 2 + (marg & w & 1);
    format!("{}{s}{}", rep(" ", left), rep(" ", marg - left))
}

/// Word-wrap to w columns; the last allowed line is cut with fit().
pub fn wrap_text(s: &str, w: i64, max_lines: usize) -> Vec<String> {
    let mut lines: Vec<String> = vec![];
    let mut cur = String::new();
    for word in s.split(py::isspace).filter(|x| !x.is_empty()) {
        if !cur.is_empty() && clen(&cur) + 1 + clen(word) > w {
            lines.push(std::mem::replace(&mut cur, word.to_string()));
        } else if cur.is_empty() {
            cur = word.to_string();
        } else {
            cur = format!("{cur} {word}");
        }
    }
    if !cur.is_empty() {
        lines.push(cur);
    }
    if lines.len() > max_lines {
        let rest = lines[max_lines - 1..].join(" ");
        lines.truncate(max_lines - 1);
        lines.push(fit(&rest, w));
    }
    let out: Vec<String> = lines.iter().map(|l| fit(l, w)).collect();
    if out.is_empty() { vec![String::new()] } else { out }
}

/// The GUI banner's story (folder → persona → ●) drawn in linework, sized to the window.
pub fn text_banner(w: i64) -> Vec<String> {
    let labels = ["folder", "profile", "●"];
    let bw = 11; // box width
    let gap = 6.max(18.min(fdiv(w - 2 - 3 * bw - 8, 2)));
    let tail = 2.max(8.min(fdiv(w - 2 - 3 * bw - 2 * gap, 2)));
    let pad = rep(" ", 0.max(fdiv(w - 3 * bw - 2 * gap - 2 * tail, 2)));
    let edge = format!("{}╭{}╮", rep(" ", tail), rep("─", bw - 2));
    let tops = edge + &format!("{}╭{}╮", rep(" ", gap - 1), rep("─", bw - 2)).repeat(2);
    let bots = tops.replace('╭', "╰").replace('╮', "╯");
    let mut mid = rep("─", tail);
    for (i, l) in labels.iter().enumerate() {
        let mut inner = center(l, bw - 2);
        if *l == "●" {
            inner = inner.replace('●', &format!("{EMERALD}●{LINE}"));
        } else {
            inner = format!("{TEXT2}{inner}{LINE}");
        }
        let after = if i < 2 { rep("─", gap - 2) + "→" } else { rep("─", tail) };
        mid += &format!("┤{inner}├{after}");
    }
    vec![format!("{pad}{LINE}{tops}{R}"), format!("{pad}{LINE}{mid}{R}"), format!("{pad}{LINE}{bots}{R}")]
}

/// re.sub(r"\x1b\[[0-9;]*m", "", s)
fn strip_sgr(s: &str) -> String {
    let c: Vec<char> = s.chars().collect();
    let mut out = String::new();
    let mut i = 0;
    while i < c.len() {
        if c[i] == '\x1b' && c.get(i + 1) == Some(&'[') {
            let mut j = i + 2;
            while j < c.len() && (c[j].is_ascii_digit() || c[j] == ';') {
                j += 1;
            }
            if c.get(j) == Some(&'m') {
                i = j + 1;
                continue;
            }
        }
        out.push(c[i]);
        i += 1;
    }
    out
}

/// Extra args as one line people can edit; args_parse() reads it back to the same list.
fn args_text(p: &Obj) -> String {
    py::list2cmdline(&reidcc::args(p))
}

fn persona_name(p: &Obj) -> String {
    profile::persona_name(p)
}

/// str(p.get("engine") or "claude")
fn engine_str(p: &Obj) -> String {
    let e = text(p, "engine");
    if e.is_empty() { "claude".into() } else { e }
}

fn prof(cfg: &Obj, name: &str) -> Obj {
    profiles(cfg).get(name).and_then(Value::as_object).cloned().unwrap_or_default()
}

fn profiles_mut(cfg: &mut Obj) -> &mut Obj {
    cfg.get_mut("profiles").and_then(Value::as_object_mut).expect("load_config checked profiles")
}

fn prof_mut<'a>(cfg: &'a mut Obj, name: &str) -> &'a mut Obj {
    profiles_mut(cfg).get_mut(name).and_then(Value::as_object_mut).expect("a profile is an object")
}

/// p[key] = val, or remove it for None / "" / [] / False (as dict.pop: order kept).
fn setk(p: &mut Obj, key: &str, val: Value) {
    let empty = match &val {
        Value::Null => true,
        Value::String(s) => s.is_empty(),
        Value::Array(a) => a.is_empty(),
        Value::Bool(b) => !b,
        Value::Number(n) => n.as_f64() == Some(0.0),
        Value::Object(_) => false,
    };
    if empty {
        p.shift_remove(key);
    } else {
        p.insert(key.into(), val);
    }
}

fn strs(v: &[&str]) -> Value {
    Value::Array(v.iter().map(|s| Value::String(s.to_string())).collect())
}

/// {(new if k == old else k): q for k, q in profiles.items()}
fn renamed(profs: &Obj, old: &str, new: &str) -> Obj {
    let mut out = Obj::new();
    for (k, q) in profs {
        out.insert(if k == old { new.to_string() } else { k.clone() }, q.clone());
    }
    out
}

fn save(ctx: &Ctx, cfg: &Obj) -> Result<(), Stop> {
    save_json(&ctx.config, &Value::Object(cfg.clone())).map_err(|e| Stop::Err(ReidError(e.to_string())))
}

/// The Reidcc assets folder: the nearest folder at or above this exe with assets\tui\tui.json
/// (python\..\assets for reid.py, E:\reidcc\assets for rs\target\release\reid.exe).
fn asset(name: &str) -> Option<String> {
    let exe = std::env::current_exe().ok()?.to_string_lossy().into_owned();
    let mut d = py::dirname(&py::abspath(&exe));
    loop {
        let p = py::join(&d, &[name]);
        if py::exists(&p) {
            return Some(p);
        }
        let up = py::dirname(&d);
        if up == d {
            return None;
        }
        d = up;
    }
}

/// How the TUI ends early: Ctrl+C (KeyboardInterrupt) or a ReidError (a broken reid.json).
pub enum Stop {
    Int,
    Err(ReidError),
}

impl From<Interrupt> for Stop {
    fn from(_: Interrupt) -> Stop {
        Stop::Int
    }
}

impl From<ReidError> for Stop {
    fn from(e: ReidError) -> Stop {
        Stop::Err(e)
    }
}

type T<X> = Result<X, Stop>;

struct Art {
    cols: i64,
    frames: std::rc::Rc<Vec<Vec<String>>>,
    meta: Value,
}

pub struct Tui {
    ctx: &'static Ctx,
    cwd: String,
    msg: String,
    idx: usize,
    login: Option<std::thread::JoinHandle<()>>,
    art: HashMap<String, std::rc::Rc<Vec<Vec<String>>>>,
    /// a newer version the launcher saw (reid_state.json): the footer says how to get it
    update: Option<String>,
}

fn getkey() -> T<String> {
    if console::interrupted() {
        return Err(Stop::Int);
    }
    Ok(console::getkey()?)
}

impl Tui {
    pub fn new(ctx: &'static Ctx, cwd: &str, msg: &str) -> Tui {
        Tui { ctx, cwd: cwd.into(), msg: msg.into(), idx: 0, login: None, art: HashMap::new(), update: reidcc::pending_update(ctx) }
    }

    // ---------------------------------------------------------- drawing ---
    fn size(&self) -> (i64, i64) {
        let (c, l) = console::terminal_size();
        (c.max(40), l.max(12))
    }

    fn paint(&self, lines: &[String]) {
        let (_, h) = self.size();
        let mut out = String::from("\x1b[?25l\x1b[H");
        for l in lines.iter().take((h - 1).max(0) as usize) {
            out += l;
            out += "\x1b[K\r\n";
        }
        out += "\x1b[J";
        write(&out);
    }

    fn header(&self, crumb: &str) -> Vec<String> {
        let (w, _) = self.size();
        let mut title = format!(" {TEXT2}REIDCC{R}");
        if !crumb.is_empty() {
            title += &format!(" {DIM}·{R} {}", fit(crumb, w - 12));
        }
        vec![title, format!(" {DIM}folder{R}  {}", fit(&show_path(&self.cwd), w - 10)), String::new()]
    }

    fn rule(&self) -> String {
        let (w, _) = self.size();
        format!(" {DIM}{}{R}", rep("─", w - 2))
    }

    fn help(&self, text: &str) -> String {
        let (w, _) = self.size();
        format!(" {DIM}{}{R}", fit(text, w - 2))
    }

    fn flash(&mut self) -> Vec<String> {
        if self.msg.is_empty() {
            return vec![];
        }
        let (w, _) = self.size();
        let m = std::mem::take(&mut self.msg);
        vec![format!(" {WARN}{}{R}", fit(&m, w - 2)), String::new()]
    }

    fn row(&self, selected: bool, left: &str, right: &str, lw: i64) -> String {
        let (w, _) = self.size();
        let mark = if selected { "→" } else { " " };
        let plain_l = ljust(&fit(left, lw), lw);
        let plain_r = fit(right, 0.max(w - lw - 6));
        if selected {
            return format!(" {SEL}{}{R}", ljust(&format!(" {mark} {plain_l} {plain_r}"), w - 2));
        }
        format!("  {mark} {plain_l} {DIM}{plain_r}{R}")
    }

    // ----------------------------------------------------------- inputs ---
    /// Ask `codex login status` off the main thread (about a second); key() redraws when it's back.
    fn check_login(&mut self) {
        if self.login.as_ref().is_none_or(|t| t.is_finished()) {
            let ctx = self.ctx;
            self.login = Some(std::thread::spawn(move || {
                codex::login(ctx, false);
            }));
        }
    }

    /// getkey(), or None once a pending login check finishes so the screen can show its answer.
    fn key(&mut self) -> T<Option<String>> {
        if let Some(t) = &self.login {
            while !t.is_finished() && !console::kbhit() {
                if console::interrupted() {
                    return Err(Stop::Int);
                }
                std::thread::sleep(Duration::from_millis(50));
            }
            if t.is_finished() {
                self.login = None;
                if !console::kbhit() {
                    return Ok(None);
                }
            }
        }
        getkey().map(Some)
    }

    /// One line of text at the bottom. Empty = cancel, '-' = clear.
    fn ask(&self, label: &str, current: &str) -> Option<String> {
        let (_, h) = self.size();
        let hint = if current.is_empty() { String::new() } else { format!(" [{current}]") };
        write(&format!("\x1b[{h};1H\x1b[K\x1b[?25h"));
        let val = py::strip(&console::input(&format!(" {ACC}{label}{R}{DIM}{hint}{R}: "))).to_string();
        write("\x1b[?25l");
        if val.is_empty() { None } else { Some(val) }
    }

    fn confirm(&self, text: &str, yes: &str, no: &str) -> T<bool> {
        let (_, h) = self.size();
        write(&format!("\x1b[{h};1H\x1b[K {TEXT}{text}{R}  {DIM}y {yes} · any other key {no}{R} "));
        let k = getkey()?;
        Ok(k == "y" || k == "Y")
    }

    /// Arrow-key list. Returns the chosen index or None.
    fn pick(&mut self, crumb: &str, options: &[String], current: usize) -> T<Option<usize>> {
        let n = options.len() as i64;
        let mut i = 0.max((current as i64).min(n - 1));
        loop {
            let (_, h) = self.size();
            let room = 3.max(h - 8);
            let top = 0.max((i - room / 2).min(n - room));
            let mut lines = self.header(crumb);
            for j in top..n.min(top + room) {
                lines.push(self.row(j == i, &options[j as usize], "", self.size().0 - 8));
            }
            lines.extend([String::new(), self.rule(), self.help("↑↓ move · ↵ choose · esc back")]);
            self.paint(&lines);
            let k = getkey()?;
            match k.as_str() {
                "up" | "k" => i = (i - 1).rem_euclid(n),
                "down" | "j" => i = (i + 1).rem_euclid(n),
                "home" => i = 0,
                "end" => i = n - 1,
                "enter" => return Ok(Some(i as usize)),
                "esc" | "q" | "left" => return Ok(None),
                _ => {}
            }
        }
    }

    // ------------------------------------------------------------- main ---
    pub fn run(&mut self) -> i32 {
        console::catch_ctrl_c();
        write("\x1b[?1049h");
        let r = self.main_loop();
        write(&format!("{R}\x1b[?25h\x1b[?1049l"));
        match r {
            Ok(()) | Err(Stop::Int) => 0,
            Err(Stop::Err(e)) => {
                reidcc::errln!("{e}");
                1
            }
        }
    }

    fn main_loop(&mut self) -> T<()> {
        loop {
            let cfg = load_config(self.ctx)?;
            let names: Vec<String> = profiles(&cfg).keys().cloned().collect();
            self.idx = self.idx.min(names.len() - 1);
            self.draw_main(&cfg, &names);
            let Some(k) = self.key()? else {
                continue; // the Codex login check finished: draw again with its answer
            };
            let name = names[self.idx].clone();
            // the key can come hours later; what we save must start from reid.json as it is now
            let mut cfg = load_config(self.ctx)?;
            if !profiles(&cfg).contains_key(&name) {
                continue; // gone meanwhile: draw the list again
            }
            let n = names.len();
            let digit = k.len() == 1 && k.as_bytes()[0].is_ascii_digit() && k != "0";
            match k.as_str() {
                "q" | "esc" => return Ok(()),
                "up" | "k" => self.idx = (self.idx + n - 1) % n,
                "down" | "j" => self.idx = (self.idx + 1) % n,
                _ if digit && k.parse::<usize>().unwrap() <= n => self.idx = k.parse::<usize>().unwrap() - 1,
                "enter" => {
                    if self.launch(&cfg, &name, None)? {
                        return Ok(());
                    }
                }
                "r" => {
                    if self.resume(&cfg, &name)? {
                        return Ok(());
                    }
                }
                "e" | "right" => self.edit(cfg, name)?,
                "n" => self.new_profile(&name)?,
                "x" => self.delete_profile(&cfg, &name)?,
                "d" => {
                    cfg.insert("default".into(), Value::String(name.clone()));
                    save(self.ctx, &cfg)?;
                    self.msg = format!("Default is now {name}.");
                }
                "w" => self.pick_dir()?,
                "m" => {
                    crate::open_file(&memory_path(self.ctx, &cfg, None));
                    self.msg = "Memory open in your editor. The next session picks it up.".into();
                }
                _ => {}
            }
        }
    }

    /// The GUI's one screen in text: banner, folder, profiles with the selected one's fields
    /// beside them, the command, then `folder → profile → open gate` and the ready dot.
    fn draw_main(&mut self, cfg: &Obj, names: &[String]) {
        let ctx = self.ctx;
        let (w, h) = self.size();
        let name = &names[self.idx];
        let p = prof(cfg, name);
        let (error, preview, have) = profile::check(ctx, cfg, name, &self.cwd);

        let mut top = vec![format!(" {TEXT}Folder. Profile. Gate.{R}"),
                           format!(" {DIM}{}{R}", fit("Pick a project and a profile. Your persona, memory and settings are already there.", w - 2)),
                           String::new()];
        let hint = "w pick folder";
        let fw = w - 12 - clen(hint) - 3;
        top.push(format!(" {DIM}folder{R}   {TEXT}{}{R}{DIM}{hint}{R}", ljust(&fit(&show_path(&self.cwd), fw), fw)));
        if let Some(Value::Object(last)) = load_state(ctx).get("last").filter(|v| pyjson::truthy(v)) {
            let at = last.get("at").and_then(Value::as_str).unwrap_or("");
            let when: String = at.chars().skip(11).take(5).collect();
            let lcwd = last.get("cwd").map(pyjson::py_str).unwrap_or_default();
            let where_ = if py::normcase(&lcwd) == py::normcase(&self.cwd) { String::new() } else { format!(" · {}", show_path(&lcwd)) };
            let lp = last.get("profile").map(pyjson::py_str).unwrap_or_else(|| "None".into());
            top.push(format!(" {DIM}last{R}     {lp} · {when}{where_}   {DIM}r resumes it{R}"));
        }
        let fl = self.flash();
        top.extend(if fl.is_empty() { vec![String::new()] } else { fl });
        top.push(self.rule());

        // right pane: the selected profile, the same rows as the GUI form
        let persona = if on(&p, "persona").is_some() { persona_name(&p) } else { String::new() };
        let mut tags: Vec<String> = vec![];
        if !persona.is_empty() {
            tags.push(format!("PERSONA · {}", persona.to_uppercase()));
        }
        if on(&p, "memory").is_some() {
            tags.push("MEMORY · ON".into());
        }
        let mcp = text(&p, "mcp");
        let boxed = |on: bool, label: &str| format!("{}{label}", if on { "☒ " } else { "☐ " });
        let cx = is_codex(&p);
        let tool = if cx { "Codex" } else { "Claude Code" };
        if cx && on(&p, "settings").is_none() && codex::login_cached(ctx).is_none() {
            self.check_login();
        }
        let settings = text(&p, "settings");
        let sign_in = if !settings.is_empty() { settings } else if cx { codex::login_label(ctx) } else { "subscription".into() };
        let model = text(&p, "model");
        let px = proxy::list(&p).join("+");
        let rows: Vec<(&str, String)> = vec![
            ("name", name.clone()),
            ("engine", engine_str(&p)),
            ("model", if !model.is_empty() { model } else if cx { "engine default".into() } else { "provider default".into() }),
            ("sign-in", sign_in),
            ("persona", { let s = text(&p, "persona"); if s.is_empty() { "none".into() } else { s } }),
            ("persona mode", if persona.is_empty() { "needs a persona".into() }
                             else if text(&p, "mode") == "replace" { format!("replace {tool}'s prompt") }
                             else { format!("add to {tool}'s prompt") }),
            ("proxy", if px.is_empty() { "off".into() } else { px }),
            ("tools", if !p.contains_key("tools") { "all".into() } else {
                let t = reidcc::list(&p, "tools").join(", ");
                if t.is_empty() { "none".into() } else { t } }),
            ("mcp", if mcp.is_empty() { "your servers".into() } else { mcp }),
            ("switches", String::new()),
            ("extra args", args_text(&p)),
        ];
        let lw: i64 = 22; // profile list width
        let rw = 20.max(w - lw - 5); // right pane width
        if cx {
            // same as the GUI: say why the greyed rows are greyed out
            tags.insert(0, CODEX_TAG.into());
        }
        let greyed: &[&str] = if cx { &["proxy", "tools", "mcp"] } else { &[] };
        let mut right = vec![format!("{TEXT}{B}{name}{R}   {DIM}{}{R}", tags.join(" · ")), String::new()];
        for (k, v) in &rows {
            if *k == "switches" {
                // memory works for both engines; the other three are Claude's
                let parts = [(boxed(on(&p, "memory").is_some(), "memory"), false),
                             (boxed(on(&p, "no_chrome").is_none(), "chrome"), cx),
                             (boxed(on(&p, "no_connectors").is_none(), "connectors"), cx),
                             (boxed(on(&p, "safe").is_some(), "safe mode"), cx)];
                let v: Vec<String> = parts.iter().map(|(s, g)| format!("{}{s}{R}", if *g { DIM } else { TEXT })).collect();
                right.push(format!("{DIM}{}{R}{}", ljust(k, 14), v.join("  ")));
                continue;
            }
            let col = if *k == "sign-in" && cx && v.ends_with("not signed in") { OXIDE }
                      else if greyed.contains(k) { DIM } else { TEXT };
            right.push(format!("{DIM}{}{R}{col}{}{R}", ljust(k, 14), fit(v, rw - 14)));
        }
        right.extend([String::new(), format!("{DIM}command{R}")]);
        if let Some(e) = &error {
            // wrap it: the way out is usually at the end ("…, or pick a Claude profile.")
            right.extend(wrap_text(e, rw, 3).iter().map(|l| format!("{OXIDE}{l}{R}")));
        } else {
            right.push(format!("{DIM}{}{R}", fit(&preview, rw)));
        }

        let help2 = if cx {
            if on(&p, "persona").is_some() && text(&p, "mode") == "replace" { CODEX_REPLACE_HINT }
            else { "codex: /quit comes back here · resume is Claude's" }
        } else { "in a session: /reid comes back here" };
        let mut bottom = vec![self.rule(),
                              self.help("↵ open gate · r resume · e edit · n new · x delete · d default · m memory · q quit"),
                              self.help(help2),
                              String::new()];
        let status = if error.is_some() { "not ready".to_string() }
                     else if have.is_empty() { "ready".to_string() }
                     else { format!("ready · {}", have.join(" + ")) };
        let flow = match &self.update {
            Some(v) => format!("update {v}: reid --update"),
            None => "folder → profile → open gate".to_string(),
        };
        let gap = 1.max(w - 2 - clen(&flow) - clen(&status) - 3);
        bottom.push(format!(" {DIM}{flow}{R}{}{}●{R} {TEXT2}{status}{R}", rep(" ", gap), if error.is_some() { OXIDE } else { EMERALD }));

        // the list scrolls if the window is short; the banner only shows when everything else fits
        let (nt, nb, nn) = (top.len() as i64, bottom.len() as i64, names.len() as i64);
        let mut body_h = (right.len() as i64).max((nn + 1).min(h - 1 - nt - nb));
        body_h = 3.max(body_h.min(h - 1 - nt - nb));
        let banner = text_banner(w);
        if h - 1 - nt - nb - body_h >= banner.len() as i64 + 1 {
            let mut t = banner;
            t.push(String::new());
            t.extend(top);
            top = t;
        }

        let room = body_h - 1;
        let idx = self.idx as i64;
        let first = 0.max((idx - fdiv(room, 2)).min(nn - room));
        let mut left = vec![format!(" {DIM}profiles{R}")];
        let def = cfg.get("default").and_then(Value::as_str);
        let mut i = first;
        while i < nn.min(first + room) {
            let n = &names[i as usize];
            let default = Some(n.as_str()) == def; // the one emerald: the profile `open gate` uses by default
            let label = fit(n, lw - 6) + if default { " ●" } else { "" };
            let mut cell = if i == idx {
                format!(" {SEL}{}{R}", ljust(&format!(" → {label}"), lw - 1))
            } else {
                format!("    {TEXT2}{label}{R}{}", rep(" ", lw - 4 - clen(&label)))
            };
            if default {
                cell = cell.replacen('●', &format!("{EMERALD}●{}", if i == idx { SEL } else { R }), 1);
            }
            left.push(cell);
            i += 1;
        }
        if nn > room {
            left.push(format!(" {DIM}{}{R}", ljust(&format!("↑↓ {} more", nn - room), lw - 1)));
        }
        let mut body = vec![];
        for j in 0..body_h.max(0) as usize {
            let l = left.get(j).cloned().unwrap_or_else(|| rep(" ", lw));
            let r = right.get(j).cloned().unwrap_or_default();
            body.push(format!("{l} {DIM}│{R}  {r}"));
        }
        let mut all = top;
        all.extend(body);
        all.extend(bottom);
        self.paint(&all);
    }

    /// Pre-rendered terminal frames at the widest size that fits, or None.
    fn tui_art(&mut self, name: &str, max_cols: i64, max_rows: i64) -> Option<Art> {
        let meta_path = asset(&py::join("assets", &["tui", "tui.json"]))?;
        let meta = pyjson::loads(&py::read_text(&meta_path, false).ok()?).ok()?;
        let mut sizes: Vec<i64> = meta.get(name).and_then(Value::as_array)?.iter().filter_map(Value::as_i64).collect();
        sizes.sort_unstable_by(|a, b| b.cmp(a));
        for cols in sizes {
            let path = asset(&py::join("assets", &["tui", &format!("{name}_{cols}.json.gz")]));
            let Some(path) = path.filter(|_| cols <= max_cols) else { continue };
            if !self.art.contains_key(&path) {
                use std::io::Read;
                let f = std::fs::File::open(&path).ok()?;
                let mut s = String::new();
                flate2::read::GzDecoder::new(f).read_to_string(&mut s).ok()?;
                let v: Vec<Vec<String>> = serde_json::from_str(&s).ok()?;
                self.art.insert(path.clone(), std::rc::Rc::new(v));
            }
            let frames = self.art[&path].clone();
            if frames.first().map_or(0, Vec::len) as i64 <= max_rows {
                return Some(Art { cols, frames, meta });
            }
        }
        None
    }

    /// The gate opens, in text: about 1.2 s at the GUI's pace; any key skips it, and that key
    /// never reaches the session.
    fn gate(&mut self) -> T<()> {
        let (w, h) = self.size();
        let art = self.tui_art("gate", w, h - 2);
        let Some(art) = art.filter(|_| is_tty()) else { return Ok(()) };
        let (frames, meta) = (&art.frames, &art.meta);
        let pace = 1.375; // same pace as the GUI's gate
        let mut plan: Vec<(usize, f64)> = vec![]; // (frame index, ms after start): the GUI's step times
        for step in meta.get("steps").and_then(Value::as_array).into_iter().flatten() {
            let s = step.as_array().cloned().unwrap_or_default();
            let num = |i: usize| s.get(i).and_then(Value::as_f64).unwrap_or(0.0);
            let (count, start, dur) = (num(1) as usize, num(2), num(3));
            let base = plan.len();
            plan.extend((0..count).map(|i| (base + i, (start + dur * i as f64 / count as f64) * pace)));
        }
        let dark = frames.len() as i64 - 4; // the last frames go into the dark: no tag over them
        let bgv: Vec<i64> = meta.get("bg").and_then(Value::as_array).into_iter().flatten().filter_map(Value::as_i64).collect();
        let bg = format!("\x1b[48;2;{};{};{}m", bgv.first().unwrap_or(&0), bgv.get(1).unwrap_or(&0), bgv.get(2).unwrap_or(&0));
        let rows = frames[0].len() as i64;
        let (y0, x0) = (0.max(fdiv(h - rows - 1, 2)), fdiv(w - art.cols, 2));
        let tag = "REIDCC · OPENING";
        write(&format!("\x1b[?25l{R}{bg}\x1b[2J")); // dim everything: the gate's own ground
        let t0 = Instant::now();
        let ms = || t0.elapsed().as_secs_f64() * 1000.0;
        for (n, &(i, at)) in plan.iter().enumerate() {
            while ms() < at {
                if console::kbhit() {
                    getkey()?; // the key only skips; it must not reach the session
                    write(&format!("{R}\x1b[2J"));
                    return Ok(());
                }
                std::thread::sleep(Duration::from_millis(4));
            }
            if n + 1 < plan.len() && ms() > plan[n + 1].1 {
                continue; // running late: drop this frame, stay on time
            }
            let Some(frame) = frames.get(i) else { continue };
            let mut out = String::new();
            for (r, line) in frame.iter().enumerate() {
                out += &format!("\x1b[{};{}H{line}", y0 + r as i64 + 1, x0 + 1);
            }
            if y0 + rows + 1 <= h {
                let t = if (i as i64) < dark { tag.to_string() } else { rep(" ", clen(tag)) };
                out += &format!("\x1b[{};{}H{bg}{BRONZE}{t}{R}", y0 + rows + 1, x0 + art.cols - clen(tag));
            }
            write(&format!("\x1b[?2026h{out}\x1b[?2026l")); // synchronized output: shown whole, never torn
        }
        std::thread::sleep(Duration::from_secs_f64(0.12 * pace));
        write(&format!("{R}\x1b[2J"));
        Ok(())
    }

    /// Returns true for "quit".
    fn after_session(&mut self, rc: i32, back: bool, codex: bool) -> bool {
        let rc_s = (rc as u32).to_string(); // Windows exit codes are unsigned, as Python prints them
        if codex {
            // Codex has no /reid: quitting it comes back here
            self.msg = if rc == 0 { "Back from Codex.".into() } else { format!("Codex ended with code {rc_s}. See the output above.") };
            write("\x1b[?1049h");
            return false;
        }
        if back {
            self.msg = "Back from the session. r resumes it.".into();
            write("\x1b[?1049h");
            return false;
        }
        if rc == 0 {
            return true; // a normal /exit means you're done
        }
        self.msg = format!("Session ended with code {rc_s}. See the output above.");
        write("\x1b[?1049h");
        false
    }

    fn launch(&mut self, cfg: &Obj, name: &str, resume: Option<&str>) -> T<bool> {
        if let Some(error) = profile::check(self.ctx, cfg, name, &self.cwd).0 {
            self.msg = error; // say it here; no gate for a session that can't start
            return Ok(false);
        }
        self.gate()?;
        match session::run(self.ctx, cfg, name, &self.cwd, &[], resume) {
            Err(e) => {
                write("\x1b[?1049h");
                self.msg = e.0;
                Ok(false)
            }
            Ok(end) => Ok(self.after_session(end.rc, end.back, is_codex(&prof(cfg, name)))),
        }
    }

    fn resume(&mut self, cfg: &Obj, name: &str) -> T<bool> {
        if engine_str(&prof(cfg, name)) != "claude" {
            self.msg = "Resume is for Claude profiles for now. ↵ opens a new Codex session.".into();
            return Ok(false);
        }
        let st = load_state(self.ctx);
        let Some(last) = st.get("last").filter(|v| pyjson::truthy(v)) else {
            self.msg = "Nothing to resume yet.".into();
            return Ok(false);
        };
        let last = last.as_object().cloned().unwrap_or_default();
        let lcwd = text(&last, "cwd");
        if !lcwd.is_empty() && py::isdir(&lcwd) {
            self.cwd = lcwd; // claude finds sessions by folder
        }
        let sid = text(&last, "sid");
        self.launch(cfg, name, Some(if sid.is_empty() { "-c" } else { &sid }))
    }

    fn pick_dir(&mut self) -> T<()> {
        let recents: Vec<String> = match load_state(self.ctx).get("recent_dirs") {
            Some(Value::Array(a)) => a.iter().filter_map(Value::as_str).filter(|d| py::isdir(d)).map(String::from).collect(),
            _ => vec![],
        };
        let mut opts: Vec<String> = recents.iter().map(|d| show_path(d)).collect();
        opts.push("type a path…".into());
        let Some(i) = self.pick("folder", &opts, 0)? else { return Ok(()) };
        if i == recents.len() {
            let Some(p) = self.ask("folder", &show_path(&self.cwd)) else { return Ok(()) };
            let p = py::abspath(&py::expanduser(p.trim_matches('"')));
            if !py::isdir(&p) {
                self.msg = "Can't find that folder. It may have moved.".into();
                return Ok(());
            }
            self.cwd = p;
        } else {
            self.cwd = recents[i].clone();
        }
        Ok(())
    }

    fn new_profile(&mut self, src: &str) -> T<()> {
        let Some(name) = self.ask(&format!("new profile (copies {src})"), "") else { return Ok(()) };
        let mut cfg = load_config(self.ctx)?; // fresh after the typing
        if !profiles(&cfg).contains_key(src) {
            return Ok(());
        }
        if profiles(&cfg).contains_key(&name) {
            self.msg = format!("A profile named {name} already exists.");
            return Ok(());
        }
        let copy = profiles(&cfg)[src].clone();
        profiles_mut(&mut cfg).insert(name.clone(), copy);
        save(self.ctx, &cfg)?;
        self.idx = profiles(&cfg).keys().position(|k| *k == name).unwrap_or(0);
        self.edit(cfg, name)
    }

    fn delete_profile(&mut self, cfg: &Obj, name: &str) -> T<()> {
        if profiles(cfg).len() == 1 {
            self.msg = "Can't delete the last profile.".into();
            return Ok(());
        }
        if !self.confirm(&format!("Delete profile {name}?"), "delete", "keep")? {
            return Ok(());
        }
        let mut cfg = load_config(self.ctx)?; // fresh after the question
        if !profiles(&cfg).contains_key(name) || profiles(&cfg).len() == 1 {
            return Ok(());
        }
        profiles_mut(&mut cfg).shift_remove(name);
        if cfg.get("default").and_then(Value::as_str) == Some(name) {
            let first = profiles(&cfg).keys().next().cloned().unwrap();
            cfg.insert("default".into(), Value::String(first));
        }
        save(self.ctx, &cfg)?;
        self.msg = format!("Deleted {name}.");
        Ok(())
    }

    // ------------------------------------------------------------- edit ---
    fn edit(&mut self, mut cfg: Obj, mut name: String) -> T<()> {
        const FIELDS: [&str; 14] = ["engine", "model", "auth", "persona", "mode", "memory", "proxy", "tools", "mcp",
                                    "chrome", "connectors", "safe", "args", "name"];
        let label = |f: &str| match f {
            "auth" => "sign-in", "mode" => "persona mode", "safe" => "safe mode", "args" => "extra args", _ => f,
        }.to_string();
        let ctx = self.ctx;
        let mut i: usize = 0;
        loop {
            let p = prof(&cfg, &name);
            let persona = text(&p, "persona");
            let mcp = text(&p, "mcp");
            let cx = is_codex(&p);
            let tool = if cx { "Codex" } else { "Claude Code" };
            if cx && on(&p, "settings").is_none() && codex::login_cached(ctx).is_none() {
                self.check_login();
            }
            let model = text(&p, "model");
            let settings = text(&p, "settings");
            let px = proxy::list(&p).join("+");
            let tools = reidcc::list(&p, "tools").join(", ");
            let args = args_text(&p);
            let val = |f: &str| -> String {
                match f {
                    "engine" => engine_str(&p),
                    "model" => if !model.is_empty() { model.clone() } else if cx { "engine default".into() } else { "provider default".into() },
                    "auth" => if !settings.is_empty() { format!("{}{settings}", if cx { "" } else { "api · " }) }
                              else if cx { codex::login_label(ctx) } else { "subscription".into() },
                    "persona" => if persona.is_empty() { "none".into() } else { persona.clone() },
                    "mode" => if persona.is_empty() { "needs a persona".into() }
                              else if text(&p, "mode") == "replace" { format!("replace {tool}'s prompt") }
                              else { format!("add to {tool}'s prompt") },
                    "memory" => if on(&p, "memory").is_some() { "on" } else { "off" }.into(),
                    "proxy" => if px.is_empty() { "off".into() } else { px.clone() },
                    "tools" => if !p.contains_key("tools") { "all".into() } else if tools.is_empty() { "none".into() } else { tools.clone() },
                    "mcp" => if mcp.is_empty() { "your servers".into() } else if mcp == "none" { "none".into() } else { format!("only {mcp}") },
                    "chrome" => if on(&p, "no_chrome").is_some() { "off" } else { "on" }.into(),
                    "connectors" => if on(&p, "no_connectors").is_some() { "off · claude.ai connectors" } else { "on" }.into(),
                    "safe" => if on(&p, "safe").is_some() { "on · no CLAUDE.md, no MCP" } else { "off" }.into(),
                    "args" => if args.is_empty() { "none".into() } else { args.clone() },
                    _ => name.clone(),
                }
            };
            let mut lines = self.header(&format!("settings · {name}"));
            lines.extend(self.flash());
            for (j, f) in FIELDS.iter().enumerate() {
                let mut line = self.row(j == i, &label(f), &val(f), 13);
                if cx && claude_only_field(f) && j != i {
                    line = format!("{DIM}{}{R}", strip_sgr(&line)); // greyed like the main screen
                }
                lines.push(line);
            }
            let w = self.size().0;
            lines.extend([String::new(), format!(" {DIM}{}{R}", fit(&profile::summary(ctx, &cfg, &name), w - 2)),
                          String::new(), self.rule(), self.help("↵ change · o open persona · m open memory · esc back")]);
            self.paint(&lines);
            let Some(k) = self.key()? else { continue };
            match k.as_str() {
                "esc" | "q" | "left" => return Ok(()),
                "up" | "k" => i = (i + FIELDS.len() - 1) % FIELDS.len(),
                "down" | "j" => i = (i + 1) % FIELDS.len(),
                "o" => {
                    if !persona.is_empty() && py::exists(&ctx.resolve(&persona)) {
                        crate::open_file(&ctx.resolve(&persona));
                        self.msg = "Persona open in your editor. Every session reads it fresh.".into();
                    } else {
                        self.msg = "This profile has no persona.".into();
                    }
                }
                "m" => crate::open_file(&memory_path(ctx, &cfg, Some(&p))),
                "enter" => {
                    let f = FIELDS[i];
                    if cx && claude_only_field(f) && !field_on(&p, f) {
                        // one that's on stays changeable, so it can be turned off
                        self.msg = format!("{} is Claude's. Switch engine to change it.", label(f));
                        continue;
                    }
                    let new = self.change(&mut cfg, &name, f)?.unwrap_or_else(|| name.clone());
                    cfg = self.commit(&cfg, &name, &new)?;
                    name = new;
                }
                _ => {}
            }
        }
    }

    /// Save this screen's copy of one profile onto reid.json as it is on disk now, so edits made
    /// meanwhile in the GUI or another TUI stay. `new` differs after a rename. Returns the fresh config.
    fn commit(&self, cfg: &Obj, old: &str, new: &str) -> T<Obj> {
        let mut fresh = load_config(self.ctx)?;
        let profs = renamed(profiles(&fresh), old, new);
        fresh.insert("profiles".into(), Value::Object(profs));
        let mine = profiles(cfg).get(new).cloned().unwrap_or(Value::Null);
        profiles_mut(&mut fresh).insert(new.into(), mine);
        if fresh.get("default").and_then(Value::as_str) == Some(old) {
            fresh.insert("default".into(), Value::String(new.into()));
        }
        save(self.ctx, &fresh)?;
        Ok(fresh)
    }

    fn change(&mut self, cfg: &mut Obj, name: &str, field: &str) -> T<Option<String>> {
        let ctx = self.ctx;
        let engine = engine_str(&prof(cfg, name));
        match field {
            "engine" => {
                let opts: Vec<String> = ENGINES.iter().map(|s| s.to_string()).collect();
                let cur = ENGINES.iter().position(|e| *e == engine).unwrap_or(0);
                let Some(i) = self.pick(&format!("settings · {name} · engine"), &opts, cur)? else { return Ok(None) };
                if ENGINES[i] == engine {
                    return Ok(None);
                }
                let p = prof_mut(cfg, name);
                setk(p, "engine", if ENGINES[i] == "claude" { Value::Null } else { Value::String(ENGINES[i].into()) });
                // a model and a sign-in file belong to one engine; start from the new engine's defaults
                setk(p, "model", Value::Null);
                setk(p, "settings", Value::Null);
                let on_ = if ENGINES[i] == "codex" { engines::claude_only_on(p) } else { vec![] };
                self.msg = format!("Engine is now {}. Model and sign-in reset to its defaults.", ENGINES[i])
                    + &if on_.is_empty() { String::new() } else { format!(" Codex can't use {}: turn it off to open the gate.", on_.join(", ")) };
            }
            "model" => {
                // each engine lists its own models: Claude's names, or the ones other Codex profiles use
                let mut same: Vec<String> = profiles(cfg).values().filter_map(Value::as_object)
                    .filter(|q| on(q, "model").is_some() && engine_str(q) == engine).map(|q| text(q, "model"))
                    .filter(|m| !BASE_MODELS.contains(&m.as_str())).collect();
                same.sort();
                same.dedup();
                let mut opts: Vec<String> = vec![];
                if engine == "claude" {
                    opts.extend(BASE_MODELS.iter().map(|s| s.to_string()));
                    opts.extend(same);
                    opts.extend(["provider default".into(), "type a model id…".into()]);
                } else {
                    opts.extend(same);
                    opts.extend(["engine default".into(), "type a model id…".into()]);
                }
                let p = prof(cfg, name);
                let cur = match p.get("model") {
                    Some(Value::String(m)) => opts.iter().position(|o| o == m).unwrap_or(0),
                    _ => 0,
                };
                let Some(i) = self.pick(&format!("settings · {name} · model"), &opts, cur)? else { return Ok(None) };
                if opts[i] == "provider default" || opts[i] == "engine default" {
                    setk(prof_mut(cfg, name), "model", Value::Null);
                } else if opts[i] == "type a model id…" {
                    if let Some(v) = self.ask("model id", &text(&p, "model")) {
                        setk(prof_mut(cfg, name), "model", Value::String(v));
                    }
                } else {
                    setk(prof_mut(cfg, name), "model", Value::String(opts[i].clone()));
                }
            }
            "auth" => {
                let cx = engine == "codex";
                let files = profile::signin_files(ctx, cx);
                let mut opts = vec![if cx { codex::login_label(ctx) } else { "subscription".into() }];
                opts.extend(files);
                opts.push("type a path…".into());
                let cur = match prof(cfg, name).get("settings") {
                    Some(Value::String(s)) => opts.iter().position(|o| o == s).unwrap_or(0),
                    _ => 0,
                };
                let crumb = if cx { "sign-in (codex login is your terminal's; a .toml file sets another provider)" }
                            else { "sign-in (a settings file means API mode)" };
                let Some(i) = self.pick(&format!("settings · {name} · {crumb}"), &opts, cur)? else { return Ok(None) };
                if i == 0 {
                    setk(prof_mut(cfg, name), "settings", Value::Null);
                } else if i == opts.len() - 1 {
                    let v = self.ask(if cx { "provider .toml path" } else { "settings.json path" }, "");
                    self.set_path(cfg, name, "settings", v);
                } else {
                    setk(prof_mut(cfg, name), "settings", Value::String(opts[i].clone()));
                }
            }
            "persona" => {
                let mut files = vec![];
                for (dir, pat) in [(py::join(&ctx.home, &["personas"]), "*.md"), (ctx.proxy_dir.clone(), "*-system.md"),
                                   (py::join(&ctx.home, &["mds"]), "*.md")] {
                    let mut g = py::glob(&dir, pat);
                    g.sort();
                    files.extend(g);
                }
                let mut opts = vec!["none".to_string()];
                opts.extend(files.iter().map(|f| ctx.relpath(f)));
                opts.push("type a path…".into());
                let cur = match prof(cfg, name).get("persona") {
                    Some(Value::String(s)) => opts.iter().position(|o| o == s).unwrap_or(0),
                    _ => 0,
                };
                let Some(i) = self.pick(&format!("settings · {name} · persona"), &opts, cur)? else { return Ok(None) };
                if i == 0 {
                    let p = prof_mut(cfg, name);
                    setk(p, "persona", Value::Null);
                    setk(p, "mode", Value::Null);
                } else if i == opts.len() - 1 {
                    let v = self.ask("persona file path", "");
                    self.set_path(cfg, name, "persona", v);
                } else {
                    setk(prof_mut(cfg, name), "persona", Value::String(opts[i].clone()));
                }
            }
            "mode" => {
                if on(&prof(cfg, name), "persona").is_none() {
                    self.msg = "Pick a persona first. Persona mode only applies to it.".into();
                    return Ok(None);
                }
                let p = prof_mut(cfg, name);
                let m = if p.get("mode").and_then(Value::as_str) == Some("replace") { "append" } else { "replace" };
                p.insert("mode".into(), Value::String(m.into()));
                let tool = if engine == "codex" { "Codex" } else { "Claude Code" };
                self.msg = if m == "replace" {
                    format!("The persona now replaces {tool}'s prompt, including its tool guidance. Add is the safe one.")
                } else {
                    format!("The persona now adds to {tool}'s prompt.")
                };
            }
            "memory" | "safe" => {
                let p = prof_mut(cfg, name);
                let v = on(p, field).is_none();
                setk(p, field, Value::Bool(v));
            }
            "chrome" | "connectors" => {
                let key = format!("no_{field}");
                let p = prof_mut(cfg, name);
                let v = on(p, &key).is_none();
                setk(p, &key, Value::Bool(v));
            }
            "proxy" => {
                let mut opts = vec!["off".to_string()];
                opts.extend(proxy::CHOICES.iter().map(|s| s.to_string()));
                let cur = proxy::list(&prof(cfg, name)).join("+");
                let cur = if cur.is_empty() { "off".into() } else { cur };
                let at = opts.iter().position(|o| *o == cur).unwrap_or(0);
                let crumb = format!("settings · {name} · proxy (slim and ultra rewrite requests, unsupported)");
                if let Some(i) = self.pick(&crumb, &opts, at)? {
                    setk(prof_mut(cfg, name), "proxy", if i == 0 { Value::Null } else { Value::String(opts[i].clone()) });
                }
            }
            "tools" => {
                let mut core_web: Vec<&str> = CORE_TOOLS.to_vec();
                core_web.extend(WEB_TOOLS);
                let presets: Vec<(String, Value)> = vec![
                    ("all".into(), Value::Null),
                    (format!("core · {}", CORE_TOOLS.join(" ")), strs(&CORE_TOOLS)),
                    ("core + web".into(), strs(&core_web)),
                    ("web only".into(), strs(&WEB_TOOLS)),
                    ("none · plain chat".into(), Value::Array(vec![])),
                ];
                let mut opts: Vec<String> = presets.iter().map(|(o, _)| o.clone()).collect();
                opts.push("type a list…".into());
                let have = prof(cfg, name).get("tools").cloned().unwrap_or(Value::Null);
                let cur = presets.iter().position(|(_, v)| *v == have).unwrap_or(0);
                let Some(i) = self.pick(&format!("settings · {name} · tools"), &opts, cur)? else { return Ok(None) };
                if i < presets.len() {
                    let p = prof_mut(cfg, name);
                    if presets[i].1.is_null() {
                        p.shift_remove("tools");
                    } else {
                        p.insert("tools".into(), presets[i].1.clone()); // [] is meaningful: no tools
                    }
                } else {
                    let cur = reidcc::list(&prof(cfg, name), "tools").join(",");
                    if let Some(v) = self.ask("tools, comma separated", &cur) {
                        let list: Vec<Value> = v.split(',').map(py::strip).filter(|t| !t.is_empty())
                            .map(|t| Value::String(t.into())).collect();
                        prof_mut(cfg, name).insert("tools".into(), Value::Array(list));
                    }
                }
            }
            "mcp" => {
                let mut files = py::glob(&ctx.proxy_dir, "*mcp*.json");
                files.sort();
                let mut opts = vec!["your servers".to_string(), "none".into()];
                opts.extend(files.iter().map(|f| ctx.relpath(f)));
                opts.push("type a path…".into());
                let cur = match prof(cfg, name).get("mcp") {
                    Some(Value::String(s)) => opts.iter().position(|o| o == s).unwrap_or(0),
                    _ => 0,
                };
                let Some(i) = self.pick(&format!("settings · {name} · mcp"), &opts, cur)? else { return Ok(None) };
                if i == 0 {
                    setk(prof_mut(cfg, name), "mcp", Value::Null);
                } else if i == opts.len() - 1 {
                    let v = self.ask("MCP config path", "");
                    self.set_path(cfg, name, "mcp", v);
                } else {
                    setk(prof_mut(cfg, name), "mcp", Value::String(opts[i].clone()));
                }
            }
            "args" => {
                let v = self.ask("extra args (− or - clears)", &args_text(&prof(cfg, name)));
                match v.as_deref() {
                    Some("-") | Some("−") => setk(prof_mut(cfg, name), "args", Value::Null),
                    Some(v) => {
                        let list = reidcc::args_parse(v).into_iter().map(Value::String).collect();
                        setk(prof_mut(cfg, name), "args", Value::Array(list));
                    }
                    None => {}
                }
            }
            "name" => {
                let Some(v) = self.ask("rename to", name) else { return Ok(None) };
                if v == name {
                    return Ok(None);
                }
                if profiles(cfg).contains_key(&v) {
                    self.msg = format!("A profile named {v} already exists.");
                    return Ok(None);
                }
                let profs = renamed(profiles(cfg), name, &v);
                cfg.insert("profiles".into(), Value::Object(profs));
                if cfg.get("default").and_then(Value::as_str) == Some(name) {
                    cfg.insert("default".into(), Value::String(v.clone()));
                }
                return Ok(Some(v));
            }
            _ => {}
        }
        Ok(None)
    }

    /// A typed path for a file field: kept relative to the Reidcc folder if it exists.
    fn set_path(&mut self, cfg: &mut Obj, name: &str, key: &str, v: Option<String>) {
        let Some(v) = v else { return };
        let path = v.trim_matches('"');
        if py::exists(path) {
            setk(prof_mut(cfg, name), key, Value::String(self.ctx.relpath(path)));
        } else {
            self.msg = format!("Can't find {v}. Check the path.");
        }
    }
}

fn claude_only_field(f: &str) -> bool {
    ["proxy", "tools", "mcp", "chrome", "connectors", "safe"].contains(&f)
}

/// Is this Claude-only field set to something a Codex launch would refuse?
fn field_on(p: &Obj, field: &str) -> bool {
    match field {
        "proxy" => !proxy::list(p).is_empty(),
        "tools" => p.contains_key("tools"),
        "mcp" => on(p, "mcp").is_some(),
        "chrome" => on(p, "no_chrome").is_some(),
        "connectors" => on(p, "no_connectors").is_some(),
        "safe" => on(p, "safe").is_some(),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn strings() {
        assert_eq!(fit("abcdef", 4), "abc…");
        assert_eq!(fit("abc", -2), "…");
        assert_eq!(center("folder", 9), "  folder ");
        assert_eq!(center("profile", 9), " profile ");
        assert_eq!(center("●", 9), "    ●    ");
        assert_eq!(wrap_text("aa bb cc dd", 5, 3), vec!["aa bb", "cc dd"]);
        assert_eq!(wrap_text("", 5, 3), vec![""]);
        assert_eq!(reidcc::args_parse(r#"--a "b c" d\"e f\\"#), vec!["--a", "b c", "d\"e", "f\\\\"]);
        assert_eq!(strip_sgr("\x1b[38;2;1;2;3mhi\x1b[0m\x1b[K"), "hi\x1b[K");
    }
}
