//! Reidcc.exe: the launcher window, 1:1 with python\reid_gui.py (vision\Spec\SPEC-rust-tui-gui.md,
//! part 2). Tauri 2 shell; the page is ui\ (plain TypeScript + CSS). Profile logic is rs\core.

#![windows_subsystem = "windows"]

mod dock;
mod fonts;
mod gate;
mod model;
mod recolor;
mod rig;
mod session;
mod settings;
mod sizes;
mod update;

use model::{Model, Op, Vars};
use reidcc::engines::{self, codex, is_codex};
use reidcc::{profiles, py, Ctx};
use serde::Serialize;
use serde_json::Value;
use std::sync::{Arc, Mutex};
use std::time::Instant;
use tauri::{AppHandle, Emitter, Manager, State};

// Tokens from vision/reidcc-palette.md (the ones the title bar uses)
const CANVAS: u32 = 0x040404;
const LINE: u32 = 0x2A2724;
const TEXT2: u32 = 0x9F978E;

pub struct App {
    pub m: Mutex<Model>,
    pub(crate) gate: gate::Shared,
    /// test hooks on (REIDCC_GUI_TEST=1)
    test: bool,
    /// first focus: the list when there's a folder to start in, else pick folder
    focus_list: bool,
}

pub type S<'a> = State<'a, App>;

/// Test runs only (REIDCC_GUI_TEST=1): every window's WebView2 profile folder.
pub static WEBVIEW_DIR: std::sync::OnceLock<std::path::PathBuf> = std::sync::OnceLock::new();

/// A bundled file: next to the exe or in a folder above it (rs\target\release -> E:\reidcc, app\ -> E:\reidcc).
fn asset(name: &str) -> Option<String> {
    let exe = std::env::current_exe().ok()?;
    let mut d = exe.parent()?.to_path_buf();
    loop {
        let p = d.join(name);
        if p.exists() {
            return Some(p.to_string_lossy().into_owned());
        }
        d = d.parent()?.to_path_buf();
    }
}

/// argv prefix that runs reid in a console: reid.exe next to this exe.
fn cli_command() -> Vec<String> {
    let exe = std::env::current_exe().unwrap_or_default();
    vec![exe.with_file_name("reid.exe").to_string_lossy().into_owned()]
}

/// Windows' own title bar in the palette: canvas background, text-2 title, hairline border.
fn theme_titlebar(hwnd: isize) {
    use windows_sys::Win32::Graphics::Dwm::DwmSetWindowAttribute;
    let rgb = |c: u32| ((c & 0xFF) << 16) | (c & 0xFF00) | ((c >> 16) & 0xFF); // 0xRRGGBB -> COLORREF 0x00BBGGRR
    for (attr, val) in [(20u32, 1u32), (34, rgb(LINE)), (35, rgb(CANVAS)), (36, rgb(TEXT2))] {
        let v = val as i32; // 20 dark mode, 34 border, 35 caption, 36 title text
        unsafe { DwmSetWindowAttribute(hwnd as _, attr, &v as *const i32 as _, 4) };
    }
}

/// Start the background `codex login status` if a load asked for it (it takes about a second).
fn kick_login(app: &AppHandle, m: &mut Model) {
    if !std::mem::take(&mut m.want_login_check) || m.login_busy {
        return;
    }
    m.login_busy = true;
    let (home, app) = (m.ctx.home.clone(), app.clone());
    std::thread::spawn(move || {
        let answer = codex::login(&Ctx::at(&home), false);
        let st: S = app.state();
        if let Some(a) = answer {
            codex::login_store(&st.m.lock().unwrap().ctx, &a);
        }
        let _ = app.emit("login-done", ());
    });
}

fn done(app: &AppHandle, m: &mut Model) -> Vec<Op> {
    kick_login(app, m);
    m.take()
}

#[derive(Serialize)]
struct Init {
    ops: Vec<Op>,
    folder: String,
    gate: Option<Value>,
    /// the form's opening (SPEC-hand.md): the emblem grows, then the view zooms into the emerald
    emblem: Option<Value>,
    test: bool,
    /// the smallest size the main layout fits in (logical px); below it the page folds to medium (the form)
    main_min: (f64, f64),
}

