//! Python's behaviour, wherever Reidcc's output depends on it: Windows path rules (ntpath),
//! the Windows command line (subprocess.list2cmdline), shutil.which, float repr, str.strip and
//! text-mode files (universal newlines in, CRLF out). Stage 0's rule is byte-identical output
//! to reid.py, so these follow CPython 3.13, not Rust's std.

use std::fs;
use std::io::Write;

fn is_sep(c: char) -> bool {
    c == '\\' || c == '/'
}

// ------------------------------------------------------------------ ntpath ---
pub fn splitroot(p: &str) -> (&str, &str, &str) {
    let n = p.replace('/', "\\"); // same byte length, so indexes carry over to p
    let b = n.as_bytes();
    if b.first() == Some(&b'\\') {
        if b.get(1) == Some(&b'\\') {
            let unc = n.get(..8).is_some_and(|s| s.eq_ignore_ascii_case("\\\\?\\UNC\\"));
            let start = if unc { 8 } else { 2 };
            let Some(i) = n[start..].find('\\').map(|i| i + start) else { return (p, "", "") };
            let Some(j) = n[i + 1..].find('\\').map(|j| j + i + 1) else { return (p, "", "") };
            return (&p[..j], &p[j..j + 1], &p[j + 1..]);
        }
        return ("", &p[..1], &p[1..]);
    }
    let mut it = n.char_indices();
    if let (Some(_), Some((i1, ':'))) = (it.next(), it.next()) {
        let d = i1 + 1;
        if b.get(d) == Some(&b'\\') {
            return (&p[..d], &p[d..d + 1], &p[d + 1..]);
        }
        return (&p[..d], "", &p[d..]);
    }
    ("", "", p)
}

pub fn normpath(path: &str) -> String {
    let path = path.replace('/', "\\");
    let (drive, root, rest) = splitroot(&path);
    let prefix = format!("{drive}{root}");
    let mut comps: Vec<&str> = rest.split('\\').collect();
    let mut i = 0;
    while i < comps.len() {
        if comps[i].is_empty() || comps[i] == "." {
            comps.remove(i);
        } else if comps[i] == ".." {
            if i > 0 && comps[i - 1] != ".." {
                comps.drain(i - 1..=i);
                i -= 1;
            } else if i == 0 && !root.is_empty() {
                comps.remove(i);
            } else {
                i += 1;
            }
        } else {
            i += 1;
        }
    }
    if prefix.is_empty() && comps.is_empty() {
        return ".".into();
    }
    prefix + &comps.join("\\")
}

pub fn isabs(s: &str) -> bool {
    let c: Vec<char> = s.chars().take(3).map(|c| if c == '/' { '\\' } else { c }).collect();
    (c.len() == 3 && c[1] == ':' && c[2] == '\\') || (c.len() >= 2 && c[0] == '\\' && c[1] == '\\')
}

pub fn join(base: &str, parts: &[&str]) -> String {
    let (d, r, t) = splitroot(base);
    let (mut rd, mut rr, mut rp) = (d.to_string(), r.to_string(), t.to_string());
    for p in parts {
        let (pd, pr, pp) = splitroot(p);
        if !pr.is_empty() {
            if !pd.is_empty() || rd.is_empty() {
                rd = pd.to_string();
            }
            rr = pr.to_string();
            rp = pp.to_string();
            continue;
        } else if !pd.is_empty() && pd != rd {
            if pd.to_lowercase() != rd.to_lowercase() {
                rd = pd.to_string();
                rr = pr.to_string();
                rp = pp.to_string();
                continue;
            }
            rd = pd.to_string();
        }
        if rp.chars().last().is_some_and(|c| !is_sep(c)) {
            rp.push('\\');
        }
        rp.push_str(pp);
    }
    if !rp.is_empty() && rr.is_empty() && rd.chars().last().is_some_and(|c| !":\\/".contains(c)) {
        return format!("{rd}\\{rp}");
    }
    format!("{rd}{rr}{rp}")
}

pub fn split(p: &str) -> (String, String) {
    let (d, r, t) = splitroot(p);
    let i = t.rfind(is_sep).map_or(0, |i| i + 1);
    let (head, tail) = t.split_at(i);
    (format!("{d}{r}{}", head.trim_end_matches(is_sep)), tail.to_string())
}

