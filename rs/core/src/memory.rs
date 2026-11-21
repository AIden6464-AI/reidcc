//! Long-term memory: the file a profile reads at launch, trimmed to fit.

use crate::{memory_path, on, py, Ctx, Obj, JOURNAL, MEMORY_LIMIT, PINNED};

fn find(hay: &[char], needle: &str) -> Option<usize> {
    let n: Vec<char> = needle.chars().collect();
    hay.windows(n.len()).position(|w| w == &n[..])
}

/// Over the limit: keep the pinned facts and the newest journal lines.
pub fn trim_memory(text: &str, limit: usize) -> String {
    let t: Vec<char> = text.chars().collect();
    if t.len() <= limit {
        return text.to_string();
    }
    if let (Some(_), Some(cut)) = (find(&t, PINNED), find(&t, JOURNAL)) {
        let (head, journal) = (&t[..cut], &t[cut..]);
        let room = limit.saturating_sub(head.len() + 40);
        let mut tail: &[char] = if room > 0 { &journal[journal.len().saturating_sub(room)..] } else { &[] };
        if let Some(nl) = tail.iter().position(|&c| c == '\n') {
            tail = &tail[nl + 1..];
        }
        return format!("{}{JOURNAL}\n- ...(older entries trimmed)\n{}", head.iter().collect::<String>(),
                       tail.iter().collect::<String>());
    }
    format!("...(older memory trimmed)\n{}", t[t.len() - limit..].iter().collect::<String>())
}

/// The memory block added to the system prompt, or "" when the profile has no memory.
pub fn memory_block(ctx: &Ctx, cfg: &Obj, prof: &Obj) -> std::io::Result<String> {
    if on(prof, "memory").is_none() {
        return Ok(String::new());
    }
    let path = memory_path(ctx, cfg, Some(prof));
    if !py::exists(&path) {
        let (y, m, d, ..) = py::now_local();
        py::write_text(&path, &format!("# Long-term memory\n\n{PINNED}\n\n{JOURNAL}\n- {y:04}-{m:02}-{d:02} - memory init\n"), false)?;
    }
    let raw = py::read_text(&path, false).map_err(std::io::Error::other)?;
    let text = py::strip(&raw);
    if text.is_empty() {
        return Ok(String::new());
    }
    let limit = on(prof, "memory_limit").and_then(|v| v.as_f64()).map_or(MEMORY_LIMIT, |f| f as usize);
    let text = trim_memory(text, limit);
    Ok(format!(
        "\n\n# ===== LONG-TERM MEMORY =====================================\n\
         # This is what you remember from before. Treat it as true and current.\n\
         # Your memory file lives at:\n#   {}\n\
         # When asked to remember something, or when something worth keeping\n\
         # happens, append it to that file with your file tools: facts under\n\
         # '{PINNED}', dated one-liners under '{JOURNAL}'. Keep it concise.\n\
         # ------------------------------------------------------------\n\n\
         {text}\n# ============================================================\n",
        py::abspath(&path)))
}
