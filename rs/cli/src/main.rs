//! reid.exe: Reidcc's CLI and TUI in Rust (vision\Spec\SPEC-rust-rewrite.md stage 0, and part 1 of
//! SPEC-rust-tui-gui.md). Same flags, output and screens as reid.py; the window is Reidcc.exe.

mod console;
mod install;
mod tui;

use reidcc::engines::{self, codex, is_codex};
use reidcc::{default_profile, errln, load_config, load_state, memory_path, out, profile, profiles, proxy, py, session, Ctx, R};

const HELP: &str = r#"reid -- Reidcc, in the terminal.

    reid                      open the Reidcc TUI (pick, edit, open gate, resume)
    reid <profile> [args]     start a session with that profile; extra args go to its engine
    reid -c / reid "do X"     anything that isn't a profile goes to the default profile's engine
    reid --resume [profile]   continue the last session (that profile, or the one it had)
    reid -l                   list profiles
    reid --dry [profile]      print what would run, don't run it
    reid --dry -v [profile]   ... and the prompt and settings files it adds
    reid --edit / --mem       open reid.json / the memory file
    reid --tui / --gui        force the TUI or the window
    reid --version            show the Reidcc version
    reid --update             install the latest Reidcc (installed copies only)

Inside a session:
    /reid                     end the session and return to the TUI. Your conversation
                              is kept: press r there to resume it, with any profile.
    /exit                     leave as usual, back to your shell.

Profile fields (reid.json): engine (claude | codex), model, settings, persona, mode, memory,
safe, args, env, plus tools, mcp, no_chrome, no_connectors, settings_json. A codex profile
starts Codex with the same persona, memory and sign-in fields.

Relative paths in reid.json resolve against the Reidcc folder, so moving it (or the drive
letter changing) doesn't break anything.

Docs: https://aiden6464-ai.github.io/reidcc/docs/cli"#;

const NO_GUI: &str = "Can't find Reidcc.exe next to reid.exe. reid --tui opens the TUI.";

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

/// What `reid --resume [profile] [args]` continues: the profile (named, else the last session's, else the
/// default), the last session's folder, its id ("-c" when there's none) and the extra args.
fn resume_target(ctx: &Ctx, cfg: &reidcc::Obj, rest: &[String]) -> (String, String, String, Vec<String>) {
    let last = load_state(ctx).get("last").and_then(|v| v.as_object().cloned()).unwrap_or_default();
    let s = |k: &str| reidcc::text(&last, k);
    let (name, extra) = match rest.first() {
        Some(n) if profiles(cfg).contains_key(n) => (n.clone(), rest[1..].to_vec()),
        _ if !s("profile").is_empty() => (s("profile"), rest.to_vec()),
        _ => (default_profile(cfg).to_string(), rest.to_vec()),
    };
    let cwd = if !s("cwd").is_empty() && py::isdir(&s("cwd")) { s("cwd") } else { py::getcwd() };
    let sid = if s("sid").is_empty() { "-c".to_string() } else { s("sid") };
    (name, cwd, sid, extra)
}

fn run(ctx: &'static Ctx, mut args: Vec<String>) -> R<i32> {
    let a0 = args.first().cloned().unwrap_or_default();
    match a0.as_str() {
        "--statusline" => return Ok(session::cmd_statusline(ctx)),
        "--install" => return Ok(install::install(ctx)),
        "--uninstall" => return Ok(install::uninstall(ctx)),
        "--update" => return Ok(install::update()),
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
            // reid --resume [profile] [args]: continue the last session
            let cfg = load_config(ctx)?;
            let (name, cwd, sid, extra) = resume_target(ctx, &cfg, &args[1..]);
            let end = session::run(ctx, &cfg, &name, &cwd, &extra, Some(&sid))?;
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
            if profiles(&cfg).values().filter_map(|v| v.as_object()).any(|p| is_codex(p) && reidcc::text(p, "settings").is_empty())
                && codex::login(ctx, false).is_none()
            {
                codex::login_store(ctx, "can't check"); // not "checking…" forever: the CLI asks once, here
            }
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
    // --dry -v: also print the prompt / settings files' text (they're deleted after the preview)
    let show = dry && args.first().map(String::as_str) == Some("-v");
    if show {
        args.remove(0);
    }
    if dry && args.first().map(String::as_str) == Some("--resume") {
        // the resume preview: what `reid --resume [profile] [args]` would run, and where
        let (name, cwd, sid, extra) = resume_target(ctx, &cfg, &args[1..]);
        let mut launch = engines::build(ctx, &cfg, &name, &extra, Some(&cwd), true)?;
        launch.remove_temps();
        if sid == "-c" || !session::session_exists(&sid) {
            launch.argv.push("-c".into());
        } else {
            launch.argv.extend(["--resume".into(), sid]);
        }
        out!("profile: {name}  ({})", profile::summary(ctx, &cfg, &name));
        out!("folder:  {}", reidcc::show_path(&cwd));
        out!("{}", py::list2cmdline(&launch.argv));
        return Ok(0);
    }
    let (name, extra) = match args.first() {
        Some(n) if profiles(&cfg).contains_key(n) => (n.clone(), args[1..].to_vec()),
        Some(n) => {
            // anything that isn't a profile goes to the engine, unless it's a profile name mistyped
            if let Some(near) = profiles(&cfg).keys().find(|p| one_edit(p, n)) {
                return reidcc::err(format!("There's no profile {n}. Did you mean {near}?"));
            }
            (default_profile(&cfg).to_string(), args.clone())
        }
        None => (default_profile(&cfg).to_string(), args.clone()),
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
            if show {
                out!("{}", std::fs::read_to_string(&pp).unwrap_or_default());
            }
        }
        for t in &launch.temps {
            let kind = if t.contains("reid_settings_") { "settings file" } else { "prompt file" };
            out!("  {kind}: {} chars", py::getsize(t));
            if show {
                out!("{}", std::fs::read_to_string(t).unwrap_or_default());
            }
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

/// One typo apart: a letter changed, added, dropped, or two neighbours swapped. Case alone counts too.
fn one_edit(a: &str, b: &str) -> bool {
    let (a, b): (Vec<char>, Vec<char>) = (a.to_lowercase().chars().collect(), b.to_lowercase().chars().collect());
    if a == b || a.len().abs_diff(b.len()) > 1 || a.len().min(b.len()) < 3 {
        return a == b;
    }
    let start = a.iter().zip(&b).take_while(|(x, y)| x == y).count();
    let (ra, rb) = (&a[start..], &b[start..]);
    let tail = |i: usize, j: usize| ra.get(i..) == rb.get(j..);
    tail(1, 1) || tail(1, 0) || tail(0, 1) || (ra.len() >= 2 && rb.len() >= 2 && ra[0] == rb[1] && ra[1] == rb[0] && tail(2, 2))
}

#[cfg(test)]
mod tests {
    use super::one_edit;

    #[test]
    fn typos_are_one_edit_and_prompts_are_not() {
        for (a, b) in [("codex-kiln", "codex-klin"), ("main", "mian"), ("main", "man"), ("main", "mains"), ("review", "reveiw"), ("Main", "main")] {
            assert!(one_edit(a, b), "{a} / {b}");
        }
        for (a, b) in [("main", "do X"), ("main", "-c"), ("ab", "ba"), ("review", "rvwiee"), ("main", "mainly")] {
            assert!(!one_edit(a, b), "{a} / {b}");
        }
    }
}
