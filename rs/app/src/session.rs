//! Reidcc session windows (vision\SPEC-vision-v1.md §2): open gate opens the real engine in a Reidcc
//! window instead of Windows Terminal. The session runs `reid.exe <profile>` in a ConPTY (portable-pty);
//! ui\session.html draws it with xterm.js under the Telemetry Bar (design doc §5, Zone 1).

use portable_pty::{native_pty_system, ChildKiller, CommandBuilder, MasterPty, PtySize};
use serde::Serialize;
use serde_json::Value;
use std::collections::HashMap;
use std::io::{Read, Write};
use std::sync::atomic::{AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tauri::ipc::Channel;
use tauri::{AppHandle, Manager, PhysicalPosition};

pub const PREFIX: &str = "session-";
pub const PANE: &str = "pane-";
pub const CANVAS: tauri::window::Color = tauri::window::Color(4, 4, 4, 255);

/// What the page hears from its session, in order.
#[derive(Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Msg {
    Data { text: String },
    /// the session ended; `back` after /reid
    Exit { rc: i32, back: bool },
}

#[derive(Clone, Serialize)]
pub struct Info {
    pub engine: String,
    pub profile: String,
    pub folder: String,
    pub persona: String,
    /// ms since the session started (the page's elapsed clock)
    pub elapsed_ms: u64,
}

#[derive(Default)]
struct Out {
    chan: Option<Channel<Msg>>,
    pending: Vec<Msg>,
    ended: bool,
    /// the exit code once it ended
    rc: Option<i32>,
}

impl Out {
    fn send(&mut self, m: Msg) {
        match &self.chan {
            Some(c) => {
                let _ = c.send(m);
            }
            None => self.pending.push(m), // the hidden page hasn't attached yet
        }
    }
}

pub struct Sess {
    pub(crate) info: Info,
    /// the real folder it runs in (info.folder is the shown one)
    cwd: String,
    started: Instant,
    file: String,
    master: Mutex<Box<dyn MasterPty + Send>>,
    writer: Mutex<Box<dyn Write + Send>>,
    killer: Mutex<Box<dyn ChildKiller + Send + Sync>>,
    pid: Option<u32>,
    out: Arc<Mutex<Out>>,
}

#[derive(Default)]
pub struct Sessions {
    map: Mutex<HashMap<u32, Arc<Sess>>>,
    next: AtomicU32,
}

/// Text from the pty: everything but a UTF-8 sequence split at the end of the chunk.
fn take_text(carry: &mut Vec<u8>) -> String {
    let mut cut = carry.len();
    for back in 1..=carry.len().min(3) {
        let b = carry[carry.len() - back];
        if b & 0xC0 == 0x80 {
            continue; // continuation byte: keep looking for the lead
        }
        let need = if b >= 0xF0 { 4 } else if b >= 0xE0 { 3 } else if b >= 0xC0 { 2 } else { 1 };
        if need > back {
            cut = carry.len() - back;
        }
        break;
    }
    let rest = carry.split_off(cut);
    let s = String::from_utf8_lossy(carry).into_owned();
    *carry = rest;
    s
}

/// The launcher's visible frame in physical pixels (Windows' invisible resize border left out).
pub fn visible_rect(h: isize) -> (i32, i32, i32, i32) {
    use windows_sys::Win32::Foundation::RECT;
    use windows_sys::Win32::Graphics::Dwm::DwmGetWindowAttribute;
    let mut r = RECT { left: 0, top: 0, right: 0, bottom: 0 };
    let ok = unsafe { DwmGetWindowAttribute(h as _, 9, &mut r as *mut RECT as _, std::mem::size_of::<RECT>() as u32) };
    if ok != 0 {
        return crate::gate::window_rect(h as _); // DWMWA_EXTENDED_FRAME_BOUNDS unavailable
    }
    (r.left, r.top, r.right, r.bottom)
}

impl Sessions {
    pub fn get(&self, id: u32) -> Option<Arc<Sess>> {
        self.map.lock().unwrap().get(&id).cloned()
    }

