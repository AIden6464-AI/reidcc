//! The updater (vision/Spec/SPEC-github-repo.md Part 4): check GitHub at start and every 6 hours,
//! offer it in the footer, install only on a click (or `reid --update`). Only installed copies check.

use std::sync::Mutex;
use std::time::Duration;
use tauri::{AppHandle, Emitter, Manager, State};
use tauri_plugin_updater::{Update, UpdaterExt};

#[derive(Default)]
pub struct Updates {
    found: Mutex<Option<Update>>,
    foot: Mutex<Foot>,
}

/// What the footer's right side says instead of `ready · …` (nothing when `text` is empty).
#[derive(Clone, Default, serde::Serialize)]
pub struct Foot {
    text: String,
    click: bool,
}

fn show(app: &AppHandle, text: String, click: bool) {
    let f = Foot { text, click };
    *app.state::<Updates>().foot.lock().unwrap() = f.clone();
    let _ = app.emit("update", f);
}

/// Back to the offer after a message has been read.
fn offer_later(app: &AppHandle, version: String) {
    let app = app.clone();
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_secs(5));
        show(&app, format!("update {version} · install"), true);
    });
}

/// Ask GitHub for latest.json. An error (offline, say) changes nothing; the caller decides if it shows.
async fn check(app: &AppHandle) -> Result<Option<String>, String> {
    let up = app.updater().map_err(|e| e.to_string())?.check().await.map_err(|e| e.to_string())?;
    let v = up.as_ref().map(|u| u.version.clone());
    reidcc::save_update(&app.state::<crate::App>().m.lock().unwrap().ctx, v.as_deref()); // for the TUI's footer
    if let Some(v) = &v {
        show(app, format!("update {v} · install"), true);
    }
    *app.state::<Updates>().found.lock().unwrap() = up;
    Ok(v)
}

/// From setup: the 6-hourly check, and with `--update` (from `reid --update`) install straight away.
pub fn start(app: &AppHandle, now: bool) {
    if !reidcc::installed_copy() {
        return;
    }
    let app = app.clone();
    std::thread::spawn(move || {
        let found = tauri::async_runtime::block_on(check(&app));
        if now {
            match found {
                Ok(Some(_)) => tauri::async_runtime::block_on(install(&app)),
                Ok(None) => show(&app, format!("Reidcc {} is the latest", env!("CARGO_PKG_VERSION")), false),
                Err(e) => show(&app, format!("couldn't check for updates: {e}"), false),
            }
        }
        loop {
            std::thread::sleep(Duration::from_secs(6 * 3600));
            let _ = tauri::async_runtime::block_on(check(&app));
        }
    });
}

async fn install(app: &AppHandle) {
    let Some(up) = app.state::<Updates>().found.lock().unwrap().clone() else { return };
    // Every session runs under a reid.exe from this folder (in a window here or in Windows Terminal),
    // and the installer can't replace a running file.
    let exe = std::env::current_exe().map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
    let busy = reidcc::win::running_in(&reidcc::py::dirname(&exe), &["reid.exe", "Reidcc.exe"]);
    if busy > 0 {
        show(app, format!("finish your {busy} session{} first", if busy == 1 { "" } else { "s" }), false);
        return offer_later(app, up.version);
    }
    let (v, a, mut got, mut last) = (up.version.clone(), app.clone(), 0u64, u64::MAX);
    show(app, format!("downloading {v}"), false);
    let res = up.download_and_install(move |n, total| {
        got += n as u64;
        let pct = total.map_or(0, |t| got * 100 / t.max(1));
        if pct != last {
            last = pct;
            show(&a, format!("downloading {v} · {pct}%"), false);
        }
    }, || {}).await;
    // On success the installer has taken over and this process has exited.
    if let Err(e) = res {
        show(app, format!("update failed: {e}"), false);
        offer_later(app, up.version);
    }
}

#[tauri::command]
pub fn update_foot(st: State<Updates>) -> Foot {
    st.foot.lock().unwrap().clone()
}

#[tauri::command]
pub async fn update_install(app: AppHandle) {
    install(&app).await
}
