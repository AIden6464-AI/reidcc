//! The settings page (vision: "Direction from Reid" in reidcc_design_motion_system.md): app-wide choices
//! only. Where sessions open and the default engine are keys in reid.json; plugins come from Claude Code;
//! locations are shown, not changed yet (palette §5, open item).

use crate::{App, S};
use reidcc::{engines::codex, py, pyjson};
use serde::Serialize;
use serde_json::Value;
use std::time::Duration;
use tauri::Manager;

#[derive(Serialize)]
pub struct View {
    /// "reidcc" or "terminal"
    open_in: String,
    /// "claude" or "codex": what `new profile` makes
    engine: String,
    /// "main", "medium" or "small": the size the launcher opens at
    start_size: String,
    version: String,
    installed: bool,
    home: String,
    temp: String,
    ai_temp: String,
}

fn view(st: &App) -> View {
    let mut m = st.m.lock().unwrap();
    let cfg = m.cfg().unwrap_or_default();
    let key = |k: &str| cfg.get(k).map(pyjson::py_str).unwrap_or_default();
    let temp = std::env::var("TEMP").unwrap_or_default();
    View {
        open_in: if key("open_in") == "terminal" { "terminal" } else { "reidcc" }.into(),
        engine: if key("default_engine") == "codex" { "codex" } else { "claude" }.into(),
        start_size: crate::sizes::start_size(&key("start_size")).into(),
        version: env!("CARGO_PKG_VERSION").into(),
        installed: reidcc::installed_copy(),
        home: m.ctx.home.clone(),
        ai_temp: py::join(&temp, &["claude"]), // Claude Code's scratch folders live in %TEMP%\claude
        temp,
    }
}

#[tauri::command]
pub fn settings_get(st: S) -> View {
    view(&st)
}

/// Writes one choice to reid.json. The default value removes the key, so an untouched reid.json stays as it was.
#[tauri::command]
pub fn settings_set(st: S, key: String, value: String) -> View {
    let known = match key.as_str() {
        "open_in" => Some(("open_in", "reidcc")),
        "engine" => Some(("default_engine", "claude")),
        "start_size" => Some(("start_size", "main")),
        _ => None,
    };
    if let Some((k, default)) = known {
        let mut m = st.m.lock().unwrap();
        if let Some(mut cfg) = m.cfg() {
            if value == default { cfg.shift_remove(k); } else { cfg.insert(k.into(), Value::String(value)); }
            m.save(&cfg);
        }
    }
    view(&st)
}

#[derive(Serialize)]
pub struct Plugin {
    id: String,
    version: String,
    enabled: bool,
}

/// `claude plugin list --json` (a few seconds), off the main thread.
#[tauri::command]
pub async fn settings_plugins() -> Result<Vec<Plugin>, String> {
    tauri::async_runtime::spawn_blocking(|| {
        let claude = py::which("claude").ok_or("Can't find Claude Code.")?;
        let argv = [claude, "plugin".into(), "list".into(), "--json".into()];
        let (rc, out, err) = codex::run_capture(&argv, &reidcc::environ(), None, Duration::from_secs(30))
            .ok_or("Claude Code didn't answer.")?;
        if rc != 0 {
            return Err(err.lines().next().unwrap_or("claude plugin list failed").to_string());
        }
        let list: Vec<Value> = serde_json::from_str(&out).map_err(|e| e.to_string())?;
        Ok(list.iter().map(|p| Plugin {
            id: p["id"].as_str().unwrap_or("").into(),
            version: p["version"].as_str().unwrap_or("").into(),
            enabled: p["enabled"].as_bool().unwrap_or(false),
        }).collect())
    }).await.map_err(|e| e.to_string())?
}

/// The page's `open` buttons: a folder in Explorer.
#[tauri::command]
pub fn settings_open(app: tauri::AppHandle, which: String) {
    let v = view(&app.state::<App>());
    let dir = match which.as_str() {
        "home" => v.home,
        "temp" => v.temp,
        "ai_temp" => v.ai_temp,
        _ => return,
    };
    if py::isdir(&dir) {
        reidcc::win::startfile(&dir);
    }
}
