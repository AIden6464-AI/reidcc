//! The launcher's sizes (vision\SPEC-vision-v1.md §1): the window size is the mode. The page picks
//! its layout from its own size; this file has the preset sizes Alt+1/2 jump to, the eased resize
//! between them, where a session window opens when the launcher is smaller than main, and the pod.
//! Reid's names (2026-11-22): main the wide layout, medium the form, small folder / sessions / combos.
//!
//! The pod is its own window ("pod", ui\pod.html): borderless and per-pixel transparent, so the
//! desktop shows outside the capsule. The launcher's window has a themed title bar and an opaque frame
//! that a transparent window would put at risk, so folding hides it and shows the pod where it was,
//! and unfolding does the reverse.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;
use std::time::{Duration, Instant};
use tauri::{AppHandle, Emitter, Manager, WebviewWindow, Window, WindowEvent};
use windows_sys::Win32::UI::WindowsAndMessaging::{SetWindowPos, SWP_NOACTIVATE, SWP_NOSIZE, SWP_NOZORDER};

/// Main: the wide layout's size (logical px), set at start (its height depends on the screen), and the
/// smallest size it fits in.
pub static MAIN: OnceLock<(f64, f64)> = OnceLock::new();
pub static MAIN_MIN: OnceLock<(f64, f64)> = OnceLock::new();
/// Small (was medium): the spec said "~520×420"; Reid: "The medium is to medium can we make it simi-mini" (2026-11-21).
/// 400 tall since rigs (2026-11-24): two rigs show under three sessions and the combos.
pub const SMALL: (f64, f64) = (380.0, 400.0);
/// Medium, the form: the old launcher's `geometry("500x800")` (SPEC-form.md).
pub const MEDIUM: (f64, f64) = (500.0, 800.0);
/// The settings page's start size, a reid.json value made safe: "main", "medium" or "small".
pub fn start_size(v: &str) -> &'static str {
    match v { "medium" => "medium", "small" => "small", _ => "main" }
}
/// The smallest the launcher goes; the page folds it into the pod below 340 x 240.
pub const MIN: (f64, f64) = (280.0, 180.0);
/// The pod: a capsule this tall, at least this wide (it grows with its slots).
pub const POD: (f64, f64) = (320.0, 64.0);
static FOLDED: AtomicBool = AtomicBool::new(false);

/// The launcher is folded into the pod (it's hidden; the pod stands in for it).
pub fn folded() -> bool {
    FOLDED.load(Ordering::Relaxed)
}
/// The design doc's motion: 120–180 ms, cubic-bezier(0.16, 1, 0.3, 1), no bounce.
const MS: f64 = 160.0;

fn main_size() -> (f64, f64) {
    *MAIN.get().unwrap_or(&(1000.0, 880.0))
}

/// cubic-bezier(0.16, 1, 0.3, 1) at time `x` (0..1).
fn ease(x: f64) -> f64 {
    let (x1, y1, x2, y2) = (0.16, 1.0, 0.3, 1.0);
    let at = |t: f64, a: f64, b: f64| 3.0 * a * t * (1.0 - t).powi(2) + 3.0 * b * t * t * (1.0 - t) + t.powi(3);
    let (mut lo, mut hi) = (0.0, 1.0);
    for _ in 0..30 {
        let mid = (lo + hi) / 2.0;
        if at(mid, x1, x2) < x { lo = mid } else { hi = mid }
    }
    at((lo + hi) / 2.0, y1, y2)
}

fn work_area(r: (i32, i32, i32, i32)) -> (i32, i32, i32, i32) {
    use windows_sys::Win32::Foundation::RECT;
    use windows_sys::Win32::Graphics::Gdi::{GetMonitorInfoW, MonitorFromRect, MONITORINFO, MONITOR_DEFAULTTONEAREST};
    let raw = RECT { left: r.0, top: r.1, right: r.2, bottom: r.3 };
    let mut info: MONITORINFO = unsafe { std::mem::zeroed() };
    info.cbSize = std::mem::size_of::<MONITORINFO>() as u32;
    if unsafe { GetMonitorInfoW(MonitorFromRect(&raw, MONITOR_DEFAULTTONEAREST), &mut info) } == 0 {
        return r;
    }
    let w = info.rcWork;
    (w.left, w.top, w.right, w.bottom)
}

/// `r` moved (not shrunk, unless it's bigger) so it's all on its monitor's work area.
fn inside(r: (i32, i32, i32, i32), work: (i32, i32, i32, i32)) -> (i32, i32, i32, i32) {
    let (w, h) = ((r.2 - r.0).min(work.2 - work.0), (r.3 - r.1).min(work.3 - work.1));
    let l = r.0.clamp(work.0, work.2 - w);
    let t = r.1.clamp(work.1, work.3 - h);
    (l, t, l + w, t + h)
}

