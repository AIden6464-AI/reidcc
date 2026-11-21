//! `reid --install` / `reid --uninstall`: what the installer runs after copying files and before
//! removing them (vision/Spec/SPEC-github-repo.md, 3b and 3d). Neither touches your Reidcc folder.

use reidcc::engines::{claude, codex};
use reidcc::{out, py, win, Ctx};

/// ~/.claude/commands/reid.md: `/reid` inside Claude goes back to the Reidcc TUI.
const SLASH: &str = "---
description: Back to the Reidcc TUI (switch profile, edit, resume this chat)
allowed-tools: Bash(reid:*)
disable-model-invocation: true
---
!`reid --back`

(If you are reading this, Reidcc did not end the session. Relay the line above to the user in one sentence and do nothing else.)
";

fn exe_dir() -> String {
    let exe = std::env::current_exe().map(|p| p.to_string_lossy().into_owned()).unwrap_or_default();
    py::dirname(&exe)
}

fn key(p: &str) -> String {
    py::normcase(p.trim_end_matches(['\\', '/']))
}

/// The user PATH with `dir` added or taken out, or None when there's nothing to do.
fn path_with(raw: &str, dir: &str, add: bool) -> Option<String> {
    let parts: Vec<&str> = raw.split(';').filter(|p| !p.is_empty()).collect();
    let has = parts.iter().any(|p| key(&py::expandvars(p)) == key(dir));
    match (add, has) {
        (true, false) => Some(parts.into_iter().chain([dir]).collect::<Vec<_>>().join(";")),
        (false, true) => Some(parts.into_iter().filter(|p| key(&py::expandvars(p)) != key(dir)).collect::<Vec<_>>().join(";")),
        _ => None,
    }
}

/// Left in the program folder when `--install` wrote `/reid`, so `--uninstall` never removes one
/// that was there before (a portable or dev copy's).
const WROTE: &str = "reid-slash.installed";

/// `/reid` is ours when it's exactly what we write (line endings aside).
fn ours(path: &str) -> bool {
    std::fs::read_to_string(path).is_ok_and(|t| t.replace("\r\n", "\n").trim() == SLASH.trim())
}

pub fn install(ctx: &Ctx) -> i32 {
    let dir = exe_dir();
    match path_with(&win::user_path(), &dir, true) {
        Some(p) if win::set_user_path(&p) => out!("+ PATH     {dir}  (terminals opened from now on)"),
        Some(_) => out!("  PATH     couldn't add {dir}; add it yourself to type reid anywhere"),
        None => out!("  PATH     already has {dir}"),
    }

    let claude_dir = py::expanduser("~/.claude");
    let slash = py::join(&claude_dir, &["commands", "reid.md"]);
    if !py::isdir(&claude_dir) {
        out!("  /reid    skipped: no ~\\.claude yet (start Claude Code once, then run reid --install)");
    } else if !py::exists(&slash) {
        let written = std::fs::create_dir_all(py::dirname(&slash)).and_then(|_| std::fs::write(&slash, SLASH))
            .and_then(|_| std::fs::write(py::join(&dir, &[WROTE]), ""));
        match written {
            Ok(_) => out!("+ /reid    {slash}"),
            Err(e) => out!("  /reid    couldn't write {slash}: {e}"),
        }
    } else if ours(&slash) {
        out!("  /reid    already there");
    } else {
        out!("  /reid    kept yours ({slash} has other text)");
    }

    match claude::find_claude() {
        Ok(_) if py::exists(&py::expanduser("~/.claude/.credentials.json")) => out!("  claude   found, signed in"),
        Ok(_) => out!("  claude   found; sign in by starting a session"),
        Err(_) => out!("  claude   not found: install Claude Code (https://docs.anthropic.com/en/docs/claude-code)"),
    }
    match codex::find_codex() {
        Ok(_) => out!("  codex    found, {}", codex::login(ctx, true).unwrap_or_else(|| "sign-in unknown".into())),
        Err(_) => out!("  codex    not found (optional)"),
    }
    out!("  your folder  {} (made on first launch)", ctx.home);
    0
}

pub fn uninstall(ctx: &Ctx) -> i32 {
    let dir = exe_dir();
    if let Some(p) = path_with(&win::user_path(), &dir, false) {
        if win::set_user_path(&p) {
            out!("- PATH     {dir}");
        }
    }
    let slash = py::expanduser("~/.claude/commands/reid.md");
    let marker = py::join(&dir, &[WROTE]);
    if py::exists(&marker) && ours(&slash) && std::fs::remove_file(&slash).is_ok() {
        out!("- /reid    {slash}");
    }
    let _ = std::fs::remove_file(marker);
    out!("  Your folder is kept: {}. Delete it yourself, or keep it for a reinstall.", ctx.home);
    0
}

/// `reid --update`: the launcher's own update flow (check, download, verify, install, restart).
/// This exits at once so the installer can replace reid.exe.
pub fn update() -> i32 {
    let dir = exe_dir();
    if !reidcc::installed_copy() {
        out!("This copy wasn't installed by Reidcc's setup, so it doesn't update itself.");
        out!("Get the latest from https://github.com/AIden6464-AI/reidcc/releases");
        return 1;
    }
    let busy = win::running_in(&dir, &["reid.exe", "Reidcc.exe"]);
    if busy > 0 {
        out!("Finish your sessions and close Reidcc first ({busy} running from {dir}): the update replaces their files.");
        return 1;
    }
    match std::process::Command::new(py::join(&dir, &["Reidcc.exe"])).arg("--update").spawn() {
        Ok(_) => {
            out!("Reidcc is checking for the update; its footer shows the progress.");
            0
        }
        Err(e) => {
            out!("Couldn't start Reidcc.exe: {e}");
            1
        }
    }
}

#[cfg(test)]
mod tests {
    use super::path_with;

    #[test]
    fn path_entry_is_added_once_and_removed_cleanly() {
        let dir = r"C:\Users\dev\AppData\Local\Reidcc";
        assert_eq!(path_with(r"C:\a;C:\b", dir, true).unwrap(), format!(r"C:\a;C:\b;{dir}"));
        assert_eq!(path_with(&format!(r"C:\a;{dir}\"), dir, true), None); // trailing slash, any case
        assert_eq!(path_with(&format!(r"c:\a;{};C:\b", dir.to_lowercase()), dir, false).unwrap(), r"c:\a;C:\b");
        assert_eq!(path_with("", dir, true).unwrap(), dir);
        assert_eq!(path_with(r"C:\a", dir, false), None);
    }
}
