//! vision\Spec\SPEC-one-window.md: the one launcher page (the webview "main") lives at home (the window
//! "main") or docked in the session window you called it from: `beside` (a column on the left) or `full`.
//! It moves; it is never copied, so what's typed in it goes along.
use crate::session::{PANE, PREFIX};
use serde::Serialize;
use std::sync::Mutex;
use tauri::{AppHandle, Emitter, Manager, PhysicalPosition, PhysicalSize, Webview, Window, WindowEvent};
use windows_sys::Win32::UI::WindowsAndMessaging::{SetWindowPos, SWP_NOACTIVATE, SWP_NOZORDER};

/// The column's width (logical px): medium's width, so the page lays itself out as the form.
pub const COL: f64 = 500.0;
const LABEL: &str = "main";

#[derive(Clone, Copy, PartialEq, Eq, Serialize, Debug)]
#[serde(rename_all = "lowercase")]
pub enum Mode { Beside, Full }

struct Docked {
    host: String,
    mode: Mode,
    /// the window's visible rect before and after it grew for the column (given back on close)
    grew: Option<(Rect, Rect)>,
    /// the beside column has been made room for (once per docking)
    grown: bool,
    /// the home window was showing when the launcher left it
    home_shown: bool,
}

#[derive(Default)]
pub struct Panel(Mutex<Option<Docked>>);

type Rect = (i32, i32, i32, i32);

/// The launcher's page, wherever it is.
pub fn launcher(app: &AppHandle) -> Option<Webview> { app.get_webview(LABEL) }
/// The launcher's own window (hidden while the page is docked).
pub fn home(app: &AppHandle) -> Option<Window> { app.get_window(LABEL) }
/// The window the launcher's page is in now: file pickers belong to it, sessions open over it.
pub fn launcher_window(app: &AppHandle) -> Option<Window> { launcher(app).map(|v| v.window()) }

/// A single session's window ("session-7"), not a frame ("session-group-2", which starts the same).
fn solo(w: &Window) -> Option<u32> { w.label().strip_prefix(PREFIX)?.parse().ok() }

fn state(app: &AppHandle) -> &Panel { app.state::<Panel>().inner() }

/// The column a window keeps aside for the docked launcher (physical px), 0 when it isn't docked there
/// or covers the window (full hides everything else instead).
pub fn reserve(window: &Window) -> i32 {
    let g = state(window.app_handle()).0.lock().unwrap();
    match g.as_ref() {
        Some(d) if d.host == window.label() && d.mode == Mode::Beside => col_px(window),
        _ => 0,
    }
}

fn col_px(window: &Window) -> i32 {
    let w = window.inner_size().map(|s| s.width as i32).unwrap_or(0);
    ((COL * window.scale_factor().unwrap_or(1.0)).round() as i32).min(w)
}

fn bounds(view: &Webview, (l, t, r, b): (i32, i32, i32, i32)) {
    let _ = view.set_bounds(tauri::Rect {
        position: PhysicalPosition::new(l, t).into(),
        size: PhysicalSize::new((r - l).max(1) as u32, (b - t).max(1) as u32).into(),
    });
}

fn set_visible_rect(window: &Window, to: (i32, i32, i32, i32)) {
    let Ok(h) = window.hwnd() else { return };
    let h = h.0 as isize;
    let (outer, vis) = (crate::gate::window_rect(h as _), crate::session::visible_rect(h));
    let (l, t) = (to.0 - (vis.0 - outer.0), to.1 - (vis.1 - outer.1));
    let (w, hh) = ((to.2 - to.0) + (vis.0 - outer.0) + (outer.2 - vis.2), (to.3 - to.1) + (vis.1 - outer.1) + (outer.3 - vis.3));
    unsafe { SetWindowPos(h as _, std::ptr::null_mut(), l, t, w, hh, SWP_NOZORDER | SWP_NOACTIVATE) };
}

/// Lay out a host window: the launcher's column (or all of it), then the session pane(s) in the rest.
fn arrange(app: &AppHandle, host: &Window) {
    let Some(view) = launcher(app) else { return };
    let mode = match state(app).0.lock().unwrap().as_ref() {
        Some(d) if d.host == host.label() => d.mode,
        _ => return,
    };
    let Ok(size) = host.inner_size() else { return };
    let (w, h) = (size.width as i32, size.height as i32);
    let col = if mode == Mode::Full { w } else { col_px(host) };
    bounds(&view, (0, 0, col, h));
    for other in host.webviews().into_iter().filter(|v| v.label() != LABEL) {
        if mode == Mode::Full { let _ = other.hide(); } else { let _ = other.show(); }
    }
    if let Some(id) = solo(host) {
        if let Some(pane) = app.get_webview(&format!("{PANE}{id}")) {
            let _ = pane.set_auto_resize(false);
            if mode == Mode::Beside { bounds(&pane, (col, 0, w, h)); }
        }
    } else {
        crate::dock::relayout(host); // a frame: its header and tiles move right of the column
    }
}

