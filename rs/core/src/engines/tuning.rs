//! Effort, MCP servers and plugins for a profile (SPEC-unified-interface Milestone 2C). A profile keeps
//! them as `effort` ("high"), `mcp_off` (["aca"]) and `plugins` ({"ponytail@ponytail": false}); a chat
//! lays the same keys over the profile for its own turns (`reid --stream --with`), and the launcher's
//! form writes them into reid.json.
use std::path::{Path, PathBuf};
use std::time::Duration;

use serde_json::Value;

use super::{codex, opencode};
use crate::{list, pyjson, text, Obj};

pub const CLAUDE_EFFORTS: [&str; 5] = ["low", "medium", "high", "xhigh", "max"];
pub const CODEX_EFFORTS: [&str; 5] = ["minimal", "low", "medium", "high", "xhigh"];
const CODEX_MCP_LIST_TIMEOUT: Duration = Duration::from_secs(10);

/// An installed plugin and whether this profile runs with it (before a chat's own changes).
#[derive(Clone, Debug, PartialEq)]
pub struct Plugin {
    pub id: String,
    pub on: bool,
}

/// What a profile can be tuned with: the effort levels, its MCP servers and its plugins.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Choices {
    pub efforts: Vec<String>,
    pub mcp: Vec<String>,
    pub plugins: Vec<Plugin>,
}

impl Choices {
    /// `{"efforts": [...], "mcp": [...], "plugins": [{"id", "on"}]}` for the chat pages.
    pub fn to_json(&self) -> Value {
        serde_json::json!({
            "efforts": self.efforts, "mcp": self.mcp,
            "plugins": self.plugins.iter().map(|p| serde_json::json!({"id": p.id, "on": p.on})).collect::<Vec<_>>(),
        })
    }
}

/// The profile's own plugin switches, in order.
fn plugin_switches(prof: &Obj) -> Vec<(String, bool)> {
    match prof.get("plugins") {
        Some(Value::Object(map)) => map.iter().map(|(id, on)| (id.clone(), pyjson::truthy(on))).collect(),
        _ => vec![],
    }
}

/// How Claude names a server in its tool names (`claude.ai Docs` -> `mcp__claude_ai_Docs__…`).
fn claude_tool_prefix(server: &str) -> String {
    let key: String = server.chars().map(|c| if c.is_ascii_alphanumeric() || c == '_' || c == '-' { c } else { '_' }).collect();
    format!("mcp__{key}")
}

/// Claude: `--effort`, and the tools of every server in `mcp_off` taken away (the server still starts;
/// its tools never reach the model).
pub fn claude_args(prof: &Obj) -> Vec<String> {
    let mut argv = vec![];
    let effort = text(prof, "effort");
    if !effort.is_empty() {
        argv.extend(["--effort".into(), effort]);
    }
    let off = list(prof, "mcp_off");
    if !off.is_empty() {
        argv.push("--disallowedTools".into());
        argv.extend(off.iter().map(|server| claude_tool_prefix(server)));
    }
    argv
}

/// Claude: the plugin switches as an `enabledPlugins` object for --settings (merged over the user's).
pub fn claude_plugins(prof: &Obj) -> Option<Value> {
    let switches = plugin_switches(prof);
    (!switches.is_empty()).then(|| Value::Object(switches.into_iter().map(|(id, on)| (id, Value::Bool(on))).collect()))
}

/// Codex: `-c` settings for effort, servers off and the plugin switches. Codex's `-c` can't address
/// `plugins."a@b".enabled`, so the whole plugins table goes, rebuilt from config.toml with the switches.
pub fn codex_args(prof: &Obj, codex_home: &str) -> Vec<String> {
    let mut argv = vec![];
    let effort = text(prof, "effort");
    if !effort.is_empty() {
        argv.extend(["-c".into(), format!("model_reasoning_effort={}", codex::toml_str(&effort))]);
    }
    for server in list(prof, "mcp_off") {
        argv.extend(["-c".into(), format!("mcp_servers.{}.enabled=false", codex::toml_key(&server))]);
    }
    let switches = plugin_switches(prof);
    if !switches.is_empty() {
        let mut table = codex_plugins(codex_home);
        for (id, on) in switches {
            match table.iter_mut().find(|plugin| plugin.id == id) {
                Some(plugin) => plugin.on = on,
                None => table.push(Plugin { id, on }),
            }
        }
        let entries: Vec<String> = table.iter().map(|p| format!("{}={{enabled={}}}", codex::toml_str(&p.id), p.on)).collect();
        argv.extend(["-c".into(), format!("plugins={{{}}}", entries.join(","))]);
    }
    argv
}

