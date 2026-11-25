//! Reidcc's core: profiles, engines, memory, state and the proxy, reading and writing the same
//! files as reid.py (vision\Spec\SPEC-rust-rewrite.md, stage 0). Python behaviour that shows in
//! output is mirrored in `py` and `pyjson`.

pub mod engines;
pub mod memory;
pub mod profile;
pub mod proxy;
pub mod py;
pub mod pyjson;
pub mod session;
pub mod term;
pub mod win;

use indexmap::IndexMap;
use serde_json::{Map, Value};
use std::sync::Mutex;
use std::collections::HashMap;

pub type Obj = Map<String, Value>;
/// A process environment the way Python's os.environ copy behaves on Windows: keys from the
/// real environment are upper-cased, keys a profile sets are kept as written.
pub type Env = IndexMap<String, String>;

#[derive(Debug)]
pub struct ReidError(pub String);

impl std::fmt::Display for ReidError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        f.write_str(&self.0)
    }
}

pub type R<T> = Result<T, ReidError>;

pub fn err<T>(msg: impl Into<String>) -> R<T> {
    Err(ReidError(msg.into()))
}

pub const MEMORY_LIMIT: usize = 6000;
pub const PINNED: &str = "## Pinned facts";
pub const JOURNAL: &str = "## Journal";
pub const BASE_MODELS: [&str; 4] = ["opus", "sonnet", "haiku", "fable"];

/// Where Reidcc's files are, and what this process caches.
pub struct Ctx {
    pub home: String,
    pub config: String,
    pub state: String,
    pub codex_dir: String,
    pub proxy_dir: String,
    /// argv prefix that runs this CLI: Claude Code runs it for the statusline.
    pub cli: Vec<String>,
    pub(crate) codex_login: Mutex<HashMap<String, String>>,
}

impl Ctx {
    pub fn new() -> Ctx {
        let ctx = Ctx::at(&home_dir());
        apply_locations(&peek_config(&ctx));
        ctx
    }

    pub fn at(home: &str) -> Ctx {
        let exe = std::env::current_exe().map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
        Ctx {
            home: home.to_string(),
            config: py::join(home, &["reid.json"]),
            state: py::join(home, &["reid_state.json"]),
            codex_dir: py::join(home, &["codex"]),
            proxy_dir: py::join(home, &["proxy"]),
            cli: vec![exe],
            codex_login: Mutex::new(HashMap::new()),
        }
    }

    /// Relative paths in reid.json resolve against the Reidcc folder.
    pub fn resolve(&self, path: &str) -> String {
        if path.is_empty() {
            return String::new();
        }
        let p = py::expandvars(&py::expanduser(path));
        py::normpath(&if py::isabs(&p) { p } else { py::join(&self.home, &[&p]) })
    }

    /// Paths inside the Reidcc folder are stored relative to it.
    pub fn relpath(&self, path: &str) -> String {
        let path = py::normpath(&py::abspath(path));
        match py::relpath(&path, &self.home) {
            Some(rel) if !rel.starts_with("..") => rel.replace('\\', "/"),
            _ => path,
        }
    }

    pub fn statusline_command(&self) -> String {
        self.cli.iter().map(String::as_str).chain(["--statusline"])
            .map(|a| format!("\"{}\"", a.replace('\\', "/"))).collect::<Vec<_>>().join(" ")
    }
}

impl Default for Ctx {
    fn default() -> Self {
        Ctx::new()
    }
}

/// reid.json as it is on disk, without load_config's first-run write or checks ({} if missing or bad).
pub fn peek_config(ctx: &Ctx) -> Obj {
    match py::read_text(&ctx.config, false).ok().and_then(|t| pyjson::loads(&t).ok()) {
        Some(Value::Object(o)) => o,
        _ => Obj::new(),
    }
}

/// The settings page's location choices, for this process and everything it starts: `temp_dir` ->
/// TMPDIR (gettempdir looks there first), `ai_temp_dir` -> CLAUDE_CODE_TMPDIR (Claude Code's scratch
/// folder). A key that's gone, or not a folder, puts back what the environment had at start.
pub fn apply_locations(cfg: &Obj) {
    static ORIG: std::sync::OnceLock<[Option<String>; 2]> = std::sync::OnceLock::new();
    let orig = ORIG.get_or_init(|| [std::env::var("TMPDIR").ok(), std::env::var("CLAUDE_CODE_TMPDIR").ok()]);
    for (i, (key, var)) in [("temp_dir", "TMPDIR"), ("ai_temp_dir", "CLAUDE_CODE_TMPDIR")].into_iter().enumerate() {
        match cfg.get(key).and_then(Value::as_str).filter(|d| py::isdir(d)) {
            Some(d) => std::env::set_var(var, d),
            None => match &orig[i] {
                Some(v) => std::env::set_var(var, v),
                None => std::env::remove_var(var),
            },
        }
    }
}

