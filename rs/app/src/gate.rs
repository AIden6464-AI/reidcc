//! The gate's Windows side (SPEC-gate.md): where the session window goes, launching it in
//! Windows Terminal, finding the new terminal window, keeping it hidden and the keyboard with the
//! launcher while the gate plays, and the hand-off. The frames and timing are in ui\src\gate.ts.

use std::collections::HashSet;
use std::sync::atomic::{AtomicIsize, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use windows_sys::Win32::Foundation::{BOOL, HWND, LPARAM, RECT};
use windows_sys::Win32::UI::Input::KeyboardAndMouse::{keybd_event, KEYEVENTF_KEYUP};
use windows_sys::Win32::UI::WindowsAndMessaging::{
    EnumWindows, GetClassNameW, GetForegroundWindow, GetWindowRect, IsWindowVisible, LockSetForegroundWindow,
    SetForegroundWindow, ShowWindow, LSFW_LOCK, LSFW_UNLOCK, SW_HIDE, SW_SHOW,
};

// Windows Terminal geometry, measured 2026-11-17 on WT 1.25 (default profile): a cell is 9x19 px, the
// window adds 49x65 px, and its frame sits 8 px left of --pos (invisible resize border).
pub const WT_CELL: (i32, i32) = (9, 19);
pub const WT_CHROME: (i32, i32) = (49, 65);
pub const WT_BORDER: i32 = 8;
pub const WT_CLASS: &str = "CASCADIA_HOSTING_WINDOW_CLASS";

/// The launcher's top-level window.
pub static MAIN: AtomicIsize = AtomicIsize::new(0);

pub fn main_hwnd() -> HWND {
    MAIN.load(Ordering::Relaxed) as HWND
}

pub fn window_rect(h: HWND) -> (i32, i32, i32, i32) {
    let mut r = RECT { left: 0, top: 0, right: 0, bottom: 0 };
    unsafe { GetWindowRect(h, &mut r) };
    (r.left, r.top, r.right, r.bottom)
}

/// Python's round(): halves go to the even neighbour.
fn py_round(x: f64) -> i32 {
    x.round_ties_even() as i32
}

/// Where the session window goes: over the launcher, at its size (wt --pos/--size values).
pub fn plan() -> (String, String) {
    let (l, t, r, b) = window_rect(main_hwnd());
    let cols = 40.max(py_round((r - l - WT_CHROME.0) as f64 / WT_CELL.0 as f64));
    let rows = 10.max(py_round((b - t - WT_CHROME.1) as f64 / WT_CELL.1 as f64));
    (format!("{},{}", l + WT_BORDER, t), format!("{cols},{rows}"))
}

unsafe extern "system" fn enum_cb(h: HWND, lp: LPARAM) -> BOOL {
    let out = &mut *(lp as *mut HashSet<isize>);
    let mut buf = [0u16; 64];
    let n = GetClassNameW(h, buf.as_mut_ptr(), 64);
    if n > 0 && String::from_utf16_lossy(&buf[..n as usize]) == WT_CLASS && IsWindowVisible(h) != 0 {
        out.insert(h as isize);
    }
    1
}

/// Visible Windows Terminal windows.
pub fn wt_windows() -> HashSet<isize> {
    let mut out: HashSet<isize> = HashSet::new();
    unsafe { EnumWindows(Some(enum_cb), &mut out as *mut _ as LPARAM) };
    out
}

/// While the gate plays, other apps can't take the foreground, so the new terminal opens without
/// grabbing the keyboard (keys go on skipping the gate).
pub fn lock_foreground(on: bool) {
    unsafe { LockSetForegroundWindow(if on { LSFW_LOCK } else { LSFW_UNLOCK }) };
}

/// 1 ms timer ticks while the gate plays (one begin per end).
pub fn fine_timer(on: bool) {
    use windows_sys::Win32::Media::{timeBeginPeriod, timeEndPeriod};
    unsafe {
        if on {
            timeBeginPeriod(1);
        } else {
            timeEndPeriod(1);
        }
    }
}

pub fn bring_front(h: HWND) {
    lock_foreground(false);
    unsafe {
        ShowWindow(h, SW_SHOW);
        SetForegroundWindow(h); // allowed while the launcher is the foreground app (it was just pressed)
        if GetForegroundWindow() != h {
            // Focus moved meanwhile: a tap of Alt lifts Windows' foreground lock for one switch.
            keybd_event(0x12, 0, 0, 0);
            keybd_event(0x12, 0, KEYEVENTF_KEYUP, 0);
            SetForegroundWindow(h);
        }
    }
}

/// One opening of the gate, shared by the page's commands and the window watcher.
#[derive(Default)]
pub struct GateState {
    pub active: bool,
    pub done: bool,
    pub uses_wt: bool,
    pub found: Option<isize>,
    pub hidden: bool,
    pub before: HashSet<isize>,
    pub t0: Option<Instant>,
    pub polling: bool,
    /// bumped on every opening, so an old watcher stops
    pub gen: u64,
}

pub type Shared = Arc<Mutex<GateState>>;

/// What the watcher tells the page.
pub enum Seen {
    /// the new terminal window exists (READY is real); `handed` when the gate was already skipped
    Found { handed: bool },
    /// 8 s and no window
    Timeout,
}

/// Watch for the new terminal window. While the gate plays it stays hidden: the session is already
/// starting behind it, and the window would otherwise cover the gate.
pub fn watch(state: Shared, notify: impl Fn(Seen) + Send + 'static) {
    let gen = {
        let mut g = state.lock().unwrap();
        if g.polling {
            return;
        }
        g.polling = true;
        g.gen
    };
    std::thread::spawn(move || loop {
        let elapsed;
        {
            let mut g = state.lock().unwrap();
            if g.gen != gen {
                g.polling = false;
                return;
            }
            elapsed = g.t0.map_or(0.0, |t| t.elapsed().as_secs_f64());
            if g.found.is_none() {
                let now = wt_windows();
                if let Some(&h) = now.difference(&g.before).next() {
                    g.found = Some(h);
                    if !g.active {
                        // skipped already: just bring it forward
                        hand_over_locked(&mut g);
                        g.polling = false;
                        drop(g);
                        notify(Seen::Found { handed: true });
                        return;
                    }
                    drop(g);
                    notify(Seen::Found { handed: false });
                    continue;
                } else if elapsed > 8.0 {
                    let active = g.active;
                    g.polling = false;
                    drop(g);
                    if active {
                        notify(Seen::Timeout);
                    }
                    return;
                }
            }
            if let (Some(h), true, false) = (g.found, g.active, g.done) {
                let h = h as HWND;
                unsafe {
                    if IsWindowVisible(h) != 0 {
                        // WT may show itself again while it starts up
                        ShowWindow(h, SW_HIDE);
                        g.hidden = true;
                    }
                    if GetForegroundWindow() == h {
                        // A hidden window can keep the keyboard: keys meant to skip would type into the
                        // session. Take it back (allowed: the press that opened the gate was the last input).
                        SetForegroundWindow(main_hwnd());
                    }
                }
            }
            if !(g.found.is_none() || (g.active && !g.done)) {
                g.polling = false;
                return;
            }
        }
        std::thread::sleep(Duration::from_millis(if elapsed < 2.0 { 10 } else { 50 }));
    });
}

pub fn hand_over_locked(g: &mut GateState) {
    if let Some(h) = g.found {
        bring_front(h as HWND);
        g.hidden = false;
    }
}

/// wt reads a bare ; as "next command", even inside an argument; \; is a plain ;
pub fn wt_args(plan: Option<&(String, String)>, name: &str, cwd: &str, cmd: &[String]) -> Vec<String> {
    let mut a: Vec<String> = vec!["-w".into(), "new".into()];
    if let Some((pos, size)) = plan {
        a.extend(["--pos".into(), pos.clone(), "--size".into(), size.clone()]);
    }
    a.push("new-tab".into());
    let tab = ["--title".to_string(), format!("Reidcc · {name}"), "-d".into(), cwd.to_string()];
    a.extend(tab.iter().chain(cmd.iter()).map(|x| x.replace(';', "\\;")));
    a
}

/// Start the session: Windows Terminal at `plan`, else a new console. (note, uses_wt)
pub fn launch(plan: Option<&(String, String)>, name: &str, cwd: &str, cmd: &[String]) -> std::io::Result<(String, bool)> {
    use std::os::windows::process::CommandExt;
    if let Some(wt) = reidcc::py::which("wt") {
        let args = wt_args(plan, name, cwd, cmd);
        std::process::Command::new(wt).raw_arg(reidcc::py::list2cmdline(&args)).spawn()?;
        return Ok(("Session open in Windows Terminal.".into(), true));
    }
    std::process::Command::new(&cmd[0]).raw_arg(reidcc::py::list2cmdline(&cmd[1..])).current_dir(cwd)
        .creation_flags(0x10).spawn()?; // CREATE_NEW_CONSOLE
    Ok(("Session open in a new window.".into(), false))
}
