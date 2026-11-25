//! The settings page (vision: "Direction from Reid" in reidcc_design_motion_system.md): app-wide choices
//! only. Where sessions open and the default engine are keys in reid.json; plugins come from Claude Code;
//! the colour choice and the locations are reid.json keys too (`colors`, `temp_dir`, `ai_temp_dir`), except
//! `local data`, which is the REIDCC_HOME user variable (it says where reid.json itself lives).

use crate::{App, S};
use reidcc::{engines::codex, py, pyjson};
use serde::Serialize;
use serde_json::Value;
use std::os::windows::process::CommandExt;
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
    /// "reidcc" (the engine's colours moved into the palette, recolor.rs) or "engine" (its own)
    colors: String,
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
    let sys_temp = std::env::var("TEMP").unwrap_or_default();
    View {
        open_in: if key("open_in") == "terminal" { "terminal" } else { "reidcc" }.into(),
        engine: if key("default_engine") == "codex" { "codex" } else { "claude" }.into(),
        start_size: crate::sizes::start_size(&key("start_size")).into(),
        colors: if key("colors") == "engine" { "engine" } else { "reidcc" }.into(),
        version: env!("CARGO_PKG_VERSION").into(),
        installed: reidcc::installed_copy(),
        home: m.ctx.home.clone(),
        // what apply_locations set, else Claude Code's own default (%TEMP%\claude) and the system temp
        ai_temp: std::env::var("CLAUDE_CODE_TMPDIR").unwrap_or_else(|_| py::join(&sys_temp, &["claude"])),
        temp: py::gettempdir(),
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
        "colors" => Some(("colors", "reidcc")),
        _ => None,
    };
    if let Some((k, default)) = known {
        let mut m = st.m.lock().unwrap();
        if let Some(mut cfg) = m.cfg() {
            if value == default { cfg.shift_remove(k); } else { cfg.insert(k.into(), Value::String(value)); }
            m.save(&cfg);
            crate::recolor::set_from(&cfg); // sessions opened from now on
        }
    }
    view(&st)
}

#[derive(Serialize)]
pub struct Changed {
    view: View,
    /// what happened, for the page to show under locations ("" when nothing changed)
    note: String,
}

/// `change` beside a location: pick a folder, then point Reidcc at it. Picking the default puts it back.
#[tauri::command]
pub fn settings_change(app: tauri::AppHandle, which: String) -> Changed {
    let st = app.state::<App>();
    let v = view(&st);
    let cur = match which.as_str() {
        "home" => v.home.clone(),
        "temp" => v.temp.clone(),
        "ai_temp" => v.ai_temp.clone(),
        _ => return Changed { view: v, note: String::new() },
    };
    let picked = if st.test {
        std::env::var("REIDCC_TEST_PICK").ok() // rs\tests\settings_flow.py: no dialog to drive
    } else {
        let start = if py::isdir(&cur) { cur.clone() } else { py::expanduser("~") };
        let mut d = rfd::FileDialog::new().set_title("pick a folder").set_directory(&start);
        if let Some(w) = crate::parent(&app) {
            d = d.set_parent(&w);
        }
        d.pick_folder().map(|p| p.to_string_lossy().into_owned())
    };
    let Some(dir) = picked.filter(|d| py::isdir(d)).map(|d| py::normpath(&py::abspath(&d))) else {
        return Changed { view: v, note: String::new() };
    };
    let note = if which == "home" { change_home(&st, &dir) } else { change_temp(&st, &which, &dir) };
    Changed { view: view(&st), note }
}

fn same(a: &str, b: &str) -> bool {
    py::normcase(&py::normpath(a)) == py::normcase(&py::normpath(b))
}

fn change_temp(st: &App, which: &str, dir: &str) -> String {
    let sys = std::env::var("TEMP").unwrap_or_default();
    let (key, default) = if which == "temp" { ("temp_dir", sys.clone()) } else { ("ai_temp_dir", py::join(&sys, &["claude"])) };
    let mut m = st.m.lock().unwrap();
    let Some(mut cfg) = m.cfg() else { return "reid.json has an error. Fix it, then try again.".into() };
    if same(dir, &default) { cfg.shift_remove(key); } else { cfg.insert(key.into(), Value::String(dir.into())); }
    m.save(&cfg);
    reidcc::apply_locations(&cfg);
    if which == "temp" { "Sessions opened from now on put their temp files here." } else { "Claude sessions opened from now on keep their scratch folders here." }.into()
}

/// What a Reidcc folder holds that reid.json can point at. Copied into a new `local data` folder that has
/// no reid.json yet; files already there win, and nothing in the old folder is touched.
/// shortcut: a profile path outside these (say `notes\x.md`) isn't copied; copy it by hand if one breaks.
const HOME_ITEMS: [&str; 9] = ["reid.json", "reid_state.json", "config.toml", "json", "personas", "mds", "codex", "proxy", "reidcc_memory.md"];

fn copy_missing(from: &std::path::Path, to: &std::path::Path) -> std::io::Result<()> {
    if from.is_dir() {
        std::fs::create_dir_all(to)?;
        for e in std::fs::read_dir(from)? {
            let e = e?;
            if e.file_name() != "logs" { // proxy\logs: old captures stay where they are
                copy_missing(&e.path(), &to.join(e.file_name()))?;
            }
        }
    } else if !to.exists() {
        std::fs::copy(from, to)?;
    }
    Ok(())
}

fn change_home(st: &App, dir: &str) -> String {
    let (cur, memory) = {
        let mut m = st.m.lock().unwrap();
        let mem = m.cfg().and_then(|c| c.get("memory_file").and_then(Value::as_str).map(String::from));
        (m.ctx.home.clone(), mem)
    };
    if same(dir, &cur) {
        return String::new();
    }
    if !py::exists(&py::join(dir, &["reid.json"])) {
        let mut items: Vec<String> = HOME_ITEMS.iter().map(|s| s.to_string()).collect();
        items.extend(memory.filter(|f| !std::path::Path::new(f).is_absolute()));
        for item in items {
            let from = std::path::Path::new(&cur).join(&item);
            if from.exists() {
                if let Err(e) = copy_missing(&from, &std::path::Path::new(dir).join(&item)) {
                    return format!("Couldn't copy {item} to {dir}: {e}. Nothing changed.");
                }
            }
        }
    }
    let back = same(dir, &reidcc::default_home_dir());
    if !st.test { // tests never touch the real user environment
        // setx and reg write HKCU\Environment and tell Windows, so the next Reidcc start sees it
        let r = if back {
            std::process::Command::new("reg").args(["delete", r"HKCU\Environment", "/v", "REIDCC_HOME", "/f"]).creation_flags(0x0800_0000).status()
        } else {
            std::process::Command::new("setx").args(["REIDCC_HOME", dir]).creation_flags(0x0800_0000).status()
        };
        if !r.is_ok_and(|s| s.success()) {
            return format!("Couldn't save REIDCC_HOME for {dir}. Nothing changed.");
        }
    }
    format!("Reidcc uses {dir} from its next start (every copy on this PC). The old folder stays as it was.")
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