/// The Reidcc data folder: REIDCC_HOME, else the nearest folder above this exe with a reid.json
/// (E:\reidcc for rs\target\release\reid.exe and for app\reid.exe), else %USERPROFILE%\Reidcc (an installed copy).
pub fn home_dir() -> String {
    if let Ok(h) = std::env::var("REIDCC_HOME") {
        if !h.is_empty() {
            return py::abspath(&h);
        }
    }
    default_home_dir()
}

/// Where this copy keeps its data when REIDCC_HOME isn't set (settings: `local data` back to the default).
pub fn default_home_dir() -> String {
    let exe = std::env::current_exe().map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
    let exe_dir = py::dirname(&py::abspath(&exe));
    let mut d = exe_dir.clone();
    loop {
        if py::exists(&py::join(&d, &["reid.json"])) {
            return d;
        }
        let up = py::dirname(&d);
        if up == d {
            // an installed copy: your own folder, made by the first load_config, never by the installer
            return match std::env::var("USERPROFILE") {
                Ok(u) if !u.is_empty() => py::join(&u, &["Reidcc"]),
                _ => py::dirname(&exe_dir),
            };
        }
        d = up;
    }
}

/// Add PATH entries the registry has but our environment lacks (Explorer can hand apps a stale
/// PATH). Entries we were given come first and stay.
pub fn refresh_path() {
    // Windows looks in the current folder before PATH, so a claude.cmd in a cloned repo would run
    // instead of Claude. This turns that off for py::which and for everything we start.
    std::env::set_var("NoDefaultCurrentDirectoryInExePath", "1");
    let reg: Vec<String> = win::registry_paths().iter()
        .flat_map(|v| v.split(';').filter(|p| !p.is_empty()).map(py::expandvars).collect::<Vec<_>>()).collect();
    let mut have: Vec<String> = std::env::var("PATH").unwrap_or_default().split(';')
        .filter(|p| !p.is_empty()).map(String::from).collect();
    let key = |p: &str| py::normcase(p.trim_end_matches(['\\', '/']));
    let mut seen: std::collections::HashSet<String> = have.iter().map(|p| key(p)).collect();
    for p in reg {
        if seen.insert(key(&p)) {
            have.push(p);
        }
    }
    std::env::set_var("PATH", have.join(";"));
}

/// dict(os.environ)
pub fn environ() -> Env {
    let mut e = Env::new();
    for (k, v) in std::env::vars_os() {
        e.insert(k.to_string_lossy().to_uppercase(), v.to_string_lossy().into_owned());
    }
    e
}

/// os.environ.get(k): case-insensitive.
pub fn getenv(k: &str) -> Option<String> {
    std::env::var(k).ok()
}

/// A path the way the voice guide writes it: home as ~, forward slashes.
pub fn show_path(path: &str) -> String {
    let mut path = py::normpath(path);
    let home = py::normpath(&py::expanduser("~"));
    let (np, nh) = (py::normcase(&path), py::normcase(&home));
    if np == nh {
        path = "~".into();
    } else if np.starts_with(&(nh + "\\")) {
        path = format!("~{}", &path[home.len()..]);
    }
    path.replace('\\', "/")
}

// ---------------------------------------------------------------- config ---
pub fn default_config() -> Value {
    // no memory_file: reidcc_memory.md is its default, and a setting at its default isn't written
    serde_json::json!({"default": "main", "profiles": {"main": {"model": "opus", "memory": true}}})
}

/// json.dump(indent=2, ensure_ascii=False) to a temp file, then replace.
pub fn save_json(path: &str, data: &Value) -> std::io::Result<()> {
    let tmp = format!("{path}.{}.tmp", std::process::id()); // per process: two writers never share a temp file
    py::write_text(&tmp, &pyjson::dumps(data, Some(2), false), false)?;
    std::fs::rename(&tmp, path)
}

pub fn load_config(ctx: &Ctx) -> R<Obj> {
    if !py::exists(&ctx.config) {
        let _ = std::fs::create_dir_all(&ctx.home); // first run of an installed copy: %USERPROFILE%\Reidcc
        save_json(&ctx.config, &default_config()).map_err(|e| ReidError(format!(
            "Can't make the Reidcc folder {} ({e}). Set REIDCC_HOME to a folder you can write to.", ctx.home)))?;
    }
    let bad = |e: String| ReidError(format!("reid.json has an error ({e}). Fix it, then try again."));
    let text = py::read_text(&ctx.config, false).map_err(bad)?;
    let Value::Object(mut cfg) = pyjson::loads(&text).map_err(bad)? else {
        return Err(bad("it isn't an object".into()));
    };
    let has = cfg.get("profiles").is_some_and(pyjson::truthy);
    match cfg.get("profiles") {
        Some(Value::Object(_)) | None => {}
        Some(v) if !pyjson::truthy(v) => {}
        _ => return Err(bad("profiles isn't an object".into())),
    }
    if !has {
        cfg.insert("profiles".into(), default_config()["profiles"].clone());
    }
    let default_ok = match cfg.get("default") {
        Some(Value::String(d)) => cfg["profiles"].as_object().unwrap().contains_key(d),
        _ => false,
    };
    if !default_ok {
        let first = cfg["profiles"].as_object().unwrap().keys().next().cloned().unwrap();
        cfg.insert("default".into(), Value::String(first));
    }
    Ok(cfg)
}

