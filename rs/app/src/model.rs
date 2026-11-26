//! The launcher's data side: a port of `App` in python\reid_gui.py (everything that reads or
//! writes reid.json). Each action returns the screen operations it causes, in the order Python
//! does them, and the page applies them (ui\src\main.ts). Every change loads reid.json fresh,
//! changes it and saves it at once, as `App.apply` does.

use reidcc::engines::{self, codex, is_codex};
use reidcc::{profile, profiles, proxy, py, pyjson, Ctx, Obj};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};

pub const SUB: &str = "subscription";
pub const NO_PERSONA: &str = "none";
pub const TOOLS_CHOICES: [&str; 5] = ["all", "core", "core + web", "web only", "none"];
pub const MCP_DEFAULT: &str = "your servers";
pub const CODEX_REPLACE_HINT: &str = "replace drops Codex's own instructions; add is the safe one.";
pub const CORE_TOOLS: [&str; 6] = ["Read", "Edit", "Write", "Glob", "Grep", "Bash"];
pub const WEB_TOOLS: [&str; 2] = ["WebSearch", "WebFetch"];

/// One thing the page does, in order.
#[derive(Serialize, Clone, Debug)]
#[serde(tag = "op", rename_all = "snake_case")]
pub enum Op {
    /// say(text, kind, actions, seconds): actions are [label, action id]
    Say { text: String, kind: String, actions: Vec<(String, String)>, seconds: Option<f64>, focus: Option<usize> },
    /// clear_msg()
    Clear,
    /// clear the message only if it still shows this text (a not-ready error that went away)
    ClearIf { text: String },
    /// the profile list's lines
    List { items: Vec<String>, names: Vec<String> },
    /// select and show this list row
    Select { index: usize },
    /// every field of the selected profile, with each box's choices
    Fields(Box<Fields>),
    /// header, tags, greyed fields, status and command preview
    Refresh(Box<Refresh>),
    /// set one field without saving (Python sets the Tk variable while `loading`)
    Var { key: String, value: String },
    /// add a choice to the persona box
    PersonaChoice { value: String },
    /// look again in 3 s (a profile that isn't ready)
    Recheck,
    /// keyboard focus: "list", "pick", "name"
    Focus { target: String },
}

#[derive(Serialize, Clone, Debug, Default)]
pub struct Fields {
    pub name: String,
    pub engine: String,
    pub model: String,
    pub auth: String,
    pub persona: String,
    pub mode: String,
    pub proxy: String,
    pub tools: String,
    pub mcp: String,
    pub args: String,
    pub memory: bool,
    pub chrome: bool,
    pub connectors: bool,
    pub safe: bool,
    pub engines: Vec<String>,
    pub models: Vec<String>,
    pub auths: Vec<String>,
    pub personas: Vec<String>,
    pub proxies: Vec<String>,
    pub tools_choices: Vec<String>,
    pub mcps: Vec<String>,
}

#[derive(Serialize, Clone, Debug, Default)]
pub struct Refresh {
    pub title: String,
    pub tags: String,
    pub mode_texts: [String; 2],
    pub mode_disabled: bool,
    /// widget -> disabled (proxy, tools, mcp, safe, chrome, connectors)
    pub disabled: Map<String, Value>,
    pub codex: bool,
    pub ready: bool,
    pub status: String,
    pub preview: String,
}

/// What the page sends with apply(): the Tk variables.
#[derive(Deserialize, Clone, Debug, Default)]
pub struct Vars {
    pub engine: String,
    pub model: String,
    pub auth: String,
    pub persona: String,
    pub mode: String,
    pub proxy: String,
    pub tools: String,
    pub mcp: String,
    pub args: String,
    pub memory: bool,
    pub chrome: bool,
    pub connectors: bool,
    pub safe: bool,
}

pub struct Model {
    pub ctx: Ctx,
    pub cli: Vec<String>,
    pub current: Option<String>,
    pub names: Vec<String>,
    pub not_ready: Option<String>,
    pub login_busy: bool,
    /// the folder box's text
    pub folder: String,
    /// set when a background `codex login status` should start
    pub want_login_check: bool,
    pub ops: Vec<Op>,
}