#[tauri::command]
fn init(app: AppHandle, st: S) -> Init {
    let mut m = st.m.lock().unwrap();
    let cfg = m.cfg();
    let d = cfg.as_ref().and_then(|c| c.get("default")).and_then(Value::as_str).map(String::from);
    m.reload(d.as_deref());
    m.ops.push(Op::Focus { target: (if st.focus_list { "list" } else { "pick" }).into() });
    let meta = |f: &str| asset(f).and_then(|p| py::read_text(&p, false).ok()).and_then(|t| serde_json::from_str(&t).ok());
    let (gate, emblem) = (meta("assets\\gate.json"), meta("assets\\emblem.json"));
    let folder = m.folder.clone();
    let main_min = *sizes::MAIN_MIN.get().unwrap_or(&(960.0, 820.0));
    Init { ops: done(&app, &mut m), folder, gate, emblem, test: st.test, main_min }
}

#[tauri::command]
fn folder_text(st: S, text: String) {
    st.m.lock().unwrap().folder = text;
}

#[tauri::command]
fn select(app: AppHandle, st: S, name: String, typed: String) -> Vec<Op> {
    let mut m = st.m.lock().unwrap();
    if m.current.as_deref() != Some(&name) {
        m.select(&name, &typed);
    }
    done(&app, &mut m)
}

#[tauri::command]
fn apply(app: AppHandle, st: S, vars: Vars) -> Vec<Op> {
    let mut m = st.m.lock().unwrap();
    m.apply(&vars);
    done(&app, &mut m)
}

#[tauri::command]
fn rename(app: AppHandle, st: S, typed: String) -> Vec<Op> {
    let mut m = st.m.lock().unwrap();
    m.rename(&typed);
    done(&app, &mut m)
}

#[tauri::command]
fn action(app: AppHandle, st: S, name: String) -> Vec<Op> {
    let mut m = st.m.lock().unwrap();
    match name.as_str() {
        "new" => m.new_profile(),
        "dup" => m.dup(),
        "delete" => m.delete(),
        "default" => m.set_default(),
        "retry" => m.retry(),
        "login_done" => m.login_done(),
        "commit_folder" => m.commit_folder(),
        "open_memory" => m.open_memory(),
        "open_config" => model::open_file(&m.ctx.config),
        n if n.starts_with("delete:") => m.really_delete(&n["delete:".len()..]),
        _ => {}
    }
    done(&app, &mut m)
}

#[tauri::command]
fn open_persona(st: S, persona: String) -> Vec<Op> {
    let mut m = st.m.lock().unwrap();
    m.open_persona(&persona);
    m.take()
}

fn parent(app: &AppHandle) -> Option<tauri::WebviewWindow> {
    app.get_webview_window("main")
}

#[tauri::command]
fn pick_folder(app: AppHandle, st: S) -> Vec<Op> {
    let start = {
        let m = st.m.lock().unwrap();
        let f = m.real_folder();
        if py::isdir(&f) { f } else { py::expanduser("~") }
    };
    let mut d = rfd::FileDialog::new().set_title("pick folder").set_directory(&start);
    if let Some(w) = parent(&app) {
        d = d.set_parent(&w);
    }
    let picked = d.pick_folder();
    let mut m = st.m.lock().unwrap();
    if let Some(p) = picked {
        m.set_folder(&py::normpath(&p.to_string_lossy()));
        m.ops.push(Op::Clear);
    }
    m.take()
}

#[tauri::command]
fn browse_persona(app: AppHandle, st: S, choices: Vec<String>) -> Vec<Op> {
    let dir = py::join(&st.m.lock().unwrap().ctx.home, &["personas"]);
    let mut d = rfd::FileDialog::new().set_title("persona").set_directory(&dir)
        .add_filter("Markdown", &["md"]).add_filter("Text", &["txt"]).add_filter("All", &["*"]);
    if let Some(w) = parent(&app) {
        d = d.set_parent(&w);
    }
    let picked = d.pick_file();
    let mut m = st.m.lock().unwrap();
    if let Some(f) = picked {
        m.persona_picked(&f.to_string_lossy(), &choices);
    }
    m.take()
}

