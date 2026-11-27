//! Vision v1 §3. A frame owns the layout. Each pane keeps its original WebView and PTY.
use crate::session::{self, PANE, PREFIX};
use serde::Serialize;
use serde_json::{json, Value};
use std::{
    collections::HashMap,
    sync::{atomic::{AtomicBool, AtomicU32, Ordering}, Mutex},
    time::{Duration, Instant},
};
use tauri::{AppHandle, Emitter, EventTarget, Manager, PhysicalPosition, PhysicalSize, Webview, Window, WindowEvent};
use windows_sys::Win32::{
    Foundation::{POINT, RECT},
    Graphics::Gdi::{GetMonitorInfoW, MonitorFromRect, MONITORINFO, MONITOR_DEFAULTTONEAREST},
    UI::{Input::KeyboardAndMouse::{GetAsyncKeyState, VK_LBUTTON}, WindowsAndMessaging::{
        GetCursorPos, SetWindowPos, ShowWindow, SW_HIDE, SW_SHOWNOACTIVATE, SWP_NOACTIVATE, SWP_NOZORDER,
    }},
};

const GROUP: &str = "session-group-";
const HEADER: &str = "frame-";
const NEAR: i32 = 48;
const MAGNET: i32 = 16;
const BAR: f64 = 36.0;
const PACE: f64 = 1.375; // same pace as the gate

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
enum Side { Left, Right, Top, Bottom }

impl Side {
    fn opposite(self) -> Self {
        match self {
            Self::Left => Self::Right, Self::Right => Self::Left,
            Self::Top => Self::Bottom, Self::Bottom => Self::Top,
        }
    }

