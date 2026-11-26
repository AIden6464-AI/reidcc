//! OS-backed locks (SPEC-unified-interface, Milestone 1). A lock is an open file that only its
//! holder may write: Windows closes a process's handles when it dies, however it dies, so a lock
//! can't outlive its process and there's nothing stale to clean up.
//!
//!   REIDCC_HOME\sessions\<id>.lock   one engine process per session
//!   REIDCC_HOME\sessions\<id>.json   that session's record: pid (always), hwnd (when a window has it)
//!   REIDCC_HOME\locks\<folder>.lock  per folder: shared by any number of interactive windows, or held
//!                                    alone by one headless writing turn (<folder>.json names it)

use crate::{err, py, Ctx, R};
use serde_json::Value;
use std::fs::File;
use std::io::Write;
use std::os::windows::fs::OpenOptionsExt;

const FILE_SHARE_READ: u32 = 1;

pub struct Lock {
    file: Option<File>,
    paths: Vec<String>, // removed on release: the lock, and the session record next to it
}

impl Drop for Lock {
    fn drop(&mut self) {
        self.file.take(); // release first; removing fails harmlessly if someone took it meanwhile
        for p in &self.paths {
            let _ = std::fs::remove_file(p);
        }
    }
}

/// Hold `path`, with `info` written in it for whoever finds it taken. Err(the holder's info).
fn take(path: &str, info: &Value) -> Result<Lock, Value> {
    let _ = std::fs::create_dir_all(py::dirname(path));
    // others may read it (to name the holder), nobody else may open it to write
    let opened = std::fs::OpenOptions::new().write(true).create(true).truncate(true)
        .share_mode(FILE_SHARE_READ).open(path);
    match opened {
        Ok(mut f) => {
            let _ = f.write_all(info.to_string().as_bytes());
            let _ = f.flush();
            Ok(Lock { file: Some(f), paths: vec![path.into()] })
        }
        Err(_) => Err(std::fs::read_to_string(path).ok().and_then(|t| serde_json::from_str(&t).ok()).unwrap_or(Value::Null)),
    }
}

fn holder_pid(info: &Value) -> String {
    info.get("pid").and_then(Value::as_u64).map(|p| format!(" (pid {p})")).unwrap_or_default()
}

/// Session ids name files, so only the characters Claude's and Codex's ids use.
pub fn valid_id(id: &str) -> bool {
    !id.is_empty() && id.len() <= 80 && id.bytes().all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
}

/// The record kept while a session runs (REIDCC_HOME\sessions\<id>.json).
pub fn record(id: &str, engine: &str, profile: &str, folder: &str, mode: &str) -> Value {
    let (y, mo, d, h, mi, s) = py::now_local();
    serde_json::json!({
        "id": id, "engine": engine, "profile": profile, "folder": folder, "mode": mode,
        "pid": std::process::id(),
        "hwnd": std::env::var("REIDCC_HWND").ok().and_then(|h| h.parse::<u64>().ok()),
        "started": format!("{y:04}-{mo:02}-{d:02}T{h:02}:{mi:02}:{s:02}"),
    })
}

/// One process per session: Err names the window (pid) that has it open.
pub fn session(ctx: &Ctx, rec: &Value) -> R<Lock> {
    let id = rec["id"].as_str().unwrap_or_default();
    if !valid_id(id) {
        return err(format!("{id} isn't a session id."));
    }
    let dir = py::join(&ctx.home, &["sessions"]);
    match take(&py::join(&dir, &[&format!("{id}.lock")]), rec) {
        Ok(mut lock) => {
            let json = py::join(&dir, &[&format!("{id}.json")]);
            let _ = crate::save_json(&json, rec);
            lock.paths.push(json);
            Ok(lock)
        }
        Err(holder) => err(format!("That session is open in another window{}. Switch to it, or start a new one.", holder_pid(&holder))),
    }
}

/// The folder's lock file and the file naming its writer.
fn folder_paths(ctx: &Ctx, folder: &str) -> (String, String) {
    let key = py::normcase(py::abspath(folder).trim_end_matches(['\\', '/']));
    // FNV-1a: a stable file name for the folder (std's hasher may change between Rust versions)
    let hash = key.bytes().fold(0xcbf29ce484222325u64, |h, b| (h ^ b as u64).wrapping_mul(0x100000001b3));
    let dir = py::join(&ctx.home, &["locks"]);
    let _ = std::fs::create_dir_all(&dir);
    (py::join(&dir, &[&format!("{hash:016x}.lock")]), py::join(&dir, &[&format!("{hash:016x}.json")]))
}