#[derive(Serialize)]
struct Recent {
    dirs: Vec<(String, String)>,
    ops: Vec<Op>,
}

#[tauri::command]
fn recent(st: S) -> Recent {
    let mut m = st.m.lock().unwrap();
    let dirs: Vec<(String, String)> = m.recent_dirs().into_iter().map(|d| (reidcc::show_path(&d), d)).collect();
    if dirs.is_empty() {
        m.ops.push(Op::Say { text: "No projects yet. Pick a folder to start.".into(), kind: "info".into(),
                             actions: vec![("pick folder".into(), "pick_folder".into())], seconds: None, focus: None });
    }
    Recent { dirs, ops: m.take() }
}

#[tauri::command]
fn set_folder(st: S, path: String) -> Vec<Op> {
    let mut m = st.m.lock().unwrap();
    m.set_folder(&path);
    m.take()
}

#[derive(Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
enum Go {
    /// nothing to open: just these messages
    Ops { ops: Vec<Op> },
    /// the session started; play the gate
    /// `found`: the session window already exists (a Reidcc session window, not Windows Terminal)
    Gate { note: String, uses_wt: bool, found: bool, title: String, sub: String, ops: Vec<Op> },
}

/// Async: a session window is made here, and Windows can't make one from the main thread's command.
#[tauri::command]
async fn go(app: AppHandle, st: S<'_>, sessions: State<'_, session::Sessions>, resume: bool, gate_ok: bool) -> Result<Go, String> {
    Ok(go_now(&app, &st, &sessions, resume, gate_ok))
}

