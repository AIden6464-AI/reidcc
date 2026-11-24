//! The proxy: mitmproxy add-ons in proxy\ (SPEC-proxy.md). They stay Python; Reidcc starts
//! mitmdump in a kill-on-close Job Object so it never outlives the session.

use crate::{err, environ, on, py, show_path, Ctx, Env, Obj, R};
use serde_json::Value;
use std::net::{SocketAddr, TcpListener, TcpStream};
use std::os::windows::io::AsRawHandle;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

pub const ADDONS: [(&str, &str, Option<(&str, &str)>); 4] = [
    ("slim", "slim_tools_addon.py", Some(("SLIM_LEVEL", "slim"))),
    ("ultra", "slim_tools_addon.py", Some(("SLIM_LEVEL", "ultra"))),
    ("optimize", "claude_optimizer_addon.py", None),
    ("capture", "capture_addon.py", None),
];
pub const CHOICES: [&str; 7] = ["slim", "ultra", "optimize", "capture", "slim+capture", "ultra+capture", "optimize+capture"];
/// Codex's add-ons (SPEC-codex-proxy.md): its own scripts, and no optimize.
pub const CODEX_ADDONS: [(&str, &str, Option<(&str, &str)>); 3] = [
    ("slim", "codex_slim_addon.py", Some(("SLIM_LEVEL", "slim"))),
    ("ultra", "codex_slim_addon.py", Some(("SLIM_LEVEL", "ultra"))),
    ("capture", "codex_capture_addon.py", None),
];
pub const CODEX_CHOICES: [&str; 5] = ["slim", "ultra", "capture", "slim+capture", "ultra+capture"];
pub const NO_OPTIMIZE: &str = "optimize is Claude's. Pick slim, ultra or capture for Codex.";

pub fn choices(codex: bool) -> &'static [&'static str] {
    if codex { &CODEX_CHOICES } else { &CHOICES }
}

/// Switching a profile to Codex: take optimize out of its proxy field. True if it was there.
pub fn drop_optimize(prof: &mut Obj) -> bool {
    let names = list(prof);
    if !names.iter().any(|n| n == "optimize") {
        return false;
    }
    let rest: Vec<String> = names.into_iter().filter(|n| n != "optimize").collect();
    if rest.is_empty() {
        prof.shift_remove("proxy");
    } else {
        prof.insert("proxy".into(), Value::String(rest.join("+")));
    }
    true
}

/// The profile's proxy field as add-on names: "slim+capture", "slim,capture" or a list.
pub fn list(prof: &Obj) -> Vec<String> {
    match on(prof, "proxy") {
        Some(Value::String(s)) => s.replace('+', ",").split(',').filter(|x| !py::strip(x).is_empty())
            .map(|x| py::strip(x).to_lowercase()).collect(),
        Some(_) => crate::list(prof, "proxy").iter().map(|x| py::strip(x).to_lowercase()).collect(),
        None => vec![],
    }
}

pub struct Plan {
    pub scripts: Vec<String>,
    pub env: Env,
}

/// (scripts, env) for the profile's proxy field, or None. Fails on bad values.
pub fn plan(ctx: &Ctx, prof: &Obj) -> R<Option<Plan>> {
    let names = list(prof);
    if names.is_empty() {
        return Ok(None);
    }
    let codex = crate::engines::is_codex(prof);
    let addons: &[_] = if codex { &CODEX_ADDONS } else { &ADDONS };
    if codex && names.iter().any(|n| n == "optimize") {
        return err(NO_OPTIMIZE);
    }
    let bad: Vec<&str> = names.iter().filter(|n| !addons.iter().any(|a| a.0 == n.as_str())).map(String::as_str).collect();
    if !bad.is_empty() {
        return err(format!("Unknown proxy add-on: {}. Use one of: {}.", bad.join(", "),
                           addons.iter().map(|a| a.0).collect::<Vec<_>>().join(", ")));
    }
    if names.iter().any(|n| n == "slim") && names.iter().any(|n| n == "ultra") {
        return err("slim and ultra are one add-on at two levels. Pick one.");
    }
    let mut p = Plan { scripts: vec![], env: Env::new() };
    for n in &names {
        let (_, script, e) = addons.iter().find(|a| a.0 == n).unwrap();
        p.scripts.push(py::join(&ctx.proxy_dir, &[script]));
        if let Some((k, v)) = e {
            p.env.insert(k.to_string(), v.to_string());
        }
    }
    if on(prof, "proxy_drop").is_some() {
        p.env.insert("SLIM_DROP".into(), crate::list(prof, "proxy_drop").join(","));
    }
    Ok(Some(p))
}

pub fn mitmdump_path(ctx: &Ctx) -> Option<String> {
    for c in [py::join(&ctx.proxy_dir, &[".venv", "Scripts", "mitmdump.exe"]), py::join(&ctx.proxy_dir, &[".venv", "bin", "mitmdump"])] {
        if py::exists(&c) {
            return Some(c);
        }
    }
    py::which("mitmdump")
}

