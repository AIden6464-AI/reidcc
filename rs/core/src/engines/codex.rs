//! Codex: the command for a Codex profile, its sign-in (codex login or a codex\*.toml provider
//! file) and its persona + memory prompt file (vision\SPEC-codex-signin-persona.md).

use super::{apply_env, claude_only_on, io, is_claude_model, need, Launch};
use crate::{err, environ, memory, on, on_by_default, py, pyjson, show_path, text, Ctx, Env, Obj, R};
use serde_json::{Number, Value};
use std::collections::HashSet;
use std::io::Read;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant, SystemTime};

pub const STATUS_LINE: [&str; 5] = ["model-with-reasoning", "current-dir", "context-used", "five-hour-limit", "weekly-limit"];
pub const LOGIN: &str = "codex login";
/// If Codex's own prompt can't be read, persona + memory up to this size go inline.
pub const INLINE_LIMIT: usize = 24000;

/// Reidcc in a Codex session: its status line (Codex only takes its own items) and our tab title.
pub fn ui_settings() -> [String; 2] {
    let items = Value::Array(STATUS_LINE.iter().map(|s| Value::String(s.to_string())).collect());
    [format!("tui.status_line={}", pyjson::dumps_compact(&items)), "tui.terminal_title=[]".into()]
}

/// codex.exe and the environment the npm wrapper would set. Never the npm .cmd shim: batch files
/// re-parse arguments through cmd.exe.
pub fn find_codex() -> R<(String, Vec<(String, String)>)> {
    if let Some(shim) = py::which("codex") {
        let pkg = py::join(&py::dirname(&shim), &["node_modules", "@openai", "codex"]);
        let arm = std::env::var("PROCESSOR_ARCHITECTURE").unwrap_or_default().to_uppercase() == "ARM64";
        let triple = if arm { "aarch64-pc-windows-msvc" } else { "x86_64-pc-windows-msvc" };
        let plat = if arm { "codex-win32-arm64" } else { "codex-win32-x64" };
        for exe in [py::join(&pkg, &["node_modules", "@openai", plat, "vendor", triple, "bin", "codex.exe"]),
                    py::join(&pkg, &["vendor", triple, "bin", "codex.exe"])] {
            if py::exists(&exe) {
                return Ok((exe, vec![("CODEX_MANAGED_PACKAGE_ROOT".into(), py::realpath(&pkg)),
                                     ("CODEX_MANAGED_BY_NPM".into(), "1".into())]));
            }
        }
    }
    if let Some(exe) = py::which("codex.exe") {
        return Ok((exe, vec![]));
    }
    // shortcut: a wrapper we can't see through (pnpm, volta, scoop, a .cmd of your own) runs as is, like
    // find_claude; cmd.exe may re-parse odd quotes in its arguments. Look inside more wrappers if one breaks.
    if let Some(shim) = py::which("codex") {
        return Ok((shim, vec![]));
    }
    err("Can't find Codex. Install it (npm install -g @openai/codex), then try again.")
}

/// The environment a `codex login` profile runs with: no stray API key may switch the billing.
pub fn login_env() -> R<(String, Env)> {
    let (exe, wrapper) = find_codex()?;
    let mut env = environ();
    env.extend(wrapper);
    for k in ["OPENAI_API_KEY", "CODEX_API_KEY"] {
        env.shift_remove(k);
    }
    Ok((exe, env))
}

