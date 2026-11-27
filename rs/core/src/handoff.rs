//! Switch (SPEC-unified-interface, Milestone 1): `.reid\handoff.md`, written by plain code from
//! git and what you typed, never by a model, then handed to the next engine's turn.

use crate::R;
use std::fmt::Write;
use std::path::Path;
use std::process::{Command, Stdio};

pub const DIR: &str = ".reid";

pub struct Switch<'a> {
    pub folder: &'a str,
    pub profile: &'a str,
    pub engine: &'a str,
    pub tests: Option<&'a str>,
    pub note: Option<&'a str>,
}

/// git's output in `folder` (pathspecs leave .reid\ out), or None when git fails.
fn git(folder: &str, args: &[&str]) -> Option<String> {
    let out = Command::new("git").args(["-c", "core.quotepath=off", "-C", folder]).args(args)
        .args(["--", ".", ":(exclude).reid"])
        .stdin(Stdio::null()).stderr(Stdio::null()).output().ok()?;
    out.status.success().then(|| String::from_utf8_lossy(&out.stdout).trim_end().to_string())
}

/// The handoff's text.
pub fn render(switch: &Switch) -> String {
    let written = crate::now_iso()[..16].replacen('T', " ", 1); // to the minute
    let mut md = format!("# Handoff\n\n- Folder: {}\n- From: {} · {}\n- Written: {written}\n",
                         switch.folder, switch.profile, switch.engine);
    // git's default lists a new folder once (?? .venv/), not every file in it
    match git(switch.folder, &["status", "--porcelain=v1"]) {
        None => section(&mut md, "Changed files", "Not a git repo, so no list of changes."),
        Some(status) => {
            section(&mut md, "Changed files", &if status.is_empty() { "None.".into() } else { format!("```\n{status}\n```") });
            // staged and unstaged against the last commit; a repo with no commit yet has only the working tree
            let stat = git(switch.folder, &["diff", "--stat", "HEAD"]).or_else(|| git(switch.folder, &["diff", "--stat"]))
                .unwrap_or_default();
            section(&mut md, "Diff stat", &if stat.is_empty() { "No changes to tracked files.".into() } else { format!("```\n{stat}\n```") });
        }
    }
    if let Some(tests) = switch.tests.map(str::trim).filter(|tests| !tests.is_empty()) {
        section(&mut md, "Tests", tests);
    }
    if let Some(note) = switch.note.map(str::trim).filter(|note| !note.is_empty()) {
        section(&mut md, "Note", note);
    }
    md
}

fn section(md: &mut String, title: &str, body: &str) {
    let _ = writeln!(md, "\n## {title}\n\n{body}"); // writing to a String can't fail
}

/// Write `<folder>\.reid\handoff.md`; returns its path and text.
pub fn write(switch: &Switch) -> R<(String, String)> {
    let md = render(switch);
    let dir = Path::new(switch.folder).join(DIR);
    let path = dir.join("handoff.md");
    // git ignores the whole folder, so `git add -A` never commits a handoff (or the local path in it)
    std::fs::create_dir_all(&dir).and_then(|_| std::fs::write(dir.join(".gitignore"), "*\n"))
        .and_then(|_| std::fs::write(&path, &md)).map_err(crate::engines::io)?;
    Ok((path.to_string_lossy().into_owned(), md))
}

/// The next engine's turn: the handoff first, then what you asked.
pub fn prompt(md: &str, ask: &str) -> String {
    format!("Another coding agent worked in this folder before you. Its handoff ({DIR}/handoff.md):\n\n{md}\n---\n\n{ask}")
}