fn go_now(app: &AppHandle, st: &App, sessions: &session::Sessions, resume: bool, gate_ok: bool) -> Go {
    // One press at a time: the model lock is let go below (the login check, the window build), so a second
    // press can't count on it to wait its turn.
    use std::sync::atomic::{AtomicBool, Ordering::SeqCst};
    static OPENING: AtomicBool = AtomicBool::new(false);
    struct Opening;
    impl Drop for Opening {
        fn drop(&mut self) {
            OPENING.store(false, SeqCst);
        }
    }
    if OPENING.swap(true, SeqCst) {
        return Go::Ops { ops: vec![] };
    }
    let _opening = Opening;
    let mut m = st.m.lock().unwrap();
    let ops = |m: &mut Model| Go::Ops { ops: m.take() };
    let Some(cfg) = m.cfg() else { return ops(&mut m) };
    let Some(name) = m.current.clone() else { return ops(&mut m) };
    if st.gate.lock().unwrap().active {
        return ops(&mut m); // one session per press
    }
    let mut cwd = m.real_folder();
    let prof = profiles(&cfg).get(&name).and_then(Value::as_object).cloned().unwrap_or_default();
    let engine = match prof.get("engine") {
        Some(v) if reidcc::pyjson::truthy(v) => reidcc::pyjson::py_str(v),
        _ => "claude".into(),
    };
    let say = |m: &mut Model, text: &str, kind: &str, actions: Vec<(String, String)>, seconds: Option<f64>| {
        m.ops.push(Op::Say { text: text.into(), kind: kind.into(), actions, seconds, focus: None });
    };
    if resume && engine != "claude" {
        say(&mut m, "Resume is for Claude profiles for now. open gate starts a new Codex session.", "info", vec![], Some(5.0));
        return ops(&mut m);
    }
    if is_codex(&prof) && !reidcc::on(&prof, "settings").is_some() && codex::login_cached(&m.ctx).as_deref() == Some("not signed in") {
        // signed in from a terminal since? (about a second, so without the lock: clicks keep working)
        let home = m.ctx.home.clone();
        drop(m);
        let answer = codex::login(&Ctx::at(&home), true);
        m = st.m.lock().unwrap();
        if let Some(a) = answer {
            codex::login_store(&m.ctx, &a);
        }
        m.login_done();
    }
    if resume {
        let last = reidcc::load_state(&m.ctx).get("last").cloned().filter(reidcc::pyjson::truthy);
        let Some(last) = last else {
            say(&mut m, "Nothing to resume yet.", "info", vec![], Some(4.0));
            return ops(&mut m);
        };
        if let Some(c) = last.get("cwd").filter(|c| reidcc::pyjson::truthy(c)) {
            cwd = reidcc::pyjson::py_str(c);
        }
    }
    if !py::isdir(&cwd) {
        say(&mut m, "Can't find that folder. It may have moved.", "error", vec![("pick again".into(), "pick_folder".into())], None);
        return ops(&mut m);
    }
    // catch config problems here instead of in a terminal that closes
    match engines::build(&m.ctx, &cfg, &name, &[], Some(&cwd), false) {
        Ok(l) => l.remove_temps(),
        Err(e) => {
            let again = if resume { "go_resume" } else { "go" };
            say(&mut m, &e.0, "error", vec![("try again".into(), again.into())], None);
            return ops(&mut m);
        }
    }
    let mut cmd = m.cli.clone();
    if resume {
        cmd.push("--resume".into());
    }
    cmd.push(name.clone());
    let title = format!("{engine} · {name}");
    let sub = reidcc::show_path(&cwd);
    // vision v1 §2: a Reidcc session window by default; "open_in": "terminal" keeps Windows Terminal
    let open_in = cfg.get("open_in").map(reidcc::pyjson::py_str).unwrap_or_default();
    if open_in != "terminal" {
        let info = session::Info { engine: engine.clone(), profile: name.clone(), folder: sub.clone(),
                                   persona: reidcc::profile::persona_name(&prof), elapsed_ms: 0 };
        // Without the lock: making the window waits on the main thread, whose commands take this lock.
        drop(m);
        let sf = app.get_webview_window("main").and_then(|w| w.scale_factor().ok()).unwrap_or(1.0);
        let rect = sizes::session_rect(session::visible_rect(gate::main_hwnd() as isize), sf); // main's size at least
        let opened = sessions.open(app, info, &cwd, &cmd, rect, None);
        m = st.m.lock().unwrap();
        let w = match opened {
            Ok(w) => w,
            Err(e) => {
                say(&mut m, &format!("Couldn't open the session window ({e})."), "error", vec![], None);
                return ops(&mut m);
            }
        };
        let note = "Session window open.".to_string();
        if !gate_ok {
            let _ = w.show();
            let _ = w.set_focus();
            say(&mut m, &note, "quiet", vec![], Some(4.0));
            return ops(&mut m);
        }
        // It's hidden over the launcher already: the gate shows it out of the dark at the hand-off.
        let found = w.hwnd().ok().map(|h| h.0 as isize); // asks the main thread: not under the gate lock
        {
            let mut g = st.gate.lock().unwrap();
            g.gen += 1;
            *g = gate::GateState { active: true, uses_wt: false, found, hidden: true,
                                   t0: Some(Instant::now()), gen: g.gen, ..Default::default() };
        }
        gate::fine_timer(true);
        gate::lock_foreground(true);
        return Go::Gate { note, uses_wt: true, found: true, title, sub, ops: m.take() };
    }
    if !gate_ok {
        let note = match gate::launch(None, &name, &cwd, &cmd) {
            Ok((note, _)) => note,
            Err(e) => format!("Couldn't open the session ({e}). Check that Windows Terminal or Claude Code still runs."),
        };
        say(&mut m, &note, "quiet", vec![], Some(4.0));
        return ops(&mut m);
    }
    // The session starts first; the gate never delays it.
    let plan = gate::plan();
    let before = gate::wt_windows();
    gate::lock_foreground(true);
    match gate::launch(Some(&plan), &name, &cwd, &cmd) {
        Ok((note, uses_wt)) => {
            {
                let mut g = st.gate.lock().unwrap();
                g.gen += 1;
                *g = gate::GateState { active: true, uses_wt, before, t0: Some(Instant::now()), gen: g.gen, ..Default::default() };
            }
            gate::fine_timer(true);
            if uses_wt {
                start_watch(app, &st.gate);
            }
            Go::Gate { note, uses_wt, found: false, title, sub, ops: m.take() }
        }
        Err(e) => {
            gate::lock_foreground(false);
            let t = format!("Couldn't open the session ({e}). Check that Windows Terminal or Claude Code still runs.");
            say(&mut m, &t, "error", vec![], None);
            ops(&mut m)
        }
    }
}