/// Where a session window opens: over the launcher, at least main's size (centred on the launcher when
/// it's smaller), on screen. Physical px, visible frame.
pub fn session_rect(launcher: (i32, i32, i32, i32), scale: f64) -> (i32, i32, i32, i32) {
    let (fw, fh) = main_size();
    let (w, h) = ((launcher.2 - launcher.0).max((fw * scale) as i32), (launcher.3 - launcher.1).max((fh * scale) as i32));
    if (w, h) == (launcher.2 - launcher.0, launcher.3 - launcher.1) {
        return launcher;
    }
    let (cx, cy) = ((launcher.0 + launcher.2) / 2, (launcher.1 + launcher.3) / 2);
    inside((cx - w / 2, cy - h / 2, cx - w / 2 + w, cy - h / 2 + h), work_area(launcher))
}

/// The window rect (`from`, Windows' invisible edges included) grown by `dw` x `dh`, its visible frame
/// (`vis`) kept on the work area: moved, and shrunk when it's bigger than the screen.
fn resized(from: (i32, i32, i32, i32), vis: (i32, i32, i32, i32), dw: i32, dh: i32,
           work: (i32, i32, i32, i32)) -> (i32, i32, i32, i32) {
    let t = inside((vis.0, vis.1, vis.2 + dw, vis.3 + dh), work);
    (t.0 - (vis.0 - from.0), t.1 - (vis.1 - from.1), t.2 + (from.2 - vis.2), t.3 + (from.3 - vis.3))
}

/// Alt+1 main, Alt+2 small: ease the launcher to that size, its top-left corner staying put unless
/// that would put it off screen.
#[tauri::command]
pub fn set_size(app: AppHandle, size: String) {
    let Some(w) = app.get_webview_window("main") else { return };
    let (lw, lh) = match size.as_str() {
        "main" => main_size(),
        "small" => SMALL,
        _ => return,
    };
    let (Ok(hwnd), Ok(scale), Ok(inner)) = (w.hwnd(), w.scale_factor(), w.inner_size()) else { return };
    if w.is_maximized().unwrap_or(false) {
        let _ = w.unmaximize();
    }
    let h = hwnd.0 as isize;
    let from = crate::gate::window_rect(h as _); // the whole window, Windows' invisible edges included
    // the same frame around the new inner size
    let (dw, dh) = ((lw * scale).round() as i32 - inner.width as i32, (lh * scale).round() as i32 - inner.height as i32);
    let vis = crate::session::visible_rect(h);
    let to = resized(from, vis, dw, dh, work_area(vis));
    std::thread::spawn(move || {
        let t0 = Instant::now();
        loop {
            let x = (t0.elapsed().as_secs_f64() * 1000.0 / MS).min(1.0);
            let k = ease(x);
            let lerp = |a: i32, b: i32| a + ((b - a) as f64 * k).round() as i32;
            let (l, t, r, b) = (lerp(from.0, to.0), lerp(from.1, to.1), lerp(from.2, to.2), lerp(from.3, to.3));
            unsafe { SetWindowPos(h as _, std::ptr::null_mut(), l, t, r - l, b - t, SWP_NOZORDER | SWP_NOACTIVATE) };
            if x >= 1.0 {
                break;
            }
            std::thread::sleep(Duration::from_millis(8));
        }
    });
}

fn pod(app: &AppHandle) -> Option<WebviewWindow> {
    if let Some(p) = app.get_webview_window("pod") {
        return Some(p);
    }
    let mut b = tauri::WebviewWindowBuilder::new(app, "pod", tauri::WebviewUrl::App("pod.html".into()))
        .title(concat!("Reidcc ", env!("CARGO_PKG_VERSION")))
        .inner_size(POD.0, POD.1)
        .decorations(false)
        .transparent(true)
        .shadow(false) // a borderless window's shadow is a rectangle around the capsule
        .resizable(false)
        .maximizable(false)
        .theme(Some(tauri::Theme::Dark))
        .visible(false);
    if let Some(d) = crate::WEBVIEW_DIR.get() {
        b = b.data_directory(d.clone());
    }
    if let Some(ico) = crate::asset("reidcc.ico").and_then(|p| std::fs::read(p).ok()) {
        if let Ok(img) = tauri::image::Image::from_bytes(&ico) {
            b = b.icon(img.to_owned()).ok()?;
        }
    }
    b.build().ok()
}

