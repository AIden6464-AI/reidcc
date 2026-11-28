//! The engine's exact (24-bit) colours, moved to the nearest Reidcc colour on the way to the session
//! window (vision\Spec\SPEC-one-look.md Part 7.1). Claude Code paints most of its UI with `38;2;r;g;b`,
//! which skips xterm's 16-colour theme, so the theme alone can't put it in the palette.

/// Off when settings says `terminal colours: the engine's own` (reid.json `"colors": "engine"`).
pub static ON: std::sync::atomic::AtomicBool = std::sync::atomic::AtomicBool::new(true);

pub fn set_from(cfg: &reidcc::Obj) {
    let on = cfg.get("colors").and_then(serde_json::Value::as_str) != Some("engine");
    ON.store(on, std::sync::atomic::Ordering::Relaxed);
}

/// Text colours: the bone family, oxide, bronze, emerald, and the session theme's bright steps.
const FG: &[u32] = &[
    0xD6D0C8, 0x9F978E, 0x746F69, 0x4A4540, 0xEDE8E1, 0x928A82, 0xA8968A, 0xB4ACA2, 0xC4B3A6, 0xBDB6AD,
    0xC0584B, 0xD4705F, 0xC99A45, 0xDDB264, 0x00C463, 0x2BD57E,
];
/// Backgrounds: the surfaces, plus dark and mid oxide / emerald / bronze so diff lines keep their meaning.
const BG: &[u32] = &[
    0x040404, 0x0E0D0C, 0x171513, 0x292723, 0x4A4540,
    0x2E1714, 0x5A2A24, 0x0F2A1C, 0x1C4A30, 0x2B2213, 0x54421F,
];

/// A CSI longer than this with no final byte isn't cut off by a chunk boundary: pass it through.
const MAX_SPLIT_CSI_LEN: usize = 64;

/// The nearest palette entry by "redmean" distance (CompuPhase's weighted RGB: a cheap stand-in for
/// how far apart colours look). Twenty palette entries a colour, so no colour-science crate.
fn nearest(palette: &[u32], r: u8, g: u8, b: u8) -> (u8, u8, u8) {
    let distance = |color: u32| {
        let (pr, pg, pb) = ((color >> 16) as i32, ((color >> 8) & 0xFF) as i32, (color & 0xFF) as i32);
        let red_mean = (pr + r as i32) / 2;
        let (dr, dg, db) = (pr - r as i32, pg - g as i32, pb - b as i32);
        (512 + red_mean) * dr * dr / 256 + 4 * dg * dg + (767 - red_mean) * db * db / 256
    };
    let best = *palette.iter().min_by_key(|&&color| distance(color)).unwrap();
    ((best >> 16) as u8, (best >> 8) as u8, best as u8)
}

/// One SGR parameter list (`1;38;2;255;193;7`) with its 24-bit colours swapped.
fn params(list: &str) -> String {
    let parts: Vec<&str> = list.split(';').collect();
    let mut out: Vec<String> = Vec::with_capacity(parts.len());
    let mut i = 0;
    while i < parts.len() {
        let rgb = || -> Option<(u8, u8, u8)> {
            Some((parts.get(i + 2)?.parse().ok()?, parts.get(i + 3)?.parse().ok()?, parts.get(i + 4)?.parse().ok()?))
        };
        if (parts[i] == "38" || parts[i] == "48") && parts.get(i + 1) == Some(&"2") {
            if let Some((r, g, b)) = rgb() {
                let (r, g, b) = nearest(if parts[i] == "38" { FG } else { BG }, r, g, b);
                out.push(format!("{};2;{r};{g};{b}", parts[i]));
                i += 5;
                continue;
            }
        }
        out.push(parts[i].to_string());
        i += 1;
    }
    out.join(";")
}

/// `text` with every SGR colour moved into the palette. A CSI cut off at the end is returned in the
/// second part, to go in front of the next chunk. Hand-parsed: only `ESC [ digits ; : m` matters
/// here, and everything else passes through byte for byte, which a full VT parser wouldn't promise.
pub fn recolor(text: &str) -> (String, String) {
    if !ON.load(std::sync::atomic::Ordering::Relaxed) {
        return (text.to_string(), String::new());
    }
    let (mut out, mut rest) = (String::with_capacity(text.len()), text);
    while let Some(at) = rest.find('\x1b') {
        out.push_str(&rest[..at]);
        let seq = &rest[at..];
        if !seq.starts_with("\x1b[") {
            if seq.len() == 1 {
                return (out, seq.to_string()); // a lone ESC: its sequence comes next chunk
            }
            out.push('\x1b');
            rest = &seq[1..];
            continue;
        }
        let body = &seq[2..];
        let end = body.find(|c: char| !(c.is_ascii_digit() || c == ';' || c == ':')).unwrap_or(body.len());
        if end == body.len() {
            if seq.len() <= MAX_SPLIT_CSI_LEN {
                return (out, seq.to_string()); // cut off mid-sequence
            }
            out.push_str(seq);
            return (out, String::new());
        }
        if !body.as_bytes()[end].is_ascii() {
            // a stray ESC [ in text (a file's own bytes, say): its "final byte" is no CSI final byte,
            // so pass the two bytes and carry on. Slicing here would split the character and panic.
            out.push_str("\x1b[");
            rest = body;
            continue;
        }
        if body.as_bytes()[end] == b'm' {
            out.push_str("\x1b[");
            out.push_str(&params(&body[..end]));
            out.push('m');
        } else {
            out.push_str(&seq[..2 + end + 1]);
        }
        rest = &body[end + 1..];
    }
    out.push_str(rest);
    (out, String::new())
}

#[cfg(test)]
mod tests {
    use super::recolor;

    #[test]
    fn truecolor_moves_into_the_palette() {
        // Claude's yellow -> bronze (bright), its orange -> oxide (bright); bold and plain codes stay
        let (s, rest) = recolor("a\x1b[1;38;2;255;193;7mX\x1b[38;2;215;119;87mY\x1b[0m");
        assert_eq!(s, "a\x1b[1;38;2;221;178;100mX\x1b[38;2;212;112;95mY\x1b[0m");
        assert!(rest.is_empty());
        // a red diff background keeps red (mid oxide), not grey
        assert_eq!(recolor("\x1b[48;2;122;41;54m").0, "\x1b[48;2;90;42;36m");
        // other sequences pass through untouched
        assert_eq!(recolor("\x1b[2J\x1b[?25l\x1b]0;t\x07·").0, "\x1b[2J\x1b[?25l\x1b]0;t\x07·");
    }

    #[test]
    fn a_split_sequence_waits_for_the_rest() {
        let (s, rest) = recolor("ab\x1b[38;2;25");
        assert_eq!((s.as_str(), rest.as_str()), ("ab", "\x1b[38;2;25"));
        assert_eq!(recolor("x\x1b"), ("x".to_string(), "\x1b".to_string()));
    }

    #[test]
    fn a_stray_escape_before_a_multibyte_char_passes_through() {
        // a file's own ESC [ then a non-ASCII char: no CSI final byte, and no panic on the boundary
        assert_eq!(recolor("\x1b[é!").0, "\x1b[é!");
        assert_eq!(recolor("\x1b[12;\u{1b}[é").0, "\x1b[12;\u{1b}[é");
    }
}
