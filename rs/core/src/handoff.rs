//! Switch (SPEC-unified-interface, Milestone 1): `.reid\handoff.md`, written by plain code from
//! git and what you typed, never by a model, then handed to the next engine's turn.

use crate::{py, R};
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
pub fn render(s: &Switch) -> String {
    let (y, mo, d, h, mi, _) = py::now_local();
    let mut md = format!("# Handoff\n\n- Folder: {}\n- From: {} · {}\n- Written: {y:04}-{mo:02}-{d:02} {h:02}:{mi:02}\n",
                         s.folder, s.profile, s.engine);
    let section = |md: &mut String, title: &str, body: &str| md.push_str(&format!("\n## {title}\n\n{body}\n"));
    match git(s.folder, &["status", "--porcelain=v1", "-uall"]) {
        None => section(&mut md, "Changed files", "Not a git repo, so no list of changes."),
        Some(st) => {
            section(&mut md, "Changed files", &if st.is_empty() { "None.".into() } else { format!("```\n{st}\n```") });
            // staged and unstaged against the last commit; a repo with no commit yet has only the working tree
            let stat = git(s.folder, &["diff", "--stat", "HEAD"]).or_else(|| git(s.folder, &["diff", "--stat"])).unwrap_or_default();
            section(&mut md, "Diff stat", &if stat.is_empty() { "No changes to tracked files.".into() } else { format!("```\n{stat}\n```") });
        }
    }
    if let Some(t) = s.tests.map(str::trim).filter(|t| !t.is_empty()) {
        section(&mut md, "Tests", t);
    }
    if let Some(n) = s.note.map(str::trim).filter(|n| !n.is_empty()) {
        section(&mut md, "Note", n);
    }
    md
}

/// Write `<folder>\.reid\handoff.md`; returns its path and text.
pub fn write(s: &Switch) -> R<(String, String)> {
    let md = render(s);
    let path = py::join(s.folder, &[DIR, "handoff.md"]);
    std::fs::create_dir_all(py::dirname(&path)).and_then(|_| std::fs::write(&path, &md)).map_err(crate::engines::io)?;
    Ok((path, md))
}

/// The next engine's turn: the handoff first, then what you asked.
pub fn prompt(md: &str, ask: &str) -> String {
    format!("Another coding agent worked in this folder before you. Its handoff ({DIR}/handoff.md):\n\n{md}\n---\n\n{ask}")
}