/// What the tune popover writes into a profile (SPEC-unified-interface Milestone 2C).
const TUNE_KEYS: [&str; 3] = ["effort", "mcp_off", "plugins"];

fn s(v: &str) -> String {
    v.to_string()
}

fn say(text: impl Into<String>, kind: &str, actions: &[(&str, &str)], seconds: Option<f64>) -> Op {
    Op::Say { text: text.into(), kind: s(kind), actions: actions.iter().map(|(a, b)| (s(a), s(b))).collect(), seconds, focus: None }
}

/// Python's truthiness of p.get(key).
fn on(p: &Obj, key: &str) -> bool {
    p.get(key).is_some_and(pyjson::truthy)
}

/// str(p.get(key) or default)
fn text_or(p: &Obj, key: &str, default: &str) -> String {
    match p.get(key) {
        Some(v) if pyjson::truthy(v) => pyjson::py_str(v),
        _ => s(default),
    }
}

/// Extra args as one line people can edit (subprocess.list2cmdline(list(args or []))).
pub fn args_text(p: &Obj) -> String {
    py::list2cmdline(&reidcc::args(p))
}

fn tools_label(p: &Obj) -> String {
    if !p.contains_key("tools") {
        return s("all");
    }
    let t: Vec<String> = match p.get("tools") {
        Some(v) if pyjson::truthy(v) => reidcc::list(p, "tools"),
        _ => vec![],
    };
    let core: Vec<String> = CORE_TOOLS.iter().map(|x| s(x)).collect();
    let web: Vec<String> = WEB_TOOLS.iter().map(|x| s(x)).collect();
    let both: Vec<String> = core.iter().chain(web.iter()).cloned().collect();
    // Python compares the saved value itself (t == key), so only a real list can match
    let is_list = matches!(p.get("tools"), Some(Value::Array(_))) || !p.get("tools").is_some_and(pyjson::truthy);
    for (label, key) in [("none", vec![]), ("core", core), ("core + web", both), ("web only", web)] {
        if is_list && t == key {
            return s(label);
        }
    }
    t.join(",")
}

fn tools_value(label: &str) -> Option<Vec<String>> {
    let label = py::strip(label);
    let v = |a: &[&str]| a.iter().map(|x| s(x)).collect::<Vec<_>>();
    match label {
        "all" | "" => None,
        "none" => Some(vec![]),
        "core" => Some(v(&CORE_TOOLS)),
        "core + web" => Some(v(&CORE_TOOLS).into_iter().chain(v(&WEB_TOOLS)).collect()),
        "web only" => Some(v(&WEB_TOOLS)),
        _ => Some(label.split(',').map(|t| py::strip(t).to_string()).filter(|t| !t.is_empty()).collect()),
    }
}

/// Python's put(): drop the key for None / "" / False / an empty list (except tools), else set it.
fn put(p: &mut Obj, key: &str, val: Value) {
    let drop = match &val {
        Value::Null => true,
        Value::String(x) => x.is_empty(),
        Value::Bool(b) => !b,
        Value::Array(a) => a.is_empty() && key != "tools",
        Value::Number(n) => n.as_f64() == Some(0.0),
        _ => false,
    };
    if drop {
        p.shift_remove(key);
    } else {
        p.insert(s(key), val);
    }
}

fn opt(v: Option<String>) -> Value {
    v.map_or(Value::Null, Value::String)
}

impl Model {
    pub fn new(ctx: Ctx, cli: Vec<String>, folder: String) -> Model {
        Model { ctx, cli, current: None, names: vec![], not_ready: None, login_busy: false, folder,
                want_login_check: false, ops: vec![] }
    }

    pub fn take(&mut self) -> Vec<Op> {
        std::mem::take(&mut self.ops)
    }

    fn push(&mut self, op: Op) {
        self.ops.push(op);
    }