/// subprocess.run(argv, capture_output=True, text=True, errors="replace", timeout=...):
/// (exit code, stdout, stderr), or None if it couldn't start or timed out.
pub fn run_capture(argv: &[String], env: &Env, cwd: Option<&str>, timeout: Duration) -> Option<(i32, String, String)> {
    use std::os::windows::process::CommandExt;
    let mut cmd = Command::new(&argv[0]);
    cmd.args(&argv[1..]).env_clear().envs(env).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::piped())
        .creation_flags(0x0800_0000); // CREATE_NO_WINDOW
    if let Some(c) = cwd.filter(|c| !c.is_empty()) {
        cmd.current_dir(c);
    }
    let mut child = cmd.spawn().ok()?;
    let mut pipes = [child.stdout.take().map(|p| Box::new(p) as Box<dyn Read + Send>),
                     child.stderr.take().map(|p| Box::new(p) as Box<dyn Read + Send>)];
    let readers: Vec<_> = pipes.iter_mut().map(|p| {
        let mut p = p.take();
        std::thread::spawn(move || {
            let mut buf = vec![];
            if let Some(p) = p.as_mut() {
                let _ = p.read_to_end(&mut buf);
            }
            String::from_utf8_lossy(&buf).replace("\r\n", "\n").replace('\r', "\n")
        })
    }).collect();
    let deadline = Instant::now() + timeout;
    let code = loop {
        match child.try_wait() {
            Ok(Some(s)) => break s.code().unwrap_or(1),
            Ok(None) if Instant::now() < deadline => std::thread::sleep(Duration::from_millis(20)),
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                return None;
            }
        }
    };
    let mut out = readers.into_iter().map(|r| r.join().unwrap_or_default());
    Some((code, out.next().unwrap_or_default(), out.next().unwrap_or_default()))
}

/// What `codex login status` says, in screen words; cached per CODEX_HOME (it takes about a
/// second). None when Codex can't be asked.
pub fn login(ctx: &Ctx, refresh: bool) -> Option<String> {
    let key = std::env::var("CODEX_HOME").unwrap_or_default();
    if !refresh {
        if let Some(s) = ctx.codex_login.lock().unwrap().get(&key) {
            return Some(s.clone());
        }
    }
    let (exe, env) = login_env().ok()?;
    let (code, out, errs) = run_capture(&[exe, "login".into(), "status".into()], &env, None, Duration::from_secs(15))?;
    let all = (out + &errs).to_lowercase();
    let s = if code != 0 || all.contains("not logged in") {
        "not signed in"
    } else if all.contains("chatgpt") {
        "ChatGPT"
    } else if all.contains("api key") {
        "API key"
    } else {
        "signed in"
    };
    ctx.codex_login.lock().unwrap().insert(key, s.into());
    Some(s.into())
}

pub fn login_cached(ctx: &Ctx) -> Option<String> {
    ctx.codex_login.lock().unwrap().get(&std::env::var("CODEX_HOME").unwrap_or_default()).cloned()
}

pub fn login_label(ctx: &Ctx) -> String {
    format!("{LOGIN} · {}", login_cached(ctx).unwrap_or_else(|| "checking…".into()))
}

/// Cache an answer `login()` got elsewhere (the GUI asks on a background thread with its own Ctx).
pub fn login_store(ctx: &Ctx, status: &str) {
    ctx.codex_login.lock().unwrap().insert(std::env::var("CODEX_HOME").unwrap_or_default(), status.into());
}

// ----------------------------------------------------------------- toml ---
/// JSON strings are TOML basic strings, except TOML also forbids a raw DEL.
pub fn toml_str(s: &str) -> String {
    pyjson::quote(s, false).replace('\x7f', "\\u007f")
}

pub(crate) fn toml_key(k: &str) -> String {
    if !k.is_empty() && k.chars().all(|c| c.is_ascii_alphanumeric() || c == '_' || c == '-') {
        k.to_string()
    } else {
        toml_str(k)
    }
}

fn iso(d: &toml::value::Datetime, sep: char) -> String {
    let mut s = String::new();
    if let Some(date) = &d.date {
        s += &format!("{:04}-{:02}-{:02}", date.year, date.month, date.day);
    }
    if let Some(t) = &d.time {
        if d.date.is_some() {
            s.push(sep);
        }
        s += &format!("{:02}:{:02}:{:02}", t.hour, t.minute, t.second);
        let micro = t.nanosecond / 1000;
        if micro != 0 {
            s += &format!(".{micro:06}");
        }
    }
    match &d.offset {
        Some(toml::value::Offset::Z) => s += "+00:00",
        Some(toml::value::Offset::Custom { minutes }) => {
            let m = minutes.unsigned_abs();
            s += &format!("{}{:02}:{:02}", if *minutes < 0 { '-' } else { '+' }, m / 60, m % 60);
        }
        None => {}
    }
    s
}