pub fn dirname(p: &str) -> String {
    split(p).0
}

pub fn basename(p: &str) -> String {
    split(p).1
}

pub fn splitext(p: &str) -> (String, String) {
    let sep_i = p.rfind(is_sep).map_or(-1, |i| i as isize);
    if let Some(dot) = p.rfind('.') {
        if dot as isize > sep_i {
            let start = (sep_i + 1) as usize;
            if p[start..dot].chars().any(|c| c != '.') {
                return (p[..dot].to_string(), p[dot..].to_string());
            }
        }
    }
    (p.to_string(), String::new())
}

/// ntpath.abspath on Windows: GetFullPathNameW of the normalized path.
pub fn abspath(p: &str) -> String {
    let n = normpath(p);
    crate::win::full_path_name(&n).unwrap_or_else(|| {
        if isabs(&n) { n } else { normpath(&join(&getcwd(), &[p])) }
    })
}

pub fn getcwd() -> String {
    std::env::current_dir().map(|p| p.to_string_lossy().into_owned()).unwrap_or_default()
}

pub fn normcase(s: &str) -> String {
    s.replace('/', "\\").to_lowercase()
}

pub fn expanduser(path: &str) -> String {
    if !path.starts_with('~') {
        return path.to_string();
    }
    let chars: Vec<char> = path.chars().collect();
    let mut i = 1;
    while i < chars.len() && !is_sep(chars[i]) {
        i += 1;
    }
    let userhome = if let Ok(h) = std::env::var("USERPROFILE") {
        h
    } else if let Ok(hp) = std::env::var("HOMEPATH") {
        join(&std::env::var("HOMEDRIVE").unwrap_or_default(), &[&hp])
    } else {
        return path.to_string();
    };
    let mut userhome = userhome;
    if i != 1 {
        let target: String = chars[1..i].iter().collect();
        let current = std::env::var("USERNAME").ok();
        if current.as_deref() != Some(target.as_str()) {
            if current.as_deref() != Some(basename(&userhome).as_str()) {
                return path.to_string();
            }
            userhome = join(&dirname(&userhome), &[&target]);
        }
    }
    userhome + &chars[i..].iter().collect::<String>()
}

fn getenv(var: &str) -> Option<String> {
    if var.is_empty() || var.contains('=') || var.contains('\0') {
        return None;
    }
    std::env::var(var).ok()
}

pub fn expandvars(path: &str) -> String {
    if !path.contains('$') && !path.contains('%') {
        return path.to_string();
    }
    let varchar = |c: char| c.is_ascii_alphanumeric() || c == '_' || c == '-';
    let mut p: Vec<char> = path.chars().collect();
    let mut res = String::new();
    let mut index = 0usize;
    while index < p.len() {
        let c = p[index];
        if c == '\'' {
            p = p[index + 1..].to_vec();
            res.push('\'');
            match p.iter().position(|&x| x == '\'') {
                Some(i) => {
                    res.extend(&p[..=i]);
                    index = i;
                }
                None => {
                    res.extend(&p);
                    index = p.len().wrapping_sub(1);
                }
            }
        } else if c == '%' {
            if p.get(index + 1) == Some(&'%') {
                res.push('%');
                index += 1;
            } else {
                p = p[index + 1..].to_vec();
                match p.iter().position(|&x| x == '%') {
                    None => {
                        res.push('%');
                        res.extend(&p);
                        index = p.len().wrapping_sub(1);
                    }
                    Some(i) => {
                        let var: String = p[..i].iter().collect();
                        res += &getenv(&var).unwrap_or_else(|| format!("%{var}%"));
                        index = i;
                    }
                }
            }
        } else if c == '$' {
            if p.get(index + 1) == Some(&'$') {
                res.push('$');
                index += 1;
            } else if p.get(index + 1) == Some(&'{') {
                p = p[index + 2..].to_vec();
                match p.iter().position(|&x| x == '}') {
                    None => {
                        res += "${";
                        res.extend(&p);
                        index = p.len().wrapping_sub(1);
                    }
                    Some(i) => {
                        let var: String = p[..i].iter().collect();
                        res += &getenv(&var).unwrap_or_else(|| format!("${{{var}}}"));
                        index = i;
                    }
                }
            } else {
                let mut var = String::new();
                index += 1;
                while index < p.len() && varchar(p[index]) {
                    var.push(p[index]);
                    index += 1;
                }
                res += &getenv(&var).unwrap_or_else(|| format!("${var}"));
                if index < p.len() {
                    index -= 1;
                }
            }
        } else {
            res.push(c);
        }
        index = index.wrapping_add(1);
    }
    res
}

