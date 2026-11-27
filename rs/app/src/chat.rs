//! The chat window (vision\Spec\SPEC-unified-interface.md Part 6): one folder, one composer over Claude
//! Code and Codex, beside the session windows. Each turn is a `reid --stream` child, so a turn that
//! crashes can't take Reidcc down and `stop` is a kill (reid's job takes the engine with it). The child's
//! JSON lines go to ui\chat.html as they come.

use crate::model::Op;
use reidcc::{changes, profiles, py, Obj};
use serde::Serialize;
use serde_json::Value;
use std::collections::HashMap;
use std::io::{BufRead, Read, Write};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicU32, Ordering};
use std::sync::{Arc, Mutex};
use tauri::ipc::Channel;
use tauri::{AppHandle, Manager, State};

pub const PREFIX: &str = "chat-";

pub struct Chat {
    folder: String,
    profile: String,
    /// the running turn's reid.exe
    turn: Mutex<Option<Child>>,
    stopped: AtomicBool,
    /// the folder before the running write turn (a git tree), for its diff
    before: Mutex<Option<String>>,
    /// the session window `open terminal` made
    terminal: Mutex<Option<u32>>,
}

#[derive(Default)]
pub struct Chats {
    map: Mutex<HashMap<u32, Arc<Chat>>>,
    next: AtomicU32,
}

impl Chats {
    fn get(&self, id: u32) -> Result<Arc<Chat>, String> {
        self.map.lock().unwrap().get(&id).cloned().ok_or_else(|| "That chat window is gone.".into())
    }

    /// Its window closed: stop a running turn.
    pub fn end(&self, id: u32) {
        if let Some(c) = self.map.lock().unwrap().remove(&id) {
            if let Some(mut child) = c.turn.lock().unwrap().take() {
                let _ = child.kill();
            }
        }
    }
}

/// What the page hears from a turn, in order.
#[derive(Clone, Serialize)]
#[serde(tag = "kind", rename_all = "snake_case")]
pub enum Out {
    /// one of reid --stream's events, as it printed it
    Event { event: Value },
    /// reid.exe ended; `err` is the end of its stderr (it failed before streaming anything)
    Exit { rc: i32, stopped: bool, err: String },
}

#[derive(Serialize)]
pub struct Info {
    folder: String,
    /// the folder as the launcher shows it
    shown: String,
    profile: String,
    /// every profile: [name, engine]
    profiles: Vec<(String, String)>,
}

#[derive(Serialize)]
pub struct Changed {
    from: String,
    to: String,
    files: Vec<Value>,
}

fn engine(p: &Obj) -> String {
    match p.get("engine") {
        Some(v) if reidcc::pyjson::truthy(v) => reidcc::pyjson::py_str(v),
        _ => "claude".into(),
    }
}