fn toml_value(v: &toml::Value) -> String {
    match v {
        toml::Value::Boolean(b) => if *b { "true" } else { "false" }.into(),
        toml::Value::Integer(i) => i.to_string(),
        toml::Value::Float(f) => py::float_repr(*f),
        toml::Value::Array(a) => format!("[{}]", a.iter().map(toml_value).collect::<Vec<_>>().join(", ")),
        toml::Value::Table(t) => format!("{{{}}}", t.iter().map(|(k, x)| format!("{} = {}", toml_key(k), toml_value(x)))
            .collect::<Vec<_>>().join(", ")),
        toml::Value::Datetime(d) => iso(d, 'T'),
        toml::Value::String(s) => toml_str(s),
    }
}

/// Python's str() of a TOML value (an [env] entry).
fn toml_py_str(v: &toml::Value) -> String {
    match v {
        toml::Value::String(s) => s.clone(),
        toml::Value::Boolean(b) => if *b { "True" } else { "False" }.into(),
        toml::Value::Datetime(d) => iso(d, ' '),
        other => toml_value(other),
    }
}

/// A codex\*.toml sign-in file -> (["key=value", ...] for -c, env). Tables become dotted keys so
/// they merge into Reid's Codex config instead of replacing it; [env] goes into the environment.
pub fn provider(path: &str) -> R<(Vec<(String, String)>, Vec<(String, String)>)> {
    let raw = std::fs::read(path).map_err(io)?;
    // The wording is toml's, not tomllib's (a known stage-0 gap); the location matches Python's.
    let located = |s: &str, e: toml::de::Error| match e.span() {
        Some(sp) => {
            let before = &s[..sp.start.min(s.len())];
            let line = before.matches('\n').count() + 1;
            let col = before.chars().rev().take_while(|&c| c != '\n').count() + 1;
            format!("{} (at line {line}, column {col})", e.message())
        }
        None => e.message().to_string(),
    };
    let parsed = std::str::from_utf8(&raw).map_err(|e| e.to_string())
        .and_then(|s| s.parse::<toml::Table>().map_err(|e| located(s, e)));
    let mut data = parsed.map_err(|e| crate::ReidError(format!("{} isn't valid TOML ({e}). Fix it, then try again.", show_path(path))))?;
    let env = match data.remove("env") {
        None => vec![],
        Some(toml::Value::Table(t)) => t.iter().map(|(k, v)| (k.clone(), toml_py_str(v))).collect(),
        Some(_) => return err(format!("{}: [env] has to be a table of NAME = \"value\". Fix it, then try again.", show_path(path))),
    };
    let mut pairs = vec![];
    fn walk(prefix: &str, t: &toml::Table, pairs: &mut Vec<(String, String)>) {
        for (k, v) in t {
            let key = format!("{prefix}{}", toml_key(k));
            match v {
                toml::Value::Table(sub) if !sub.is_empty() => walk(&format!("{key}."), sub, pairs),
                _ => pairs.push((key, toml_value(v))),
            }
        }
    }
    walk("", &data, &mut pairs);
    Ok((pairs, env))
}

// ----------------------------------------------------------------- args ---
/// The extra args that change Codex's config (and so its own prompt).
fn config_args(args: &[String]) -> Vec<String> {
    let mut out = vec![];
    let mut i = 0;
    while i < args.len() {
        let a = &args[i];
        if ["-c", "--config", "-p", "--profile", "--enable", "--disable"].contains(&a.as_str()) && i + 1 < args.len() {
            out.extend([a.clone(), args[i + 1].clone()]);
            i += 2;
            continue;
        }
        let short = a.chars().count() > 2 && (a.starts_with("-c") || a.starts_with("-p")) && !a.starts_with("--");
        if ["--config=", "--profile=", "--enable=", "--disable="].iter().any(|p| a.starts_with(p)) || short {
            out.push(a.clone());
        }
        i += 1;
    }
    out
}