    // ---------------------------------------------------------------- data ---
    pub fn cfg(&mut self) -> Option<Obj> {
        match reidcc::load_config(&self.ctx) {
            Ok(c) => Some(c),
            Err(e) => {
                self.push(say(e.0, "error", &[("open reid.json", "open_config")], None));
                None
            }
        }
    }

    pub fn save(&mut self, cfg: &Obj) {
        let _ = reidcc::save_json(&self.ctx.config, &Value::Object(cfg.clone()));
    }

    pub fn real_folder(&self) -> String {
        let t = py::strip(&self.folder).trim_matches('"');
        py::abspath(&py::expanduser(t))
    }

    pub fn reload(&mut self, select: Option<&str>) {
        let Some(cfg) = self.cfg() else { return };
        if profiles(&cfg).is_empty() {
            return;
        }
        self.names = profiles(&cfg).keys().cloned().collect();
        let default = cfg.get("default").and_then(Value::as_str).unwrap_or("").to_string();
        let items = self.names.iter().map(|n| format!(" {n}{}", if *n == default { "  ●" } else { "" })).collect();
        self.push(Op::List { items, names: self.names.clone() });
        let target = match select {
            Some(n) if self.names.iter().any(|x| x == n) => s(n),
            _ => match &self.current {
                Some(c) if self.names.contains(c) => c.clone(),
                _ => self.names[0].clone(),
            },
        };
        self.load_profile(&cfg, &target);
    }

    /// The list moved to `name`; `typed` is the name box's text (a rename not yet confirmed).
    pub fn select(&mut self, name: &str, typed: &str) {
        self.rename(typed);
        if let Some(cfg) = self.cfg() {
            if profiles(&cfg).contains_key(name) {
                self.load_profile(&cfg, name);
            }
        }
    }

    pub fn load_profile(&mut self, cfg: &Obj, name: &str) {
        let empty = Obj::new();
        let p = profiles(cfg).get(name).and_then(Value::as_object).unwrap_or(&empty).clone();
        self.current = Some(s(name));
        if let Some(i) = self.names.iter().position(|n| n == name) {
            self.push(Op::Select { index: i });
        }
        let engine = text_or(&p, "engine", "claude");
        let cx = is_codex(&p);
        // each engine lists its own models: Claude's names, or the ones other Codex profiles use
        let mut used: Vec<String> = vec![];
        for q in profiles(cfg).values().filter_map(Value::as_object) {
            if on(q, "model") && text_or(q, "engine", "claude") == engine {
                let m = pyjson::py_str(&q["model"]);
                if !reidcc::BASE_MODELS.contains(&m.as_str()) && !used.contains(&m) {
                    used.push(m);
                }
            }
        }
        used.sort();
        let mut models: Vec<String> = if engine == "claude" { reidcc::BASE_MODELS.iter().map(|m| s(m)).collect() } else { vec![] };
        models.extend(used);
        let mut auths = vec![self.login_choice(cx)];
        auths.extend(profile::signin_files(&self.ctx, cx));
        if cx && !on(&p, "settings") && codex::login_cached(&self.ctx).is_none() {
            self.want_login_check = true;
        }
        let home = self.ctx.home.clone();
        let mut personas = vec![];
        for (dir, pat) in [(py::join(&home, &["personas"]), "*.md"), (self.ctx.proxy_dir.clone(), "*-system.md"),
                           (py::join(&home, &["mds"]), "*.md")] {
            let mut g = py::glob(&dir, pat);
            g.sort();
            personas.extend(g);
        }
        let mut pvals = vec![s(NO_PERSONA)];
        pvals.extend(personas.iter().map(|f| self.ctx.relpath(f)));
        let persona = text_or(&p, "persona", "");
        if !persona.is_empty() && !pvals.contains(&persona) {
            pvals.push(persona.clone());
        }
        let mut mcps: Vec<String> = py::glob(&self.ctx.proxy_dir, "*mcp*.json")
            .iter().map(|f| self.ctx.relpath(f)).collect();
        mcps.sort();
        let mut mvals = vec![s(MCP_DEFAULT), s("none")];
        mvals.extend(mcps);
        let mcp = text_or(&p, "mcp", "");
        if !mcp.is_empty() && !mvals.contains(&mcp) {
            mvals.push(mcp.clone());
        }
        let px = proxy::list(&p).join("+");
        let model = match p.get("model") {
            None => String::new(),
            Some(Value::Null) => s("None"),
            Some(v) => pyjson::py_str(v),
        };
        let settings = text_or(&p, "settings", "");
        let f = Fields {
            name: s(name),
            engine: engine.clone(),
            model,
            auth: if settings.is_empty() { self.login_choice(cx) } else { settings },
            persona: if persona.is_empty() { s(NO_PERSONA) } else { persona },
            mode: text_or(&p, "mode", "append"),
            proxy: if px.is_empty() { s("off") } else { px },
            tools: tools_label(&p),
            mcp: if mcp.is_empty() { s(MCP_DEFAULT) } else { mcp },
            args: args_text(&p),
            memory: on(&p, "memory"),
            chrome: !on(&p, "no_chrome"),
            connectors: !on(&p, "no_connectors"),
            safe: on(&p, "safe"),
            engines: engines::ENGINES.iter().map(|e| s(e)).collect(),
            models,
            auths,
            personas: pvals,
            proxies: std::iter::once(s("off")).chain(proxy::choices(cx).iter().map(|c| s(c))).collect(),
            tools_choices: TOOLS_CHOICES.iter().map(|c| s(c)).collect(),
            mcps: mvals,
        };
        self.push(Op::Fields(Box::new(f)));
        self.refresh(cfg);
    }

