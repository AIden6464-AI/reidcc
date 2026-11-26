//! Running a session in this terminal, /reid back to Reidcc, and Claude Code's statusline.

use crate::engines::{self, engine_of};
use crate::term::{is_tty, write, BRONZE, OXIDE, R, TERM_RESET, TEXT, TEXT2, TEXT3};
use crate::{errln, load_config, out, profile, profiles, proxy, py, pyjson, remember_session, Ctx, Obj, R as Res};
use serde_json::Value;
use std::process::{Command, Stdio};
use std::time::{Duration, SystemTime};

pub fn back_flag_path() -> String {
    py::join(&py::gettempdir(), &[&format!("reid_back_{}.flag", std::process::id())])
}

pub fn claude_dir() -> String {
    std::env::var("CLAUDE_CONFIG_DIR").ok().filter(|s| !s.is_empty()).unwrap_or_else(|| py::expanduser("~/.claude"))
}

/// Claude keeps a session file once it has a message: projects\*\<sid>.jsonl.
pub fn session_exists(sid: &str) -> bool {
    if sid.is_empty() || sid.contains(['*', '?', '[']) {
        return false;
    }
    let projects = py::join(&claude_dir(), &["projects"]);
    std::fs::read_dir(projects).into_iter().flatten().flatten()
        .filter(|d| !d.file_name().to_string_lossy().starts_with('.')) // glob's * skips dot names
        .any(|d| d.path().join(format!("{sid}.jsonl")).exists())
}

