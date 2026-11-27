//! OpenCode: the command for an OpenCode profile (SPEC-codex-opencode milestone 2, SPEC-0.2.6 Part 3).
//! Always `--standalone`, a private server: only it reads the per-launch config layer
//! (OPENCODE_CONFIG_CONTENT) that carries the model and persona, so Reid's background service and his
//! own opencode.json are never touched.

use super::codex::{prompt_file, run_capture};
use super::{apply_env, io, need, refuse_claude_only, Launch};
use crate::{environ, err, memory, on, py, text, Ctx, Env, Obj, R};
use serde_json::{json, Value};
use std::time::Duration;

/// The per-launch config layer, over the user's own opencode.json.
pub const CONFIG_CONTENT: &str = "OPENCODE_CONFIG_CONTENT";
/// The agent a chat turn runs as: the permissions that make it read-only or edits-only.
pub const TURN_AGENT: &str = "reidcc-turn";
const ASK_TIMEOUT: Duration = Duration::from_secs(15);

/// opencode.exe, never the npm .cmd shim (batch files re-parse arguments through cmd.exe).
/// `opencode` and `opencode2` are the same program.
pub fn find_opencode() -> R<String> {
    for shim in ["opencode", "opencode2"] {
        if let Some(s) = py::which(shim) {
            let exe = py::join(&py::dirname(&s), &["node_modules", "@opencode", "cli", "bin", "opencode.exe"]);
            if py::exists(&exe) {
                return Ok(exe);
            }
        }
    }
    if let Some(exe) = py::which("opencode.exe") {
        return Ok(exe);
    }
    // shortcut: a wrapper we can't see through runs as is, like find_codex; look inside it if one breaks
    if let Some(shim) = py::which("opencode") {
        return Ok(shim);
    }
    err("Can't find OpenCode. Install it (npm install -g @opencode/cli), then try again.")
}

/// A new session id. OpenCode makes a session for an id it doesn't know (`--session`, TUI and run
/// alike), so Reidcc names it up front, like Claude's --session-id: locked and remembered from the start.
pub fn new_session_id() -> String {
    format!("ses_{}", uuid::Uuid::new_v4().simple())
}

/// `opencode session export <id>` succeeds only for a session that's there (~1 s).
pub fn session_exists(env: &Env, cwd: &str, id: &str) -> bool {
    let Ok(exe) = find_opencode() else { return false };
    let argv = [exe, "session".into(), "export".into(), id.into(), "--standalone".into()];
    run_capture(&argv, env, Some(cwd), ASK_TIMEOUT).is_some_and(|(code, _, _)| code == 0)
}

/// A session's name in OpenCode's own list: the ask's first line, up to 60 characters.
fn title(ask: &str) -> String {
    let line = ask.trim().lines().next().unwrap_or_default().trim();
    match line.char_indices().nth(60) {
        Some((cut, _)) => format!("{}…", line[..cut].trim_end()),
        None => line.to_string(),
    }
}

/// Names a session after `ask` in OpenCode's own list (`session list`, the TUI's sessions). A standalone run
/// or import gets no title (OpenCode's server makes them), so it would read "Untitled session". Best effort.
pub fn set_title(env: &Env, cwd: &str, id: &str, ask: &str) {
    let (Ok(exe), name) = (find_opencode(), title(ask)) else { return };
    if name.is_empty() {
        return;
    }
    let mut env = env.clone();
    env.insert("PWD".into(), cwd.into()); // OpenCode's folder (see build)
    let argv = [exe, "api".into(), "--standalone".into(), "session.update".into(), "--param".into(),
                format!("sessionID={id}"), "-d".into(), json!({"title": name}).to_string()];
    let _ = run_capture(&argv, &env, Some(cwd), ASK_TIMEOUT);
}

/// `opencode api <operation>`'s answer, or None.
fn api(env: &Env, cwd: &str, operation: &str) -> Option<Value> {
    let argv = [find_opencode().ok()?, "api".into(), "--standalone".into(), operation.into()];
    let mut env = env.clone();
    env.insert("PWD".into(), cwd.into()); // OpenCode's folder (see build)
    let (code, out, _) = run_capture(&argv, &env, Some(cwd), ASK_TIMEOUT)?;
    if code != 0 {
        return None;
    }
    serde_json::from_str(&out).ok()
}

