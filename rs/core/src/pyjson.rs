//! JSON the way Python's json module reads and writes it: the same error messages (reid.json
//! errors are shown to Reid), the same key order, and json.dumps's exact spacing and escaping.
//! Values are serde_json's, with key order kept. Known gaps: NaN/Infinity and integers past
//! 64 bits load as null/float, lone surrogates as U+FFFD.

use serde_json::{Map, Number, Value};

const WS: [char; 4] = [' ', '\t', '\n', '\r'];

enum E {
    Stop(usize),
    Err(String),
}

fn msg(s: &[char], m: &str, pos: usize) -> E {
    E::Err(errmsg(s, m, pos))
}

fn errmsg(s: &[char], m: &str, pos: usize) -> String {
    let pos = pos.min(s.len());
    let line = s[..pos].iter().filter(|&&c| c == '\n').count() + 1;
    let col = match s[..pos].iter().rposition(|&c| c == '\n') {
        Some(i) => pos - i,
        None => pos + 1,
    };
    format!("{m}: line {line} column {col} (char {pos})")
}

fn ws(s: &[char], mut i: usize) -> usize {
    while i < s.len() && WS.contains(&s[i]) {
        i += 1;
    }
    i
}

fn starts(s: &[char], i: usize, lit: &str) -> bool {
    let l: Vec<char> = lit.chars().collect();
    s.get(i..i + l.len()) == Some(&l[..])
}

/// json.loads
pub fn loads(text: &str) -> Result<Value, String> {
    let s: Vec<char> = text.chars().collect();
    if s.first() == Some(&'\u{feff}') {
        return Err(errmsg(&s, "Unexpected UTF-8 BOM (decode using utf-8-sig)", 0));
    }
    let start = ws(&s, 0);
    let (v, end) = match scan(&s, start) {
        Ok(r) => r,
        Err(E::Stop(p)) => return Err(errmsg(&s, "Expecting value", p)),
        Err(E::Err(m)) => return Err(m),
    };
    let end = ws(&s, end);
    if end != s.len() {
        return Err(errmsg(&s, "Extra data", end));
    }
    Ok(v)
}

fn scan(s: &[char], i: usize) -> Result<(Value, usize), E> {
    let Some(&c) = s.get(i) else { return Err(E::Stop(i)) };
    match c {
        '"' => scanstring(s, i + 1).map(|(t, e)| (Value::String(t), e)),
        '{' => object(s, i + 1),
        '[' => array(s, i + 1),
        'n' if starts(s, i, "null") => Ok((Value::Null, i + 4)),
        't' if starts(s, i, "true") => Ok((Value::Bool(true), i + 4)),
        'f' if starts(s, i, "false") => Ok((Value::Bool(false), i + 5)),
        _ => {
            if let Some(r) = number(s, i) {
                return Ok(r);
            }
            if starts(s, i, "NaN") {
                Ok((Value::Null, i + 3))
            } else if starts(s, i, "Infinity") {
                Ok((Value::Null, i + 8))
            } else if starts(s, i, "-Infinity") {
                Ok((Value::Null, i + 9))
            } else {
                Err(E::Stop(i))
            }
        }
    }
}

fn number(s: &[char], i: usize) -> Option<(Value, usize)> {
    let digit = |j: usize| s.get(j).is_some_and(|c| c.is_ascii_digit());
    let mut j = i;
    if s.get(j) == Some(&'-') {
        j += 1;
    }
    if s.get(j) == Some(&'0') {
        j += 1;
    } else if s.get(j).is_some_and(|c| ('1'..='9').contains(c)) {
        while digit(j) {
            j += 1;
        }
    } else {
        return None;
    }
    let int_end = j;
    if s.get(j) == Some(&'.') && digit(j + 1) {
        j += 1;
        while digit(j) {
            j += 1;
        }
    }
    if matches!(s.get(j), Some('e' | 'E')) {
        let mut k = j + 1;
        if matches!(s.get(k), Some('+' | '-')) {
            k += 1;
        }
        if digit(k) {
            while digit(k) {
                k += 1;
            }
            j = k;
        }
    }
    let text: String = s[i..j].iter().collect();
    let v = if j == int_end {
        if let Ok(n) = text.parse::<i64>() {
            Value::Number(n.into())
        } else if let Ok(n) = text.parse::<u64>() {
            Value::Number(n.into())
        } else {
            Number::from_f64(text.parse::<f64>().unwrap_or(0.0)).map_or(Value::Null, Value::Number)
        }
    } else {
        Number::from_f64(text.parse::<f64>().unwrap_or(0.0)).map_or(Value::Null, Value::Number)
    };
    Some((v, j))
}