fn config_keys(args: &[String]) -> Vec<String> {
    let mut keys = vec![];
    let mut i = 0;
    while i < args.len() {
        let a = &args[i];
        let mut kv = None;
        if (a == "-c" || a == "--config") && i + 1 < args.len() {
            kv = Some(args[i + 1].clone());
            i += 1;
        } else if let Some(rest) = a.strip_prefix("--config=") {
            kv = Some(rest.to_string());
        } else if a.starts_with("-c") && a.chars().count() > 2 && !a.starts_with("--") {
            kv = Some(a[2..].to_string());
        }
        if let Some(kv) = kv {
            keys.push(py::strip(kv.split('=').next().unwrap_or("")).to_string());
        }
        i += 1;
    }
    keys
}

/// codex\prompts\<profile>.md; names that aren't plain get a short hash so two can't collide.
pub fn prompt_path(ctx: &Ctx, name: &str) -> String {
    let (mut slug, mut run) = (String::new(), false);
    for c in name.to_lowercase().chars() {
        if c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-' {
            slug.push(c);
            run = false;
        } else if !run {
            slug.push('-'); // a run of other characters becomes one "-"
            run = true;
        }
    }
    let mut slug = slug.trim_matches('-').to_string();
    if slug.is_empty() {
        slug = "profile".into();
    }
    if slug != name {
        slug = format!("{slug}-{}", &py::sha1_hex(name)[..6]);
    }
    py::join(&ctx.codex_dir, &["prompts", &format!("{slug}.md")])
}

/// Codex's own prompt ("You are Codex…") for these settings, via `codex debug prompt-input` (no
/// model call). Cached in codex\prompts\.base-<key>.md until Codex, the settings or
/// ~/.codex/config.toml change. None if it can't be read.
fn base_prompt(ctx: &Ctx, exe: &str, env: &Env, pre: &[String], cwd: Option<&str>) -> Option<String> {
    let home = codex_home(env);
    let conf = py::join(&home, &["config.toml"]);
    let meta = std::fs::metadata(exe).ok()?;
    let mtime = py::getmtime(exe)?;
    let conf_m = if py::exists(&conf) { Value::Number(Number::from_f64(py::getmtime(&conf)?)?) } else { Value::from(0) };
    let key_src = Value::Array(vec![Value::from(meta.len()), Value::Number(Number::from_f64(mtime)?),
                                    Value::Array(pre.iter().map(|s| Value::String(s.clone())).collect()), conf_m,
                                    Value::String(home.clone())]);
    let key = &py::sha1_hex(&pyjson::dumps(&key_src, None, true))[..16];
    let dir = py::join(&ctx.codex_dir, &["prompts"]);
    let cache = py::join(&dir, &[&format!(".base-{key}.md")]);
    if py::exists(&cache) {
        return py::read_text(&cache, true).ok();
    }
    let mut argv = vec![exe.to_string()];
    argv.extend(pre.iter().cloned());
    argv.extend(["debug".into(), "prompt-input".into()]);
    let (code, out, _) = run_capture(&argv, env, cwd, Duration::from_secs(10))?;
    let items = if code == 0 { pyjson::loads(&out).ok()? } else { Value::Array(vec![]) };
    let mut base = None;
    for it in items.as_array().into_iter().flatten() {
        if it.get("type").and_then(Value::as_str) == Some("message") && it.get("role").and_then(Value::as_str) == Some("developer") {
            let t: String = it.get("content").and_then(Value::as_array).into_iter().flatten()
                .filter_map(|c| c.get("text").and_then(Value::as_str)).collect();
            if !py::strip(&t).is_empty() && !t.trim_start_matches(py::isspace).starts_with('<') {
                base = Some(t); // the others are <skills_…>, <multi_agent_…>
                break;
            }
        }
    }
    let base = base?;
    std::fs::create_dir_all(&dir).ok()?;
    if let Ok(rd) = std::fs::read_dir(&dir) {
        let now = std::time::SystemTime::now();
        for e in rd.flatten() {
            let n = e.file_name().to_string_lossy().into_owned();
            if n.starts_with(".base-") && n.ends_with(".md") {
                let old = e.metadata().ok().and_then(|m| m.modified().ok())
                    .and_then(|m| now.duration_since(m).ok()).is_some_and(|d| d.as_secs() > 30 * 86400);
                if old {
                    let _ = std::fs::remove_file(e.path());
                }
            }
        }
    }
    py::write_text(&cache, &base, true).ok()?;
    Some(base)
}