/// `open chat`: a chat window on the launcher's folder and profile.
#[tauri::command]
pub async fn chat_open(app: AppHandle, st: crate::S<'_>, chats: State<'_, Chats>) -> Result<Vec<Op>, String> {
    let (folder, profile) = {
        let mut m = st.m.lock().unwrap();
        let say = |m: &mut crate::model::Model, t: &str| m.ops.push(Op::Say { text: t.into(), kind: "error".into(), actions: vec![], seconds: None, focus: None });
        let Some(profile) = m.current.clone() else { return Ok(m.take()) };
        let folder = m.real_folder();
        if !py::isdir(&folder) {
            say(&mut m, "Can't find that folder. It may have moved.");
            return Ok(m.take());
        }
        (folder, profile)
    };
    let id = chats.next.fetch_add(1, Ordering::Relaxed) + 1;
    let sf = crate::panel::launcher_window(&app).and_then(|w| w.scale_factor().ok()).unwrap_or(1.0);
    let (l, t, r, b) = crate::sizes::session_rect(crate::session::visible_rect(crate::gate::main_hwnd() as isize), sf);
    let mut wb = tauri::WebviewWindowBuilder::new(&app, format!("{PREFIX}{id}"), tauri::WebviewUrl::App(format!("chat.html?id={id}").into()))
        .title(format!("chat · {profile}"))
        .decorations(false)
        .position(l as f64 / sf, t as f64 / sf)
        .inner_size((r - l) as f64 / sf, (b - t) as f64 / sf)
        .min_inner_size(640.0, 400.0)
        .background_color(crate::session::CANVAS)
        .theme(Some(tauri::Theme::Dark));
    if let Some(d) = crate::WEBVIEW_DIR.get() {
        wb = wb.data_directory(d.clone());
    }
    if let Some(ico) = crate::asset("reidcc.ico").and_then(|p| std::fs::read(p).ok()) {
        if let Ok(img) = tauri::image::Image::from_bytes(&ico) {
            wb = wb.icon(img.to_owned()).map_err(|e| e.to_string())?;
        }
    }
    chats.map.lock().unwrap().insert(id, Arc::new(Chat {
        folder, profile, turn: Mutex::new(None), stopped: AtomicBool::new(false), before: Mutex::new(None), terminal: Mutex::new(None),
    }));
    if let Err(e) = wb.build() {
        chats.map.lock().unwrap().remove(&id);
        let mut m = st.m.lock().unwrap();
        m.ops.push(Op::Say { text: format!("Couldn't open the chat window ({e})."), kind: "error".into(), actions: vec![], seconds: None, focus: None });
        return Ok(m.take());
    }
    Ok(vec![])
}

#[tauri::command]
pub fn chat_info(st: crate::S, chats: State<Chats>, id: u32) -> Result<Info, String> {
    let c = chats.get(id)?;
    let cfg = st.m.lock().unwrap().cfg().unwrap_or_default();
    let profiles = profiles(&cfg).iter().filter_map(|(n, p)| Some((n.clone(), engine(p.as_object()?)))).collect();
    Ok(Info { shown: reidcc::show_path(&c.folder), folder: c.folder.clone(), profile: c.profile.clone(), profiles })
}

/// What the tune panel offers for `profile` (SPEC-unified-interface Milestone 2C): the profile's own
/// model / effort / mcp_off / plugins, the models and efforts to pick from, its MCP servers and plugins.
/// Async: Codex's server list runs `codex mcp list`.
#[tauri::command]
pub async fn chat_tuning(st: crate::S<'_>, chats: State<'_, Chats>, id: u32, profile: String) -> Result<Value, String> {
    let folder = chats.get(id)?.folder.clone();
    let cfg = st.m.lock().unwrap().cfg().unwrap_or_default();
    Ok(tuning_json(&cfg, &profile, &folder))
}

/// chat_tuning's answer, also the launcher's tune popover (main.rs profile_tuning).
pub fn tuning_json(cfg: &reidcc::Obj, profile: &str, folder: &str) -> Value {
    use reidcc::engines::tuning;
    let prof = profiles(cfg).get(profile).and_then(Value::as_object).cloned().unwrap_or_default();
    let mut out = tuning::choices(&prof, folder).to_json();
    let own: reidcc::Obj = ["model", "effort", "mcp_off", "plugins"].iter()
        .filter_map(|k| prof.get(*k).map(|v| (k.to_string(), v.clone()))).collect();
    out["own"] = Value::Object(own);
    out["models"] = Value::from(tuning::models(cfg, engine(&prof).as_str()));
    out
}

const TURN_RUNNING: &str = "A turn is running. Stop it first.";

/// The folder as a git tree, off the async runtime's threads: `git add -A` on a big repo takes seconds.
async fn snapshot(folder: &str) -> Option<String> {
    let folder = folder.to_string();
    tauri::async_runtime::spawn_blocking(move || changes::snapshot(&folder)).await.ok().flatten()
}