/// Fold the launcher into the pod, at the launcher's top-left corner. `drag`: asked because the window
/// was dragged under the threshold; not while the mouse button is still down (it's still being dragged).
/// Async: the first fold makes the pod's window, which a main-thread command can't.
#[tauri::command]
pub async fn pod_fold(app: AppHandle, drag: bool) -> bool {
    use windows_sys::Win32::UI::Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON};
    if drag && unsafe { GetAsyncKeyState(i32::from(VK_LBUTTON)) } < 0 {
        return false;
    }
    let (Some(main), Some(pod)) = (app.get_webview_window("main"), pod(&app)) else { return false };
    let Ok(h) = main.hwnd() else { return false };
    let vis = crate::session::visible_rect(h.0 as isize);
    let scale = main.scale_factor().unwrap_or(1.0);
    let (pw, ph) = ((POD.0 * scale) as i32, (POD.1 * scale) as i32);
    let at = inside((vis.0, vis.1, vis.0 + pw, vis.1 + ph), work_area(vis));
    let _ = pod.set_position(tauri::PhysicalPosition::new(at.0, at.1));
    FOLDED.store(true, Ordering::Relaxed);
    let _ = pod.emit_to("pod", "pod-shown", ());
    let _ = pod.show();
    let _ = pod.set_focus();
    let _ = main.hide();
    true
}

/// Unfold the pod back into the launcher at `size` (main or small), from where the pod is.
#[tauri::command]
pub async fn pod_unfold(app: AppHandle, size: String) {
    let (Some(main), Some(pod)) = (app.get_webview_window("main"), app.get_webview_window("pod")) else { return };
    let (Ok(mh), Ok(ph)) = (main.hwnd(), pod.hwnd()) else { return };
    let (mh, at) = (mh.0 as isize, crate::gate::window_rect(ph.0 as _));
    // the launcher's visible frame to the pod's corner (its window rect has invisible edges)
    let (outer, vis) = (crate::gate::window_rect(mh as _), crate::session::visible_rect(mh));
    unsafe {
        SetWindowPos(mh as _, std::ptr::null_mut(), at.0 - (vis.0 - outer.0), at.1 - (vis.1 - outer.1), 0, 0,
                     SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOSIZE);
    }
    FOLDED.store(false, Ordering::Relaxed);
    let _ = main.show();
    let _ = main.set_focus();
    let _ = pod.hide();
    set_size(app, size);
}

/// The pod's width for its slots (logical px); its height stays.
#[tauri::command]
pub fn pod_fit(app: AppHandle, width: f64) {
    if let Some(p) = app.get_webview_window("pod") {
        // grows sideways with its slots, kept on the screen it's on (no frame: outer = visible)
        let (Ok(pos), Ok(scale)) = (p.outer_position(), p.scale_factor()) else { return };
        let (w, h) = ((width.max(POD.0) * scale).round() as i32, (POD.1 * scale).round() as i32);
        let r = (pos.x, pos.y, pos.x + w, pos.y + h);
        let r = inside(r, work_area(r));
        let _ = p.set_size(tauri::PhysicalSize::new((r.2 - r.0) as u32, (r.3 - r.1) as u32));
        if (r.0, r.1) != (pos.x, pos.y) {
            let _ = p.set_position(tauri::PhysicalPosition::new(r.0, r.1));
        }
    }
}

/// Move the pod with the mouse (the press is already down).
#[tauri::command]
pub fn pod_drag(window: Window) {
    let _ = window.start_dragging();
}

/// The pod stands in for the launcher: closing it (Alt+F4) closes the launcher, and the launcher
/// going takes the hidden pod with it, so nothing invisible keeps Reidcc running.
pub fn window_event(window: &Window, event: &WindowEvent) {
    let app = window.app_handle();
    match (window.label(), event) {
        ("pod", WindowEvent::CloseRequested { api, .. }) => {
            api.prevent_close();
            if let Some(m) = app.get_webview_window("main") {
                let _ = m.close();
            }
        }
        ("main", WindowEvent::Destroyed) => {
            if let Some(p) = app.get_webview_window("pod") {
                let _ = p.destroy();
            }
        }
        _ => {}
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ease_starts_fast_and_lands_without_bounce() {
        assert!(ease(0.0).abs() < 1e-6 && (ease(1.0) - 1.0).abs() < 1e-6);
        assert!(ease(0.25) > 0.6); // most of the way early
        let mut last = 0.0;
        for i in 0..=100 {
            let y = ease(i as f64 / 100.0);
            assert!(y >= last - 1e-9 && y <= 1.0 + 1e-9); // never past the end, never back
            last = y;
        }
    }

    #[test]
    fn a_small_launcher_opens_sessions_at_full_size_on_screen() {
        let work = (0, 0, 1920, 1040);
        let r = inside((1700, 900, 2700, 1780), work);
        assert_eq!(r, (920, 160, 1920, 1040));
        let r = inside((-50, 10, 950, 890), work);
        assert_eq!(r.0, 0);
    }

    #[test]
    fn full_on_a_scaled_screen_shrinks_to_fit_the_work_area() {
        // small (380 x 320) at 150%, 7 px invisible edges left/right/bottom; main 1000 x 880 -> 1500 x 1320
        let (vis, from, work) = ((100, 100, 670, 580), (93, 100, 677, 587), (0, 0, 1920, 1032));
        let to = resized(from, vis, 1500 - 570, 1320 - 480, work);
        assert_eq!(to, (93, 0, 1607, 1039)); // visible frame (100, 0, 1600, 1032): on screen, above the taskbar
    }
}
