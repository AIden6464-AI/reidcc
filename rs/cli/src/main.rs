//! reid.exe: Reidcc's CLI and TUI in Rust (vision\Spec\SPEC-rust-rewrite.md stage 0, and part 1 of
//! SPEC-rust-tui-gui.md). Same flags, output and screens as reid.py; the window is Reidcc.exe.

mod console;
mod tui;

use reidcc::engines::{self, codex, is_codex};
use reidcc::{default_profile, errln, load_config, load_state, memory_path, out, profile, profiles, proxy, py, session, Ctx, R};

const HELP: &str = r#"reid -- Reidcc, in the terminal.

    reid                      open the Reidcc TUI (pick, edit, open gate, resume)
    reid <profile> [args]     start a session with that profile; extra args go to claude
    reid -c / reid "do X"     anything that isn't a profile goes to claude (default profile)
    reid -l                   list profiles
    reid --version            show the Reidcc version
    reid --dry [profile]      print what would run, don't run it
    reid --edit / --mem       open reid.json / the memory file

Inside Claude:
    /reid                     end the session and return to the TUI. Your conversation
                              is kept: press r there to resume it, with any profile.
    /exit                     leave as usual, back to your shell.

Profile fields (reid.json): engine (claude | codex), model, settings, persona, mode, memory,
safe, args, env, plus proxy, proxy_drop, tools, mcp, no_chrome, no_connectors, settings_json.
A codex profile starts Codex in the folder (vision/SPEC-codex-opencode.md) with the same persona,
memory and sign-in fields: persona + memory go in codex/prompts/<profile>.md, a sign-in file is a
codex/*.toml provider file (vision/SPEC-codex-signin-persona.md).
See SPEC-proxy.md for the proxy and lean-setup fields.

Relative paths in reid.json resolve against this folder, so moving the folder
(or the drive letter changing) doesn't break anything."#;

const NO_GUI: &str = "The Rust Reidcc window (Reidcc.exe) isn't built yet. reid --tui opens the TUI.";

pub fn open_file(path: &str) {
    match std::env::var("EDITOR").ok().filter(|e| !e.is_empty()) {
        Some(editor) => {
            let _ = std::process::Command::new(editor).arg(path).status();
        }
        None => reidcc::win::startfile(path),
    }
}

fn main() {
    let args: Vec<String> = std::env::args().skip(1).collect();
    reidcc::refresh_path(); // before anything looks for claude, wt, git...
    reidcc::win::enable_vt();
    let ctx: &'static Ctx = Box::leak(Box::new(Ctx::new())); // the TUI's sign-in check shares it with a thread
    let rc = match run(ctx, args) {
        Ok(rc) => rc,
        Err(e) => {
            errln!("{e}");
            1
        }
    };
    std::process::exit(rc);
}

/// Run the GUI: Reidcc.exe next to this exe, detached so the shell gets its prompt back.
fn open_gui(from_terminal: bool) -> i32 {
    use std::os::windows::process::CommandExt;
    let exe = std::env::current_exe().map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
    let gui = py::join(&py::dirname(&exe), &["Reidcc.exe"]);
    if py::exists(&gui) {
        let started = std::process::Command::new(&gui).args(["--gui", "--cwd", &py::getcwd()])
            .creation_flags(0x0000_0008 | 0x0000_0200) // DETACHED | NEW_GROUP
            .stdin(std::process::Stdio::null()).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null())
            .spawn().is_ok();
        if started {
            if from_terminal {
                out!("Reidcc window opened.");
            }
            return 0;
        }
    }
    errln!("{NO_GUI}");
    if !from_terminal {
        let _ = console::getkey(); // started as an app: its console closes on exit, so wait to be read
    }
    1
}

fn run(ctx: &'static Ctx, mut args: Vec<String>) -> R<i32> {
    let a0 = args.first().cloned().unwrap_or_default();
    match a0.as_str() {
        "--statusline" => return Ok(session::cmd_statusline(ctx)),
        "--tui" => return Ok(tui::Tui::new(ctx, &py::getcwd(), "").run()),
        "--gui" => return Ok(open_gui(reidcc::win::launched_from_terminal())),
        "--version" if args.len() == 1 => {
            out!("Reidcc {}", env!("CARGO_PKG_VERSION"));
            return Ok(0);
        }
        // No args: typed in a terminal -> tool (TUI); double-clicked / shortcut -> app (GUI).
        "" if args.is_empty() => {
            if reidcc::win::launched_from_terminal() {
                return Ok(tui::Tui::new(ctx, &py::getcwd(), "").run());
            }
            return Ok(open_gui(false));
        }
        "--resume" => {
            // reid --resume [profile]: continue the last session
            let cfg = load_config(ctx)?;
            let last = load_state(ctx).get("last").and_then(|v| v.as_object().cloned()).unwrap_or_default();
            let s = |k: &str| reidcc::text(&last, k);
            let name = match args.get(1) {
                Some(n) if profiles(&cfg).contains_key(n) => n.clone(),
                _ if !s("profile").is_empty() => s("profile"),
                _ => default_profile(&cfg).to_string(),
            };
            let cwd = if !s("cwd").is_empty() && py::isdir(&s("cwd")) { s("cwd") } else { py::getcwd() };
            let sid = if s("sid").is_empty() { "-c".to_string() } else { s("sid") };
            let end = session::run(ctx, &cfg, &name, &cwd, &[], Some(&sid))?;
            if let Some(rc) = session::window_end(&end) {
                return Ok(rc);
            }
            if end.back {
                return Ok(tui::Tui::new(ctx, &cwd, "Back from the session. r resumes it.").run());
            }
            return Ok(end.rc);
        }
        "-h" | "--help" => {
            out!("{HELP}");
            return Ok(0);
        }
        "--back" => return Ok(session::cmd_back()),
        _ => {}
    }
    let cfg = load_config(ctx)?;
    match a0.as_str() {
        "-l" | "--list" => {
            let def = default_profile(&cfg);
            for n in profiles(&cfg).keys() {
                out!("{} {:<14} {}", if n == def { "*" } else { " " }, n, profile::summary(ctx, &cfg, n));
            }
            return Ok(0);
        }
        "--edit" => {
            open_file(&ctx.config);
            return Ok(0);
        }
        "--mem" => {
            open_file(&memory_path(ctx, &cfg, None));
            return Ok(0);
        }
        _ => {}
    }
    let dry = a0 == "--dry";
    if dry {
        args.remove(0);
    }
    let (name, extra) = match args.first() {
        Some(n) if profiles(&cfg).contains_key(n) => (n.clone(), args[1..].to_vec()),
        _ => (default_profile(&cfg).to_string(), args.clone()),
    };
    let empty = reidcc::Obj::new();
    let prof = profiles(&cfg).get(&name).and_then(|v| v.as_object()).unwrap_or(&empty);
    let cwd = py::getcwd();
    if dry {
        let launch = engines::build(ctx, &cfg, &name, &extra, Some(&cwd), true)?;
        out!("profile: {name}  ({})", profile::summary(ctx, &cfg, &name));
        if let Some(plan) = proxy::plan(ctx, prof)? {
            let env = if plan.env.is_empty() {
                String::new()
            } else {
                format!("  [{}]", plan.env.iter().map(|(k, v)| format!("{k}={v}")).collect::<Vec<_>>().join(" "))
            };
            out!("proxy:   {} -s {} on a free port{env}",
                 proxy::mitmdump_path(ctx).unwrap_or_else(|| "mitmdump (not set up)".into()),
                 plan.scripts.iter().map(|s| ctx.relpath(s)).collect::<Vec<_>>().join(" -s "));
        }
        for k in ["ENABLE_CLAUDEAI_MCP_SERVERS", "CLAUDE_CODE_DISABLE_CLAUDE_MDS"] {
            if let Some(v) = launch.env.get(k).filter(|v| !v.is_empty()) {
                if Some(v.clone()) != reidcc::getenv(k) {
                    out!("env:     {k}={v}");
                }
            }
        }
        out!("{}", py::list2cmdline(&launch.argv));
        let pp = codex::prompt_path(ctx, &name);
        if is_codex(prof) && py::exists(&pp) && launch.argv.iter().any(|a| a.contains("model_instructions_file=")) {
            out!("  prompt file: {}, {} chars", reidcc::show_path(&pp), py::getsize(&pp));
        }
        for t in &launch.temps {
            let kind = if t.contains("reid_settings_") { "settings file" } else { "prompt file" };
            out!("  {kind}: {} chars", py::getsize(t));
            let _ = std::fs::remove_file(t);
        }
        return Ok(0);
    }
    let end = session::run(ctx, &cfg, &name, &cwd, &extra, None)?;
    if let Some(rc) = session::window_end(&end) {
        return Ok(rc);
    }
    if is_codex(prof) && extra.is_empty() && reidcc::term::is_tty() {
        // no /reid in Codex: quitting it comes back
        let msg = if end.rc == 0 { "Back from Codex.".to_string() }
                  else { format!("Codex ended with code {}. See the output above.", end.rc as u32) };
        return Ok(tui::Tui::new(ctx, &py::getcwd(), &msg).run());
    }
    if end.back {
        return Ok(tui::Tui::new(ctx, &py::getcwd(), "Back from the session. r resumes it.").run());
    }
    Ok(end.rc)
}