/// The model a launch runs: the profile's, else the last config layer that names one.
fn model_of(prof: &Obj, env: &Env, cwd: &str) -> String {
    let own = text(prof, "model");
    if !own.is_empty() {
        return own;
    }
    // each layer as OpenCode read it: "model" is {"providerID", "model"} there (2.3.0), a string in the file
    let named = |model: &Value| match model {
        Value::String(m) => Some(m.clone()),
        Value::Object(m) => Some(format!("{}/{}", m.get("providerID")?.as_str()?, m.get("model")?.as_str()?)),
        _ => None,
    };
    let layers = api(env, cwd, "config.get").unwrap_or_default();
    layers.as_array().into_iter().flatten().rev().find_map(|layer| named(&layer["info"]["model"])).unwrap_or_default()
}

/// The effort levels (OpenCode's model variants) the launch's model has.
pub fn variants(prof: &Obj, env: &Env, cwd: &str) -> Vec<String> {
    let model = model_of(prof, env, cwd);
    let Some((provider, id)) = model.split('#').next().unwrap_or_default().split_once('/') else { return vec![] };
    let models = api(env, cwd, "model.list").unwrap_or_default();
    models["data"].as_array().into_iter().flatten()
        .find(|m| m["providerID"] == provider && m["id"] == id)
        .and_then(|m| m["variants"].as_array())
        .map(|vs| vs.iter().filter_map(|v| v["id"].as_str().map(String::from)).collect())
        .unwrap_or_default()
}

/// `opencode models`: every provider/model the user's setup can run.
pub fn models() -> Vec<String> {
    let Ok(exe) = find_opencode() else { return vec![] };
    run_capture(&[exe, "models".into(), "--standalone".into()], &environ(), None, ASK_TIMEOUT)
        .filter(|(code, _, _)| *code == 0)
        .map(|(_, out, _)| out.lines().map(str::trim).filter(|l| l.contains('/')).map(String::from).collect())
        .unwrap_or_default()
}

/// A chat turn's `-m model#effort`, when the profile picks an effort (the full screen has no -m, so the
/// session window runs the model's default effort).
pub fn turn_args(prof: &Obj, env: &Env, cwd: &str) -> Vec<String> {
    let effort = text(prof, "effort");
    if effort.is_empty() {
        return vec![];
    }
    match model_of(prof, env, cwd).split('#').next().unwrap_or_default() {
        "" => vec![],
        model => vec!["-m".into(), format!("{model}#{effort}")],
    }
}

/// Puts the turn's agent into the config layer: read-only keeps only the tools that read; a writing
/// turn edits but has no shell, no subagents and nothing outside the folder (the composer's
/// `edits · no shell`). A replace-mode persona's prompt comes along.
pub fn turn_agent(env: &mut Env, read_only: bool) {
    let mut config: Obj = env.get(CONFIG_CONTENT).and_then(|c| serde_json::from_str(c).ok()).unwrap_or_default();
    let permission = if read_only {
        json!({"*": "deny", "read": "allow", "glob": "allow", "grep": "allow", "list": "allow", "lsp": "allow",
               "webfetch": "allow", "websearch": "allow"})
    } else {
        json!({"bash": "deny", "task": "deny", "external_directory": "deny"})
    };
    let mut agent = json!({"mode": "primary", "description": "Reidcc chat turn", "permission": permission});
    if let Some(prompt) = config.get("agent").and_then(|a| a.get("reidcc")).and_then(|r| r.get("prompt")) {
        agent["prompt"] = prompt.clone();
    }
    let agents = config.entry("agent").or_insert_with(|| json!({}));
    if let Some(agents) = agents.as_object_mut() {
        agents.insert(TURN_AGENT.into(), agent);
    }
    env.insert(CONFIG_CONTENT.into(), Value::Object(config).to_string());
}

