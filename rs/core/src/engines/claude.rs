//! Claude Code: the command for a Claude profile.

use super::{apply_env, io, need, Launch};
use crate::{err, environ, list, memory, on, on_by_default, py, pyjson, text, Ctx, Obj, R};
use serde_json::Value;

/// Prefer the real claude.exe so args never pass through cmd.exe quoting.
pub fn find_claude() -> R<String> {
    let shim = py::which("claude");
    if let Some(s) = &shim {
        let exe = py::join(&py::dirname(s), &["node_modules", "@anthropic-ai", "claude-code", "bin", "claude.exe"]);
        if py::exists(&exe) {
            return Ok(exe);
        }
    }
    let native = py::expanduser("~/.local/bin/claude.exe");
    if py::exists(&native) {
        return Ok(native);
    }
    if let Some(s) = shim {
        return Ok(s);
    }
    // Also hit for a moment while Claude Code updates itself (its files are being replaced).
    err("Can't find Claude Code. If it's updating, this clears in a moment; otherwise install it.")
}

pub fn build(ctx: &Ctx, cfg: &Obj, name: &str, prof: &Obj, extra: &[String], cwd: Option<&str>) -> R<Launch> {
    let settings_field = text(prof, "settings");
    if settings_field.to_lowercase().ends_with(".toml") {
        return err(format!("{settings_field} is a Codex sign-in file. Pick a Claude one, or use subscription."));
    }
    let mut argv = vec![find_claude()?];
    let mut env = environ();
    let mut temps = vec![];

    let mut settings = if settings_field.is_empty() { String::new() } else { need(ctx, name, &settings_field, "settings file")? };
    let ppath = match text(prof, "persona") {
        p if p.is_empty() => String::new(),
        p => need(ctx, name, &p, "persona file")?,
    };
    let mcp = text(prof, "mcp");
    let mcp_path = if !mcp.is_empty() && mcp != "none" { need(ctx, name, &mcp, "MCP config")? } else { String::new() };
    let extra_settings = match on(prof, "settings_json") {
        None => crate::Obj::new(),
        Some(Value::Object(m)) => m.clone(),
        Some(_) => return err(format!("Profile {name}: settings_json has to be an object. Fix it in reid.json.")),
    };
    crate::proxy::plan(ctx, prof)?; // validates the proxy field

    let model = text(prof, "model");
    if !model.is_empty() {
        argv.extend(["--model".into(), model]);
    }
    // Auth: a settings file means API mode (the file carries key + base URL).
    // No settings file means your Pro/Max login, so strip inherited API creds.
    if settings.is_empty() {
        for k in ["ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"] {
            env.shift_remove(k);
        }
    }
    let statusline = on_by_default(prof, "statusline"); // reid's telemetry line; "statusline": false opts out
    if !extra_settings.is_empty() || statusline {
        // Claude takes one --settings, so merge the profile's extras onto the file.
        let mut merged = Value::Object(crate::Obj::new());
        if !settings.is_empty() {
            let bad = |e: String| crate::ReidError(format!("{} isn't valid JSON ({e}). Fix it, then try again.", crate::show_path(&settings)));
            merged = pyjson::loads(&py::read_text(&settings, false).map_err(bad)?).map_err(bad)?;
        }
        let Value::Object(m) = &mut merged else {
            return err(format!("{} has to hold a JSON object. Fix it, then try again.", crate::show_path(&settings)));
        };
        for (k, v) in extra_settings {
            let joined = match (&v, m.get(&k)) {
                (Value::Object(new), Some(Value::Object(old))) => {
                    let mut o = old.clone();
                    o.extend(new.clone());
                    Value::Object(o)
                }
                _ => v,
            };
            m.insert(k, joined);
        }
        if statusline && !m.contains_key("statusLine") {
            m.insert("statusLine".into(), serde_json::json!({"type": "command", "command": ctx.statusline_command()}));
        }
        // the pid in the name tells sweep_temps the file belongs to a session that's still running
        settings = py::mkstemp(&format!("reid_settings_{}_", std::process::id()), ".json", &pyjson::dumps(&merged, Some(2), true)).map_err(io)?;
        temps.push(settings.clone());
    }
    if !settings.is_empty() {
        argv.extend(["--settings".into(), settings]);
    }

    let mut persona = if ppath.is_empty() { String::new() } else { py::read_text(&ppath, false).map_err(crate::ReidError)? };
    let replace = !persona.is_empty() && text(prof, "mode") == "replace";
    if replace {
        // Replacing Claude Code's prompt drops its environment section; put the basics back.
        persona = format!("{}\n\nWorking directory: {}. Platform: Windows; shells: PowerShell and Git Bash.\n",
                          py::rstrip(&persona), cwd.map(String::from).unwrap_or_else(py::getcwd));
    }
    let prompt = persona + &memory::memory_block(ctx, cfg, prof).map_err(io)?;
    if !py::strip(&prompt).is_empty() {
        let pfile = match py::mkstemp(&format!("reid_prompt_{}_", std::process::id()), ".md", &prompt) {
            Ok(p) => p,
            Err(e) => {
                for t in &temps {
                    let _ = std::fs::remove_file(t);
                }
                return Err(io(e));
            }
        };
        temps.push(pfile.clone());
        argv.extend([if replace { "--system-prompt-file" } else { "--append-system-prompt-file" }.into(), pfile]);
    }

    if prof.contains_key("tools") {
        argv.extend(["--tools".into(), list(prof, "tools").join(",")]);
    }
    if !mcp_path.is_empty() {
        argv.extend(["--mcp-config".into(), mcp_path]);
    }
    if !mcp.is_empty() || on(prof, "safe").is_some() {
        argv.push("--strict-mcp-config".into());
    }
    if on(prof, "no_chrome").is_some() {
        argv.push("--no-chrome".into());
    }
    if on(prof, "no_connectors").is_some() {
        env.insert("ENABLE_CLAUDEAI_MCP_SERVERS".into(), "false".into());
    }
    if on(prof, "safe").is_some() {
        env.insert("CLAUDE_CODE_DISABLE_CLAUDE_MDS".into(), "1".into());
        if !settings_field.is_empty() {
            argv.push("--bare".into()); // --bare skips OAuth, so only valid in API mode
        }
    }
    apply_env(&mut env, prof);
    argv.extend(crate::args(prof));
    argv.extend(extra.iter().cloned());
    Ok(Launch { argv, env, temps })
}