    /// The first sign-in choice: `subscription` for Claude, `codex login · <status>` for Codex.
    fn login_choice(&self, cx: bool) -> String {
        if cx { codex::login_label(&self.ctx) } else { s(SUB) }
    }

    /// After the background `codex login status`: update the sign-in row.
    pub fn login_done(&mut self) {
        self.login_busy = false;
        let Some(cfg) = self.cfg() else { return };
        let Some(cur) = self.current.clone() else { return };
        let Some(p) = profiles(&cfg).get(&cur).and_then(Value::as_object).cloned() else { return };
        if !is_codex(&p) {
            return;
        }
        let mut auths = vec![self.login_choice(true)];
        auths.extend(profile::signin_files(&self.ctx, true));
        self.push(Op::Var { key: s("auths"), value: serde_json::to_string(&auths).unwrap() });
        if !on(&p, "settings") {
            self.push(Op::Var { key: s("auth"), value: self.login_choice(true) });
        }
        self.refresh(&cfg);
    }

    pub fn refresh(&mut self, cfg: &Obj) {
        let Some(name) = self.current.clone() else { return };
        let empty = Obj::new();
        let p = profiles(cfg).get(&name).and_then(Value::as_object).unwrap_or(&empty).clone();
        let persona = if on(&p, "persona") { profile::persona_name(&p) } else { String::new() };
        // the shared tags (SPEC-one-look Part 2): `claude · persona plain · memory`, lowercase. Greyed
        // fields say "Claude only" on hover, so no tag explains them (4.7).
        let cx = is_codex(&p);
        let mut tags = vec![s(if cx { "codex" } else { "claude" })];
        if !persona.is_empty() {
            tags.push(format!("persona {persona}"));
        }
        if on(&p, "memory") {
            tags.push(s("memory"));
        }
        let tool = if cx { "Codex" } else { "Claude Code" };
        let mut disabled = Map::new();
        let live = [("tools", p.contains_key("tools")), ("mcp", on(&p, "mcp")),
                    ("safe", on(&p, "safe")), ("chrome", on(&p, "no_chrome")), ("connectors", on(&p, "no_connectors"))];
        for (k, live_on) in live {
            disabled.insert(s(k), Value::Bool(cx && !live_on));
        }
        let folder = self.real_folder();
        let (error, text, have) = profile::check(&self.ctx, cfg, &name, &folder);
        let mut r = Refresh {
            title: name.clone(),
            tags: tags.join(" · "),
            mode_texts: [format!("add to {tool}'s prompt"), format!("replace {tool}'s prompt")],
            mode_disabled: persona.is_empty(),
            disabled,
            codex: cx,
            ..Default::default()
        };
        if let Some(e) = error {
            r.ready = false;
            r.status = s("not ready");
            r.preview = e.clone();
            self.push(Op::Refresh(Box::new(r)));
            // Look again on our own: e.g. Claude Code mid-update, or reid.json fixed in an editor.
            self.push(Op::Recheck);
            self.not_ready = Some(e);
            return;
        }
        if let Some(nr) = self.not_ready.take() {
            self.push(Op::ClearIf { text: nr });
        }
        r.ready = true;
        r.status = format!("ready{}", if have.is_empty() { String::new() } else { format!(" · {}", have.join(" + ")) });
        r.preview = text;
        self.push(Op::Refresh(Box::new(r)));
    }