/// Models to offer for `engine`: Claude's names or what `opencode models` lists, then the ones other
/// profiles of that engine use.
pub fn models(cfg: &Obj, engine: &str) -> Vec<String> {
    let mut models: Vec<String> = match engine {
        "claude" => crate::BASE_MODELS.map(String::from).to_vec(),
        "opencode" => opencode::models(),
        _ => vec![],
    };
    let mut used: Vec<String> = crate::profiles(cfg).values().filter_map(Value::as_object)
        .filter(|prof| super::engine_of(prof, "").unwrap_or("claude") == engine)
        .map(|prof| text(prof, "model")).filter(|model| !model.is_empty() && !models.contains(model)).collect();
    used.sort();
    used.dedup();
    models.extend(used);
    models
}

/// What `name` can be tuned with in `cwd`.
pub fn choices(prof: &Obj, cwd: &str) -> Choices {
    if super::engine_name(prof) == "opencode" {
        // shortcut: OpenCode's MCP servers and plugins aren't offered (none to try them on, 2026-11-27); its
        // effort is the model's variants, looked up without a profile's sign-in file
        return Choices { efforts: opencode::variants(prof, &crate::environ(), cwd), ..Choices::default() };
    }
    if super::is_codex(prof) {
        let (home, mcp) = match codex::login_env() {
            Ok((exe, env)) => {
                let argv = [exe, "mcp".into(), "list".into(), "--json".into()];
                let listed = codex::run_capture(&argv, &env, Some(cwd), CODEX_MCP_LIST_TIMEOUT)
                    .and_then(|(code, out, _)| (code == 0).then_some(out))
                    .and_then(|out| serde_json::from_str::<Value>(&out).ok());
                let servers = listed.as_ref().and_then(Value::as_array).into_iter().flatten()
                    .filter(|server| server["enabled"].as_bool() != Some(false))
                    .filter_map(|server| server["name"].as_str().map(String::from)).collect();
                (codex::codex_home(&env), servers)
            }
            Err(_) => (String::new(), vec![]),
        };
        let mut plugins = codex_plugins(&home);
        apply_switches(&mut plugins, prof);
        return Choices { efforts: CODEX_EFFORTS.map(String::from).to_vec(), mcp, plugins };
    }
    let mut plugins = claude_plugins_installed(cwd);
    if let Some(Value::Object(settings)) = prof.get("settings_json") {
        if let Some(Value::Object(enabled)) = settings.get("enabledPlugins") {
            for plugin in &mut plugins {
                if let Some(on) = enabled.get(&plugin.id) {
                    plugin.on = pyjson::truthy(on);
                }
            }
        }
    }
    apply_switches(&mut plugins, prof);
    Choices { efforts: CLAUDE_EFFORTS.map(String::from).to_vec(), mcp: claude_servers(prof, cwd), plugins }
}

fn apply_switches(plugins: &mut [Plugin], prof: &Obj) {
    for (id, on) in plugin_switches(prof) {
        if let Some(plugin) = plugins.iter_mut().find(|plugin| plugin.id == id) {
            plugin.on = on;
        }
    }
}

fn read_json(path: &Path) -> Option<Value> {
    serde_json::from_str(&std::fs::read_to_string(path).ok()?).ok()
}

fn server_names(config: Option<&Value>, names: &mut Vec<String>) {
    for name in config.and_then(|c| c.get("mcpServers")).and_then(Value::as_object).into_iter().flat_map(|m| m.keys()) {
        if !names.contains(name) {
            names.push(name.clone());
        }
    }
}