/// Codex's own folder for a launch: CODEX_HOME, else ~/.codex.
pub(crate) fn codex_home(env: &Env) -> String {
    env.get("CODEX_HOME").filter(|h| !h.is_empty()).cloned().unwrap_or_else(|| py::expanduser("~/.codex"))
}

/// Codex's thread files: sessions\YYYY\MM\DD\rollout-<time>-<thread id>.jsonl.
fn thread_files(env: &Env) -> Vec<PathBuf> {
    let mut level = vec![PathBuf::from(py::join(&codex_home(env), &["sessions"]))];
    for _ in 0..3 {
        level = level.iter().filter_map(|d| std::fs::read_dir(d).ok()).flatten().flatten()
            .filter(|e| e.file_type().is_ok_and(|t| t.is_dir())).map(|e| e.path()).collect();
    }
    level.iter().filter_map(|d| std::fs::read_dir(d).ok()).flatten().flatten().map(|e| e.path())
        .filter(|p| p.file_name().is_some_and(|n| { let n = n.to_string_lossy(); n.starts_with("rollout-") && n.ends_with(".jsonl") }))
        .collect()
}

pub fn thread_exists(env: &Env, id: &str) -> bool {
    !id.is_empty() && thread_files(env).iter().any(|p| p.to_string_lossy().ends_with(&format!("-{id}.jsonl")))
}

/// The thread a running Codex writes: a thread file changed since `since` and held open by `root` or a
/// process under it, so two windows in one folder each find their own (never "the newest thread").
/// Subagent threads (guardian…) are skipped. `skip` keeps files already known to be someone else's.
pub fn thread_of(env: &Env, root: u32, since: SystemTime, skip: &mut HashSet<PathBuf>) -> Option<String> {
    for p in thread_files(env) {
        if skip.contains(&p) || std::fs::metadata(&p).and_then(|m| m.modified()).map_or(true, |m| m < since) {
            continue;
        }
        if !crate::win::file_holders(&p.to_string_lossy()).iter().any(|&h| crate::win::descends_from(h, root)) {
            skip.insert(p); // another session's (or a finished one's): it never becomes ours
            continue;
        }
        let pl = session_meta(&p)?;
        if helper_thread(&pl) {
            skip.insert(p);
            continue;
        }
        return pl.get("id").and_then(Value::as_str).map(str::to_string);
    }
    None
}

/// The thread a Codex that already exited wrote, when thread_of never saw it (a message, then /quit
/// within the second between looks): the one thread file in `cwd` changed since `since` that nothing holds
/// open. Another window's is still held; two candidates means it can't tell, so none.
pub fn thread_left(env: &Env, cwd: &str, since: SystemTime, skip: &HashSet<PathBuf>) -> Option<String> {
    let same = |a: &str, b: &str| py::normcase(a.trim_end_matches('\\')) == py::normcase(b.trim_end_matches('\\'));
    let mut found = thread_files(env).into_iter()
        .filter(|p| !skip.contains(p) && std::fs::metadata(p).and_then(|m| m.modified()).is_ok_and(|m| m >= since))
        .filter(|p| crate::win::file_holders(&p.to_string_lossy()).is_empty())
        .filter_map(|p| session_meta(&p))
        .filter(|pl| !helper_thread(pl) && pl.get("cwd").and_then(Value::as_str).is_some_and(|c| same(c, cwd)))
        .filter_map(|pl| pl.get("id").and_then(Value::as_str).map(str::to_string));
    let id = found.next()?;
    found.next().is_none().then_some(id)
}