/// Give a host its panes back, full width.
fn release(app: &AppHandle, host: &Window) {
    let Ok(size) = host.inner_size() else { return };
    for other in host.webviews().into_iter().filter(|v| v.label() != LABEL) { let _ = other.show(); }
    if let Some(id) = solo(host) {
        if let Some(pane) = app.get_webview(&format!("{PANE}{id}")) {
            bounds(&pane, (0, 0, size.width as i32, size.height as i32));
            let _ = pane.set_auto_resize(true);
        }
    } else {
        crate::dock::relayout(host);
    }
}

#[derive(Clone, Serialize)]
struct Look { mode: Option<Mode>, session: String }

fn tell(app: &AppHandle) {
    let (mode, host) = match state(app).0.lock().unwrap().as_ref() {
        Some(d) => (Some(d.mode), d.host.clone()),
        None => (None, String::new()),
    };
    let session = host.strip_prefix(PREFIX).and_then(|id| id.parse::<u32>().ok())
        .and_then(|id| app.state::<crate::session::Sessions>().get(id))
        .map(|s| format!("{} · {}", s.info.engine, s.info.profile))
        .unwrap_or_else(|| if host.is_empty() { String::new() } else { "sessions".into() });
    let _ = app.emit_to(LABEL, "panel", Look { mode, session });
}

/// Dock the launcher into `host` (or switch its mode there).
pub fn open(app: &AppHandle, host: &Window, mode: Mode) {
    if crate::sizes::folded() || launcher(app).is_none() {
        return;
    }
    if host.is_minimized().unwrap_or(false) { let _ = host.unminimize(); }
    let here = state(app).0.lock().unwrap().as_ref().map(|d| d.host == host.label());
    if here == Some(false) { go_home(app, false); }
    let Some(view) = launcher(app) else { return };
    if here != Some(true) {
        let home_shown = home(app).is_some_and(|w| w.is_visible().unwrap_or(false));
        if view.reparent(host).is_err() { return; }
        let _ = view.set_auto_resize(false);
        *state(app).0.lock().unwrap() = Some(Docked { host: host.label().into(), mode, grew: None, grown: false, home_shown });
        if let Some(w) = home(app) { let _ = w.hide(); }
        if let Ok(h) = host.hwnd() { crate::gate::MAIN.store(h.0 as isize, std::sync::atomic::Ordering::Relaxed); }
    }
    let grow = {
        let mut g = state(app).0.lock().unwrap();
        let d = g.as_mut().unwrap();
        d.mode = mode;
        let now = mode == Mode::Beside && !d.grown && !host.is_maximized().unwrap_or(false);
        if mode == Mode::Beside { d.grown = true; }
        now
    };
    if grow {
        // The window grows on its left by the column, so the terminal keeps its place and its size on
        // screen (no PTY resize). No room on the left: it moves right. Wider than the screen: the terminal
        // gives up width, once.
        if let Ok(h) = host.hwnd() {
            let vis = crate::session::visible_rect(h.0 as isize);
            let col = col_px(host).max((COL * host.scale_factor().unwrap_or(1.0)) as i32);
            let to = crate::sizes::on_screen((vis.0 - col, vis.1, vis.2, vis.3));
            set_visible_rect(host, to);
            if let Some(d) = state(app).0.lock().unwrap().as_mut() { d.grew = Some((vis, to)); }
        }
    }
    arrange(app, host);
    let _ = host.set_focus();
    let _ = view.set_focus();
    tell(app);
}

