//! What the screens say about a profile: its one-line summary and its launch check.

use crate::engines::{self, codex, is_codex};
use crate::{on, profiles, proxy, py, text, Ctx, Obj};
use serde_json::Value;

/// Short persona name for tags (file name without extension), or "".
pub fn persona_name(prof: &Obj) -> String {
    py::splitext(&py::basename(&text(prof, "persona"))).0
}

fn stem(path: &str) -> String {
    py::splitext(&py::basename(path)).0
}

pub fn summary(ctx: &Ctx, cfg: &Obj, name: &str) -> String {
    let empty = Obj::new();
    let p = profiles(cfg).get(name).and_then(Value::as_object).unwrap_or(&empty);
    let cx = is_codex(p);
    let mut bits: Vec<String> = if cx { vec!["codex".into()] } else { vec![] };
    let model = text(p, "model");
    bits.push(if !model.is_empty() { model } else if cx { "engine default".into() } else { "provider default".into() });
    let settings = text(p, "settings");
    if !settings.is_empty() {
        let miss = if py::exists(&ctx.resolve(&settings)) { "" } else { " (missing)" };
        bits.push(format!("{}{}{miss}", if cx { "" } else { "api " }, stem(&settings)));
    } else {
        bits.push(if cx { codex::login_label(ctx) } else { "subscription".into() });
    }
    let persona = text(p, "persona");
    if !persona.is_empty() {
        let miss = if py::exists(&ctx.resolve(&persona)) { "" } else { " (missing)" };
        let rep = if text(p, "mode") == "replace" { " (replace)" } else { "" };
        bits.push(format!("persona {}{rep}{miss}", persona_name(p)));
    }
    if on(p, "memory").is_some() {
        bits.push("memory".into());
    }
    let px = proxy::list(p);
    if !px.is_empty() {
        bits.push(format!("proxy {}", px.join("+")));
    }
    if p.contains_key("tools") {
        let n = crate::list(p, "tools").len();
        bits.push(if n > 0 { format!("{n} tools") } else { "no tools".into() });
    }
    let mcp = text(p, "mcp");
    if !mcp.is_empty() {
        bits.push(if mcp == "none" { "no mcp".into() } else { format!("mcp {}", stem(&mcp)) });
    }
    for (k, words) in [("no_chrome", "chrome off"), ("no_connectors", "connectors off"), ("safe", "safe mode")] {
        if on(p, k).is_some() {
            bits.push(words.into());
        }
    }
    let claude_only = engines::claude_only_on(p);
    if cx && !claude_only.is_empty() {
        bits.push(format!("won't start: {} {} Claude only", claude_only.join(", "), if claude_only.len() > 1 { "are" } else { "is" }));
    }
    bits.join(" · ")
}

/// The sign-in files an engine can use: codex\*.toml for Codex, json\*.json for Claude, stored
/// the way reid.json keeps them (relative to the Reidcc folder), sorted.
pub fn signin_files(ctx: &Ctx, codex: bool) -> Vec<String> {
    let files: Vec<String> = if codex {
        py::glob(&ctx.codex_dir, "*.toml")
    } else {
        py::glob(&py::join(&ctx.home, &["json"]), "*.json").into_iter().filter(|f| !f.contains("token_log")).collect()
    };
    let mut out: Vec<String> = files.iter().map(|f| ctx.relpath(f)).collect();
    out.sort();
    out
}

/// Can this profile start here? (error, command preview, what's on: persona/memory). Shared by
/// the launcher and the TUI so both show the same `ready · persona + memory` and preview.
pub fn check(ctx: &Ctx, cfg: &Obj, name: &str, cwd: &str) -> (Option<String>, String, Vec<&'static str>) {
    let empty = Obj::new();
    let p = profiles(cfg).get(name).and_then(Value::as_object).unwrap_or(&empty);
    let have: Vec<&str> = [("persona", "persona"), ("memory", "memory")].iter()
        .filter(|(k, _)| on(p, k).is_some()).map(|(_, w)| *w).collect();
    let launch = match engines::build(ctx, cfg, name, &[], Some(cwd), false) {
        Ok(l) => l,
        Err(e) => return (Some(e.0), String::new(), have),
    };
    launch.remove_temps();
    let engine = engines::engine_of(p, name).unwrap_or("claude");
    let home = format!("{}/", ctx.home.replace('\\', "/").trim_end_matches('/'));
    let ui = codex::ui_settings();
    let mut shown: Vec<String> = vec![];
    for a in &launch.argv[1..] {
        // Reidcc's own status line and title: like Claude's statusline, not shown
        if ui.contains(a) && shown.last().map(String::as_str) == Some("-c") {
            shown.pop();
            continue;
        }
        shown.push(a.clone());
    }
    let mut cmd = vec![engine.to_string()];
    cmd.extend(shown.iter().map(|a| if a.contains("reid_") { "<temp>".into() } else { a.replace(&home, "") }));
    let mut preview = py::list2cmdline(&cmd);
    if proxy::plan(ctx, p).ok().flatten().is_some() {
        preview = format!("via proxy {} · {preview}", proxy::list(p).join("+"));
    }
    (None, preview, have)
}