/// os.path.relpath; None where Python raises ValueError (another drive).
pub fn relpath(path: &str, start: &str) -> Option<String> {
    let (sa, pa) = (abspath(start), abspath(path));
    let (sd, _, sr) = splitroot(&sa);
    let (pd, _, pr) = splitroot(&pa);
    if normcase(sd) != normcase(pd) {
        return None;
    }
    let sl: Vec<&str> = if sr.is_empty() { vec![] } else { sr.split('\\').collect() };
    let pl: Vec<&str> = if pr.is_empty() { vec![] } else { pr.split('\\').collect() };
    let i = sl.iter().zip(&pl).take_while(|(a, b)| normcase(a) == normcase(b)).count();
    let mut rel: Vec<&str> = vec![".."; sl.len() - i];
    rel.extend(&pl[i..]);
    Some(if rel.is_empty() { ".".into() } else { rel.join("\\") })
}

pub fn exists(p: &str) -> bool {
    !p.is_empty() && fs::metadata(p).is_ok()
}

pub fn isdir(p: &str) -> bool {
    !p.is_empty() && fs::metadata(p).is_ok_and(|m| m.is_dir())
}

/// os.path.getsize, 0 if it can't be read.
pub fn getsize(p: &str) -> u64 {
    fs::metadata(p).map(|m| m.len()).unwrap_or(0)
}

/// st_mtime the way CPython computes it on Windows: seconds + nanoseconds * 1e-9.
pub fn getmtime(p: &str) -> Option<f64> {
    let m = fs::metadata(p).ok()?.modified().ok()?;
    let d = m.duration_since(std::time::UNIX_EPOCH).ok()?;
    Some(d.as_secs() as f64 + d.subsec_nanos() as f64 * 1e-9)
}

/// os.path.realpath for an existing path: the final path, without the \\?\ prefix.
pub fn realpath(p: &str) -> String {
    match fs::canonicalize(p) {
        Ok(c) => {
            let s = c.to_string_lossy().into_owned();
            if let Some(rest) = s.strip_prefix("\\\\?\\UNC\\") {
                format!("\\\\{rest}")
            } else if let Some(rest) = s.strip_prefix("\\\\?\\") {
                rest.to_string()
            } else {
                s
            }
        }
        Err(_) => abspath(p),
    }
}

/// glob.glob(join(dir, pattern)) for a pattern whose only wildcard is `*`: names in scandir order,
/// dot names skipped, matched case-insensitively (fnmatch on Windows), joined onto `dir`.
pub fn glob(dir: &str, pattern: &str) -> Vec<String> {
    fn matches(name: &[char], pat: &[char]) -> bool {
        match pat.split_first() {
            None => name.is_empty(),
            Some(('*', rest)) => (0..=name.len()).any(|i| matches(&name[i..], rest)),
            Some((c, rest)) => name.first() == Some(c) && matches(&name[1..], rest),
        }
    }
    let pat: Vec<char> = normcase(pattern).chars().collect();
    let Ok(rd) = fs::read_dir(if dir.is_empty() { "." } else { dir }) else { return vec![] };
    rd.flatten().map(|e| e.file_name().to_string_lossy().into_owned())
        .filter(|n| !n.starts_with('.'))
        .filter(|n| matches(&normcase(n).chars().collect::<Vec<_>>(), &pat))
        .map(|n| join(dir, &[&n])).collect()
}

