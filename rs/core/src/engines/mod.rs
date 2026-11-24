//! The engine boundary: one module per coding tool, each turning a profile into the command,
//! environment and temp files that start it (SPEC-rust-rewrite: "build(profile) -> argv, env,
//! temp files").

pub mod claude;
pub mod codex;

use crate::{err, profiles, py, Ctx, Env, Obj, R, BASE_MODELS};
use serde_json::Value;

pub const ENGINES: [&str; 2] = ["claude", "codex"];

/// Fields only Claude Code understands, with the words the screens use.
pub const CLAUDE_ONLY: [(&str, &str); 6] = [("tools", "a tools limit"), ("mcp", "an MCP choice"),
    ("safe", "safe mode"), ("no_chrome", "chrome off"), ("no_connectors", "connectors off"),
    ("settings_json", "settings_json")];

pub struct Launch {
    pub argv: Vec<String>,
    pub env: Env,
    pub temps: Vec<String>,
}

impl Launch {
    pub fn remove_temps(&self) {
        for t in &self.temps {
            let _ = std::fs::remove_file(t);
        }
    }
}

/// Exactly "claude" or "codex"; missing (or null) means claude. Anything else is an error.
pub fn engine_of(prof: &Obj, name: &str) -> R<&'static str> {
    match prof.get("engine") {
        None | Some(Value::Null) => Ok("claude"),
        Some(Value::String(s)) if s == "claude" => Ok("claude"),
        Some(Value::String(s)) if s == "codex" => Ok("codex"),
        Some(v) => err(format!("Profile {name}: there's no engine called {}. Use claude or codex.", crate::pyjson::py_str(v))),
    }
}

/// For the screens: never fails.
pub fn is_codex(prof: &Obj) -> bool {
    prof.get("engine").and_then(Value::as_str) == Some("codex")
}

/// The Claude-only fields switched on in this profile, in screen words. "tools" counts whenever
/// present: even [] means "no tools", a limit.
pub fn claude_only_on(prof: &Obj) -> Vec<&'static str> {
    CLAUDE_ONLY.iter().filter(|(k, _)| prof.get(*k).is_some_and(|v| *k == "tools" || crate::pyjson::truthy(v)))
        .map(|(_, w)| *w).collect()
}

pub fn is_claude_model(model: &str) -> bool {
    !model.is_empty() && (BASE_MODELS.contains(&model) || model.to_lowercase().starts_with("claude"))
}

/// Return the launch for profile `name`. Everything that can fail is checked before any temp
/// file is written. `prepare=false` (previews) only matters for Codex: no prompt file written.
pub fn build(ctx: &Ctx, cfg: &Obj, name: &str, extra: &[String], cwd: Option<&str>, prepare: bool) -> R<Launch> {
    let profs = profiles(cfg);
    let Some(Value::Object(prof)) = profs.get(name) else {
        if profs.contains_key(name) {
            return err(format!("Profile {name} isn't an object. Fix it in reid.json."));
        }
        return err(format!("No profile named {name}. Profiles: {}.", profs.keys().cloned().collect::<Vec<_>>().join(", ")));
    };
    if engine_of(prof, name)? == "codex" {
        return codex::build(ctx, cfg, name, prof, extra, cwd, prepare);
    }
    claude::build(ctx, cfg, name, prof, extra, cwd)
}

/// A profile's file field: resolved, and it has to exist.
pub(crate) fn need(ctx: &Ctx, name: &str, path: &str, what: &str) -> R<String> {
    let full = ctx.resolve(path);
    if !py::exists(&full) {
        return err(format!("Can't find the {what} for {name}: {}. Pick it again in settings.", crate::show_path(&full)));
    }
    Ok(full)
}

/// env[k] = str(v) for the profile's env field; null removes the variable.
pub(crate) fn apply_env(env: &mut Env, prof: &Obj) {
    if let Some(Value::Object(m)) = prof.get("env") {
        for (k, v) in m {
            if v.is_null() {
                env.shift_remove(k);
            } else {
                env.insert(k.clone(), crate::pyjson::py_str(v));
            }
        }
    }
}

pub(crate) fn io(e: std::io::Error) -> crate::ReidError {
    crate::ReidError(e.to_string())
}