/// Claude's MCP servers for this profile: its own config file when it names one (it runs with
/// --strict-mcp-config then), else the user's, this folder's in ~/.claude.json, and the folder's .mcp.json.
/// Servers that come with a plugin go with the plugin's switch.
fn claude_servers(prof: &Obj, cwd: &str) -> Vec<String> {
    let mut names = vec![];
    let own = text(prof, "mcp");
    if own == "none" {
        return names;
    }
    if !own.is_empty() {
        server_names(read_json(Path::new(&crate::py::expanduser(&own))).as_ref(), &mut names);
        return names;
    }
    let state_file = match std::env::var("CLAUDE_CONFIG_DIR").ok().filter(|d| !d.is_empty()) {
        Some(dir) => PathBuf::from(dir).join(".claude.json"),
        None => PathBuf::from(crate::py::expanduser("~/.claude.json")),
    };
    let state = read_json(&state_file);
    server_names(state.as_ref(), &mut names);
    let folder = cwd.replace('\\', "/").trim_end_matches('/').to_lowercase();
    let project = state.as_ref().and_then(|s| s.get("projects")).and_then(Value::as_object)
        .and_then(|projects| projects.iter().find(|(path, _)| path.replace('\\', "/").trim_end_matches('/').to_lowercase() == folder))
        .map(|(_, project)| project.clone());
    server_names(project.as_ref(), &mut names);
    server_names(read_json(&Path::new(cwd).join(".mcp.json")).as_ref(), &mut names);
    names
}

/// Claude's installed plugins, on where the user's or this folder's settings enable them.
fn claude_plugins_installed(cwd: &str) -> Vec<Plugin> {
    let dir = PathBuf::from(crate::session::claude_dir());
    let installed = read_json(&dir.join("plugins").join("installed_plugins.json"));
    let ids: Vec<String> = installed.as_ref().and_then(|d| d.get("plugins")).and_then(Value::as_object)
        .map(|m| m.keys().cloned().collect()).unwrap_or_default();
    let mut enabled = serde_json::Map::new();
    let project = Path::new(cwd).join(".claude");
    for settings in [dir.join("settings.json"), project.join("settings.json"), project.join("settings.local.json")] {
        if let Some(Value::Object(map)) = read_json(&settings).and_then(|s| s.get("enabledPlugins").cloned()) {
            enabled.extend(map);
        }
    }
    ids.into_iter().map(|id| Plugin { on: enabled.get(&id).is_some_and(pyjson::truthy), id }).collect()
}

/// Codex's plugins from config.toml's [plugins."id"] tables.
fn codex_plugins(codex_home: &str) -> Vec<Plugin> {
    let path = Path::new(codex_home).join("config.toml");
    let Some(config) = std::fs::read_to_string(path).ok().and_then(|t| t.parse::<toml::Table>().ok()) else { return vec![] };
    let Some(table) = config.get("plugins").and_then(toml::Value::as_table) else { return vec![] };
    table.iter().map(|(id, entry)| Plugin {
        id: id.clone(),
        on: entry.get("enabled").and_then(toml::Value::as_bool).unwrap_or(true),
    }).collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    fn prof(json: &str) -> Obj {
        serde_json::from_str(json).unwrap()
    }

    #[test]
    fn claude_flags() {
        let p = prof(r#"{"effort": "high", "mcp_off": ["aca", "claude.ai Docs"], "plugins": {"a@b": false, "c@d": true}}"#);
        assert_eq!(claude_args(&p), ["--effort", "high", "--disallowedTools", "mcp__aca", "mcp__claude_ai_Docs"]);
        assert_eq!(claude_plugins(&p), Some(serde_json::json!({"a@b": false, "c@d": true})));
        assert!(claude_args(&prof("{}")).is_empty() && claude_plugins(&prof("{}")).is_none());
    }

    #[test]
    fn codex_flags_rebuild_the_plugins_table() {
        let home = std::env::temp_dir().join(format!("reid_tuning_{}", std::process::id()));
        std::fs::create_dir_all(&home).unwrap();
        std::fs::write(home.join("config.toml"), "model = \"x\"\n[plugins.\"a@b\"]\nenabled = true\n[plugins.\"c@d\"]\nenabled = false\n").unwrap();
        let p = prof(r#"{"effort": "low", "mcp_off": ["node_repl", "odd name"], "plugins": {"a@b": false, "e@f": true}}"#);
        let argv = codex_args(&p, home.to_str().unwrap());
        assert_eq!(argv, ["-c", "model_reasoning_effort=\"low\"", "-c", "mcp_servers.node_repl.enabled=false",
                          "-c", "mcp_servers.\"odd name\".enabled=false",
                          "-c", "plugins={\"a@b\"={enabled=false},\"c@d\"={enabled=false},\"e@f\"={enabled=true}}"]);
        assert_eq!(codex_plugins(home.to_str().unwrap()), [Plugin { id: "a@b".into(), on: true }, Plugin { id: "c@d".into(), on: false }]);
        let _ = std::fs::remove_dir_all(home);
    }
}