    pub fn retry(&mut self) {
        if let Some(cfg) = self.cfg() {
            if self.current.as_ref().is_some_and(|c| profiles(&cfg).contains_key(c)) {
                self.refresh(&cfg);
            }
        }
    }

    /// Write the fields into the selected profile and save.
    pub fn apply(&mut self, v: &Vars) {
        let Some(cur) = self.current.clone() else { return };
        let Some(mut cfg) = self.cfg() else { return };
        let Some(Value::Object(mut p)) = profiles(&cfg).get(&cur).cloned() else { return };
        let engine = if v.engine.is_empty() { s("claude") } else { v.engine.clone() };
        if engine != text_or(&p, "engine", "claude") {
            // a model belongs to one engine: start from the new engine's default
            self.push(Op::Var { key: s("model"), value: String::new() });
            put(&mut p, "engine", if engine == "claude" { Value::Null } else { Value::String(engine.clone()) });
            put(&mut p, "model", Value::Null);
            put(&mut p, "settings", Value::Null); // sign-in files are per engine too
            let no_opt = engine == "codex" && proxy::drop_optimize(&mut p);
            set_profile(&mut cfg, &cur, p);
            self.save(&cfg);
            self.load_profile(&cfg, &cur); // new model and sign-in lists for the new engine
            let tail = if no_opt { " optimize is Claude's, so it's off." } else { "" };
            self.push(say(format!("Engine is now {engine}. Model and sign-in reset to its defaults.{tail}"), "quiet", &[], Some(3.0)));
            return;
        }
        let mode_changed = text_or(&p, "mode", "append") != v.mode;
        put(&mut p, "model", Value::String(py::strip(&v.model).to_string()));
        let auth = &v.auth;
        put(&mut p, "settings", opt((auth != SUB && !auth.starts_with(codex::LOGIN)).then(|| auth.clone())));
        put(&mut p, "persona", opt((v.persona != NO_PERSONA).then(|| v.persona.clone())));
        let mode = on(&p, "persona").then(|| v.mode.clone());
        put(&mut p, "mode", opt(mode));
        put(&mut p, "proxy", opt((v.proxy != "off").then(|| v.proxy.clone())));
        match tools_value(&v.tools) {
            None => {
                p.shift_remove("tools");
            }
            Some(t) => {
                p.insert(s("tools"), json!(t));
            }
        }
        put(&mut p, "mcp", opt((v.mcp != MCP_DEFAULT).then(|| v.mcp.clone())));
        if v.args != args_text(&p) {
            // untouched args stay exactly as saved
            put(&mut p, "args", json!(reidcc::args_parse(&v.args)));
        }
        put(&mut p, "memory", Value::Bool(v.memory));
        put(&mut p, "safe", Value::Bool(v.safe));
        put(&mut p, "no_chrome", Value::Bool(!v.chrome));
        put(&mut p, "no_connectors", Value::Bool(!v.connectors));
        let replace_codex = mode_changed && p.get("mode").and_then(Value::as_str) == Some("replace") && is_codex(&p);
        set_profile(&mut cfg, &cur, p);
        self.save(&cfg);
        self.refresh(&cfg);
        if replace_codex {
            self.push(say(CODEX_REPLACE_HINT, "quiet", &[], Some(4.0)));
        } else {
            self.push(say("Saved.", "quiet", &[], Some(1.5)));
        }
    }