fn kill_tree(child: &mut std::process::Child) {
    let _ = Command::new("taskkill").args(["/F", "/T", "/PID", &child.id().to_string()])
        .stdout(Stdio::null()).stderr(Stdio::null()).status();
    let deadline = std::time::Instant::now() + Duration::from_secs(5);
    while std::time::Instant::now() < deadline {
        if child.try_wait().ok().flatten().is_some() {
            return;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    let _ = child.kill();
}

/// Remove prompt/settings temps left by sessions whose terminal was closed (Windows kills reid
/// outright then, so its own cleanup never runs).
pub fn sweep_temps(max_age_h: u64) {
    let cutoff = Duration::from_secs(max_age_h * 3600);
    let Ok(rd) = std::fs::read_dir(py::gettempdir()) else { return };
    for e in rd.flatten() {
        let n = e.file_name().to_string_lossy().into_owned();
        if let Some(rest) = n.strip_prefix("reid_prompt_").or_else(|| n.strip_prefix("reid_settings_")) {
            // a session running longer than max_age_h still reads its files
            let pid = rest.split_once('_').filter(|(d, _)| !d.is_empty() && d.bytes().all(|b| b.is_ascii_digit()))
                .and_then(|(d, _)| d.parse::<u32>().ok());
            if pid.is_some_and(crate::win::pid_alive) {
                continue;
            }
            let old = e.metadata().ok().and_then(|m| m.modified().ok())
                .and_then(|m| SystemTime::now().duration_since(m).ok()).is_some_and(|d| d > cutoff);
            if old {
                let _ = std::fs::remove_file(e.path());
            }
        }
    }
}

pub struct Ended {
    pub rc: i32,
    pub back: bool,
    pub sid: Option<String>,
    pub note: String,
}

/// Run the profile's engine in this terminal. `resume` is a session id, or "-c" for the last one in
/// the folder. /reid is Claude's; a Codex session's id is found while it runs (codex::thread_of).
pub fn run(ctx: &Ctx, cfg: &Obj, name: &str, cwd: &str, extra: &[String], resume: Option<&str>) -> Res<Ended> {
    let empty = Obj::new();
    let prof = profiles(cfg).get(name).and_then(Value::as_object).unwrap_or(&empty);
    let engine = engine_of(prof, name)?;
    let claude = engine == "claude";
    sweep_temps(6);
    let mut launch = engines::build(ctx, cfg, name, extra, Some(cwd), true)?;
    let plan = match proxy::plan(ctx, prof) {
        Ok(p) => p,
        Err(e) => {
            launch.remove_temps();
            return Err(e);
        }
    };
    let mut note = String::new();
    let continuing = extra.iter().any(|a| ["-c", "--continue", "-r", "--resume"].contains(&a.as_str()) || a.starts_with("--resume="));
    let mut sid = None;
    if claude {
        match resume {
            Some("-c") => launch.argv.push("-c".into()),
            Some(r) if session_exists(r) => {
                launch.argv.extend(["--resume".into(), r.into()]);
                sid = Some(r.to_string());
            }
            Some(_) => note = "That session had no messages yet, so this is a new one.".into(),
            None => {}
        }
        if sid.is_none() && !continuing && resume != Some("-c") {
            let id = uuid::Uuid::new_v4().to_string();
            launch.argv.extend(["--session-id".into(), id.clone()]);
            sid = Some(id);
        }
    } else if let Some(r) = resume {
        // right after codex.exe, so the profile's own flags go to the resumed session
        let known = r != "-c" && engines::codex::thread_exists(&launch.env, r);
        launch.argv.splice(1..1, ["resume".to_string(), if known { r.into() } else { "--last".into() }]);
        if known {
            sid = Some(r.to_string());
        } else if r != "-c" {
            note = "That Codex session isn't there any more, so this continues the last one in this folder.".into();
        }
    }
    // one process per session (SPEC-unified-interface M1): a second window on it is refused
    let lock = |id: &str| crate::locks::session(ctx, &crate::locks::record(id, engine, name, cwd, "interactive"));
    // and a share of the folder: other windows may join, a headless writing turn may not
    let taken = sid.as_deref().map(lock).transpose().and_then(|l| Ok((l, crate::locks::folder_shared(ctx, cwd)?)));
    let (mut held, room) = match taken {
        Ok(l) => l,
        Err(e) => {
            launch.remove_temps();
            return Err(e);
        }
    };
    let flag = back_flag_path();
    let _ = std::fs::remove_file(&flag);
    if claude {
        launch.env.insert("REID_FLAG".into(), flag.clone()); // only Claude has the /reid command
    }
    launch.env.insert("REID_PROFILE".into(), name.into());

    let saved = crate::win::console_save();
    crate::win::ignore_ctrl_c_while(true); // Ctrl+C belongs to the session
    let mut px = None;
    let result = (|| -> Res<(i32, bool)> {
        // Banner goes to stderr so stdout stays clean for `reid <profile> -p ... | jq`.
        if is_tty() {
            write(&format!("{TERM_RESET}\x1b[?1049l"));
        }
        let back = if claude { "/reid comes back here" } else { "codex · /quit comes back here" };
        if window_file().is_some() {
            errln!("{TEXT3}{back}{R}"); // a session window's bar already names the profile (SPEC-one-look 7.4)
        } else {
            errln!("{TEXT2}REIDCC{TEXT} · {name} {TEXT3}· {back}{R}");
        }
        if !claude && is_tty() {
            write(&format!("\x1b]0;REIDCC · codex · {name}\x07")); // the tab title (Codex's own is off)
        }
        if !note.is_empty() {
            errln!("{TEXT3}{note}{R}");
        }
        if let Some(plan) = &plan {
            let p = proxy::start(ctx, name, plan)?;
            launch.env.extend(proxy::env(&p, !claude));
            errln!("{TEXT3}proxy {} on 127.0.0.1:{} · log {}{R}", proxy::list(prof).join("+"), p.port, crate::show_path(&p.log_path));
            px = Some(p);
        }
        let since = SystemTime::now() - Duration::from_secs(2); // file times are coarse
        let mut child = Command::new(&launch.argv[0]).args(&launch.argv[1..]).env_clear().envs(&launch.env)
            .current_dir(cwd).spawn().map_err(engines::io)?;
        let (mut skip, mut tick) = (std::collections::HashSet::new(), 0u32);
        loop {
            if let Some(s) = child.try_wait().map_err(engines::io)? {
                return Ok((s.code().unwrap_or(1), false));
            }
            if py::exists(&flag) {
                kill_tree(&mut child);
                return Ok((child.try_wait().ok().flatten().and_then(|s| s.code()).unwrap_or(1), true));
            }
            tick += 1;
            if !claude && sid.is_none() && tick % 5 == 0 {
                // Codex picks its own id: its thread file appears with the first message
                sid = engines::codex::thread_of(&launch.env, child.id(), since, &mut skip);
                if let Some(id) = sid.as_deref() {
                    held = lock(id).ok(); // a thread Codex just made: nobody else has it
                    let _ = remember_session(ctx, name, cwd, Some(id), engine); // kept even if the window is closed
                }
            }
            std::thread::sleep(Duration::from_millis(200));
        }
    })();
    if !claude && is_tty() {
        write("\x1b]0;Reidcc\x07");
    }
    proxy::stop(px.as_mut());
    crate::win::ignore_ctrl_c_while(false);
    if is_tty() {
        write(TERM_RESET); // never put escape codes into piped output (reid -p ... | jq)
    }
    crate::win::console_restore(&saved);
    launch.remove_temps();
    let _ = std::fs::remove_file(&flag);
    drop((held, room));
    let (rc, back) = result?;
    remember_session(ctx, name, cwd, sid.as_deref(), engine).map_err(engines::io)?;
    Ok(Ended { rc, back, sid, note })
}

/// Called by the /reid slash command from inside Claude.
pub fn cmd_back() -> i32 {
    let Some(flag) = std::env::var("REID_FLAG").ok().filter(|f| !f.is_empty()) else {
        out!("This session wasn't started by Reidcc, so there's nothing to go back to. Run reid to open it.");
        return 0;
    };
    let _ = std::fs::write(flag, "back");
    out!("Back to Reidcc.");
    std::thread::sleep(Duration::from_secs(8)); // reid ends the session long before this finishes
    0
}

/// int(round(float(v))) clamped to 0..100, or None.
fn pct(v: Option<&Value>) -> Option<i64> {
    let f = match v? {
        Value::Number(n) => n.as_f64()?,
        Value::Bool(b) => *b as i64 as f64,
        Value::String(s) => py::strip(s).parse::<f64>().ok()?,
        _ => return None,
    };
    if !f.is_finite() {
        return None;
    }
    Some((f.round_ties_even() as i64).clamp(0, 100))
}

fn level(p: i64) -> &'static str {
    if p >= 90 { OXIDE } else if p >= 75 { BRONZE } else { TEXT2 }
}

/// Claude Code's statusLine command for reid sessions: reads the session JSON on stdin.
///     ~/kiln · PROFILE · MAIN · PERSONA · KURE   context 42% · limit 61%
pub fn cmd_statusline(ctx: &Ctx) -> i32 {
    use std::io::Read;
    let mut input = String::new();
    let _ = std::io::stdin().read_to_string(&mut input);
    let input = input.replace("\r\n", "\n").replace('\r', "\n");
    let data = pyjson::loads(if input.is_empty() { "{}" } else { &input }).ok()
        .and_then(|v| v.as_object().cloned()).unwrap_or_default();
    let get = |o: &Obj, k: &str| o.get(k).filter(|v| pyjson::truthy(v)).cloned();
    let ws = get(&data, "workspace").and_then(|v| v.as_object().cloned()).unwrap_or_default();
    let dir = get(&ws, "current_dir").or_else(|| get(&data, "cwd")).map(|v| pyjson::py_str(&v)).unwrap_or_else(py::getcwd);
    let mut parts = vec![format!("{TEXT}{}{R}", crate::show_path(&dir))];
    if let Some(name) = std::env::var("REID_PROFILE").ok().filter(|n| !n.is_empty()) {
        parts.push(format!("{TEXT2}PROFILE · {}{R}", name.to_uppercase()));
        let pn = load_config(ctx).ok()
            .and_then(|cfg| profiles(&cfg).get(&name).and_then(Value::as_object).map(profile::persona_name))
            .unwrap_or_default();
        if !pn.is_empty() {
            parts.push(format!("{TEXT2}PERSONA · {}{R}", pn.to_uppercase()));
        }
    }
    let sep = format!(" {TEXT3}·{R} ");
    let left = parts.join(&sep);
    let cw = get(&data, "context_window").and_then(|v| v.as_object().cloned()).unwrap_or_default();
    let ctxp = pct(cw.get("used_percentage")); // None until Claude knows: shown as unknown, never 0%
    let mut meters = vec![match ctxp {
        Some(p) => format!("{}context {p}%{R}", level(p)),
        None => format!("{TEXT3}context unknown{R}"),
    }];
    let rl = get(&data, "rate_limits").and_then(|v| v.as_object().cloned()).unwrap_or_default();
    let lim: Vec<i64> = ["five_hour", "seven_day"].iter()
        .filter_map(|w| pct(rl.get(*w).and_then(Value::as_object).and_then(|o| o.get("used_percentage")))).collect();
    if let Some(m) = lim.iter().max() {
        meters.push(format!("{}limit {m}%{R}", level(*m))); // only subscribers get this, after the first reply
    }
    if let Some(path) = window_file() {
        // In a Reidcc session window the Telemetry Bar shows these; Claude's own line stays empty.
        let v = serde_json::json!({ "context": ctxp, "limit": lim.iter().max(),
                                    "context_window": cw, "rate_limits": rl });
        let tmp = format!("{path}.{}.tmp", std::process::id());
        if std::fs::write(&tmp, v.to_string()).is_ok() {
            let _ = std::fs::rename(&tmp, &path);
        }
        return 0;
    }
    out!("{left}   {}", meters.join(&sep));
    0
}

/// The session file of the Reidcc session window this runs in (vision v1 §2), if any.
pub fn window_file() -> Option<String> {
    std::env::var("REIDCC_SESSION").ok().filter(|s| !s.is_empty())
}

/// In a session window: tell the window how the session ended instead of opening the TUI.
pub fn window_end(end: &Ended) -> Option<i32> {
    let path = window_file()?;
    let _ = std::fs::write(format!("{path}.end"), serde_json::json!({ "back": end.back, "rc": end.rc }).to_string());
    Some(end.rc)
}