fn start_watch(app: &AppHandle, g: &gate::Shared) {
    let app = app.clone();
    gate::watch(g.clone(), move |seen| {
        let _ = match seen {
            gate::Seen::Found { handed } => app.emit("gate-found", handed),
            gate::Seen::Timeout => app.emit("gate-timeout", ()),
        };
    });
}

/// 5. The real terminal window to the front (the page moved its focus first).
#[tauri::command]
fn gate_handover(st: S) {
    let mut g = st.gate.lock().unwrap();
    g.done = true;
    gate::hand_over_locked(&mut g);
}

/// Any key or click: straight to the end. Exactly one session either way.
#[tauri::command]
fn gate_skip(st: S) {
    let mut g = st.gate.lock().unwrap();
    if g.found.is_some() && g.hidden {
        gate::hand_over_locked(&mut g);
    }
    g.done = true;
}

#[tauri::command]
fn gate_finish(app: AppHandle, st: S) {
    let restart = {
        let mut g = st.gate.lock().unwrap();
        if !g.active {
            return;
        }
        g.active = false;
        g.found.is_none() && g.uses_wt && !g.polling
    };
    gate::fine_timer(false);
    gate::lock_foreground(false);
    if restart {
        start_watch(&app, &st.gate); // skipped before the window appeared: keep watching to bring it forward
    }
}

// ------------------------------------------------------------ test hooks ---
// Only with REIDCC_GUI_TEST=1 (rs\tests\gui_parity.py, gui_shots.py).

#[tauri::command]
fn test_login(app: AppHandle, st: S, status: Option<String>) -> Vec<Op> {
    if !st.test {
        return vec![];
    }
    let mut m = st.m.lock().unwrap();
    // the answer a finished `codex login status` would cache, without running Codex
    codex::login_store(&m.ctx, &status.unwrap_or_else(|| "not signed in".into()));
    m.login_done();
    done(&app, &mut m)
}