pub fn profiles(cfg: &Obj) -> &Obj {
    cfg["profiles"].as_object().expect("load_config checked profiles")
}

pub fn default_profile(cfg: &Obj) -> &str {
    cfg["default"].as_str().expect("load_config checked default")
}

pub fn load_state(ctx: &Ctx) -> Obj {
    py::read_text(&ctx.state, false).ok().and_then(|t| pyjson::loads(&t).ok())
        .and_then(|v| if let Value::Object(m) = v { Some(m) } else { None }).unwrap_or_default()
}

/// Folder history always; the resume record (`last`) only for sessions `resume` can reopen.
pub fn remember_session(ctx: &Ctx, name: &str, cwd: &str, sid: Option<&str>, last: bool) -> std::io::Result<()> {
    let lock = take_lock(&format!("{}.lock", ctx.state), 5.0, 10.0);
    let res = remember_locked(ctx, name, cwd, sid, last);
    if let Some(l) = lock {
        let _ = std::fs::remove_file(l);
    }
    res
}

/// A lock file around a read-change-write that several sessions (and reid.py) can do at once.
/// Returns the path to remove when done, or None after `wait` seconds: saving unlocked beats
/// losing the write. A lock older than `stale` seconds was left by a killed process.
pub fn take_lock(path: &str, wait: f64, stale: f64) -> Option<String> {
    use std::time::{Duration, Instant, SystemTime};
    let end = Instant::now() + Duration::from_secs_f64(wait);
    loop {
        if std::fs::OpenOptions::new().write(true).create_new(true).open(path).is_ok() {
            return Some(path.into());
        }
        // exists, or is being deleted
        let age = std::fs::metadata(path).and_then(|m| m.modified()).ok()
            .and_then(|m| SystemTime::now().duration_since(m).ok());
        if age.is_some_and(|a| a.as_secs_f64() > stale) && std::fs::remove_file(path).is_ok() {
            continue;
        }
        if Instant::now() > end {
            return None;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
}

fn remember_locked(ctx: &Ctx, name: &str, cwd: &str, sid: Option<&str>, last: bool) -> std::io::Result<()> {
    let mut st = load_state(ctx);
    if last {
        let (y, mo, d, h, mi, s) = py::now_local();
        st.insert("last".into(), serde_json::json!({
            "profile": name, "cwd": cwd, "sid": sid,
            "at": format!("{y:04}-{mo:02}-{d:02}T{h:02}:{mi:02}:{s:02}")}));
    }
    let mut dirs = vec![Value::String(cwd.into())];
    if let Some(Value::Array(old)) = st.get("recent_dirs") {
        dirs.extend(old.iter().filter(|d| py::normcase(&pyjson::py_str(d)) != py::normcase(cwd)).cloned());
    }
    dirs.truncate(10);
    st.insert("recent_dirs".into(), Value::Array(dirs));
    save_json(&ctx.state, &Value::Object(st))
}

// ------------------------------------------------------------- updates ---
// vision/Spec/SPEC-github-repo.md Part 4. The launcher checks; reid only reads what it saved.

/// The folder the installer registered (its Add/Remove Programs entry), if Reidcc is installed.
pub fn install_dir() -> Option<String> {
    win::hkcu_str(r"Software\Microsoft\Windows\CurrentVersion\Uninstall\Reidcc", "InstallLocation")
        .map(|d| d.trim_matches('"').to_string()).filter(|d| !d.is_empty())
}

/// Only installed copies update: dev builds and portable folders never try to.
pub fn installed_copy() -> bool {
    let exe = std::env::current_exe().map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
    install_dir().is_some_and(|d| py::normcase(d.trim_end_matches('\\')) == py::normcase(&py::dirname(&exe)))
}

/// `a` is a later version than `b` ("0.10.0" > "0.9.3").
pub fn newer(a: &str, b: &str) -> bool {
    let nums = |v: &str| v.split('.').map(|p| p.parse::<u64>().unwrap_or(0)).collect::<Vec<_>>();
    nums(a) > nums(b)
}

/// The update the launcher last saw, while it's still newer than this build.
pub fn pending_update(ctx: &Ctx) -> Option<String> {
    let v = load_state(ctx).get("update").map(pyjson::py_str)?;
    newer(&v, env!("CARGO_PKG_VERSION")).then_some(v)
}

/// Save (or clear) the update the launcher saw, for the TUI's footer.
pub fn save_update(ctx: &Ctx, version: Option<&str>) {
    let lock = take_lock(&format!("{}.lock", ctx.state), 5.0, 10.0);
    let mut st = load_state(ctx);
    let changed = match version {
        Some(v) => st.insert("update".into(), Value::String(v.into())) != Some(Value::String(v.into())),
        None => st.remove("update").is_some(),
    };
    if changed {
        let _ = save_json(&ctx.state, &Value::Object(st));
    }
    if let Some(l) = lock {
        let _ = std::fs::remove_file(l);
    }
}

/// A profile field, if Python would call it true.
pub fn on<'a>(prof: &'a Obj, key: &str) -> Option<&'a Value> {
    prof.get(key).filter(|v| pyjson::truthy(v))
}

