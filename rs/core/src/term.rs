//! Terminal colours from vision\reidcc-palette.md (bone text, one emerald signal) and the reset
//! that undoes whatever a session left behind.

pub const TEXT: &str = "\x1b[38;2;214;208;200m"; // #D6D0C8
pub const TEXT2: &str = "\x1b[38;2;159;151;142m"; // #9F978E
pub const TEXT3: &str = "\x1b[38;2;127;122;115m"; // #7F7A73: the lowest warm stone clearing 4.5:1 on canvas and s1
pub const BRONZE: &str = "\x1b[38;2;201;154;69m"; // #C99A45
pub const OXIDE: &str = "\x1b[38;2;192;88;75m"; // #C0584B
pub const R: &str = "\x1b[0m";

pub const TERM_RESET: &str = "\x1b[0m\x1b[?25h\x1b[?2004l\x1b[?1000l\x1b[?1002l\x1b[?1003l\x1b[?1006l\x1b[?1004l\x1b[<u";

/// print(): Python writes "\r\n" for "\n" on Windows, even into a pipe.
#[macro_export]
macro_rules! out {
    ($($t:tt)*) => {{
        use std::io::Write;
        let s = format!($($t)*).replace('\n', "\r\n");
        let mut o = std::io::stdout().lock();
        let _ = o.write_all(s.as_bytes());
        let _ = o.write_all(b"\r\n");
        let _ = o.flush();
    }};
}

/// print(..., file=sys.stderr)
#[macro_export]
macro_rules! errln {
    ($($t:tt)*) => {{
        use std::io::Write;
        let s = format!($($t)*).replace('\n', "\r\n");
        let mut o = std::io::stderr().lock();
        let _ = o.write_all(s.as_bytes());
        let _ = o.write_all(b"\r\n");
        let _ = o.flush();
    }};
}

pub fn is_tty() -> bool {
    use std::io::IsTerminal;
    std::io::stdout().is_terminal()
}

/// Raw bytes to stdout, no newline.
pub fn write(s: &str) {
    use std::io::Write;
    let mut o = std::io::stdout().lock();
    let _ = o.write_all(s.as_bytes());
    let _ = o.flush();
}
