//! What one turn changed (SPEC-unified-interface Part 6: "compute collapsible diff summary from git
//! diff on Done"). The folder is written as a git tree before and after the turn, from a scratch copy
//! of the index, so the diff is that turn's alone and the real index is never touched.

use std::process::{Command, Stdio};

#[derive(Debug, PartialEq)]
pub struct FileStat {
    pub path: String,
    /// None for a binary file
    pub added: Option<u64>,
    pub removed: Option<u64>,
}

impl FileStat {
    pub fn to_json(&self) -> serde_json::Value {
        serde_json::json!({"path": self.path, "added": self.added, "removed": self.removed})
    }
}

fn git(folder: &str, index: Option<&str>, args: &[&str]) -> Option<String> {
    use std::os::windows::process::CommandExt;
    let mut c = Command::new("git");
    c.args(["-c", "core.quotepath=off", "-C", folder]).args(args)
        .stdin(Stdio::null()).stderr(Stdio::null()).creation_flags(0x0800_0000);
    if let Some(i) = index {
        c.env("GIT_INDEX_FILE", i);
    }
    let out = c.output().ok()?;
    out.status.success().then(|| String::from_utf8_lossy(&out.stdout).trim_end().to_string())
}

/// New (untracked) files bigger than this stay out of a snapshot: every snapshot writes its files into
/// .git/objects, and logs or build output would pile up there turn after turn.
pub const UNTRACKED_MAX_BYTES: u64 = 2 * 1024 * 1024;

/// The folder as a git tree: tracked and new files, .gitignore respected, `.reid` and new files over
/// UNTRACKED_MAX_BYTES left out. None outside a git repo (or without git).
pub fn snapshot(folder: &str) -> Option<String> {
    use std::sync::atomic::{AtomicU32, Ordering};
    static N: AtomicU32 = AtomicU32::new(0);
    let real = git(folder, None, &["rev-parse", "--git-path", "index"])?;
    let real = if crate::py::isabs(&real) { real } else { crate::py::join(folder, &[&real]) };
    let tmp = crate::py::join(&crate::py::gettempdir(),
                              &[&format!("reidcc_index_{}_{}", std::process::id(), N.fetch_add(1, Ordering::Relaxed))]);
    let specs = format!("{tmp}.specs");
    let _ = std::fs::copy(&real, &tmp); // its file times spare git re-reading every file; none yet is fine
    // the pathspecs go in a file: one exclude per big new file can outgrow a command line
    let mut list = String::from(".\0:(exclude).reid\0");
    let new = git(folder, Some(&tmp), &["ls-files", "-z", "--others", "--exclude-standard", "--", ".", ":(exclude).reid"]);
    for path in new.as_deref().unwrap_or_default().split('\0').filter(|p| !p.is_empty()) {
        if std::fs::metadata(crate::py::join(folder, &[path])).is_ok_and(|m| m.len() > UNTRACKED_MAX_BYTES) {
            list.push_str(&format!(":(exclude,literal){path}\0"));
        }
    }
    let from_file = format!("--pathspec-from-file={specs}");
    let tree = std::fs::write(&specs, list).ok()
        .and_then(|()| git(folder, Some(&tmp), &["add", "-A", &from_file, "--pathspec-file-nul"]))
        .and_then(|_| git(folder, Some(&tmp), &["write-tree"]));
    let _ = std::fs::remove_file(&tmp);
    let _ = std::fs::remove_file(&specs);
    tree.filter(|t| !t.is_empty())
}

/// Files that differ between two snapshots, with their line counts.
pub fn changed(folder: &str, from: &str, to: &str) -> Vec<FileStat> {
    let out = git(folder, None, &["diff", "--numstat", "--no-renames", from, to]).unwrap_or_default();
    out.lines().filter_map(|l| {
        let mut p = l.splitn(3, '\t');
        let (a, r, path) = (p.next()?, p.next()?, p.next()?);
        Some(FileStat { path: path.to_string(), added: a.parse().ok(), removed: r.parse().ok() })
    }).collect()
}

/// One file's diff between two snapshots, cut at `max` lines.
pub fn file_diff(folder: &str, from: &str, to: &str, path: &str, max: usize) -> String {
    let out = git(folder, None, &["diff", "--no-renames", from, to, "--", path]).unwrap_or_default();
    let mut lines: Vec<&str> = out.lines().skip_while(|l| !l.starts_with("@@")).collect();
    if lines.len() > max {
        let more = lines.len() - max;
        lines.truncate(max);
        return format!("{}\n… {more} more lines", lines.join("\n"));
    }
    lines.join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_turn_s_changes_are_its_own_and_leave_reid_out() {
        let dir = std::env::temp_dir().join(format!("reid_changes_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(dir.join(".reid")).unwrap();
        let d = dir.to_string_lossy().to_string();
        assert_eq!(snapshot(&d), None, "not a repo yet");
        git(&d, None, &["init", "-q"]).unwrap();
        std::fs::write(dir.join("a.txt"), "one\n").unwrap();
        let before = snapshot(&d).unwrap();
        std::fs::write(dir.join("a.txt"), "one\ntwo\n").unwrap();
        std::fs::write(dir.join("new.txt"), "x\n").unwrap();
        std::fs::write(dir.join(".reid").join("handoff.md"), "h\n").unwrap();
        std::fs::write(dir.join("build [1].log"), vec![b'x'; UNTRACKED_MAX_BYTES as usize + 1]).unwrap();
        let after = snapshot(&d).unwrap();
        assert_eq!(changed(&d, &before, &after), vec![
            FileStat { path: "a.txt".into(), added: Some(1), removed: Some(0) },
            FileStat { path: "new.txt".into(), added: Some(1), removed: Some(0) },
        ]);
        assert!(file_diff(&d, &before, &after, "a.txt", 50).ends_with("+two"));
        assert_eq!(git(&d, None, &["status", "--porcelain"]).unwrap().lines().count(), 4, "the real index is untouched");
        assert!(changed(&d, &after, &snapshot(&d).unwrap()).is_empty(), "no change, no files");
        let _ = std::fs::remove_dir_all(dir);
    }
}