fn hex4(s: &[char], i: usize) -> Option<u32> {
    let h: String = s.get(i..i + 4)?.iter().collect();
    if h.chars().all(|c| c.is_ascii_hexdigit()) { u32::from_str_radix(&h, 16).ok() } else { None }
}

/// The string after the quote at `end - 1`; returns it and the index after the closing quote.
fn scanstring(s: &[char], mut end: usize) -> Result<(String, usize), E> {
    let begin = end - 1;
    let mut out = String::new();
    loop {
        let Some(&c) = s.get(end) else { return Err(msg(s, "Unterminated string starting at", begin)) };
        if c == '"' {
            return Ok((out, end + 1));
        }
        if (c as u32) < 0x20 {
            return Err(msg(s, "Invalid control character at", end));
        }
        if c != '\\' {
            out.push(c);
            end += 1;
            continue;
        }
        let Some(&esc) = s.get(end + 1) else { return Err(msg(s, "Unterminated string starting at", begin)) };
        if esc != 'u' {
            let ch = match esc {
                '"' => '"', '\\' => '\\', '/' => '/', 'b' => '\x08', 'f' => '\x0c', 'n' => '\n', 'r' => '\r', 't' => '\t',
                _ => return Err(msg(s, "Invalid \\escape", end)),
            };
            out.push(ch);
            end += 2;
            continue;
        }
        let Some(mut u) = hex4(s, end + 2) else { return Err(msg(s, "Invalid \\uXXXX escape", end + 1)) };
        end += 6;
        if (0xd800..=0xdbff).contains(&u) && s.get(end) == Some(&'\\') && s.get(end + 1) == Some(&'u') {
            let Some(u2) = hex4(s, end + 2) else { return Err(msg(s, "Invalid \\uXXXX escape", end + 1)) };
            if (0xdc00..=0xdfff).contains(&u2) {
                u = 0x10000 + (((u - 0xd800) << 10) | (u2 - 0xdc00));
                end += 6;
            }
        }
        out.push(char::from_u32(u).unwrap_or('\u{fffd}'));
    }
}

fn object(s: &[char], mut end: usize) -> Result<(Value, usize), E> {
    let mut map = Map::new();
    let mut next = s.get(end).copied();
    if next != Some('"') {
        if next.is_some_and(|c| WS.contains(&c)) {
            end = ws(s, end);
            next = s.get(end).copied();
        }
        if next == Some('}') {
            return Ok((Value::Object(map), end + 1));
        } else if next != Some('"') {
            return Err(msg(s, "Expecting property name enclosed in double quotes", end));
        }
    }
    end += 1;
    loop {
        let (key, e) = scanstring(s, end)?;
        end = e;
        if s.get(end) != Some(&':') {
            end = ws(s, end);
            if s.get(end) != Some(&':') {
                return Err(msg(s, "Expecting ':' delimiter", end));
            }
        }
        end = ws(s, end + 1);
        let (value, e) = match scan(s, end) {
            Ok(r) => r,
            Err(E::Stop(p)) => return Err(msg(s, "Expecting value", p)),
            Err(e) => return Err(e),
        };
        end = e;
        map.insert(key, value);
        end = ws(s, end);
        let next = s.get(end).copied();
        end += 1;
        if next == Some('}') {
            break;
        } else if next != Some(',') {
            return Err(msg(s, "Expecting ',' delimiter", end - 1));
        }
        let comma = end - 1;
        end = ws(s, end);
        let next = s.get(end).copied();
        end += 1;
        if next != Some('"') {
            if next == Some('}') {
                return Err(msg(s, "Illegal trailing comma before end of object", comma));
            }
            return Err(msg(s, "Expecting property name enclosed in double quotes", end - 1));
        }
    }
    Ok((Value::Object(map), end))
}

fn array(s: &[char], mut end: usize) -> Result<(Value, usize), E> {
    let mut items = vec![];
    end = ws(s, end);
    if s.get(end) == Some(&']') {
        return Ok((Value::Array(items), end + 1));
    }
    loop {
        let (value, e) = match scan(s, end) {
            Ok(r) => r,
            Err(E::Stop(p)) => return Err(msg(s, "Expecting value", p)),
            Err(e) => return Err(e),
        };
        items.push(value);
        end = ws(s, e);
        let next = s.get(end).copied();
        end += 1;
        if next == Some(']') {
            break;
        } else if next != Some(',') {
            return Err(msg(s, "Expecting ',' delimiter", end - 1));
        }
        let comma = end - 1;
        end = ws(s, end);
        if s.get(end) == Some(&']') {
            return Err(msg(s, "Illegal trailing comma before end of array", comma));
        }
    }
    Ok((Value::Array(items), end))
}