// --------------------------------------------------------------- shutil ---
/// shutil.which(cmd) on Windows, default mode (F_OK | X_OK).
pub fn which(cmd: &str) -> Option<String> {
    let (dir, name) = split(cmd);
    let dirs: Vec<String> = if !dir.is_empty() {
        vec![dir]
    } else {
        let path = std::env::var("PATH").ok()?;
        if path.is_empty() {
            return None;
        }
        let mut d: Vec<String> = path.split(';').map(String::from).collect();
        if crate::win::need_current_dir_for_exe(&name) {
            d.insert(0, ".".into());
        }
        d
    };
    let pathext = std::env::var("PATHEXT").ok().filter(|s| !s.is_empty())
        .unwrap_or_else(|| ".COM;.EXE;.BAT;.CMD;.VBS;.JS;.WS;.MSC".into());
    let exts: Vec<String> = pathext.split(';').filter(|e| !e.is_empty())
        .map(|e| e.trim_end_matches('.').to_string()).collect();
    let mut files: Vec<String> = exts.iter().map(|e| format!("{name}{e}")).collect();
    let up = name.to_uppercase();
    if exts.iter().any(|e| up.ends_with(&e.to_uppercase())) {
        files.insert(0, name.clone());
    }
    let mut seen = std::collections::HashSet::new();
    for d in dirs {
        if seen.insert(normcase(&d)) {
            for f in &files {
                let full = join(&d, &[f]);
                if exists(&full) && !isdir(&full) {
                    return Some(full);
                }
            }
        }
    }
    None
}

// ----------------------------------------------------------- subprocess ---
/// subprocess.list2cmdline: the command line Windows programs parse back into the same args.
pub fn list2cmdline<S: AsRef<str>>(args: &[S]) -> String {
    let mut out = String::new();
    for (n, arg) in args.iter().enumerate() {
        let arg = arg.as_ref();
        let mut bs = 0usize;
        if n > 0 {
            out.push(' ');
        }
        let quote = arg.contains(' ') || arg.contains('\t') || arg.is_empty();
        if quote {
            out.push('"');
        }
        for c in arg.chars() {
            match c {
                '\\' => bs += 1,
                '"' => {
                    out.push_str(&"\\".repeat(bs * 2));
                    bs = 0;
                    out.push_str("\\\"");
                }
                _ => {
                    out.push_str(&"\\".repeat(bs));
                    bs = 0;
                    out.push(c);
                }
            }
        }
        out.push_str(&"\\".repeat(bs));
        if quote {
            out.push_str(&"\\".repeat(bs));
            out.push('"');
        }
    }
    out
}

// -------------------------------------------------------------- strings ---
pub fn isspace(c: char) -> bool {
    c.is_whitespace() || ('\x1c'..='\x1f').contains(&c)
}

pub fn strip(s: &str) -> &str {
    s.trim_matches(isspace)
}

pub fn rstrip(s: &str) -> &str {
    s.trim_end_matches(isspace)
}

/// Python's repr(float).
pub fn float_repr(f: f64) -> String {
    if f.is_nan() {
        return "nan".into();
    }
    if f.is_infinite() {
        return if f > 0.0 { "inf" } else { "-inf" }.into();
    }
    if f == 0.0 {
        return if f.is_sign_negative() { "-0.0" } else { "0.0" }.into();
    }
    let s = format!("{:e}", f.abs()); // shortest round-trip digits: "1.2345e9"
    let (mant, exp) = s.split_once('e').unwrap();
    let exp: i32 = exp.parse().unwrap();
    let digits = mant.replace('.', "");
    let out = if !(-4..16).contains(&exp) {
        let m = if digits.len() > 1 { format!("{}.{}", &digits[..1], &digits[1..]) } else { digits };
        format!("{m}e{}{:02}", if exp < 0 { '-' } else { '+' }, exp.abs())
    } else if exp < 0 {
        format!("0.{}{digits}", "0".repeat((-exp - 1) as usize))
    } else {
        let e = exp as usize;
        if digits.len() > e + 1 {
            format!("{}.{}", &digits[..=e], &digits[e + 1..])
        } else {
            format!("{digits}{}.0", "0".repeat(e + 1 - digits.len()))
        }
    };
    if f < 0.0 { format!("-{out}") } else { out }
}

pub fn sha1_hex(s: &str) -> String {
    sha1_smol::Sha1::from(s.as_bytes()).digest().to_string()
}