/// The folder's writer, if one is running (its lock can't be read while it's held alone).
fn writer(side: &str) -> Option<Value> {
    std::fs::read_to_string(side).ok().and_then(|t| serde_json::from_str::<Value>(&t).ok())
        .filter(|i| i["pid"].as_u64().is_some_and(|p| crate::win::pid_alive(p as u32)))
}

/// A headless writing turn holds its folder alone: refused while a window or another writing turn
/// is in it. Read-only turns take nothing.
pub fn folder(ctx: &Ctx, folder: &str, session: Option<&str>) -> R<Lock> {
    let (path, side) = folder_paths(ctx, folder);
    match std::fs::OpenOptions::new().write(true).create(true).truncate(true).share_mode(0).open(&path) {
        Ok(f) => {
            let info = serde_json::json!({ "folder": folder, "pid": std::process::id(), "session": session });
            let _ = std::fs::write(&side, info.to_string());
            Ok(Lock { file: Some(f), paths: vec![path, side] })
        }
        Err(_) => match writer(&side) {
            Some(w) => err(format!("Another turn is writing in this folder{}. Wait for it to finish, or run this one read-only.", holder_pid(&w))),
            None => err("A Reidcc window is open in this folder. Close it, or run this turn read-only."),
        },
    }
}

/// An interactive window's share of its folder: any number of windows at once, never alongside a
/// headless writing turn.
pub fn folder_shared(ctx: &Ctx, folder: &str) -> R<Lock> {
    use std::os::windows::io::FromRawHandle;
    use windows_sys::Win32::Foundation::{GENERIC_READ, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::{CreateFileW, FILE_ATTRIBUTE_NORMAL, OPEN_ALWAYS};
    let (path, side) = folder_paths(ctx, folder);
    // read access, and others may only read: windows share it, a writer (who needs it alone) can't open it
    let h = unsafe { CreateFileW(crate::win::wide(&path).as_ptr(), GENERIC_READ, FILE_SHARE_READ, std::ptr::null(),
                                 OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, std::ptr::null_mut()) };
    if h == INVALID_HANDLE_VALUE {
        let pid = writer(&side).map(|w| holder_pid(&w)).unwrap_or_default();
        return err(format!("A turn is writing in this folder right now{pid}. Open this when it's done."));
    }
    Ok(Lock { file: Some(unsafe { File::from_raw_handle(h as _) }), paths: vec![path] })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_held_lock_refuses_and_names_its_holder_then_frees_on_drop() {
        let dir = std::env::temp_dir().join(format!("reid_locks_{}", std::process::id()));
        let ctx = Ctx::at(&dir.to_string_lossy());
        let rec = record("abc-123", "claude", "main", "C:\\x", "write");
        let held = session(&ctx, &rec).unwrap();
        let e = session(&ctx, &rec).err().unwrap().0;
        assert!(e.contains(&format!("pid {}", std::process::id())), "{e}");
        assert!(dir.join("sessions").join("abc-123.json").exists());
        let f = folder(&ctx, "C:\\Work\\", None).unwrap();
        assert!(folder(&ctx, "c:\\work", Some("x")).err().unwrap().0.contains("pid"), "same folder, any case or trailing slash");
        assert!(folder_shared(&ctx, "C:\\Work").err().unwrap().0.contains("writing in this folder"));
        drop((held, f));
        let (w1, w2) = (folder_shared(&ctx, "C:\\Work").unwrap(), folder_shared(&ctx, "C:\\Work").unwrap());
        assert!(folder(&ctx, "C:\\Work", None).err().unwrap().0.contains("window is open"), "two windows, no writer");
        drop((w1, w2));
        assert!(!dir.join("sessions").join("abc-123.json").exists());
        assert!(session(&ctx, &rec).is_ok() && folder(&ctx, "C:\\Work", None).is_ok());
        assert!(session(&ctx, &record("..\\x", "claude", "m", "f", "write")).is_err());
        let _ = std::fs::remove_dir_all(dir);
    }
}
