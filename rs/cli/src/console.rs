//! The console calls the TUI makes, ported from what reid.py uses: msvcrt.getwch / kbhit (the
//! UCRT reads CONIN$ with the input mode at 0 for each key, so Ctrl+C arrives as a key),
//! getkey() on top of them, shutil.get_terminal_size, and input() for one line of text.

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::OnceLock;
use std::time::Duration;
use windows_sys::Win32::Foundation::{BOOL, GENERIC_READ, GENERIC_WRITE, HANDLE, INVALID_HANDLE_VALUE, TRUE};
use windows_sys::Win32::Storage::FileSystem::{CreateFileW, FILE_SHARE_READ, FILE_SHARE_WRITE, OPEN_EXISTING};
use windows_sys::Win32::System::Console::*;

/// Ctrl+C or Ctrl+Break while not reading a key: Python's KeyboardInterrupt.
pub struct Interrupt;

static INTERRUPTED: AtomicBool = AtomicBool::new(false);
static PUSHBACK: std::sync::Mutex<Option<u16>> = std::sync::Mutex::new(None);

unsafe extern "system" fn on_ctrl_c(kind: u32) -> BOOL {
    if kind == CTRL_C_EVENT || kind == CTRL_BREAK_EVENT {
        INTERRUPTED.store(true, Ordering::SeqCst);
        return TRUE;
    }
    0
}

/// Python turns Ctrl+C into KeyboardInterrupt instead of dying; the TUI does the same.
pub fn catch_ctrl_c() {
    unsafe { SetConsoleCtrlHandler(Some(on_ctrl_c), TRUE) };
}

/// Was Ctrl+C pressed since the last check? Clears it.
pub fn interrupted() -> bool {
    INTERRUPTED.swap(false, Ordering::SeqCst)
}

fn conin() -> HANDLE {
    static H: OnceLock<usize> = OnceLock::new();
    *H.get_or_init(|| {
        let name: Vec<u16> = "CONIN$\0".encode_utf16().collect();
        let h = unsafe {
            CreateFileW(name.as_ptr(), GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE,
                        std::ptr::null(), OPEN_EXISTING, 0, std::ptr::null_mut())
        };
        h as usize
    }) as HANDLE
}

// The UCRT's tables (getch.cpp): (scan code, regular, shift, ctrl, alt) as (lead, second).
type Code = (u16, u16);
const ENHANCED: [(u16, Code, Code, Code, Code); 12] = [
    (0x1c, (13, 0), (13, 0), (10, 0), (0, 166)),
    (0x35, (47, 0), (63, 0), (0, 149), (0, 164)),
    (0x47, (224, 71), (224, 71), (224, 119), (0, 151)),
    (0x48, (224, 72), (224, 72), (224, 141), (0, 152)),
    (0x49, (224, 73), (224, 73), (224, 134), (0, 153)),
    (0x4b, (224, 75), (224, 75), (224, 115), (0, 155)),
    (0x4d, (224, 77), (224, 77), (224, 116), (0, 157)),
    (0x4f, (224, 79), (224, 79), (224, 117), (0, 159)),
    (0x50, (224, 80), (224, 80), (224, 145), (0, 160)),
    (0x51, (224, 81), (224, 81), (224, 118), (0, 161)),
    (0x52, (224, 82), (224, 82), (224, 146), (0, 162)),
    (0x53, (224, 83), (224, 83), (224, 147), (0, 163)),
];

/// The normal-key table, for the keys without a character (F keys, the keypad's nav keys).
fn normal(scan: u16) -> Option<(Code, Code, Code, Code)> {
    Some(match scan {
        0x3b..=0x44 => { let n = scan - 0x3b; ((0, 59 + n), (0, 84 + n), (0, 94 + n), (0, 104 + n)) }
        0x57 => ((0, 133), (0, 135), (0, 137), (0, 139)),
        0x58 => ((0, 134), (0, 136), (0, 138), (0, 140)),
        0x47 => ((0, 71), (0, 0), (0, 119), (0, 0)),
        0x48 => ((0, 72), (0, 0), (0, 141), (0, 0)),
        0x49 => ((0, 73), (0, 0), (0, 132), (0, 0)),
        0x4b => ((0, 75), (0, 0), (0, 115), (0, 0)),
        0x4c => ((0, 76), (0, 0), (0, 143), (0, 0)),
        0x4d => ((0, 77), (0, 0), (0, 116), (0, 0)),
        0x4f => ((0, 79), (0, 0), (0, 117), (0, 0)),
        0x50 => ((0, 80), (0, 0), (0, 145), (0, 0)),
        0x51 => ((0, 81), (0, 0), (0, 118), (0, 0)),
        0x52 => ((0, 82), (0, 0), (0, 146), (0, 0)),
        0x53 => ((0, 83), (0, 0), (0, 147), (0, 0)),
        _ => return None,
    })
}

/// _getextendedkeycode
fn extended(k: &KEY_EVENT_RECORD) -> Option<Code> {
    let cks = k.dwControlKeyState;
    let alt = cks & (LEFT_ALT_PRESSED | RIGHT_ALT_PRESSED) != 0;
    let ctrl = cks & (LEFT_CTRL_PRESSED | RIGHT_CTRL_PRESSED) != 0;
    let shift = cks & SHIFT_PRESSED != 0;
    let pick = |r: Code, s: Code, c: Code, a: Code| if alt { a } else if ctrl { c } else if shift { s } else { r };
    if cks & ENHANCED_KEY != 0 {
        return ENHANCED.iter().find(|e| e.0 == k.wVirtualScanCode).map(|e| pick(e.1, e.2, e.3, e.4));
    }
    let (r, s, c, a) = normal(k.wVirtualScanCode)?;
    let code = pick(r, s, c, a);
    if (code.0 != 0 && code.0 != 224) || code.1 == 0 {
        return None;
    }
    Some(code)
}