/// A thread file's first line: {"type":"session_meta","payload":{"id":…,"cwd":…}}.
fn session_meta(path: &Path) -> Option<Value> {
    let mut first = String::new();
    let _ = std::io::BufRead::read_line(&mut std::io::BufReader::new(std::fs::File::open(path).ok()?), &mut first);
    pyjson::loads(&first).ok()?.get("payload").cloned()
}

/// {"source": {"subagent": …}}: a helper thread (guardian…), not the session's own.
fn helper_thread(payload: &Value) -> bool {
    payload.get("source").is_some_and(Value::is_object)
}

/// Codex's command. `prepare` writes the prompt file (and may read Codex's own prompt, ~1 s the
/// first time); previews pass false and get the same command without touching anything.
pub fn build(ctx: &Ctx, cfg: &Obj, name: &str, prof: &Obj, extra: &[String], cwd: Option<&str>, prepare: bool) -> R<Launch> {
    let on_c = claude_only_on(prof);
    if !on_c.is_empty() {
        let listing = if on_c.len() > 1 {
            format!("{} and {}", on_c[..on_c.len() - 1].join(", "), on_c[on_c.len() - 1])
        } else {
            on_c[0].to_string()
        };
        return err(format!("Codex can't use {listing}. Turn {} off for {name}, or pick a Claude profile.",
                           if on_c.len() > 1 { "them" } else { "it" }));
    }
    crate::proxy::plan(ctx, prof)?; // validates the proxy field
    let model = text(prof, "model");
    if is_claude_model(&model) {
        return err(format!("{model} is a Claude model. Clear the model to use Codex's default, or type a Codex model."));
    }
    let settings = text(prof, "settings");
    if !settings.is_empty() && !settings.to_lowercase().ends_with(".toml") {
        return err(format!("{settings} is a Claude sign-in file. Pick a Codex one, or use codex login."));
    }
    let ppath = match text(prof, "persona") {
        p if p.is_empty() => String::new(),
        p => need(ctx, name, &p, "persona file")?,
    };
    let prompt_on = !ppath.is_empty() || on(prof, "memory").is_some();

    let mut args = crate::args(prof);
    args.extend(extra.iter().cloned());
    for a in &args {
        if a == "-C" || a == "--cd" || a.starts_with("--cd=") || (a.starts_with("-C") && a.chars().count() > 2) {
            return err("Leave -C / --cd out of the extra args: Codex opens in the folder you picked.");
        }
    }
    for k in config_keys(&args) {
        if prompt_on && (k == "model_instructions_file" || k == "developer_instructions") {
            return err(format!("Leave {k} out of the extra args: it would replace the persona."));
        }
        if !settings.is_empty() && k == "model_provider" {
            return err("Leave model_provider out of the extra args: the sign-in file sets it.");
        }
    }

    let mut pre: Vec<String> = if model.is_empty() { vec![] } else { vec!["-m".into(), model.clone()] };
    let (exe, mut env) = if !settings.is_empty() {
        let (exe, wrapper) = find_codex()?;
        let mut env = environ();
        env.extend(wrapper);
        let (pairs, penv) = provider(&need(ctx, name, &settings, "sign-in file")?)?;
        for (k, v) in pairs {
            if !(!model.is_empty() && k == "model") {
                pre.extend(["-c".into(), format!("{k}={v}")]); // the profile's own model wins
            }
        }
        env.extend(penv);
        (exe, env)
    } else {
        let (exe, env) = login_env()?;
        if prepare && matches!(login_cached(ctx).as_deref(), None | Some("not signed in")) {
            login(ctx, true);
        }
        if login_cached(ctx).as_deref() == Some("not signed in") {
            return err("Codex isn't signed in. Run codex login in a terminal, then try again.");
        }
        (exe, env)
    };
    apply_env(&mut env, prof);

    let mut argv = vec![exe.clone()];
    argv.extend(pre.iter().cloned());
    let ui = ui_settings();
    for s in if on_by_default(prof, "statusline") { &ui[..] } else { &ui[1..] } {
        argv.extend(["-c".into(), s.clone()]); // before the extra args, so a -c of your own there still wins
    }
    argv.extend(super::tuning::codex_args(prof, &codex_home(&env)));
    if prompt_on {
        let mut pfile = Some(prompt_path(ctx, name));
        let mut setting = format!("model_instructions_file={}", toml_str(&pfile.as_ref().unwrap().replace('\\', "/")));
        if prepare {
            let persona = if ppath.is_empty() { String::new() } else { py::read_text(&ppath, false).map_err(crate::ReidError)? };
            let mut body = format!("{}\n", (persona.clone() + &memory::memory_block(ctx, cfg, prof).map_err(io)?).trim_matches('\n'));
            if !(!persona.is_empty() && text(prof, "mode") == "replace") {
                // add mode: Codex's own prompt first, untouched, then the persona and memory
                let mut pa = pre.clone();
                pa.extend(config_args(&args));
                match base_prompt(ctx, &exe, &env, &pa, cwd) {
                    Some(base) => body = format!("{}\n\n{body}", base.trim_end_matches('\n')),
                    None if body.chars().count() <= INLINE_LIMIT => {
                        setting = format!("developer_instructions={}", toml_str(&body));
                        pfile = None;
                    }
                    None => return err("Couldn't read Codex's own prompt to add the persona to. Use replace mode, or update Reidcc."),
                }
            }
            if let Some(p) = &pfile {
                std::fs::create_dir_all(py::dirname(p)).map_err(io)?;
                py::write_text(p, &body, true).map_err(io)?; // \n only: \r\n would change the text
            }
        }
        argv.extend(["-c".into(), setting]);
    }
    argv.extend(args);
    Ok(Launch { argv, env, temps: vec![] })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn thread_left_finds_the_one_unheld_thread_in_the_folder() {
        let home = std::env::temp_dir().join(format!("reid_codex_threads_{}", std::process::id()));
        let day = home.join("sessions").join("2026").join("11").join("26");
        std::fs::create_dir_all(&day).unwrap();
        let work = home.join("work").to_string_lossy().into_owned();
        let write = |id: &str, cwd: &str, source: &str| {
            let meta = serde_json::json!({"type": "session_meta", "payload": {"id": id, "cwd": cwd, "source": serde_json::from_str::<Value>(source).unwrap()}});
            std::fs::write(day.join(format!("rollout-2026-11-26T20-00-00-{id}.jsonl")), format!("{meta}\n")).unwrap();
        };
        let env: Env = [("CODEX_HOME".to_string(), home.to_string_lossy().into_owned())].into_iter().collect();
        let since = SystemTime::now() - Duration::from_secs(2);
        write("t-other", r"C:\elsewhere", "\"cli\"");
        write("t-helper", &work, "{\"subagent\": \"guardian\"}");
        assert_eq!(thread_left(&env, &work, since, &HashSet::new()), None);
        write("t-mine", &format!("{work}\\"), "\"cli\"");
        assert_eq!(thread_left(&env, &work, since, &HashSet::new()).as_deref(), Some("t-mine"));
        // a second candidate in the folder: can't tell which was ours
        write("t-mine-too", &work, "\"cli\"");
        assert_eq!(thread_left(&env, &work, since, &HashSet::new()), None);
        let _ = std::fs::remove_dir_all(&home);
    }
}