pub fn mitm_ca_path() -> String {
    py::join(&py::expanduser("~"), &[".mitmproxy", "mitmproxy-ca-cert.pem"])
}

pub struct Proxy {
    pub child: Child,
    pub port: u16,
    job: Option<windows_sys::Win32::Foundation::HANDLE>,
    pub log_path: String,
}

fn listening(port: u16) -> bool {
    TcpStream::connect_timeout(&SocketAddr::from(([127, 0, 0, 1], port)), Duration::from_millis(300)).is_ok()
}

fn log_name(name: &str) -> String {
    let (mut out, mut run) = (String::new(), false);
    for c in name.chars() {
        if c.is_alphanumeric() || c == '_' || c == '.' || c == '-' {
            out.push(c);
            run = false;
        } else if !run {
            out.push('_');
            run = true;
        }
    }
    out
}

pub fn start(ctx: &Ctx, name: &str, plan: &Plan) -> R<Proxy> {
    use std::os::windows::process::CommandExt;
    let Some(mitm) = mitmdump_path(ctx) else {
        return err(format!("The proxy isn't set up. Build it: cd {}; python -m venv .venv; \
                            .venv\\Scripts\\pip install --only-binary :all: mitmproxy", ctx.proxy_dir));
    };
    for s in &plan.scripts {
        if !py::exists(s) {
            return err(format!("Proxy add-on missing: {}. Restore it in proxy/.", show_path(s)));
        }
    }
    let port = TcpListener::bind("127.0.0.1:0").and_then(|l| l.local_addr()).map(|a| a.port())
        .map_err(|e| crate::ReidError(e.to_string()))?;
    let logs = py::join(&ctx.proxy_dir, &["logs"]);
    std::fs::create_dir_all(&logs).map_err(crate::engines::io)?;
    let log_path = py::join(&logs, &[&format!("{}.log", log_name(name))]);
    let log = std::fs::File::create(&log_path).map_err(crate::engines::io)?;
    let mut env = environ();
    env.extend(plan.env.clone());
    let mut cmd = Command::new(&mitm);
    for s in &plan.scripts {
        cmd.args(["-s", s]);
    }
    cmd.args(["--listen-host", "127.0.0.1", "--listen-port", &port.to_string(), "-q"])
        .current_dir(&ctx.proxy_dir).env_clear().envs(&env).stdin(Stdio::null())
        .stdout(log.try_clone().map_err(crate::engines::io)?).stderr(log)
        .creation_flags(0x0800_0000 | 0x0000_0004); // CREATE_NO_WINDOW | CREATE_SUSPENDED
    let child = cmd.spawn().map_err(crate::engines::io)?;
    let job = crate::win::job_kill_on_close(child.as_raw_handle() as _);
    let mut px = Proxy { child, port, job, log_path };
    let deadline = Instant::now() + Duration::from_secs(15);
    let mut exited = false;
    while Instant::now() < deadline {
        if px.child.try_wait().ok().flatten().is_some() {
            exited = true;
            break;
        }
        if listening(port) && py::exists(&mitm_ca_path()) {
            return Ok(px);
        }
        std::thread::sleep(Duration::from_millis(150));
    }
    let log_path = px.log_path.clone();
    stop(Some(&mut px));
    let text = py::read_text(&log_path, false).unwrap_or_default();
    let lines: Vec<&str> = py::strip(&text).lines().collect();
    let tail = lines[lines.len().saturating_sub(8)..].join("\n  ");
    err(format!("The proxy didn't start ({}). See {}:\n  {}", if exited { "it exited" } else { "timed out" },
                show_path(&log_path), if tail.is_empty() { "empty log".into() } else { tail }))
}

pub fn stop(px: Option<&mut Proxy>) {
    let Some(px) = px else { return };
    if let Some(job) = px.job.take() {
        crate::win::job_kill(job);
    } else {
        let _ = Command::new("taskkill").args(["/F", "/T", "/PID", &px.child.id().to_string()])
            .stdout(Stdio::null()).stderr(Stdio::null()).status();
    }
    let deadline = Instant::now() + Duration::from_secs(5);
    while Instant::now() < deadline && px.child.try_wait().ok().flatten().is_none() {
        std::thread::sleep(Duration::from_millis(50));
    }
}

/// What the session gets: Claude (Node) trusts the CA through NODE_EXTRA_CA_CERTS, Codex through
/// CODEX_CA_CERTIFICATE.
pub fn env(px: &Proxy, codex: bool) -> [(String, String); 3] {
    [("HTTPS_PROXY".into(), format!("http://127.0.0.1:{}", px.port)),
     ((if codex { "CODEX_CA_CERTIFICATE" } else { "NODE_EXTRA_CA_CERTS" }).into(), mitm_ca_path()),
     ("NO_PROXY".into(), "localhost,127.0.0.1,::1".into())]
}