    /// A rig's pane: the session's profile and real folder.
    pub fn leaf(&self, id: u32) -> Option<Value> {
        let s = self.get(id)?;
        Some(serde_json::json!({"profile": s.info.profile, "folder": s.cwd}))
    }

    /// Start `cmd` in a ConPTY and make its window, hidden, over `rect` (physical px). Returns the window.
    /// With `host` (a rig's frame and the pane's bounds in it) the page is made there instead: moving a
    /// WebView that's receiving output can drop a channel message, and the terminal then stalls for good.
    pub fn open(&self, app: &AppHandle, info: Info, cwd: &str, cmd: &[String], rect: (i32, i32, i32, i32),
                host: Option<(tauri::Window, (i32, i32, i32, i32))>) -> Result<tauri::Window, String> {
        let id = self.next.fetch_add(1, Ordering::Relaxed) + 1;
        let file = reidcc::py::join(&reidcc::py::gettempdir(), &[&format!("reidcc_session_{}_{id}.json", std::process::id())]);
        for f in [file.clone(), format!("{file}.end")] {
            let _ = std::fs::remove_file(f);
        }
        let (l, t, r, b) = rect;
        let sf = crate::panel::launcher_window(app).and_then(|w| w.scale_factor().ok()).unwrap_or(1.0);
        // a first guess at the grid (the page fits it exactly once it loads): 8x17 px cells at 100%
        let cols = (((r - l) as f64 / sf - 26.0) / 8.0).max(40.0) as u16;
        let rows = (((b - t) as f64 / sf - 36.0 - 26.0) / 17.0).max(10.0) as u16;
        let pair = native_pty_system().openpty(PtySize { rows, cols, pixel_width: 0, pixel_height: 0 })
            .map_err(|e| e.to_string())?;
        let mut cb = CommandBuilder::new(&cmd[0]);
        cb.args(&cmd[1..]);
        cb.cwd(cwd);
        cb.env("REIDCC_SESSION", &file);
        let mut child = pair.slave.spawn_command(cb).map_err(|e| e.to_string())?;
        drop(pair.slave);
        let reader = pair.master.try_clone_reader().map_err(|e| e.to_string())?;
        let writer = pair.master.take_writer().map_err(|e| e.to_string())?;
        let out = Arc::new(Mutex::new(Out::default()));
        let sess = Arc::new(Sess {
            info, cwd: cwd.to_string(), started: Instant::now(), file: file.clone(), master: Mutex::new(pair.master), writer: Mutex::new(writer),
            killer: Mutex::new(child.clone_killer()), pid: child.process_id(), out: out.clone(),
        });

        let o = out.clone();
        std::thread::spawn(move || {
            let (mut reader, mut buf, mut carry, mut held) = (reader, vec![0u8; 65536], Vec::new(), String::new());
            while let Ok(n) = reader.read(&mut buf) {
                if n == 0 {
                    break;
                }
                carry.extend_from_slice(&buf[..n]);
                let (text, h) = crate::recolor::recolor(&(std::mem::take(&mut held) + &take_text(&mut carry)));
                held = h; // a colour code cut off at the chunk's end
                if !text.is_empty() {
                    o.lock().unwrap().send(Msg::Data { text });
                }
            }
        });
        let o = out.clone();
        std::thread::spawn(move || {
            let mut rc = child.wait().map(|s| s.exit_code() as i32).unwrap_or(1);
            std::thread::sleep(Duration::from_millis(150)); // the last output is still on its way
            let end: Option<Value> = std::fs::read_to_string(format!("{file}.end")).ok().and_then(|t| serde_json::from_str(&t).ok());
            let back = end.as_ref().and_then(|e| e.get("back")).and_then(Value::as_bool).unwrap_or(false);
            if let Some(r) = end.as_ref().and_then(|e| e.get("rc")).and_then(Value::as_i64) {
                rc = r as i32;
            }
            let mut o = o.lock().unwrap();
            o.ended = true;
            o.rc = Some(rc);
            o.send(Msg::Exit { rc, back });
        });

        let title = format!("{} · {}", sess.info.engine, sess.info.profile);
        let mut wb = tauri::Window::builder(app, format!("{PREFIX}{id}"))
            .title(&title)
            .decorations(false)
            .position(l as f64 / sf, t as f64 / sf)
            .inner_size((r - l) as f64 / sf, (b - t) as f64 / sf)
            .min_inner_size(640.0, 400.0)
            .background_color(CANVAS)
            .theme(Some(tauri::Theme::Dark))
            .visible(false);
        if let Some(ico) = crate::asset("reidcc.ico").and_then(|p| std::fs::read(p).ok()) {
            if let Ok(img) = tauri::image::Image::from_bytes(&ico) {
                wb = wb.icon(img.to_owned()).map_err(|e| e.to_string())?;
            }
        }
        self.map.lock().unwrap().insert(id, sess.clone());
        match wb.build() {
            Ok(w) => {
                // Line its visible frame up with the launcher's exactly (the window rect has invisible edges).
                if let Ok(h) = w.hwnd() {
                    let h = h.0 as isize;
                    let (wl, wt, wr, wb) = crate::gate::window_rect(h as _);
                    let (fl, ft, fr, fb) = visible_rect(h);
                    let (x, y) = (l - (fl - wl), t - (ft - wt));
                    let (cx, cy) = ((r - l) + (fl - wl) + (wr - fr), (b - t) + (ft - wt) + (wb - fb));
                    unsafe {
                        windows_sys::Win32::UI::WindowsAndMessaging::SetWindowPos(h as _, std::ptr::null_mut(), x, y, cx, cy, 0x0004 | 0x0010);
                    }
                }
                let mut view = tauri::webview::WebviewBuilder::new(format!("{PANE}{id}"), tauri::WebviewUrl::App(format!("session.html?id={id}").into()))
                    .background_color(CANVAS);
                if host.is_none() {
                    view = view.auto_resize();
                }
                if let Some(d) = crate::WEBVIEW_DIR.get() {
                    view = view.data_directory(d.clone());
                }
                let size = w.inner_size().unwrap_or_else(|_| tauri::PhysicalSize::new((r - l) as u32, (b - t) as u32));
                let added = match &host {
                    Some((frame, (hl, ht, hr, hb))) => frame.add_child(view, PhysicalPosition::new(*hl, *ht),
                                                                       tauri::PhysicalSize::new((hr - hl).max(1) as u32, (hb - ht).max(1) as u32)),
                    None => w.add_child(view, PhysicalPosition::new(0, 0), size),
                };
                if let Err(e) = added {
                    let _ = w.destroy();
                    self.end(id);
                    return Err(e.to_string());
                }
                Ok(w)
            }
            Err(e) => {
                self.end(id);
                Err(e.to_string())
            }
        }
    }

