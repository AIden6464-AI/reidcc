//! Rigs (vision v1 §5, SPEC-rust-rewrite stage 4): a snapped frame of session windows saved by name in
//! reid.json's "rigs", and opened again in one click from small. Each pane keeps its profile and folder.

use crate::{dock, session, S};
use reidcc::engines::{self};
use reidcc::{profiles, py};
use serde::Serialize;
use serde_json::{Map, Value};
use tauri::{AppHandle, Emitter, State, Webview};

#[derive(Serialize)]
pub struct Row {
    name: String,
    /// the panes' profiles, in order
    profiles: Vec<String>,
}

fn rigs(cfg: &Map<String, Value>) -> Map<String, Value> {
    cfg.get("rigs").and_then(Value::as_object).cloned().unwrap_or_default()
}

#[tauri::command]
pub fn rig_list(st: S) -> Vec<Row> {
    let Ok(cfg) = reidcc::load_config(&st.m.lock().unwrap().ctx) else { return vec![] };
    rigs(&cfg).into_iter().filter_map(|(name, r)| {
        let leaves = dock::rig_leaves(r.get("layout")?)?;
        Some(Row { name, profiles: leaves.iter().filter_map(|l| l["profile"].as_str().map(str::to_owned)).collect() })
    }).collect()
}

/// Save the frame this header belongs to as rig `name` (saving under a name it has replaces it).
#[tauri::command]
pub fn rig_save(app: AppHandle, webview: Webview, st: S, sessions: State<'_, session::Sessions>, name: String) -> Result<String, String> {
    let name = name.trim().to_string();
    if name.is_empty() {
        return Err("Name the rig first.".into());
    }
    let rig = dock::rig_of(&app, webview.window(), &|id| sessions.leaf(id)).ok_or("Couldn't read this frame's layout.")?;
    let mut m = st.m.lock().unwrap();
    let mut cfg = reidcc::load_config(&m.ctx).map_err(|e| e.0)?;
    let mut all = rigs(&cfg);
    all.insert(name.clone(), rig);
    cfg.insert("rigs".into(), Value::Object(all));
    m.save(&cfg);
    drop(m);
    let _ = app.emit_to("main", "rigs-changed", ());
    Ok(format!("Saved as rig {name}."))
}

#[tauri::command]
pub fn rig_delete(app: AppHandle, st: S, name: String) {
    let mut m = st.m.lock().unwrap();
    let Ok(mut cfg) = reidcc::load_config(&m.ctx) else { return };
    let mut all = rigs(&cfg);
    if all.remove(&name).is_some() {
        cfg.insert("rigs".into(), Value::Object(all));
        m.save(&cfg);
        drop(m);
        let _ = app.emit_to("main", "rigs-changed", ());
    }
}

/// Open every pane of rig `name` in a session window, then snap them back into the saved layout.
/// Nothing opens unless every pane can (same checks as open gate).
#[tauri::command]
pub async fn rig_open(app: AppHandle, st: S<'_>, sessions: State<'_, session::Sessions>, name: String) -> Result<String, String> {
    let m = st.m.lock().unwrap();
    if st.gate.lock().unwrap().active {
        return Ok(String::new());
    }
    let cfg = reidcc::load_config(&m.ctx).map_err(|e| e.0)?;
    let rig = rigs(&cfg).get(&name).cloned().ok_or(format!("There's no rig called {name}."))?;
    let layout = rig.get("layout").cloned().unwrap_or_default();
    let leaves = dock::rig_leaves(&layout).ok_or(format!("Rig {name} in reid.json has an error. Fix it, or save the rig again."))?;
    let mut plan = vec![];
    for leaf in &leaves {
        let prof_name = leaf["profile"].as_str().unwrap_or_default().to_string();
        let Some(prof) = profiles(&cfg).get(&prof_name).and_then(Value::as_object).cloned() else {
            return Err(format!("Rig {name} uses profile {prof_name}, which isn't there any more."));
        };
        let cwd = leaf.get("folder").and_then(Value::as_str).map(str::to_owned).unwrap_or_else(|| m.real_folder());
        if !py::isdir(&cwd) {
            return Err(format!("Rig {name}: can't find {}. It may have moved.", reidcc::show_path(&cwd)));
        }
        match engines::build(&m.ctx, &cfg, &prof_name, &[], Some(&cwd), false) {
            Ok(l) => l.remove_temps(),
            Err(e) => return Err(format!("Rig {name}, {prof_name}: {}", e.0)),
        }
        let engine = match prof.get("engine") {
            Some(v) if reidcc::pyjson::truthy(v) => reidcc::pyjson::py_str(v),
            _ => "claude".into(),
        };
        let info = session::Info { engine, profile: prof_name.clone(), folder: reidcc::show_path(&cwd),
                                   persona: reidcc::profile::persona_name(&prof), elapsed_ms: 0 };
        let mut cmd = m.cli.clone();
        cmd.push(prof_name);
        plan.push((info, cwd, cmd));
    }
    drop(m); // making windows waits on the main thread, whose commands take this lock
    let at = rig.get("rect").and_then(Value::as_array)
        .and_then(|a| a.iter().map(|v| v.as_i64().map(|n| n as i32)).collect::<Option<Vec<_>>>())
        .filter(|a| a.len() == 4 && a[2] > a[0] && a[3] > a[1])
        .map(|a| (a[0], a[1], a[2], a[3]))
        .unwrap_or_else(|| session::visible_rect(crate::gate::main_hwnd() as isize));
    let saved = layout.clone();
    let h = app.clone();
    let frame = dock::on_ui(&app, move || dock::rig_frame(&h, &saved, at)).flatten();
    let Some((group, tiles)) = frame else { return Err(format!("Couldn't open rig {name}'s frame.")) };
    let mut ids = vec![];
    for ((info, cwd, cmd), tile) in plan.into_iter().zip(tiles) {
        match sessions.open(&app, info, &cwd, &cmd, at, Some((group.clone(), tile))) {
            Ok(w) => ids.extend(w.label().strip_prefix(session::PREFIX).and_then(|n| n.parse::<u32>().ok())),
            Err(e) => {
                let (h, opened) = (app.clone(), ids.clone());
                dock::on_ui(&app, move || {
                    for id in opened { dock::close_pane(&h, id) }
                    let _ = group.destroy();
                });
                return Err(format!("Couldn't open the session window ({e})."));
            }
        }
    }
    let h = app.clone();
    dock::on_ui(&app, move || dock::rig_show(&h, &group, &layout, &ids));
    Ok(format!("Rig {name} open."))
}