    /// The tune popover: write the selected profile's effort / mcp_off / plugins (only the keys given)
    /// and save. Outside apply(): the Python GUI has no such fields, so the parity flows never touch them.
    pub fn tune(&mut self, changes: &Obj) {
        let Some(cur) = self.current.clone() else { return };
        let Some(mut cfg) = self.cfg() else { return };
        let Some(Value::Object(mut p)) = profiles(&cfg).get(&cur).cloned() else { return };
        for key in TUNE_KEYS {
            let Some(value) = changes.get(key) else { continue };
            let value = match value {
                Value::String(_) if key == "effort" => value.clone(),
                Value::Array(names) if key == "mcp_off" && names.iter().all(Value::is_string) => value.clone(),
                Value::Object(switches) if key == "plugins" && switches.values().all(Value::is_boolean) => {
                    if switches.is_empty() { Value::Null } else { value.clone() }
                }
                _ => continue, // not this key's shape: leave the profile as it is
            };
            put(&mut p, key, value);
        }
        set_profile(&mut cfg, &cur, p);
        self.save(&cfg);
        self.refresh(&cfg);
        self.push(say("Saved.", "quiet", &[], Some(1.5)));
    }

    // ------------------------------------------------------------- actions ---
    pub fn rename(&mut self, typed: &str) {
        let new = py::strip(typed).to_string();
        let Some(cur) = self.current.clone() else { return };
        if new.is_empty() || new == cur {
            return;
        }
        let Some(mut cfg) = self.cfg() else { return };
        if profiles(&cfg).contains_key(&new) {
            self.push(say(format!("A profile named {new} already exists."), "error", &[], None));
            self.push(Op::Var { key: s("name"), value: cur });
            return;
        }
        let old = std::mem::take(cfg.get_mut("profiles").unwrap().as_object_mut().unwrap());
        let renamed: Obj = old.into_iter().map(|(k, v)| (if k == cur { new.clone() } else { k }, v)).collect();
        cfg.insert(s("profiles"), Value::Object(renamed));
        if cfg.get("default").and_then(Value::as_str) == Some(cur.as_str()) {
            cfg.insert(s("default"), Value::String(new.clone()));
        }
        self.save(&cfg);
        self.current = Some(new.clone());
        self.reload(Some(&new));
    }

    fn unique(cfg: &Obj, base: &str) -> String {
        let (mut n, mut i) = (s(base), 2);
        while profiles(cfg).contains_key(&n) {
            n = format!("{base}-{i}");
            i += 1;
        }
        n
    }

    pub fn new_profile(&mut self) {
        if let Some(mut cfg) = self.cfg() {
            let n = Self::unique(&cfg, "new");
            // the settings page's default engine; a Codex profile starts on Codex's own default model
            let codex = cfg.get("default_engine").and_then(Value::as_str) == Some("codex");
            profiles_mut(&mut cfg).insert(n.clone(), if codex { json!({"engine": "codex"}) } else { json!({"model": "opus"}) });
            self.save(&cfg);
            self.reload(Some(&n));
        }
    }

    pub fn dup(&mut self) {
        let Some(cur) = self.current.clone() else { return };
        if let Some(mut cfg) = self.cfg() {
            let n = Self::unique(&cfg, &format!("{cur}-copy"));
            let copy = profiles(&cfg).get(&cur).cloned().unwrap_or(Value::Null);
            profiles_mut(&mut cfg).insert(n.clone(), copy);
            self.save(&cfg);
            self.reload(Some(&n));
        }
    }

    /// Asks inline first; `delete:<name>` is the confirm action.
    pub fn delete(&mut self) {
        let Some(cfg) = self.cfg() else { return };
        if profiles(&cfg).len() == 1 {
            self.push(say("Can't delete the last profile.", "error", &[], None));
            return;
        }
        let name = self.current.clone().unwrap_or_default();
        let really = format!("delete:{name}");
        let mut op = say(format!("Delete profile {name}?"), "info", &[("delete", &really), ("keep", "keep")], None);
        if let Op::Say { focus, .. } = &mut op {
            *focus = Some(1); // the safe choice has focus
        }
        self.push(op);
    }