/// One turn: `reid --stream <profile> …` in the chat's folder, its events to `chan`. Refusals (locks)
/// come back as reid's own `error` events. Async, so the before-snapshot never holds up the windows.
#[tauri::command]
#[allow(clippy::too_many_arguments)]
pub async fn chat_send(st: crate::S<'_>, chats: State<'_, Chats>, id: u32, profile: String, prompt: String, read_only: bool,
                       resume: Option<String>, switch_from: Option<String>, with: Option<Value>, chan: Channel<Out>) -> Result<(), String> {
    let c = chats.get(id)?;
    if c.turn.lock().unwrap().is_some() {
        return Err(TURN_RUNNING.into());
    }
    c.stopped.store(false, Ordering::Relaxed);
    let cli = st.m.lock().unwrap().cli.clone();
    let mut args: Vec<String> = cli[1..].to_vec();
    args.extend(["--stream".into(), profile]);
    if read_only {
        args.push("--read-only".into());
    }
    if let Some(r) = resume {
        args.extend(["--resume".into(), r]);
    }
    if let Some(f) = switch_from {
        args.extend(["--switch-from".into(), f]);
    }
    if let Some(with) = with.filter(|w| w.as_object().is_some_and(|o| !o.is_empty())) {
        args.extend(["--with".into(), with.to_string()]); // this chat's model / effort / MCP / plugins
    }
    args.push("-".into()); // the prompt on stdin: no length limit, nothing in the process list
    let before = if read_only { None } else { snapshot(&c.folder).await };
    if c.stopped.load(Ordering::Relaxed) {
        // `stop` came during the snapshot: the turn never starts
        let _ = chan.send(Out::Exit { rc: 1, stopped: true, err: String::new() });
        return Ok(());
    }
    let mut turn = c.turn.lock().unwrap();
    if turn.is_some() {
        return Err(TURN_RUNNING.into());
    }
    *c.before.lock().unwrap() = before;
    use std::os::windows::process::CommandExt;
    let mut child = Command::new(&cli[0]).args(&args).current_dir(&c.folder)
        .stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .creation_flags(0x0800_0000).spawn().map_err(|e| format!("Couldn't start reid ({e})."))?;
    let (mut stdin, stdout, mut stderr) = (child.stdin.take().unwrap(), child.stdout.take().unwrap(), child.stderr.take().unwrap());
    std::thread::spawn(move || {
        let _ = stdin.write_all(prompt.as_bytes());
    }); // dropped there: EOF
    let tail = std::thread::spawn(move || {
        let mut s = String::new();
        let _ = stderr.read_to_string(&mut s);
        let s = s.trim().to_string();
        s.chars().skip(s.chars().count().saturating_sub(600)).collect::<String>()
    });
    *turn = Some(child);
    drop(turn);
    let chat = c.clone();
    std::thread::spawn(move || {
        for line in std::io::BufReader::new(stdout).lines().map_while(Result::ok) {
            if let Ok(event) = serde_json::from_str::<Value>(&line) {
                let _ = chan.send(Out::Event { event });
            }
        }
        let child = chat.turn.lock().unwrap().take();
        let rc = child.and_then(|mut ch| ch.wait().ok()).and_then(|s| s.code()).unwrap_or(1);
        let err = tail.join().unwrap_or_default();
        let _ = chan.send(Out::Exit { rc, stopped: chat.stopped.load(Ordering::Relaxed), err });
    });
    Ok(())
}

/// `stop`: kill the turn's reid.exe; its kill-on-close job takes the engine down with it. Before reid
/// started (chat_send still taking its snapshot), the flag alone keeps the turn from starting.
#[tauri::command]
pub fn chat_stop(chats: State<Chats>, id: u32) -> Result<(), String> {
    let c = chats.get(id)?;
    c.stopped.store(true, Ordering::Relaxed);
    if let Some(child) = c.turn.lock().unwrap().as_mut() {
        let _ = child.kill();
    }
    Ok(())
}

/// What the last write turn changed (None outside git, or for a read-only turn). Async, like chat_send.
#[tauri::command]
pub async fn chat_changed(chats: State<'_, Chats>, id: u32) -> Result<Option<Changed>, String> {
    let c = chats.get(id)?;
    let Some(from) = c.before.lock().unwrap().take() else { return Ok(None) };
    let Some(to) = snapshot(&c.folder).await else { return Ok(None) };
    let folder = c.folder.clone();
    let (a, b) = (from.clone(), to.clone());
    let files = tauri::async_runtime::spawn_blocking(move || changes::changed(&folder, &a, &b).iter().map(|f| f.to_json()).collect())
        .await.unwrap_or_default();
    Ok(Some(Changed { from, to, files }))
}