    /// The window is gone: end the session if it's still running and clean up.
    pub fn end(&self, id: u32) {
        let Some(s) = self.map.lock().unwrap().remove(&id) else { return };
        // Off the main thread: taskkill takes a moment, and this runs from the window-closed event.
        std::thread::spawn(move || {
            if !s.out.lock().unwrap().ended {
                if let Some(pid) = s.pid {
                    use std::os::windows::process::CommandExt;
                    // reid.exe and the engine under it, like closing a Windows Terminal tab (before the
                    // kill below: /T needs reid.exe alive to find what's under it)
                    let _ = std::process::Command::new("taskkill").args(["/F", "/T", "/PID", &pid.to_string()])
                        .creation_flags(0x0800_0000).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null()).status();
                }
                let _ = s.killer.lock().unwrap().kill();
            }
            for f in [s.file.clone(), format!("{}.end", s.file)] {
                let _ = std::fs::remove_file(f);
            }
        });
    }
}

type S<'a> = tauri::State<'a, Sessions>;

/// The page is up: everything so far, then live output.
#[tauri::command]
pub fn sess_attach(st: S, id: u32, chan: Channel<Msg>) -> Option<Info> {
    let s = st.get(id)?;
    let mut o = s.out.lock().unwrap();
    for m in std::mem::take(&mut o.pending) {
        let _ = chan.send(m);
    }
    o.chan = Some(chan);
    let mut info = s.info.clone();
    info.elapsed_ms = s.started.elapsed().as_millis() as u64;
    Some(info)
}