/// prof.get(key) as text (str() of it), "" when missing or false.
pub fn text(prof: &Obj, key: &str) -> String {
    on(prof, key).map(pyjson::py_str).unwrap_or_default()
}

/// prof.get(key, True): a missing key counts as on.
pub fn on_by_default(prof: &Obj, key: &str) -> bool {
    prof.get(key).is_none_or(pyjson::truthy)
}

/// list(prof.get(key) or []) as text: a string becomes its characters, as in Python.
pub fn list(prof: &Obj, key: &str) -> Vec<String> {
    match on(prof, key) {
        Some(Value::Array(a)) => a.iter().map(pyjson::py_str).collect(),
        Some(Value::String(s)) => s.chars().map(String::from).collect(),
        Some(Value::Object(m)) => m.keys().cloned().collect(),
        _ => vec![],
    }
}

/// A profile's extra args. A string is split like a command line, not into letters:
/// `"args": "--verbose --x \"a b\""` is ["--verbose", "--x", "a b"].
pub fn args(prof: &Obj) -> Vec<String> {
    match on(prof, "args") {
        Some(Value::String(s)) => args_parse(s),
        _ => list(prof, "args"),
    }
}

/// Split an extra-args line the way Windows does (reid.py's args_parse): spaces separate, double quotes
/// group, \" is a quote, backslashes stay as typed.
pub fn args_parse(text: &str) -> Vec<String> {
    let t: Vec<char> = text.chars().collect();
    let (mut out, mut cur, mut quoted, mut started, mut i) = (vec![], String::new(), false, false, 0);
    while i < t.len() {
        let c = t[i];
        if c == '\\' {
            let n = t[i..].iter().take_while(|&&c| c == '\\').count();
            if i + n < t.len() && t[i + n] == '"' {
                cur.push_str(&"\\".repeat(n / 2));
                if n % 2 == 1 {
                    cur.push('"');
                    i += n + 1;
                } else {
                    i += n;
                }
                started = true;
                continue;
            }
            cur.push_str(&"\\".repeat(n));
            i += n;
            started = true;
            continue;
        }
        if c == '"' {
            quoted = !quoted;
            started = true;
        } else if py::isspace(c) && !quoted {
            if started {
                out.push(std::mem::take(&mut cur));
                started = false;
            }
        } else {
            cur.push(c);
            started = true;
        }
        i += 1;
    }
    if started {
        out.push(cur);
    }
    out
}

pub fn memory_path(ctx: &Ctx, cfg: &Obj, prof: Option<&Obj>) -> String {
    let p = prof.map(|p| text(p, "memory_file")).filter(|s| !s.is_empty())
        .or_else(|| on(cfg, "memory_file").map(pyjson::py_str))
        .unwrap_or_else(|| "reidcc_memory.md".into());
    ctx.resolve(&p)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn string_args_split_like_a_command_line_not_into_letters() {
        let prof = |v: Value| v.as_object().unwrap().clone();
        assert_eq!(args(&prof(serde_json::json!({"args": "--version"}))), vec!["--version"]);
        assert_eq!(args(&prof(serde_json::json!({"args": r#"--add-dir "D:\Shared Work" -v"#}))),
                   vec!["--add-dir", r"D:\Shared Work", "-v"]);
        assert_eq!(args(&prof(serde_json::json!({"args": ["--a", "b c"]}))), vec!["--a", "b c"]);
        assert!(args(&prof(serde_json::json!({}))).is_empty());
    }

    #[test]
    fn versions_compare_by_number_not_by_text() {
        assert!(newer("0.10.0", "0.9.3"));
        assert!(newer("0.2.1", "0.2.0") && newer("1.0", "0.99.99"));
        assert!(!newer("0.2.0", "0.2.0") && !newer("0.1.9", "0.2.0"));
    }
}