    fn horizontal(self) -> bool { matches!(self, Self::Left | Self::Right) }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Rect { l: i32, t: i32, r: i32, b: i32 }

impl From<(i32, i32, i32, i32)> for Rect {
    fn from((l, t, r, b): (i32, i32, i32, i32)) -> Self { Self { l, t, r, b } }
}

impl Rect {
    fn width(self) -> i32 { self.r - self.l }
    fn height(self) -> i32 { self.b - self.t }
    fn offset(self, x: i32, y: i32) -> Self {
        (self.l + x, self.t + y, self.r + x, self.b + y).into()
    }
    fn gap(self, other: Self, side: Side) -> i32 {
        match side {
            Side::Left => self.l - other.r, Side::Right => other.l - self.r,
            Side::Top => self.t - other.b, Side::Bottom => other.t - self.b,
        }
    }
    fn aligned(self, other: Self, side: Side) -> Self {
        let gap = self.gap(other, side);
        match side {
            Side::Left => self.offset(-gap, 0), Side::Right => self.offset(gap, 0),
            Side::Top => self.offset(0, -gap), Side::Bottom => self.offset(0, gap),
        }
    }
    fn near(self, other: Self, scale: f64, limit: i32) -> Option<(Side, i32)> {
        [Side::Left, Side::Right, Side::Top, Side::Bottom].into_iter().filter_map(|side| {
            let gap = self.gap(other, side);
            let (overlap, span) = if side.horizontal() {
                (self.b.min(other.b) - self.t.max(other.t), self.height().min(other.height()))
            } else {
                (self.r.min(other.r) - self.l.max(other.l), self.width().min(other.width()))
            };
            let near = (f64::from(limit) * scale).round() as i32;
            let inset = (f64::from(MAGNET) * scale).round() as i32;
            (gap >= -inset && gap <= near && overlap >= (span / 4).max(32)).then_some((side, gap.abs()))
        }).min_by_key(|&(_, gap)| gap)
    }
    fn union(self, other: Self) -> Self {
        (self.l.min(other.l), self.t.min(other.t), self.r.max(other.r), self.b.max(other.b)).into()
    }
    fn inside(self, work: Self) -> Self {
        let width = self.width().min(work.width());
        let height = self.height().min(work.height());
        let l = self.l.clamp(work.l, work.r - width);
        let t = self.t.clamp(work.t, work.b - height);
        (l, t, l + width, t + height).into()
    }
    fn touches(self, outer: Self, side: Side) -> bool {
        match side {
            Side::Left => self.l == outer.l, Side::Right => self.r == outer.r,
            Side::Top => self.t == outer.t, Side::Bottom => self.b == outer.b,
        }
    }
}

#[derive(Clone, Debug, PartialEq)]
enum Panes {
    One(u32),
    Split { horizontal: bool, first: Box<Self>, second: Box<Self>, portion: f64 },
}

impl Panes {
    fn ids(&self) -> Vec<u32> {
        match self {
            Self::One(id) => vec![*id],
            Self::Split { first, second, .. } => [first.ids(), second.ids()].concat(),
        }
    }
    fn joins(self, other: Self, side: Side, a: Rect, b: Rect) -> Self {
        let horizontal = side.horizontal();
        let (first, second, a, b) = match side {
            Side::Right | Side::Bottom => (self, other, a, b),
            Side::Left | Side::Top => (other, self, b, a),
        };
        let (a, b) = if horizontal { (a.width(), b.width()) } else { (a.height(), b.height()) };
        Self::Split { horizontal, first: Box::new(first), second: Box::new(second),
            portion: (f64::from(a) / f64::from(a + b)).clamp(0.2, 0.8) }
    }
    fn without(self, id: u32) -> Option<Self> {
        match self {
            Self::One(old) => (old != id).then_some(Self::One(old)),
            Self::Split { horizontal, first, second, portion } => match (first.without(id), second.without(id)) {
                (Some(first), Some(second)) =>
                    Some(Self::Split { horizontal, first: Box::new(first), second: Box::new(second), portion }),
                (a, b) => a.or(b),
            },
        }
    }
    fn tiles(&self, area: Rect, gap: i32, result: &mut Vec<(u32, Rect)>) {
        match self {
            Self::One(id) => result.push((*id, area)),
            Self::Split { horizontal, first, second, portion } => {
                let (a, b) = if *horizontal {
                    let x = area.l + (f64::from(area.width() - gap) * portion).round() as i32;
                    (Rect { r: x, ..area }, Rect { l: x + gap, ..area })
                } else {
                    let y = area.t + (f64::from(area.height() - gap) * portion).round() as i32;
                    (Rect { b: y, ..area }, Rect { t: y + gap, ..area })
                };
                first.tiles(a, gap, result);
                second.tiles(b, gap, result);
            }
        }
    }
}

#[derive(Default)]
pub struct Dock {
    groups: Mutex<HashMap<String, Panes>>,
    next: AtomicU32,
    dragging: AtomicBool,
}

#[derive(Clone)]
struct Frame { window: Window, panes: Panes }

fn dock(app: &AppHandle) -> tauri::State<'_, Dock> { app.state() }
fn home(app: &AppHandle, id: u32) -> Option<Window> { app.get_window(&format!("{PREFIX}{id}")) }
fn pane(app: &AppHandle, id: u32) -> Option<Webview> { app.get_webview(&format!("{PANE}{id}")) }
fn pane_id(label: &str, prefix: &str) -> Option<u32> { label.strip_prefix(prefix)?.parse().ok() }
fn header_label(window: &Window) -> Option<String> { Some(format!("{HEADER}{}", window.label().strip_prefix(GROUP)?)) }

fn frame(app: &AppHandle, window: Window) -> Option<Frame> {
    let panes = if let Some(id) = pane_id(window.label(), PREFIX) {
        // A session's original shell stays parked while its WebView belongs to a group.
        (pane(app, id)?.window().label() == window.label()).then_some(Panes::One(id))?
    } else {
        dock(app).groups.lock().unwrap().get(window.label()).cloned()?
    };
    Some(Frame { window, panes })
}

fn visible(window: &Window) -> bool {
    window.is_visible().unwrap_or(false) && !window.is_minimized().unwrap_or(true)
}

fn rect(window: &Window) -> Option<Rect> {
    Some(session::visible_rect(window.hwnd().ok()?.0 as isize).into())
}

fn place(window: &Window, target: Rect) {
    let (Some(current), Ok(hwnd)) = (rect(window), window.hwnd()) else { return };
    if current == target { return; }
    let outer: Rect = crate::gate::window_rect(hwnd.0 as _).into();
    unsafe {
        SetWindowPos(hwnd.0 as _, std::ptr::null_mut(), target.l + outer.l - current.l, target.t + outer.t - current.t,
            target.width() + outer.width() - current.width(), target.height() + outer.height() - current.height(),
            SWP_NOACTIVATE | SWP_NOZORDER);
    }
}

fn show_session_shell(window: &Window, show: bool) {
    // The gate reveals these HWNDs directly, bypassing Tao's cached visibility flag.
    if let Ok(hwnd) = window.hwnd() {
        unsafe { ShowWindow(hwnd.0 as _, if show { SW_SHOWNOACTIVATE } else { SW_HIDE }); }
    }
}

fn work_area(r: Rect) -> Rect {
    let raw = RECT { left: r.l, top: r.t, right: r.r, bottom: r.b };
    let mon = unsafe { MonitorFromRect(&raw, MONITOR_DEFAULTTONEAREST) };
    let mut data: MONITORINFO = unsafe { std::mem::zeroed() };
    data.cbSize = std::mem::size_of::<MONITORINFO>() as u32;
    if unsafe { GetMonitorInfoW(mon, &mut data) } == 0 { return r; }
    let w = data.rcWork;
    (w.left, w.top, w.right, w.bottom).into()
}

fn bounds(view: &Webview, r: Rect) -> tauri::Result<()> {
    view.set_bounds(tauri::Rect {
        position: PhysicalPosition::new(r.l, r.t).into(),
        size: PhysicalSize::new(r.width().max(1) as u32, r.height().max(1) as u32).into(),
    })
}

fn group_tiles(window: &Window, panes: &Panes) -> Option<(Rect, Vec<(u32, Rect)>)> {
    let size = window.inner_size().ok()?;
    let scale = window.scale_factor().ok()?;
    let gap = scale.round().max(1.0) as i32;
    let left = crate::panel::reserve(window); // the docked launcher's column (SPEC-one-window.md)
    let area: Rect = (left + gap, (BAR * scale).round() as i32 + gap, size.width as i32 - gap, size.height as i32 - gap).into();
    let mut tiles = vec![];
    panes.tiles(area, gap, &mut tiles);
    Some((area, tiles))
}

fn layout(window: &Window, panes: &Panes) {
    let Some((area, tiles)) = group_tiles(window, panes) else { return };
    let app = window.app_handle();
    if let Some(header) = header_label(window).and_then(|label| app.get_webview(&label)) {
        let gap = window.scale_factor().unwrap_or(1.0).round().max(1.0) as i32; // as in group_tiles
        let _ = bounds(&header, (area.l, gap, area.r, area.t).into());
    }
    for (id, r) in tiles {
        if let Some(view) = pane(app, id) { let _ = bounds(&view, r); }
    }
}

/// Lay a frame out again (the docked launcher came or went).
pub fn relayout(window: &Window) {
    let tree = dock(window.app_handle()).groups.lock().unwrap().get(window.label()).cloned();
    if let Some(tree) = tree { layout(window, &tree); }
}

#[derive(Clone, Serialize)]
struct Look { side: Option<Side>, phase: &'static str }

fn emit(app: &AppHandle, label: String, event: &str, value: impl Serialize + Clone) {
    let _ = app.emit_to(EventTarget::webview(label), event, value);
}

fn paint(target: &Frame, side: Option<Side>, phase: &'static str) {
    let app = target.window.app_handle();
    if let Some((area, tiles)) = header_label(&target.window).and_then(|label| {
        let bar_side = side.filter(|edge| *edge != Side::Bottom);
        emit(app, label, "dock-look", Look { side: bar_side, phase });
        group_tiles(&target.window, &target.panes)
    }) {
        for (id, r) in tiles {
            let side = side.filter(|&edge| r.touches(area, edge) && edge != Side::Top);
            emit(app, format!("{PANE}{id}"), "dock-look", Look { side, phase });
        }
    } else {
        for id in target.panes.ids() { emit(app, format!("{PANE}{id}"), "dock-look", Look { side, phase }); }
    }
}

fn membership(app: &AppHandle, id: u32, grouped: bool) {
    emit(app, format!("{PANE}{id}"), "dock-grouped", grouped);
}

fn transfer(view: &Webview, to: &Window, grouped: bool) -> tauri::Result<()> {
    let from = view.window();
    if from.label() != to.label() {
        if let Err(error) = view.reparent(to) {
            let _ = view.reparent(&from);
            return Err(error);
        }
    }
    let _ = view.set_auto_resize(!grouped);
    if !grouped {
        if let Ok(size) = to.inner_size() {
            let _ = bounds(view, (0, 0, size.width as i32, size.height as i32).into());
        }
    }
    Ok(())
}

fn create_group(app: &AppHandle, target: Rect, scale: f64) -> tauri::Result<Window> {
    let id = dock(app).next.fetch_add(1, Ordering::Relaxed) + 1;
    let mut builder = Window::builder(app, format!("{GROUP}{id}")).title("Reidcc · sessions")
        .decorations(false).theme(Some(tauri::Theme::Dark)).background_color(tauri::window::Color(42, 39, 36, 255))
        .inner_size(f64::from(target.width()) / scale, f64::from(target.height()) / scale)
        .min_inner_size(640.0, 360.0).visible(false);
    if let Some(icon) = app.default_window_icon() { builder = builder.icon(icon.clone())?; }
    let window = builder.build()?;
    place(&window, target);
    let mut header = tauri::webview::WebviewBuilder::new(format!("{HEADER}{id}"), tauri::WebviewUrl::App("group.html".into()))
        .background_color(session::CANVAS);
    if let Some(dir) = crate::WEBVIEW_DIR.get() { header = header.data_directory(dir.clone()); }
    let size = PhysicalSize::new(target.width() as u32, (BAR * scale).round() as u32);
    if let Err(e) = window.add_child(header, PhysicalPosition::new(0, 0), size) {
        let _ = window.destroy();
        return Err(e);
    }
    Ok(window)
}

fn fuse(source: Frame, target: Frame, side: Side) -> Option<Frame> {
    let app = source.window.app_handle();
    for w in [&source.window, &target.window] { crate::panel::leaving(app, w); } // its column would hide in the old window
    for expected in [&source, &target] {
        if !visible(&expected.window) || frame(app, expected.window.clone())?.panes != expected.panes { return None; }
    }
    let b = rect(&target.window)?;
    let a = rect(&source.window)?.aligned(b, side);
    let scale = target.window.scale_factor().ok()?;
    let mut desired = a.union(b);
    if !source.window.label().starts_with(GROUP) && !target.window.label().starts_with(GROUP) {
        desired.b += (BAR * scale).round() as i32;
    }
    let tree = source.panes.clone().joins(target.panes.clone(), side, a, b);
    let views: Vec<_> = tree.ids().into_iter().map(|id| pane(app, id)).collect::<Option<_>>()?;
    let group = create_group(app, desired.inside(work_area(b)), scale).ok()?;
    let mut moved: Vec<(&Webview, Window)> = Vec::new();
    for view in &views {
        let old = view.window();
        if transfer(view, &group, true).is_err() {
            for (view, window) in moved {
                let _ = transfer(view, &window, window.label().starts_with(GROUP));
            }
            for old in [&source, &target] {
                if old.window.label().starts_with(GROUP) { layout(&old.window, &old.panes); }
            }
            let _ = group.destroy();
            return None;
        }
        moved.push((view, old));
    }
    {
        let state = dock(app);
        let mut groups = state.groups.lock().unwrap();
        groups.remove(source.window.label());
        groups.remove(target.window.label());
        groups.insert(group.label().into(), tree.clone());
    }
    layout(&group, &tree);
    for id in tree.ids() { membership(app, id, true); }
    let _ = group.show();
    for old in [&source.window, &target.window] {
        if old.label().starts_with(GROUP) { let _ = old.destroy(); } else { show_session_shell(old, false); }
    }
    let _ = group.set_focus();
    if let Some(view) = views.last() { let _ = view.set_focus(); }
    Some(Frame { window: group, panes: tree })
}

fn restore(app: &AppHandle, id: u32, area: Rect) -> Option<Frame> {
    let (window, view) = (home(app, id)?, pane(app, id)?);
    transfer(&view, &window, false).ok()?;
    let scale = window.scale_factor().unwrap_or(1.0);
    let mut area = area;
    area.r = area.r.max(area.l + (640.0 * scale) as i32);
    area.b = area.b.max(area.t + (400.0 * scale) as i32);
    place(&window, area.inside(work_area(area)));
    membership(app, id, false);
    emit(app, format!("{PANE}{id}"), "dock-look", Look { side: None, phase: "idle" });
    show_session_shell(&window, true);
    Some(Frame { window, panes: Panes::One(id) })
}

fn remove_from_group(app: &AppHandle, group: &Window, id: u32) {
    let state = dock(app);
    let before = state.groups.lock().unwrap().get(group.label()).cloned();
    match before.and_then(|tree| tree.without(id)) {
        Some(Panes::One(last)) => {
            crate::panel::leaving(app, group);
            if rect(group).and_then(|r| restore(app, last, r)).is_some() {
                state.groups.lock().unwrap().remove(group.label());
                let _ = group.destroy();
            } else {
                state.groups.lock().unwrap().insert(group.label().into(), Panes::One(last));
                layout(group, &Panes::One(last));
            }
        }
        Some(tree) => {
            state.groups.lock().unwrap().insert(group.label().into(), tree.clone());
            layout(group, &tree);
        }
        None => {
            crate::panel::leaving(app, group);
            state.groups.lock().unwrap().remove(group.label());
            let _ = group.destroy();
        }
    }
}

pub fn close_pane(app: &AppHandle, id: u32) {
    if let Some(view) = pane(app, id) {
        let group = view.window();
        if group.label().starts_with(GROUP) {
            let _ = view.close();
            remove_from_group(app, &group, id);
        }
    }
    if let Some(window) = home(app, id) {
        crate::panel::leaving(app, &window);
        let _ = window.destroy();
    }
}

pub fn window_event(window: &Window, event: &WindowEvent) {
    let app = window.app_handle();
    if matches!(event, WindowEvent::Destroyed) {
        if let Some(id) = pane_id(window.label(), PREFIX) {
            app.state::<session::Sessions>().end(id);
        } else if window.label().starts_with(GROUP) {
            let tree = dock(app).groups.lock().unwrap().remove(window.label());
            if let Some(tree) = tree {
                for id in tree.ids() {
                    if let Some(w) = home(app, id) { let _ = w.destroy(); }
                }
            }
        }
    } else if window.label().starts_with(GROUP) && matches!(event, WindowEvent::Resized(_) | WindowEvent::ScaleFactorChanged { .. }) {
        let tree = dock(app).groups.lock().unwrap().get(window.label()).cloned();
        if let Some(tree) = tree { layout(window, &tree); }
    }
}

fn cursor() -> Option<POINT> {
    let mut point = POINT { x: 0, y: 0 };
    (unsafe { GetCursorPos(&mut point) } != 0).then_some(point)
}

fn pressed() -> bool { unsafe { GetAsyncKeyState(i32::from(VK_LBUTTON)) < 0 } }

#[derive(Clone)]
struct Candidate { target: Frame, side: Side, gap: i32, rect: Rect }

fn candidate(source: &Frame, area: Rect, excluded: &[u32]) -> Option<Candidate> {
    let app = source.window.app_handle();
    let count = source.panes.ids().len();
    app.windows().into_values().filter_map(|w| {
        if w.label() == source.window.label() || !visible(&w) || w.is_maximized().ok()? {
            return None;
        }
        let target = frame(app, w)?;
        let ids = target.panes.ids();
        if ids.len() + count > 4 || ids.iter().any(|id| excluded.contains(id)) { return None; }
        let other = rect(&target.window)?;
        let (side, gap) = area.near(other, target.window.scale_factor().ok()?, NEAR)?;
        Some(Candidate { target, side, gap, rect: other })
    }).min_by_key(|c| (c.gap, c.target.window.label().to_owned()))
}

struct Drag {
    source: Frame, initial: Rect, start: POINT, detach: Option<u32>,
    excluded: Vec<u32>, preview: Option<Candidate>, last: Option<(i32, i32)>,
}

impl Drag {
    fn tick(&mut self, mouse: POINT, down: bool) -> Option<(Frame, Candidate)> {
        let dx = mouse.x - self.start.x;
        let dy = mouse.y - self.start.y;
        if self.last.is_none() && dx.abs().max(dy.abs()) < 4 { return None; }
        let window = &self.source.window;
        if window.is_maximized().unwrap_or(false) {
            if !down { return None; }
            let _ = window.unmaximize();
            if let Some(restored) = rect(window) {
                let fraction = f64::from(self.start.x - self.initial.l) / f64::from(self.initial.width().max(1));
                let x = self.start.x - (f64::from(restored.width()) * fraction).round() as i32;
                self.initial = restored.offset(x - restored.l, self.initial.t - restored.t);
            }
        }
        if let Some(id) = self.detach {
            if !down || dx.abs().max(dy.abs()) < 16 { return None; }
            let group = &self.source.window;
            let app = group.app_handle();
            let (Some(group_rect), Some((_, tiles))) = (rect(group), group_tiles(group, &self.source.panes)) else { return None };
            let Some((_, tile)) = tiles.into_iter().find(|(pane, _)| *pane == id) else { return None };
            let from = tile.offset(group_rect.l, group_rect.t);
            let Some(floating) = restore(app, id, from.offset(dx, dy)) else { return None };
            self.excluded = self.source.panes.ids();
            remove_from_group(app, group, id);
            self.initial = from;
            if let Some(actual) = rect(&floating.window) {
                self.initial = actual.offset(-dx, -dy);
            }
            let _ = floating.window.set_focus();
            if let Some(view) = pane(app, id) { let _ = view.set_focus(); }
            self.source = floating;
            self.detach = None;
        }
        if down && self.last == Some((mouse.x, mouse.y)) { return None; }
        let moved = self.last != Some((mouse.x, mouse.y));
        self.last = Some((mouse.x, mouse.y));
        let desired = self.initial.offset(dx, dy);
        let next = candidate(&self.source, desired, &self.excluded);
        let changed = self.preview.as_ref().map(|c| (c.target.window.label(), c.side)) !=
            next.as_ref().map(|c| (c.target.window.label(), c.side));
        if changed || !down {
            if let Some(old) = self.preview.take() { paint(&old.target, None, "idle"); }
        }
        if !down {
            if moved { place(&self.source.window, desired); }
            paint(&self.source, None, "idle");
            return next.map(|c| (self.source.clone(), c));
        }
        if changed || self.preview.is_none() {
            if let Some(c) = &next {
                paint(&self.source, Some(c.side), "near");
                paint(&c.target, Some(c.side.opposite()), "near");
            } else {
                paint(&self.source, None, "drag");
            }
        }
        let magnetic = next.as_ref().filter(|c| {
            f64::from(c.gap) <= f64::from(MAGNET) * c.target.window.scale_factor().unwrap_or(1.0)
        });
        place(&self.source.window, magnetic.map_or(desired, |c| desired.aligned(c.rect, c.side)));
        self.preview = next;
        None
    }
}

pub(crate) fn on_ui<T: Send + 'static>(app: &AppHandle, f: impl FnOnce() -> T + Send + 'static) -> Option<T> {
    let (tx, rx) = std::sync::mpsc::sync_channel(1);
    app.run_on_main_thread(move || { let _ = tx.send(f()); }).ok()?;
    rx.recv().ok()
}

fn animate(app: &AppHandle, source: Frame, snap: Candidate) {
    let target = snap.target;
    let side = snap.side;
    let Some(from) = rect(&source.window) else { return };
    let to = from.aligned(snap.rect, side);
    let start = Instant::now();
    let step = Duration::from_secs_f64(0.18 * PACE);
    let (s, t) = (source.clone(), target.clone());
    on_ui(app, move || { paint(&s, Some(side), "draw"); paint(&t, Some(side.opposite()), "draw"); });
    loop {
        let progress = (start.elapsed().as_secs_f64() / step.as_secs_f64()).min(1.0);
        let ease = 1.0 - (1.0 - progress).powi(3);
        let window = source.window.clone();
        let x = (f64::from(to.l - from.l) * ease).round() as i32;
        let y = (f64::from(to.t - from.t) * ease).round() as i32;
        on_ui(app, move || place(&window, from.offset(x, y)));
        if progress == 1.0 { break; }
        std::thread::sleep(Duration::from_millis(12));
    }
    let (s, t) = (source.clone(), target.clone());
    on_ui(app, move || { paint(&s, Some(side), "meet"); paint(&t, Some(side.opposite()), "meet"); });
    std::thread::sleep(step);
    let group = on_ui(app, move || {
        let result = fuse(source.clone(), target.clone(), side);
        if let Some(group) = &result {
            for id in source.panes.ids() {
                emit(group.window.app_handle(), format!("{PANE}{id}"), "dock-look", Look { side: Some(side), phase: "fuse" });
            }
            for id in target.panes.ids() {
                emit(group.window.app_handle(), format!("{PANE}{id}"), "dock-look",
                    Look { side: Some(side.opposite()), phase: "fuse" });
            }
        } else {
            paint(&source, None, "idle");
            paint(&target, None, "idle");
        }
        result
    }).flatten();
    if let Some(group) = group {
        std::thread::sleep(Duration::from_secs_f64(0.24 * PACE));
        on_ui(app, move || paint(&group, None, "settle"));
        std::thread::sleep(step);
    }
}

#[tauri::command]
pub fn dock_drag(app: AppHandle, webview: Webview) {
    let Some(start) = cursor().filter(|_| pressed()) else { return };
    if dock(&app).dragging.swap(true, Ordering::AcqRel) { return; }
    std::thread::spawn(move || {
        let handle = app.clone();
        let drag = on_ui(&app, move || {
            let window = webview.window();
            let source = frame(&handle, window)?;
            let initial = rect(&source.window)?;
            let detach = source.window.label().starts_with(GROUP).then(|| pane_id(webview.label(), PANE)).flatten();
            Some(Drag { source, initial, start, detach, excluded: vec![], preview: None, last: None })
        }).flatten();
        if let Some(mut drag) = drag {
            while let Some(point) = cursor() {
                let down = pressed();
                let Some((next, result)) = on_ui(&app, move || {
                    let result = drag.tick(point, down);
                    (drag, result)
                }) else { break };
                drag = next;
                if let Some((frame, target)) = result { animate(&app, frame, target); }
                if !down { break; }
                std::thread::sleep(Duration::from_millis(12));
            }
        }
        dock(&app).dragging.store(false, Ordering::Release);
    });
}

/// Whether this pane is in a frame: a page that loads after its pane was snapped (a rig) missed dock-grouped.
#[tauri::command]
pub fn dock_grouped(webview: Webview) -> bool { webview.window().label().starts_with(GROUP) }

#[tauri::command]
pub fn dock_control(webview: Webview, action: &str) {
    let window = webview.window();
    match action {
        "min" => { let _ = window.minimize(); }
        "max" => {
            if window.is_maximized().unwrap_or(false) { let _ = window.unmaximize(); }
            else { let _ = window.maximize(); }
        }
        "close" if window.label().starts_with(GROUP) && webview.label().starts_with(HEADER) => {
            crate::panel::leaving(webview.app_handle(), &window);
            let _ = window.destroy();
        }
        _ => {}
    }
}

// ------------------------------------------------------------------ rigs ---
// A rig (vision v1 §5) saves a frame's layout as JSON: a leaf is {"profile", "folder"}, a split is
// {"split": "h" | "v", "portion", "first", "second"}.

impl Panes {
    fn to_json(&self, leaf: &dyn Fn(u32) -> Option<Value>) -> Option<Value> {
        match self {
            Self::One(id) => leaf(*id),
            Self::Split { horizontal, first, second, portion } => Some(json!({
                "split": if *horizontal { "h" } else { "v" }, "portion": (portion * 1000.0).round() / 1000.0,
                "first": first.to_json(leaf)?, "second": second.to_json(leaf)?,
            })),
        }
    }
    /// The saved layout with its leaves numbered by `ids`, in order.
    fn from_json(v: &Value, ids: &mut impl Iterator<Item = u32>) -> Option<Self> {
        let Some(split) = v.get("split").and_then(Value::as_str) else {
            return v.get("profile").and_then(Value::as_str).and_then(|_| ids.next()).map(Self::One);
        };
        let portion = v.get("portion").and_then(Value::as_f64).unwrap_or(0.5).clamp(0.2, 0.8);
        let first = Box::new(Self::from_json(v.get("first")?, ids)?);
        let second = Box::new(Self::from_json(v.get("second")?, ids)?);
        Some(Self::Split { horizontal: split == "h", first, second, portion })
    }
}

/// A saved layout's leaves ({"profile", "folder"}), in pane order. None if it isn't one.
pub fn rig_leaves(layout: &Value) -> Option<Vec<Value>> {
    fn walk(v: &Value, out: &mut Vec<Value>) -> Option<()> {
        if v.get("split").is_some() {
            walk(v.get("first")?, out)?;
            walk(v.get("second")?, out)
        } else {
            v.get("profile").and_then(Value::as_str)?;
            out.push(v.clone());
            Some(())
        }
    }
    let mut out = vec![];
    walk(layout, &mut out)?;
    (1..=4).contains(&out.len()).then_some(out)
}

/// The frame this webview is in, as a rig: its layout and its visible rect (physical px).
pub fn rig_of(app: &AppHandle, window: Window, leaf: &dyn Fn(u32) -> Option<Value>) -> Option<Value> {
    let f = frame(app, window)?;
    let r = rect(&f.window)?;
    Some(json!({"layout": f.panes.to_json(leaf)?, "rect": [r.l, r.t, r.r, r.b]}))
}

/// A rig's frame at `at` (physical px, kept on screen), hidden, and where each pane goes in it (window
/// coordinates, pane order). Main thread only.
pub fn rig_frame(app: &AppHandle, saved: &Value, at: (i32, i32, i32, i32)) -> Option<(Window, Vec<(i32, i32, i32, i32)>)> {
    let n = rig_leaves(saved)?.len() as u32;
    let tree = Panes::from_json(saved, &mut (0..n))?;
    let at = Rect::from(at).inside(work_area(at.into()));
    let scale = crate::panel::launcher_window(app).and_then(|w| w.scale_factor().ok()).unwrap_or(1.0);
    let group = create_group(app, at, scale).ok()?;
    let Some((_, mut tiles)) = group_tiles(&group, &tree) else { let _ = group.destroy(); return None };
    tiles.sort_by_key(|(id, _)| *id);
    Some((group, tiles.into_iter().map(|(_, r)| (r.l, r.t, r.r, r.b)).collect()))
}

/// The rig's sessions `ids` are open inside `group`: make it a live frame and show it. Main thread only.
pub fn rig_show(app: &AppHandle, group: &Window, saved: &Value, ids: &[u32]) -> bool {
    let Some(tree) = Panes::from_json(saved, &mut ids.iter().copied()) else { return false };
    dock(app).groups.lock().unwrap().insert(group.label().into(), tree.clone());
    layout(group, &tree);
    for id in tree.ids() { membership(app, id, true); }
    let _ = group.show();
    let _ = group.set_focus();
    true
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_neighboring_edges_snap_and_layout_removes_the_seam_when_detached() {
        let a: Rect = (0, 0, 600, 400).into();
        let b: Rect = (630, 50, 1230, 450).into();
        assert_eq!(a.near(b, 1.0, NEAR), Some((Side::Right, 30)));
        assert_eq!(a.near(b, 1.0, MAGNET), None);
        assert_eq!(a.near(b.offset(0, 360), 1.0, NEAR), None);
        assert_eq!(b.near(a, 1.0, NEAR), Some((Side::Left, 30)));
        assert_eq!(a.aligned(b, Side::Right).r, b.l);
        let tree = Panes::One(1).joins(Panes::One(2), Side::Right, a, b);
        let mut tiles = vec![];
        tree.tiles((0, 0, 601, 400).into(), 1, &mut tiles);
        assert_eq!(tiles, vec![(1, (0, 0, 300, 400).into()), (2, (301, 0, 601, 400).into())]);
        assert_eq!(tree.without(1), Some(Panes::One(2)));
    }

    #[test]
    fn a_rig_layout_round_trips_and_numbers_its_panes_in_order() {
        let a: Rect = (0, 0, 600, 400).into();
        let tree = Panes::One(7).joins(Panes::One(8).joins(Panes::One(9), Side::Bottom, a, a), Side::Right, a, a);
        let leaf = |id: u32| Some(json!({"profile": format!("p{id}"), "folder": "~/projects/kiln"}));
        let saved = tree.to_json(&leaf).unwrap();
        assert_eq!(saved["split"], "h");
        assert_eq!(saved["second"]["split"], "v");
        let names: Vec<_> = rig_leaves(&saved).unwrap().iter().map(|l| l["profile"].as_str().unwrap().to_owned()).collect();
        assert_eq!(names, ["p7", "p8", "p9"]);
        let back = Panes::from_json(&saved, &mut [1, 2, 3].into_iter()).unwrap();
        assert_eq!(back.ids(), [1, 2, 3]);
        assert!(Panes::from_json(&saved, &mut [1, 2].into_iter()).is_none()); // too few sessions
        assert!(rig_leaves(&json!({"split": "h", "first": {"profile": "a"}})).is_none());
    }
}