/// The launcher goes home. `show`: show the home window even if it was hidden before.
pub fn go_home(app: &AppHandle, show: bool) {
    let Some(d) = state(app).0.lock().unwrap().take() else { return };
    let Some(h) = home(app) else { return };
    if let Some(view) = launcher(app) {
        if view.window().label() != LABEL && view.reparent(&h).is_ok() {
            if let Ok(size) = h.inner_size() { bounds(&view, (0, 0, size.width as i32, size.height as i32)); }
            let _ = view.set_auto_resize(true);
        }
    } else {
        make_launcher(&h); // lost with a window that closed under it: never leave Reidcc without one
    }
    if let Ok(hh) = h.hwnd() { crate::gate::MAIN.store(hh.0 as isize, std::sync::atomic::Ordering::Relaxed); }
    if let Some(host) = app.get_window(&d.host) {
        release(app, &host);
        if let (Some((was, to)), Ok(hw)) = (d.grew, host.hwnd()) {
            let vis = crate::session::visible_rect(hw.0 as isize);
            // untouched since it grew: exactly where it was (also when the screen edge pushed it right);
            // moved or resized meanwhile: it gives back the column's width on its left
            let back = if vis == to { was } else { (vis.0 + (to.2 - to.0) - (was.2 - was.0), vis.1, vis.2, vis.3) };
            if !host.is_maximized().unwrap_or(false) && back.0 < back.2 { set_visible_rect(&host, back); }
        }
        focus_panes(&host);
    }
    if (show || d.home_shown) && !crate::sizes::folded() {
        let _ = h.show();
        let _ = h.set_focus();
    }
    tell(app);
}

fn focus_panes(host: &Window) {
    let _ = host.set_focus();
    if let Some(v) = host.webviews().into_iter().filter(|v| v.label().starts_with(PANE)).last() {
        let _ = v.set_focus();
    }
}

/// A window that holds the launcher is about to go: the launcher goes home first, or it goes with it.
pub fn leaving(app: &AppHandle, window: &Window) {
    let here = state(app).0.lock().unwrap().as_ref().is_some_and(|d| d.host == window.label());
    if here { go_home(app, false); }
}

pub fn docked_in(app: &AppHandle) -> Option<String> {
    state(app).0.lock().unwrap().as_ref().map(|d| d.host.clone())
}

/// The launcher's page in `home`, filling it (at start, and if it was ever lost).
pub fn make_launcher(home: &Window) -> Option<Webview> {
    let mut b = tauri::webview::WebviewBuilder::new(LABEL, tauri::WebviewUrl::App("index.html".into()))
        .background_color(tauri::window::Color(4, 4, 4, 255))
        .auto_resize();
    if let Some(d) = crate::WEBVIEW_DIR.get() { b = b.data_directory(d.clone()); }
    let size = home.inner_size().ok()?;
    home.add_child(b, PhysicalPosition::new(0, 0), size).ok()
}

pub fn window_event(window: &Window, event: &WindowEvent) {
    let app = window.app_handle();
    match event {
        WindowEvent::CloseRequested { .. } => leaving(app, window),
        WindowEvent::Resized(_) | WindowEvent::ScaleFactorChanged { .. } => {
            if docked_in(app).as_deref() == Some(window.label()) { arrange(app, window); }
        }
        WindowEvent::Destroyed => {
            let gone = state(app).0.lock().unwrap().as_ref().is_some_and(|d| d.host == window.label());
            if gone { go_home(app, true); }
        }
        _ => {}
    }
}

/// From a session page (RC, Alt+1/2) or the launcher (its keys and its `←`):
/// `toggle` (closed → beside → full → closed), `beside`, `full`, `close` (the page slides out first),
/// `home` (now).
#[tauri::command]
pub fn panel(app: AppHandle, webview: Webview, want: String) {
    let host = webview.window();
    if host.label() == LABEL && webview.label() == LABEL && want != "home" {
        return; // at home already: nothing to dock into
    }
    let cur = state(&app).0.lock().unwrap().as_ref().filter(|d| d.host == host.label()).map(|d| d.mode);
    let next = match (want.as_str(), cur) {
        ("toggle", None) | ("beside", _) => Some(Mode::Beside),
        ("toggle", Some(Mode::Beside)) | ("full", _) => Some(Mode::Full),
        ("toggle", Some(Mode::Full)) | ("close", _) => None,
        ("home", _) => { go_home(&app, false); return; }
        _ => return,
    };
    match next {
        Some(m) => open(&app, &host, m),
        None if cur.is_some() => { let _ = app.emit_to(LABEL, "panel-leave", ()); }
        None => {}
    }
}

/// The launcher's own bar: drag, minimise, maximise and close the window it's in. No close while docked:
/// closing a session window ends the session, and that stays the session bar's ×.
#[tauri::command]
pub fn launcher_control(webview: Webview, action: String) {
    let w = webview.window();
    match action.as_str() {
        "drag" => { let _ = w.start_dragging(); }
        "min" => { let _ = w.minimize(); }
        "max" => {
            if w.is_maximized().unwrap_or(false) { let _ = w.unmaximize(); } else { let _ = w.maximize(); }
        }
        "close" if w.label() == LABEL => { let _ = w.close(); }
        _ => {}
    }
}