// ---------------------------------------------------------------- files ---
/// open(path, encoding="utf-8").read(): universal newlines. `raw` keeps them (newline="").
pub fn read_text(path: &str, raw: bool) -> Result<String, String> {
    let b = fs::read(path).map_err(|e| e.to_string())?;
    let s = String::from_utf8(b).map_err(|e| {
        format!("'utf-8' codec can't decode byte 0x{:02x} in position {}", e.as_bytes()[e.utf8_error().valid_up_to()],
                e.utf8_error().valid_up_to())
    })?;
    Ok(if raw { s } else { s.replace("\r\n", "\n").replace('\r', "\n") })
}

/// Text-mode write: "\n" goes to disk as "\r\n" unless `raw` (newline="").
pub fn write_text(path: &str, text: &str, raw: bool) -> std::io::Result<()> {
    let data = if raw { text.to_string() } else { text.replace('\n', "\r\n") };
    fs::write(path, data)
}

/// tempfile.gettempdir()
pub fn gettempdir() -> String {
    let mut cands: Vec<String> = ["TMPDIR", "TEMP", "TMP"].iter().filter_map(|k| std::env::var(k).ok()).collect();
    cands.push(expanduser(r"~\AppData\Local\Temp"));
    if let Ok(r) = std::env::var("SYSTEMROOT") {
        cands.push(join(&r, &["Temp"]));
    }
    cands.extend([r"c:\temp", r"c:\tmp", r"\temp", r"\tmp"].map(String::from));
    cands.into_iter().find(|d| isdir(d)).map(|d| abspath(&d)).unwrap_or_else(getcwd)
}

/// tempfile.mkstemp + a text-mode write: returns the path.
pub fn mkstemp(prefix: &str, suffix: &str, text: &str) -> std::io::Result<String> {
    const CH: &[u8] = b"abcdefghijklmnopqrstuvwxyz0123456789_";
    let dir = gettempdir();
    loop {
        let r = uuid::Uuid::new_v4();
        let name: String = r.as_bytes()[..8].iter().map(|b| CH[*b as usize % CH.len()] as char).collect();
        let path = join(&dir, &[&format!("{prefix}{name}{suffix}")]);
        match fs::OpenOptions::new().write(true).create_new(true).open(&path) {
            Ok(mut f) => {
                f.write_all(text.replace('\n', "\r\n").as_bytes())?;
                return Ok(path);
            }
            Err(e) if e.kind() == std::io::ErrorKind::AlreadyExists => continue,
            Err(e) => return Err(e),
        }
    }
}

/// datetime.now(): (year, month, day, hour, minute, second), local time.
pub fn now_local() -> (u16, u16, u16, u16, u16, u16) {
    crate::win::local_time()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn floats() {
        for (f, s) in [(1.0, "1.0"), (0.1, "0.1"), (1e16, "1e+16"), (1.5e-5, "1.5e-05"), (123456789.125, "123456789.125"),
                       (1e15, "1000000000000000.0"), (0.0001, "0.0001"), (-2.5, "-2.5"), (1763412345.1234567, "1763412345.1234567")] {
            assert_eq!(float_repr(f), s);
        }
    }

    #[test]
    fn cmdline() {
        assert_eq!(list2cmdline(&["a b", "", "c\\\"d", "e\\"]), "\"a b\" \"\" c\\\\\\\"d e\\");
        assert_eq!(list2cmdline(&["x y\\"]), "\"x y\\\\\"");
    }

    #[test]
    fn paths() {
        assert_eq!(normpath("E:/reidcc/./a/../b//c"), "E:\\reidcc\\b\\c");
        assert_eq!(join("E:\\reidcc", &["personas/x.md"]), "E:\\reidcc\\personas/x.md");
        assert_eq!(join("E:\\reidcc", &["C:\\y"]), "C:\\y");
        assert!(isabs("C:/x") && !isabs("\\x") && isabs("\\\\srv\\s"));
        assert_eq!(splitext("a/b.c.md"), ("a/b.c".into(), ".md".into()));
        assert_eq!(splitext(".bashrc"), (".bashrc".into(), "".into()));
        assert_eq!(split("C:\\a\\b"), ("C:\\a".into(), "b".into()));
    }
}