fn main() {
    reidcc::refresh_path(); // before anything looks for claude, wt, git...
    let test = std::env::var("REIDCC_GUI_TEST").is_ok_and(|v| v == "1");
    let mut ctx = Ctx::new();
    ctx.cli = cli_command();
    let args: Vec<String> = std::env::args().collect();
    let cwd = args.iter().position(|a| a == "--cwd").and_then(|i| args.get(i + 1)).cloned();
    let state = reidcc::load_state(&ctx);
    let recents: Vec<String> = match state.get("recent_dirs") {
        Some(Value::Array(a)) => a.iter().map(reidcc::pyjson::py_str).filter(|d| py::isdir(d)).collect(),
        _ => vec![],
    };
    let start = match (&cwd, recents.first()) {
        (Some(c), _) if py::isdir(c) => c.clone(),
        (_, Some(r)) => r.clone(),
        _ => py::expanduser("~"),
    };
    let focus_list = !recents.is_empty() || cwd.is_some();
    let update_now = args.iter().any(|a| a == "--update"); // from `reid --update`
    let folder = reidcc::show_path(&start);
    let cli = ctx.cli.clone();
    if test {
        // a WebView2 profile of its own in the temp Reidcc folder, so a test can run beside Reid's open Reidcc
        let _ = WEBVIEW_DIR.set(std::path::PathBuf::from(py::join(&ctx.home, &[".webview"])));
    }
    let app_state = App { m: Mutex::new(Model::new(ctx, cli, folder)), gate: Arc::new(Mutex::new(gate::GateState::default())), test, focus_list };

    tauri::Builder::default()
        .manage(app_state)
        .manage(session::Sessions::default())
        .manage(dock::Dock::default())
        .manage(update::Updates::default())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .on_window_event(|w, e| {
            dock::window_event(w, e);
            sizes::window_event(w, e);
        })
        .register_uri_scheme_protocol("reid", |_ctx, req| {
            // reid://localhost/assets/... : the gate frames and the banner, straight from assets\
            let path = req.uri().path().trim_start_matches('/').replace('/', "\\");
            let body = (!path.contains("..")).then(|| asset(&path)).flatten().and_then(|p| std::fs::read(p).ok());
            match body {
                Some(b) => tauri::http::Response::builder().header("Content-Type", "image/png")
                    .header("Access-Control-Allow-Origin", "*").body(b).unwrap(),
                None => tauri::http::Response::builder().status(404).body(vec![]).unwrap(),
            }
        })
        .setup(move |app| {
            let mon = app.primary_monitor().ok().flatten();
            // logical px, like every size below (a 1080p screen at 150% is 1280 x 720)
            let (sw, sh) = mon.map(|m| {
                let s = m.scale_factor();
                ((m.size().width as f64 / s) as i32, (m.size().height as f64 / s) as i32)
            }).unwrap_or((1920, 1080));
            let h = 880.min(sh - 140); // leave room for the title bar and the taskbar
            let _ = sizes::MAIN.set((1000.0, h as f64));
            let _ = sizes::MAIN_MIN.set((960.0, 820.min(h) as f64));
            // Settings → start size (reid.json "start_size"); the page lays itself out for whatever size it gets
            let start = app.state::<App>().m.lock().unwrap().cfg().and_then(|c| c.get("start_size").map(reidcc::pyjson::py_str));
            let (ww, wh) = match sizes::start_size(&start.unwrap_or_default()) {
                "medium" => (sizes::MEDIUM.0 as i32, (sizes::MEDIUM.1 as i32).min(sh - 140)),
                "small" => (sizes::SMALL.0 as i32, sizes::SMALL.1 as i32),
                _ => (1000, h),
            };
            let mut b = tauri::WebviewWindowBuilder::new(app, "main", tauri::WebviewUrl::App("index.html".into()))
                .title(concat!("Reidcc ", env!("CARGO_PKG_VERSION")))
                .inner_size(ww as f64, wh as f64)
                .min_inner_size(sizes::MIN.0, sizes::MIN.1) // medium and small below main's size (vision v1 §1)
                // Place it ourselves: Windows' cascade can push the bottom bar under the taskbar.
                .position(0.max((sw - ww) / 2) as f64, 0.max((sh - 48 - wh - 40) / 2) as f64)
                .background_color(tauri::window::Color(4, 4, 4, 255))
                .theme(Some(tauri::Theme::Dark))
                .visible(false);
            if let Some(d) = WEBVIEW_DIR.get() {
                b = b.data_directory(d.clone());
            }
            if let Some(ico) = asset("reidcc.ico").and_then(|p| std::fs::read(p).ok()) {
                if let Ok(img) = tauri::image::Image::from_bytes(&ico) {
                    b = b.icon(img.to_owned())?;
                }
            }
            let w = b.build()?;
            update::start(app.handle(), update_now);
            if let Ok(h) = w.hwnd() {
                gate::MAIN.store(h.0 as isize, std::sync::atomic::Ordering::Relaxed);
                theme_titlebar(h.0 as isize);
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            init, folder_text, select, apply, rename, action, open_persona, pick_folder, browse_persona, recent,
            set_folder, go, gate_handover, gate_skip, gate_finish, test_login, show, metrics,
            session::sess_attach, session::sess_write, session::sess_resize, session::sess_meters, session::sess_close,
            session::clip_text, session::sess_list, session::sess_focus, sizes::set_size, sizes::pod_fold, sizes::pod_unfold, sizes::pod_fit, sizes::pod_drag, dock::dock_drag, dock::dock_control, dock::dock_grouped, rig::rig_list, rig::rig_save, rig::rig_delete, rig::rig_open, update::update_foot, update::update_install,
            update::update_check, settings::settings_get, settings::settings_set, settings::settings_plugins, settings::settings_open
        ])
        .run(tauri::generate_context!())
        .expect("Reidcc couldn't start");
}

/// The page is drawn: show the window (no white flash before the first paint).
#[tauri::command]
fn show(app: AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.show();
        let _ = w.set_focus();
    }
}

/// Tk's (GDI's) text widths for each font role, so the page can space its text to match.
#[tauri::command]
fn metrics() -> fonts::Fonts {
    fonts::fonts()
}
