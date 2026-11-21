//! Text metrics the way Tk measures them on Windows (GDI), so the page can space its text to Tk's
//! widths: Tk lays out with GDI's whole-pixel advances, WebView2 with DirectWrite's fractional ones.
//! `_fonts` in reid_gui.py picks the first installed family of each list; so does this.

use serde::Serialize;
use std::collections::BTreeMap;
use windows_sys::Win32::Foundation::{LPARAM, SIZE};
use windows_sys::Win32::Graphics::Gdi::{
    CreateCompatibleDC, CreateFontW, DeleteDC, DeleteObject, EnumFontFamiliesExW, GetGlyphIndicesW, GetTextExtentPoint32W, SelectObject,
    HDC, HFONT,
    DEFAULT_CHARSET, LOGFONTW, TEXTMETRICW,
};

pub const UI: [&str; 5] = ["Inter", "Geist", "Segoe UI Variable Text", "Segoe UI", "Helvetica"];
pub const MONO: [&str; 5] = ["Geist Mono", "JetBrains Mono", "Cascadia Mono", "Consolas", "Menlo"];
/// (role, ui font?, px) as in App._fonts
pub const ROLES: [(&str, bool, i32); 7] =
    [("title", true, 20), ("head", true, 16), ("body", true, 14), ("btn", true, 13), ("label", true, 13), ("mono", false, 12), ("tag", false, 11)];

#[derive(Serialize)]
pub struct Fonts {
    pub ui: String,
    pub mono: String,
    /// role -> char -> advance in px
    pub widths: BTreeMap<String, BTreeMap<String, i32>>,
}

unsafe extern "system" fn found(_lf: *const LOGFONTW, _tm: *const TEXTMETRICW, _ty: u32, lp: LPARAM) -> i32 {
    *(lp as *mut bool) = true;
    0
}

fn installed(dc: HDC, family: &str) -> bool {
    let mut lf: LOGFONTW = unsafe { std::mem::zeroed() };
    lf.lfCharSet = DEFAULT_CHARSET as u8;
    for (i, c) in family.encode_utf16().take(31).enumerate() {
        lf.lfFaceName[i] = c;
    }
    let mut yes = false;
    unsafe { EnumFontFamiliesExW(dc, &lf, Some(found), &mut yes as *mut bool as LPARAM, 0) };
    yes
}

/// The characters the screen can show: printable ASCII, Latin-1 and the few symbols Reidcc uses.
fn charset() -> Vec<char> {
    let mut v: Vec<char> = (0x20u32..0x7F).chain(0xA0..0x180).filter_map(char::from_u32).collect();
    v.extend("→●·…▾—–‘’“”•×".chars());
    v
}

/// Where Tk finds a glyph the chosen family lacks (e.g. ▾ in Segoe UI Variable Text).
const FALLBACK: [&str; 3] = ["Lucida Sans Unicode", "Arial Unicode MS", "Segoe UI Symbol"];

fn font(family: &str, px: i32) -> HFONT {
    let fam: Vec<u16> = family.encode_utf16().chain([0]).collect();
    unsafe { CreateFontW(-px, 0, 0, 0, 400, 0, 0, 0, DEFAULT_CHARSET as u32, 0, 0, 0, 0, fam.as_ptr()) }
}

/// Width of s in the font selected into dc, or None when the font has no glyph for it.
fn width(dc: HDC, s: &[u16]) -> Option<i32> {
    let mut gi = [0u16; 2];
    unsafe {
        GetGlyphIndicesW(dc, s.as_ptr(), s.len() as i32, gi.as_mut_ptr(), 1); // GGI_MARK_NONEXISTING_GLYPHS
        if gi[..s.len()].contains(&0xFFFF) {
            return None;
        }
        let mut sz = SIZE { cx: 0, cy: 0 };
        GetTextExtentPoint32W(dc, s.as_ptr(), s.len() as i32, &mut sz);
        Some(sz.cx)
    }
}

pub fn fonts() -> Fonts {
    unsafe {
        let dc = CreateCompatibleDC(std::ptr::null_mut());
        let pick = |list: &[&str]| list.iter().find(|f| installed(dc, f)).map(|f| f.to_string());
        let ui = pick(&UI).unwrap_or_else(|| "Segoe UI".into());
        let mono = pick(&MONO).unwrap_or_else(|| "Consolas".into());
        let chars = charset();
        let mut widths = BTreeMap::new();
        for (role, is_ui, px) in ROLES {
            let f = font(if is_ui { &ui } else { &mono }, px);
            let old = SelectObject(dc, f);
            let mut t = BTreeMap::new();
            for c in &chars {
                let mut buf = [0u16; 2];
                let s = c.encode_utf16(&mut buf);
                let mut w = width(dc, s);
                for fb in FALLBACK {
                    if w.is_some() {
                        break;
                    }
                    let g = font(fb, px);
                    let o = SelectObject(dc, g);
                    w = width(dc, s);
                    SelectObject(dc, o);
                    DeleteObject(g);
                }
                if let Some(w) = w {
                    t.insert(c.to_string(), w);
                }
            }
            SelectObject(dc, old);
            DeleteObject(f);
            widths.insert(role.to_string(), t);
        }
        DeleteDC(dc);
        Fonts { ui, mono, widths }
    }
}