// ---------------------------------------------------------------- dumps ---
/// json.dumps(v, indent=indent, ensure_ascii=ascii), with `compact` for separators=(",", ":").
pub fn dumps(v: &Value, indent: Option<usize>, ascii: bool) -> String {
    let mut out = String::new();
    enc(v, &mut out, indent, 0, ascii, false);
    out
}

pub fn dumps_compact(v: &Value) -> String {
    let mut out = String::new();
    enc(v, &mut out, None, 0, true, true);
    out
}

pub fn number_repr(n: &Number) -> String {
    if let Some(i) = n.as_i64() {
        i.to_string()
    } else if let Some(u) = n.as_u64() {
        u.to_string()
    } else {
        crate::py::float_repr(n.as_f64().unwrap_or(0.0))
    }
}

fn enc(v: &Value, out: &mut String, indent: Option<usize>, level: usize, ascii: bool, compact: bool) {
    let (item_sep, key_sep) = match (indent, compact) {
        (_, true) => (",", ":"),
        (Some(_), _) => (",", ": "),
        (None, _) => (", ", ": "),
    };
    let open = |out: &mut String, lvl: usize| {
        if let Some(n) = indent {
            out.push('\n');
            out.push_str(&" ".repeat(n * lvl));
        }
    };
    match v {
        Value::Null => out.push_str("null"),
        Value::Bool(b) => out.push_str(if *b { "true" } else { "false" }),
        Value::Number(n) => out.push_str(&number_repr(n)),
        Value::String(s) => out.push_str(&quote(s, ascii)),
        Value::Array(a) if a.is_empty() => out.push_str("[]"),
        Value::Object(m) if m.is_empty() => out.push_str("{}"),
        Value::Array(a) => {
            out.push('[');
            for (i, x) in a.iter().enumerate() {
                if i > 0 {
                    out.push_str(item_sep);
                }
                open(out, level + 1);
                enc(x, out, indent, level + 1, ascii, compact);
            }
            open(out, level);
            out.push(']');
        }
        Value::Object(m) => {
            out.push('{');
            for (i, (k, x)) in m.iter().enumerate() {
                if i > 0 {
                    out.push_str(item_sep);
                }
                open(out, level + 1);
                out.push_str(&quote(k, ascii));
                out.push_str(key_sep);
                enc(x, out, indent, level + 1, ascii, compact);
            }
            open(out, level);
            out.push('}');
        }
    }
}

/// A JSON string literal, escaped the way json.dumps does.
pub fn quote(s: &str, ascii: bool) -> String {
    let mut out = String::with_capacity(s.len() + 2);
    out.push('"');
    for c in s.chars() {
        match c {
            '"' => out.push_str("\\\""),
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            '\x08' => out.push_str("\\b"),
            '\x0c' => out.push_str("\\f"),
            c if (c as u32) < 0x20 || (ascii && (c as u32) >= 0x7f) => {
                let mut buf = [0u16; 2];
                for u in c.encode_utf16(&mut buf) {
                    out.push_str(&format!("\\u{:04x}", u));
                }
            }
            c => out.push(c),
        }
    }
    out.push('"');
    out
}

// ------------------------------------------------------ python str/repr ---
/// Python truthiness of a JSON value.
pub fn truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64() != Some(0.0),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(m) => !m.is_empty(),
    }
}

/// Python's str() of a loaded JSON value.
pub fn py_str(v: &Value) -> String {
    match v {
        Value::String(s) => s.clone(),
        _ => py_repr(v),
    }
}

pub fn py_repr(v: &Value) -> String {
    match v {
        Value::Null => "None".into(),
        Value::Bool(b) => if *b { "True" } else { "False" }.into(),
        Value::Number(n) => number_repr(n),
        Value::String(s) => str_repr(s),
        Value::Array(a) => format!("[{}]", a.iter().map(py_repr).collect::<Vec<_>>().join(", ")),
        Value::Object(m) => format!("{{{}}}", m.iter().map(|(k, x)| format!("{}: {}", str_repr(k), py_repr(x)))
            .collect::<Vec<_>>().join(", ")),
    }
}

pub fn str_repr(s: &str) -> String {
    let q = if s.contains('\'') && !s.contains('"') { '"' } else { '\'' };
    let mut out = String::from(q);
    for c in s.chars() {
        match c {
            '\\' => out.push_str("\\\\"),
            '\n' => out.push_str("\\n"),
            '\r' => out.push_str("\\r"),
            '\t' => out.push_str("\\t"),
            c if c == q => {
                out.push('\\');
                out.push(c);
            }
            c if (c as u32) < 0x20 || c as u32 == 0x7f => out.push_str(&format!("\\x{:02x}", c as u32)),
            c => out.push(c),
        }
    }
    out.push(q);
    out
}