/// OpenCode's command. `prepare` writes the persona prompt file; previews pass false.
pub fn build(ctx: &Ctx, cfg: &Obj, name: &str, prof: &Obj, extra: &[String], cwd: Option<&str>, prepare: bool) -> R<Launch> {
    refuse_claude_only(prof, name, "OpenCode")?;
    if !crate::proxy::list(prof).is_empty() {
        return err(format!("OpenCode doesn't go through the proxy. Turn the proxy off for {name}."));
    }
    let model = text(prof, "model");
    if !model.is_empty() && !model.contains('/') {
        return err(format!("{model} isn't an OpenCode model. They're provider/model, like opencode/gpt-5.5: see opencode models."));
    }
    let settings = text(prof, "settings");
    if settings.to_lowercase().ends_with(".toml") {
        return err(format!("{settings} is a Codex sign-in file. Pick an OpenCode one, or use OpenCode's own setup."));
    }
    let ppath = match text(prof, "persona") {
        p if p.is_empty() => String::new(),
        p => need(ctx, name, &p, "persona file")?,
    };
    let mut args = crate::args(prof);
    args.extend(extra.iter().cloned());
    // shortcut: a bare word after a flag counts as that flag's value, so `--continue <dir>` slips through
    for (i, a) in args.iter().enumerate() {
        if !a.starts_with('-') && (i == 0 || !args[i - 1].starts_with('-')) {
            return err(format!("Leave {a} out of the extra args: OpenCode opens in the folder you picked."));
        }
    }

    let exe = find_opencode()?;
    let mut env = environ();
    if !settings.is_empty() {
        env.insert("OPENCODE_CONFIG".into(), need(ctx, name, &settings, "sign-in file")?); // keys stay in that one file
    }
    // OpenCode takes its folder from PWD when it's set (Git Bash sets it), not from the process's own
    // folder: a turn started from a shell would edit the shell's folder
    match cwd {
        Some(folder) => env.insert("PWD".into(), folder.into()),
        None => env.shift_remove("PWD"),
    };
    apply_env(&mut env, prof);
    let mut config = Obj::new();
    if !model.is_empty() {
        config.insert("model".into(), json!(model));
    }
    if !ppath.is_empty() || on(prof, "memory").is_some() {
        let pfile = prompt_file(&py::join(&ctx.opencode_dir, &["prompts"]), name);
        if prepare {
            let persona = if ppath.is_empty() { String::new() } else { py::read_text(&ppath, false).map_err(crate::ReidError)? };
            let body = format!("{}\n", (persona + &memory::memory_block(ctx, cfg, prof).map_err(io)?).trim_matches('\n'));
            std::fs::create_dir_all(py::dirname(&pfile)).map_err(io)?;
            py::write_text(&pfile, &body, true).map_err(io)?;
        }
        let pfile = pfile.replace('\\', "/");
        if !ppath.is_empty() && text(prof, "mode") == "replace" {
            config.insert("agent".into(), json!({"reidcc": {"mode": "primary", "prompt": format!("{{file:{pfile}}}")}}));
            config.insert("default_agent".into(), json!("reidcc"));
        } else {
            config.insert("instructions".into(), json!([pfile])); // added to OpenCode's own prompt
        }
    }
    env.insert(CONFIG_CONTENT.into(), Value::Object(config).to_string());
    let mut argv = vec![exe, "--standalone".into()];
    argv.extend(args);
    Ok(Launch { argv, env, temps: vec![] })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn titles_are_the_first_line_cut_at_60_chars() {
        assert_eq!(title("  Fix the tests\nthen push  "), "Fix the tests");
        assert_eq!(title(""), "");
        assert_eq!(title(&"é".repeat(70)), format!("{}…", "é".repeat(60)));
        assert_eq!(title(&"x".repeat(60)), "x".repeat(60));
    }

    #[test]
    fn turn_agent_sets_the_guards_and_keeps_a_replace_persona() {
        let mut env = Env::new();
        env.insert(CONFIG_CONTENT.into(), r#"{"model":"a/b","agent":{"reidcc":{"mode":"primary","prompt":"{file:p.md}"}}}"#.into());
        turn_agent(&mut env, true);
        let config: Value = serde_json::from_str(&env[CONFIG_CONTENT]).unwrap();
        let agent = &config["agent"][TURN_AGENT];
        assert_eq!(agent["permission"]["*"], "deny");
        assert_eq!(agent["permission"]["read"], "allow");
        assert_eq!(agent["prompt"], "{file:p.md}");
        assert_eq!(config["model"], "a/b");
        let mut env = Env::new();
        turn_agent(&mut env, false);
        let config: Value = serde_json::from_str(&env[CONFIG_CONTENT]).unwrap();
        assert_eq!(config["agent"][TURN_AGENT]["permission"], json!({"bash": "deny", "task": "deny", "external_directory": "deny"}));
        assert!(config["agent"][TURN_AGENT].get("prompt").is_none());
    }
}