#[tauri::command]
pub fn sess_write(st: S, id: u32, data: String) {
    if let Some(s) = st.get(id) {
        let mut w = s.writer.lock().unwrap();
        let _ = w.write_all(data.as_bytes());
        let _ = w.flush();
    }
}

#[tauri::command]
pub fn sess_resize(st: S, id: u32, cols: u16, rows: u16) {
    if let Some(s) = st.get(id) {
        let _ = s.master.lock().unwrap().resize(PtySize { rows: rows.max(2), cols: cols.max(2), pixel_width: 0, pixel_height: 0 });
    }
}

/// What the statusline last wrote (context, limit and their detail), if anything.
#[tauri::command]
pub fn sess_meters(st: S, id: u32) -> Option<Value> {
    let s = st.get(id)?;
    serde_json::from_str(&std::fs::read_to_string(&s.file).ok()?).ok()
}

/// Close the window (the session ends with it). With a note, the launcher comes forward and says it.
#[tauri::command]
pub fn sess_close(app: AppHandle, id: u32, note: Option<String>) {
    if let Some(w) = app.get_webview(&format!("{PANE}{id}")).map(|v| v.window()) {
        crate::panel::leaving(&app, &w); // docked here: the launcher goes home before the window goes
    }
    if let Some(note) = note.filter(|_| !crate::sizes::folded()) { // folded: the pod's slot just goes
        if let Some(m) = crate::panel::home(&app) {
            let _ = m.unminimize();
            let _ = m.show();
            let _ = m.set_focus();
            crate::gate::bring_front(crate::gate::main_hwnd()); // past Windows' foreground lock, like the gate's hand-off
            let _ = tauri::Emitter::emit_to(&app, "main", "session-note", note);
        }
    }
    let handle = app.clone();
    let _ = app.run_on_main_thread(move || crate::dock::close_pane(&handle, id));
}

/// The session ended by itself (/reid, Codex's /quit, a clean exit): the window you were in turns into
/// Reidcc (SPEC-one-window.md fix 2). Alone, the launcher's window takes its place and size and the session
/// window goes; in a frame, the pane goes and the launcher docks beside what's left.
#[tauri::command]
pub fn sess_back(app: AppHandle, id: u32, note: String) {
    let Some(host) = app.get_webview(&format!("{PANE}{id}")).map(|v| v.window()) else { return };
    if crate::sizes::folded() {
        return sess_close(app, id, None); // the pod stands in for the launcher: its slot just goes
    }
    // "session-group-N" starts with PREFIX too: a solo window's label is PREFIX plus a number
    if host.label().strip_prefix(PREFIX).and_then(|n| n.parse::<u32>().ok()).is_none() {
        let mates: Vec<String> = host.webviews().into_iter().map(|v| v.label().to_string())
            .filter(|l| l.starts_with(PANE) && *l != format!("{PANE}{id}")).collect();
        crate::panel::leaving(&app, &host);
        crate::dock::close_pane(&app, id);
        if let Some(w) = mates.first().and_then(|l| app.get_webview(l)).map(|v| v.window()) {
            crate::panel::open(&app, &w, crate::panel::Mode::Beside);
        }
        let _ = tauri::Emitter::emit_to(&app, "main", "session-note", note);
        return;
    }
    crate::panel::go_home(&app, false);
    let Some(home) = crate::panel::home(&app) else { return sess_close(app, id, Some(note)) };
    if host.is_maximized().unwrap_or(false) {
        let _ = home.maximize();
    } else if let (Ok(hh), Ok(sh)) = (home.hwnd(), host.hwnd()) {
        if home.is_maximized().unwrap_or(false) { let _ = home.unmaximize(); }
        let (l, t, r, b) = crate::gate::window_rect(sh.0 as _); // both borderless: same window rect, same frame
        unsafe {
            windows_sys::Win32::UI::WindowsAndMessaging::SetWindowPos(hh.0 as _, std::ptr::null_mut(), l, t, r - l, b - t, 0x0004 | 0x0010);
        }
    }
    let _ = home.show();
    let _ = home.set_focus();
    crate::gate::bring_front(crate::gate::main_hwnd());
    let _ = tauri::Emitter::emit_to(&app, "main", "session-note", note);
    crate::dock::close_pane(&app, id);
}