/// msvcrt.getwch(): one UTF-16 unit; an extended key is 0 or 0xE0, then its code.
pub fn getwch() -> u16 {
    if let Some(c) = PUSHBACK.lock().unwrap().take() {
        return c;
    }
    let h = conin();
    let mut old = 0u32;
    unsafe {
        GetConsoleMode(h, &mut old);
        SetConsoleMode(h, 0);
    }
    let result = loop {
        let mut rec: INPUT_RECORD = unsafe { std::mem::zeroed() };
        let mut n = 0u32;
        if unsafe { ReadConsoleInputW(h, &mut rec, 1, &mut n) } == 0 || n == 0 {
            break 0xffff; // WEOF
        }
        if rec.EventType as u32 == KEY_EVENT as u32 {
            let k = unsafe { rec.Event.KeyEvent };
            if k.bKeyDown != 0 {
                let c = unsafe { k.uChar.UnicodeChar };
                if c != 0 {
                    break c;
                }
                if let Some((lead, second)) = extended(&k) {
                    *PUSHBACK.lock().unwrap() = Some(second);
                    break lead;
                }
            }
        }
    };
    unsafe { SetConsoleMode(h, old) };
    result
}

/// msvcrt.kbhit(): a key is waiting (doesn't consume it).
pub fn kbhit() -> bool {
    if PUSHBACK.lock().unwrap().is_some() {
        return true;
    }
    let h = conin();
    if h == INVALID_HANDLE_VALUE {
        return false;
    }
    let mut count = 0u32;
    if unsafe { GetNumberOfConsoleInputEvents(h, &mut count) } == 0 || count == 0 {
        return false;
    }
    let mut buf: Vec<INPUT_RECORD> = vec![unsafe { std::mem::zeroed() }; count as usize];
    let mut n = 0u32;
    if unsafe { PeekConsoleInputW(h, buf.as_mut_ptr(), count, &mut n) } == 0 {
        return false;
    }
    buf[..n as usize].iter().any(|r| {
        r.EventType as u32 == KEY_EVENT as u32 && {
            let k = unsafe { r.Event.KeyEvent };
            k.bKeyDown != 0 && (unsafe { k.uChar.AsciiChar } != 0 || extended(&k).is_some())
        }
    })
}

fn unit(c: u16) -> String {
    char::from_u32(c as u32).map(String::from).unwrap_or_else(|| "\u{fffd}".into())
}

/// reid.py's getkey(): "up", "enter", "esc", a character, ...; Ctrl+C is KeyboardInterrupt.
pub fn getkey() -> Result<String, Interrupt> {
    let ch = getwch();
    if ch == 0 || ch == 0xe0 {
        let code = getwch();
        return Ok(match code {
            0x48 => "up", 0x50 => "down", 0x4b => "left", 0x4d => "right", 0x47 => "home", 0x4f => "end",
            _ => "",
        }.into());
    }
    if ch == 0x1b {
        std::thread::sleep(Duration::from_millis(10));
        if kbhit() && getwch() == b'[' as u16 && kbhit() {
            return Ok(match getwch() {
                0x41 => "up", 0x42 => "down", 0x43 => "right", 0x44 => "left", 0x48 => "home", 0x46 => "end",
                _ => "",
            }.into());
        }
        return Ok("esc".into());
    }
    if ch == 3 {
        return Err(Interrupt);
    }
    Ok(match ch {
        0x0d | 0x0a => "enter".into(),
        0x08 | 0x7f => "backspace".into(),
        _ => unit(ch),
    })
}

/// shutil.get_terminal_size((100, 30)): COLUMNS / LINES first, then the console window.
pub fn terminal_size() -> (i64, i64) {
    let env = |k: &str| std::env::var(k).ok().and_then(|v| v.trim().parse::<i64>().ok()).unwrap_or(0);
    let (mut cols, mut lines) = (env("COLUMNS"), env("LINES"));
    if cols <= 0 || lines <= 0 {
        let (c, l) = unsafe {
            let mut info: CONSOLE_SCREEN_BUFFER_INFO = std::mem::zeroed();
            if GetConsoleScreenBufferInfo(GetStdHandle(STD_OUTPUT_HANDLE), &mut info) != 0 {
                ((info.srWindow.Right - info.srWindow.Left + 1) as i64, (info.srWindow.Bottom - info.srWindow.Top + 1) as i64)
            } else {
                (100, 30)
            }
        };
        if cols <= 0 {
            cols = if c != 0 { c } else { 100 };
        }
        if lines <= 0 {
            lines = if l != 0 { l } else { 30 };
        }
    }
    (cols, lines)
}

/// input(prompt): the prompt goes to stderr, the line is read in the console's own line mode.
/// Ctrl+C or end of input gives "".
pub fn input(prompt: &str) -> String {
    use std::io::Write;
    let _ = std::io::stdout().flush();
    let mut e = std::io::stderr().lock();
    let _ = e.write_all(prompt.as_bytes());
    let _ = e.flush();
    drop(e);
    let mut line = String::new();
    let ok = std::io::stdin().read_line(&mut line).is_ok_and(|n| n > 0);
    if interrupted() || !ok {
        return String::new();
    }
    line.trim_end_matches(['\r', '\n']).to_string()
}