    pub fn really_delete(&mut self, name: &str) {
        let Some(mut c) = self.cfg() else { return };
        if !profiles(&c).contains_key(name) {
            return;
        }
        profiles_mut(&mut c).shift_remove(name);
        let default_ok = c.get("default").and_then(Value::as_str).is_some_and(|d| profiles(&c).contains_key(d));
        if !default_ok {
            let first = profiles(&c).keys().next().cloned().unwrap_or_default();
            c.insert(s("default"), Value::String(first));
        }
        self.save(&c);
        self.current = None;
        let d = c.get("default").and_then(Value::as_str).map(String::from);
        self.reload(d.as_deref());
        self.push(say(format!("Deleted {name}."), "quiet", &[], Some(3.0)));
    }

    pub fn set_default(&mut self) {
        let Some(cur) = self.current.clone() else { return };
        if let Some(mut cfg) = self.cfg() {
            cfg.insert(s("default"), Value::String(cur.clone()));
            self.save(&cfg);
            self.reload(Some(&cur));
            self.push(say(format!("Default is now {cur}."), "quiet", &[], Some(3.0)));
        }
    }

    pub fn persona_picked(&mut self, file: &str, choices: &[String]) {
        let rel = self.ctx.relpath(file);
        if !choices.contains(&rel) {
            self.push(Op::PersonaChoice { value: rel.clone() });
        }
        self.push(Op::Var { key: s("persona_set"), value: rel });
    }

    pub fn open_persona(&mut self, persona: &str) {
        if !persona.is_empty() && persona != NO_PERSONA {
            open_file(&self.ctx.resolve(persona));
        } else {
            self.push(say("This profile has no persona.", "quiet", &[], Some(3.0)));
        }
    }

    pub fn open_memory(&mut self) {
        if let Some(cfg) = self.cfg() {
            let p = self.current.as_ref().and_then(|c| profiles(&cfg).get(c)).and_then(Value::as_object).cloned();
            open_file(&reidcc::memory_path(&self.ctx, &cfg, p.as_ref()));
        }
    }

    // -------------------------------------------------------------- folder ---
    pub fn set_folder(&mut self, path: &str) {
        self.folder = reidcc::show_path(path);
        self.push(Op::Var { key: s("folder"), value: self.folder.clone() });
        self.push(Op::Focus { target: s("list") }); // folder -> profile, keyboard continuity
    }

    pub fn commit_folder(&mut self) {
        let f = self.real_folder();
        if py::isdir(&f) {
            self.set_folder(&f);
            self.push(Op::Clear);
        } else {
            self.push(say("Can't find that folder. It may have moved.", "error", &[("pick again", "pick_folder")], None));
        }
    }

    pub fn recent_dirs(&self) -> Vec<String> {
        match reidcc::load_state(&self.ctx).get("recent_dirs") {
            Some(Value::Array(a)) => a.iter().map(pyjson::py_str).filter(|d| py::isdir(d)).collect(),
            _ => vec![],
        }
    }
}

fn profiles_mut(cfg: &mut Obj) -> &mut Obj {
    cfg.get_mut("profiles").and_then(Value::as_object_mut).expect("load_config checked profiles")
}

fn set_profile(cfg: &mut Obj, name: &str, p: Obj) {
    profiles_mut(cfg).insert(s(name), Value::Object(p));
}

/// reid.py's open_file: $EDITOR if set, else the file's default program.
pub fn open_file(path: &str) {
    match std::env::var("EDITOR") {
        Ok(ed) if !ed.is_empty() => {
            let (ed, path) = (ed, path.to_string());
            std::thread::spawn(move || {
                let _ = std::process::Command::new(ed).arg(path).status();
            });
        }
        _ => reidcc::win::startfile(path),
    }
}