/// One running (or just ended) session, for the small size's session list.
#[derive(Serialize)]
pub struct Row {
    id: u32,
    engine: String,
    profile: String,
    folder: String,
    elapsed_ms: u64,
    /// None while it runs
    rc: Option<i32>,
    /// context % and limit % from the statusline (Claude), once it has written them
    context: Option<i64>,
    limit: Option<i64>,
}

#[tauri::command]
pub fn sess_list(st: S) -> Vec<Row> {
    let map = st.map.lock().unwrap();
    let mut rows: Vec<Row> = map.iter().map(|(&id, s)| {
        let m: Option<Value> = std::fs::read_to_string(&s.file).ok().and_then(|t| serde_json::from_str(&t).ok());
        let pct = |k: &str| m.as_ref().and_then(|m| m.get(k)).and_then(Value::as_i64);
        Row {
            id, engine: s.info.engine.clone(), profile: s.info.profile.clone(), folder: s.info.folder.clone(),
            elapsed_ms: s.started.elapsed().as_millis() as u64, rc: s.out.lock().unwrap().rc,
            context: pct("context"), limit: pct("limit"),
        }
    }).collect();
    rows.sort_by_key(|r| r.id);
    rows
}

/// Bring a session's window forward (its frame, when it's snapped into one).
#[tauri::command]
pub fn sess_focus(app: AppHandle, id: u32) {
    let Some(w) = app.get_webview(&format!("{PANE}{id}")).map(|v| v.window()) else { return };
    let _ = w.unminimize();
    let _ = w.show();
    let _ = w.set_focus();
    if let Ok(h) = w.hwnd() {
        crate::gate::bring_front(h.0 as _);
    }
}

/// Clipboard text for paste (WebView2 asks before letting a page read the clipboard).
#[tauri::command]
pub fn clip_text() -> String {
    use windows_sys::Win32::System::DataExchange::{CloseClipboard, GetClipboardData, OpenClipboard};
    use windows_sys::Win32::System::Memory::{GlobalLock, GlobalUnlock};
    let mut out = String::new();
    unsafe {
        if OpenClipboard(std::ptr::null_mut()) == 0 {
            return out;
        }
        let h = GetClipboardData(13); // CF_UNICODETEXT
        if !h.is_null() {
            let p = GlobalLock(h as _) as *const u16;
            if !p.is_null() {
                let mut n = 0;
                while *p.add(n) != 0 {
                    n += 1;
                }
                out = String::from_utf16_lossy(std::slice::from_raw_parts(p, n));
                GlobalUnlock(h as _);
            }
        }
        CloseClipboard();
    }
    out
}

#[cfg(test)]
mod tests {
    use super::take_text;

    #[test]
    fn split_utf8_waits_for_the_rest() {
        let mut c = "ab·".as_bytes().to_vec();
        c.pop(); // · is C2 B7: keep C2 for the next chunk
        assert_eq!(take_text(&mut c), "ab");
        assert_eq!(c, vec![0xC2]);
        c.push(0xB7);
        assert_eq!(take_text(&mut c), "·");
        assert!(c.is_empty());
    }
}