#[tauri::command]
pub fn chat_file_diff(chats: State<Chats>, id: u32, from: String, to: String, path: String) -> Result<String, String> {
    let c = chats.get(id)?;
    let hex = |s: &str| !s.is_empty() && s.len() <= 64 && s.bytes().all(|b| b.is_ascii_hexdigit());
    if !hex(&from) || !hex(&to) {
        return Err("not a snapshot".into());
    }
    Ok(changes::file_diff(&c.folder, &from, &to, &path, 400))
}

/// Who has session `sid` open, if anyone: the composer shows it until it's free.
#[tauri::command]
pub fn chat_holder(st: crate::S, sid: String) -> Option<Value> {
    let home = st.m.lock().unwrap().ctx.home.clone();
    reidcc::locks::holder(&reidcc::Ctx::at(&home), &sid)
}

/// `open terminal`: the profile's session (`--resume <profile> --id <sid>`) in a Reidcc session window,
/// over the chat window; its own if it's still open.
#[tauri::command]
pub async fn chat_terminal(app: AppHandle, st: crate::S<'_>, sessions: State<'_, crate::session::Sessions>, chats: State<'_, Chats>,
                           id: u32, profile: String, sid: Option<String>) -> Result<(), String> {
    let c = chats.get(id)?;
    let open = *c.terminal.lock().unwrap();
    if let Some(t) = open.filter(|t| sessions.get(*t).is_some()) {
        crate::session::sess_focus(app, t);
        return Ok(());
    }
    let (mut cmd, prof) = {
        let mut m = st.m.lock().unwrap();
        let cfg = m.cfg().unwrap_or_default();
        (m.cli.clone(), profiles(&cfg).get(&profile).and_then(Value::as_object).cloned().unwrap_or_default())
    };
    match sid.filter(|s| reidcc::locks::valid_id(s)) {
        Some(s) => cmd.extend(["--resume".into(), profile.clone(), "--id".into(), s]),
        None => cmd.push(profile.clone()),
    }
    let info = crate::session::Info { engine: engine(&prof), profile, folder: reidcc::show_path(&c.folder),
                                      persona: reidcc::profile::persona_name(&prof), elapsed_ms: 0 };
    let rect = app.get_webview_window(&format!("{PREFIX}{id}")).and_then(|w| w.hwnd().ok())
        .map(|h| crate::session::visible_rect(h.0 as isize)).ok_or("That chat window is gone.")?;
    let w = sessions.open(&app, info, &c.folder, &cmd, rect, None)?;
    *c.terminal.lock().unwrap() = w.label().strip_prefix(crate::session::PREFIX).and_then(|n| n.parse().ok());
    let _ = w.show();
    let _ = w.set_focus();
    Ok(())
}

/// `focus terminal` / `focus window`: the chat's terminal, else any session window in its folder.
#[tauri::command]
pub fn chat_focus(app: AppHandle, sessions: State<crate::session::Sessions>, chats: State<Chats>, id: u32) -> Result<bool, String> {
    let c = chats.get(id)?;
    let t = (*c.terminal.lock().unwrap()).filter(|t| sessions.get(*t).is_some()).or_else(|| sessions.in_folder(&c.folder));
    if let Some(t) = t {
        crate::session::sess_focus(app, t);
    }
    Ok(t.is_some())
}

/// The folder's `.reid\handoff.md` in its default program.
#[tauri::command]
pub fn chat_handoff(chats: State<Chats>, id: u32) -> Result<(), String> {
    let c = chats.get(id)?;
    let p = py::join(&c.folder, &[reidcc::handoff::DIR, "handoff.md"]);
    if py::exists(&p) {
        crate::model::open_file(&p);
    }
    Ok(())
}
