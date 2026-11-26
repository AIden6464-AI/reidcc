#!/usr/bin/env python3
"""reid -- Reidcc, in the terminal.

    reid                      open the Reidcc TUI (pick, edit, open gate, resume)
    reid <profile> [args]     start a session with that profile; extra args go to claude
    reid -c / reid "do X"     anything that isn't a profile goes to claude (default profile)
    reid -l                   list profiles
    reid --dry [profile]      print what would run, don't run it
    reid --edit / --mem       open reid.json / the memory file

Inside Claude:
    /reid                     end the session and return to the TUI. Your conversation
                              is kept: press r there to resume it, with any profile.
    /exit                     leave as usual, back to your shell.

Profile fields (reid.json): engine (claude | codex), model, settings, persona, mode, memory,
safe, args, env, plus proxy, proxy_drop, tools, mcp, no_chrome, no_connectors, settings_json.
A codex profile starts Codex in the folder (vision/SPEC-codex-opencode.md) with the same persona,
memory and sign-in fields: persona + memory go in codex/prompts/<profile>.md, a sign-in file is a
codex/*.toml provider file (vision/SPEC-codex-signin-persona.md).
See SPEC-proxy.md for the proxy and lean-setup fields.

Relative paths in reid.json resolve against this folder, so moving the folder
(or the drive letter changing) doesn't break anything.
"""

import os
import re
import sys
import json
import glob
import time
import uuid
import shutil
import signal
import tempfile
import subprocess
from datetime import datetime

IS_WIN = os.name == "nt"
FROZEN = bool(getattr(sys, "frozen", False))  # running as the packaged Reidcc.exe / reidcc.com


def refresh_path():
    """Add PATH entries the registry has but our environment lacks.

    Explorer can hand apps a stale PATH: on 2026-11-17 it was giving the Start Menu app the
    system PATH only (no user PATH, so no npm, so "Can't find Claude Code"). A fresh sign-in
    would read the registry; we do the same. Entries we were given come first and stay, so a
    terminal's own PATH (venvs etc.) still wins."""
    if not IS_WIN:
        return
    # Windows looks in the current folder before PATH, so a claude.cmd in a cloned repo would run
    # instead of Claude. This turns that off for shutil.which and for everything we start.
    os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"
    import winreg
    reg = []
    for root, key in ((winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                      (winreg.HKEY_CURRENT_USER, "Environment")):
        try:
            with winreg.OpenKey(root, key) as k:
                reg += [os.path.expandvars(p) for p in winreg.QueryValueEx(k, "Path")[0].split(";") if p]
        except OSError:
            pass
    have = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    seen = {os.path.normcase(p.rstrip("\\/")) for p in have}
    for p in reg:
        n = os.path.normcase(p.rstrip("\\/"))
        if n not in seen:
            seen.add(n)
            have.append(p)
    os.environ["PATH"] = os.pathsep.join(have)


def _home():
    """The Reidcc data folder (reid.json, personas, proxy, aca...).

    Source lives in <home>\\python, the packaged exes in <home>\\app: look next to the script or
    exe and one level up for reid.json. REIDCC_HOME overrides."""
    if os.environ.get("REIDCC_HOME"):
        return os.path.abspath(os.environ["REIDCC_HOME"])
    here = os.path.dirname(os.path.abspath(sys.executable if FROZEN else __file__))
    for cand in (here, os.path.dirname(here)):
        if os.path.exists(os.path.join(cand, "reid.json")):
            return cand
    return os.path.dirname(here)


HOME = _home()
SCRIPT = os.path.abspath(__file__)  # reid.py, when running from source
APP_DIR = os.path.dirname(os.path.abspath(sys.executable)) if FROZEN else HOME


def _python(windowed):
    d, exe = os.path.split(sys.executable)
    want = "pythonw.exe" if windowed else "python.exe"
    cand = os.path.join(d, want)
    return cand if IS_WIN and exe.lower() in ("python.exe", "pythonw.exe") and os.path.exists(cand) else sys.executable


def cli_command():
    """argv prefix that runs reid in a console (TUI / CLI)."""
    if FROZEN:
        return [os.path.join(APP_DIR, "reidcc.com")]
    return [_python(False), SCRIPT]


def gui_command():
    """argv prefix that opens the Reidcc window without a console."""
    if FROZEN:
        return [os.path.join(APP_DIR, "Reidcc.exe")]
    return [_python(True), SCRIPT]


def show_path(path):
    """A path the way the voice guide writes it: home as ~, forward slashes."""
    path = os.path.normpath(path or "")
    home = os.path.normpath(os.path.expanduser("~"))
    if os.path.normcase(path) == os.path.normcase(home):
        path = "~"
    elif os.path.normcase(path).startswith(os.path.normcase(home) + os.sep):
        path = "~" + path[len(home):]
    return path.replace("\\", "/")


def statusline_command():
    """Shell command Claude Code runs for the reid statusline (Git Bash on Windows: forward slashes)."""
    return " ".join('"%s"' % a.replace("\\", "/") for a in cli_command() + ["--statusline"])


CONFIG = os.path.join(HOME, "reid.json")
STATE = os.path.join(HOME, "reid_state.json")

MEMORY_LIMIT = 6000
PINNED, JOURNAL = "## Pinned facts", "## Journal"
BASE_MODELS = ["opus", "sonnet", "haiku", "fable"]

# Which coding tool a profile starts (vision\SPEC-codex-opencode.md). No "engine" means claude.
ENGINES = ("claude", "codex")
# Fields only Claude Code understands, with the words the screens use. A Codex profile can keep them
# saved, but not switched on: launching would silently ignore them. (sign-in, persona and memory work
# for Codex too: vision\SPEC-codex-signin-persona.md)
CLAUDE_ONLY = (("proxy", "the proxy"), ("tools", "a tools limit"), ("mcp", "an MCP choice"),
               ("safe", "safe mode"), ("no_chrome", "chrome off"), ("no_connectors", "connectors off"),
               ("settings_json", "settings_json"))
CODEX_TAG = "CODEX · GREYED FIELDS ARE CLAUDE'S"
# Reidcc in a Codex session: its status line (Codex only takes its own items) and our tab title
CODEX_STATUS_LINE = ["model-with-reasoning", "current-dir", "context-used", "five-hour-limit", "weekly-limit"]
CODEX_UI = ("tui.status_line=" + json.dumps(CODEX_STATUS_LINE, separators=(",", ":")), "tui.terminal_title=[]")
CODEX_REPLACE_HINT = "replace drops Codex's own instructions; add is the safe one."
# Codex provider files (codex\*.toml) and the prompt files Reidcc writes for Codex (codex\prompts\).
CODEX_DIR = os.path.join(HOME, "codex")
CODEX_LOGIN = "codex login"
# If Codex's own prompt can't be read, persona + memory up to this size go inline on the command line.
CODEX_INLINE_LIMIT = 24000

# proxy\ add-ons a profile can run through (see SPEC-proxy.md)
PROXY_DIR = os.path.join(HOME, "proxy")
ADDONS = {
    "slim":     ("slim_tools_addon.py", {"SLIM_LEVEL": "slim"}),
    "ultra":    ("slim_tools_addon.py", {"SLIM_LEVEL": "ultra"}),
    "optimize": ("claude_optimizer_addon.py", {}),
    "capture":  ("capture_addon.py", {}),
}
PROXY_CHOICES = ["slim", "ultra", "optimize", "capture",
                 "slim+capture", "ultra+capture", "optimize+capture"]
CORE_TOOLS = ["Read", "Edit", "Write", "Glob", "Grep", "Bash"]
WEB_TOOLS = ["WebSearch", "WebFetch"]

DEFAULT_CONFIG = {
    "default": "main",
    "memory_file": "reidcc_memory.md",
    "profiles": {"main": {"model": "opus", "memory": True}},
}


class ReidError(Exception):
    pass


# ================================================================ config ===
def resolve(path):
    if not path:
        return ""
    path = os.path.expandvars(os.path.expanduser(path))
    return os.path.normpath(path if os.path.isabs(path) else os.path.join(HOME, path))


def relpath(path):
    """Store paths inside the Reidcc folder relative to it."""
    path = os.path.normpath(os.path.abspath(path))
    try:
        rel = os.path.relpath(path, HOME)
    except ValueError:  # different drive
        return path
    return path if rel.startswith("..") else rel.replace("\\", "/")


def save_json(path, data):
    tmp = "%s.%d.tmp" % (path, os.getpid())  # per process: two writers never share a temp file
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def load_config():
    if not os.path.exists(CONFIG):
        save_json(CONFIG, DEFAULT_CONFIG)
    try:
        with open(CONFIG, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except json.JSONDecodeError as e:
        # Loud, never silent: a broken config must not launch an empty persona.
        raise ReidError("reid.json has an error (%s). Fix it, then try again." % e)
    cfg.setdefault("profiles", {})
    if not cfg["profiles"]:
        cfg["profiles"] = dict(DEFAULT_CONFIG["profiles"])
    if cfg.get("default") not in cfg["profiles"]:
        cfg["default"] = next(iter(cfg["profiles"]))
    return cfg


def load_state():
    try:
        with open(STATE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def remember_session(name, cwd, sid, last=True):
    """Folder history always; the resume record (`last`) only for sessions `resume` can reopen,
    so a Codex launch never replaces the Claude session you meant to resume."""
    lock = take_lock(STATE + ".lock")
    try:
        st = load_state()
        if last:
            st["last"] = {"profile": name, "cwd": cwd, "sid": sid,
                          "at": datetime.now().isoformat(timespec="seconds")}
        dirs = [d for d in st.get("recent_dirs", []) if os.path.normcase(d) != os.path.normcase(cwd)]
        st["recent_dirs"] = ([cwd] + dirs)[:10]
        save_json(STATE, st)
    finally:
        if lock and os.path.exists(lock):
            os.remove(lock)


def take_lock(path, wait=5.0, stale=10.0):
    """A lock file around a read-change-write that several sessions (and reid.exe) can do at once.
    Returns the path to remove when done, or None after `wait` seconds: saving unlocked beats
    losing the write. A lock older than `stale` seconds was left by a killed process."""
    end = time.time() + wait
    while True:
        try:
            os.close(os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return path
        except OSError:  # exists, or is being deleted
            try:
                if time.time() - os.path.getmtime(path) > stale:
                    os.remove(path)
                    continue
            except OSError:
                pass
        if time.time() > end:
            return None
        time.sleep(0.05)


def memory_path(cfg, prof=None):
    return resolve((prof or {}).get("memory_file") or cfg.get("memory_file") or "reidcc_memory.md")


# ================================================================= build ===
def find_claude():
    """Prefer the real claude.exe so args never pass through cmd.exe quoting."""
    shim = shutil.which("claude")
    if shim:
        exe = os.path.join(os.path.dirname(shim), "node_modules", "@anthropic-ai",
                           "claude-code", "bin", "claude.exe")
        if os.path.exists(exe):
            return exe
    native = os.path.expanduser("~/.local/bin/claude.exe")
    if os.path.exists(native):
        return native
    if shim:
        return shim
    # Also hit for a moment while Claude Code updates itself (its files are being replaced).
    raise ReidError("Can't find Claude Code. If it's updating, this clears in a moment; otherwise install it.")


def find_codex():
    """Return (codex.exe, env the npm wrapper would set). Never the npm .cmd shim: batch files re-parse
    arguments through cmd.exe (quotes, %, ^, &), the same reason find_claude prefers claude.exe."""
    if not IS_WIN:
        exe = shutil.which("codex")
        if exe:
            return exe, {}
        raise ReidError("Can't find Codex. Install it (npm install -g @openai/codex) or put it on PATH.")
    shim = shutil.which("codex")
    if shim:
        pkg = os.path.join(os.path.dirname(shim), "node_modules", "@openai", "codex")
        arm = os.environ.get("PROCESSOR_ARCHITECTURE", "").upper() == "ARM64"
        triple = "aarch64-pc-windows-msvc" if arm else "x86_64-pc-windows-msvc"
        plat = "codex-win32-arm64" if arm else "codex-win32-x64"
        # codex.js looks in the platform package first, then its own vendor folder; same here.
        for exe in (os.path.join(pkg, "node_modules", "@openai", plat, "vendor", triple, "bin", "codex.exe"),
                    os.path.join(pkg, "vendor", triple, "bin", "codex.exe")):
            if os.path.exists(exe):
                return exe, {"CODEX_MANAGED_PACKAGE_ROOT": os.path.realpath(pkg), "CODEX_MANAGED_BY_NPM": "1"}
    exe = shutil.which("codex.exe")  # a standalone install
    if exe:
        return exe, {}
    raise ReidError("Can't find Codex. Install it (npm install -g @openai/codex), then try again.")


def engine_of(prof, name=""):
    """The profile's engine. Exactly "claude" or "codex"; missing (or null) means claude. Anything else,
    "CODEX" and false included, is an error, so every screen and the launch agree on one reading."""
    e = prof.get("engine")
    if e is None:
        return "claude"
    if e not in ENGINES:
        raise ReidError("Profile %s: there's no engine called %s. Use claude or codex." % (name, e))
    return e


def is_codex(prof):
    """For the screens: never raises (a bad engine shows as an error in the preview instead)."""
    return prof.get("engine") == "codex"


def claude_only_on(prof):
    """The Claude-only fields switched on in this profile, in screen words."""
    # "tools" counts whenever present: even [] means "no tools", a limit.
    return [words for key, words in CLAUDE_ONLY if key in prof and (key == "tools" or prof[key])]


def is_claude_model(model):
    return bool(model) and (model in BASE_MODELS or str(model).lower().startswith("claude"))


def as_args(v):
    """A profile's extra args. A string is split like a command line (args_parse), not into letters."""
    return args_parse(v) if isinstance(v, str) else list(v or [])


def args_text(args):
    """Extra args as one line people can edit; args_parse() reads it back to the same list."""
    return subprocess.list2cmdline(as_args(args))


def args_parse(text):
    """Split an extra-args line the way Windows does: spaces separate, double quotes group, \\" is a quote.
    Backslashes stay as typed, so "D:\\Shared Work" survives (str.split would make it two args)."""
    out, cur, quoted, started, i = [], [], False, False, 0
    while i < len(text):
        c = text[i]
        if c == "\\":
            n = len(text[i:]) - len(text[i:].lstrip("\\"))  # a run of backslashes
            if i + n < len(text) and text[i + n] == '"':
                cur.append("\\" * (n // 2))
                if n % 2:
                    cur.append('"')
                    i += n + 1
                else:
                    i += n
                started = True
                continue
            cur.append("\\" * n)
            i += n
            started = True
            continue
        if c == '"':
            quoted = not quoted
            started = True
        elif c.isspace() and not quoted:
            if started:
                out.append("".join(cur))
                cur, started = [], False
        else:
            cur.append(c)
            started = True
        i += 1
    if started:
        out.append("".join(cur))
    return out


# ------------------------------------------------- codex sign-in / persona ---
_CODEX_LOGIN = {}  # CODEX_HOME -> "ChatGPT" / "API key" / "signed in" / "not signed in"


def _no_window():
    return {"creationflags": 0x08000000} if IS_WIN else {}  # CREATE_NO_WINDOW


def codex_login_env():
    """The environment a `codex login` profile runs with: no stray API key may switch the billing."""
    exe, wrapper_env = find_codex()
    env = dict(os.environ)
    env.update(wrapper_env)
    for k in ("OPENAI_API_KEY", "CODEX_API_KEY"):
        env.pop(k, None)
    return exe, env


def codex_login(refresh=False):
    """What `codex login status` says, in screen words; cached per CODEX_HOME (it takes about a second).
    None when Codex can't be asked (not installed, timed out)."""
    key = os.environ.get("CODEX_HOME", "")
    if not refresh and key in _CODEX_LOGIN:
        return _CODEX_LOGIN[key]
    try:
        exe, env = codex_login_env()
        p = subprocess.run([exe, "login", "status"], capture_output=True, text=True, encoding="utf-8",
                           errors="replace", env=env, timeout=15, **_no_window())
    except (ReidError, OSError, subprocess.TimeoutExpired):
        return None
    out = (p.stdout + p.stderr).lower()
    if p.returncode or "not logged in" in out:
        s = "not signed in"
    elif "chatgpt" in out:
        s = "ChatGPT"
    elif "api key" in out:
        s = "API key"
    else:
        s = "signed in"
    _CODEX_LOGIN[key] = s
    return s


def codex_login_cached():
    return _CODEX_LOGIN.get(os.environ.get("CODEX_HOME", ""))


def codex_login_label():
    s = codex_login_cached()
    return "%s · %s" % (CODEX_LOGIN, s or "checking…")


def signin_files(codex):
    """The sign-in files an engine can use: codex\\*.toml for Codex, json\\*.json for Claude."""
    if codex:
        files = glob.glob(os.path.join(CODEX_DIR, "*.toml"))
    else:
        files = [f for f in glob.glob(os.path.join(HOME, "json", "*.json")) if "token_log" not in f]
    return sorted(relpath(f) for f in files)


def _toml_str(s):
    # JSON strings are TOML basic strings, except TOML also forbids a raw DEL.
    return json.dumps(s, ensure_ascii=False).replace("\x7f", "\\u007f")


def _toml_key(k):
    return k if re.fullmatch(r"[A-Za-z0-9_-]+", k) else _toml_str(k)


def _toml_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, list):
        return "[" + ", ".join(_toml_value(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{" + ", ".join("%s = %s" % (_toml_key(k), _toml_value(x)) for k, x in v.items()) + "}"
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return _toml_str(str(v))


def codex_provider(path):
    """A codex\\*.toml sign-in file -> (["-c", "key=value", ...], env). Tables become dotted keys so they
    merge into Reid's Codex config instead of replacing it; [env] goes into the environment only."""
    import tomllib
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ReidError("%s isn't valid TOML (%s). Fix it, then try again." % (show_path(path), e))
    env = data.pop("env", {}) or {}
    if not isinstance(env, dict):
        raise ReidError("%s: [env] has to be a table of NAME = \"value\". Fix it, then try again." % show_path(path))
    pairs = []

    def walk(prefix, d):
        for k, v in d.items():
            key = prefix + _toml_key(k)
            if isinstance(v, dict) and v:
                walk(key + ".", v)
            else:
                pairs.append((key, _toml_value(v)))
    walk("", data)
    return pairs, {str(k): str(v) for k, v in env.items()}


def _codex_config_args(args):
    """The extra args that change Codex's config (and so its own prompt): -c/--config, -p, --enable/--disable."""
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a in ("-c", "--config", "-p", "--profile", "--enable", "--disable") and i + 1 < len(args):
            out += [a, args[i + 1]]
            i += 2
            continue
        if a.startswith(("--config=", "--profile=", "--enable=", "--disable=")) or \
                (len(a) > 2 and a[:2] in ("-c", "-p") and not a.startswith("--")):
            out.append(a)
        i += 1
    return out


def _codex_config_keys(args):
    keys, i = [], 0
    while i < len(args):
        a, kv = args[i], None
        if a in ("-c", "--config") and i + 1 < len(args):
            kv = args[i + 1]
            i += 1
        elif a.startswith("--config="):
            kv = a[len("--config="):]
        elif a.startswith("-c") and len(a) > 2 and not a.startswith("--"):
            kv = a[2:]
        if kv is not None:
            keys.append(kv.split("=", 1)[0].strip())
        i += 1
    return keys


def codex_prompt_path(name):
    """codex\\prompts\\<profile>.md; names that aren't plain get a short hash so two can't collide."""
    slug = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-") or "profile"
    if slug != name:
        slug += "-" + __import__("hashlib").sha1(name.encode("utf-8")).hexdigest()[:6]
    return os.path.join(CODEX_DIR, "prompts", slug + ".md")


def codex_base_prompt(exe, env, pre_args, cwd):
    """Codex's own prompt ("You are Codex…") for these settings, via `codex debug prompt-input` (no model
    call). Cached in codex\\prompts\\.base-<key>.md until Codex, the settings or ~/.codex/config.toml change.
    None if it can't be read."""
    import hashlib
    home = env.get("CODEX_HOME") or os.path.expanduser("~/.codex")
    conf = os.path.join(home, "config.toml")
    try:
        st = os.stat(exe)
        conf_m = os.path.getmtime(conf) if os.path.exists(conf) else 0
    except OSError:
        return None
    key = hashlib.sha1(json.dumps([st.st_size, st.st_mtime, pre_args, conf_m, home]).encode("utf-8")).hexdigest()[:16]
    cache = os.path.join(CODEX_DIR, "prompts", ".base-%s.md" % key)
    if os.path.exists(cache):
        with open(cache, "r", encoding="utf-8", newline="") as f:
            return f.read()
    try:
        p = subprocess.run([exe] + pre_args + ["debug", "prompt-input"], capture_output=True, text=True,
                           encoding="utf-8", errors="replace", env=env, cwd=cwd or None, timeout=10,
                           **_no_window())
        items = json.loads(p.stdout) if p.returncode == 0 else []
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    base = None
    for it in items if isinstance(items, list) else []:
        if isinstance(it, dict) and it.get("type") == "message" and it.get("role") == "developer":
            text = "".join(c.get("text", "") for c in it.get("content") or [] if isinstance(c, dict))
            if text.strip() and not text.lstrip().startswith("<"):  # the others are <skills_…>, <multi_agent_…>
                base = text
                break
    if not base:
        return None
    os.makedirs(os.path.dirname(cache), exist_ok=True)
    for old in glob.glob(os.path.join(CODEX_DIR, "prompts", ".base-*.md")):
        try:
            if time.time() - os.path.getmtime(old) > 30 * 86400:
                os.remove(old)
        except OSError:
            pass
    with open(cache, "w", encoding="utf-8", newline="") as f:
        f.write(base)
    return base


def build_codex(cfg, name, prof, extra, cwd=None, prepare=True):
    """Codex's command. `prepare` writes the prompt file (and may read Codex's own prompt, ~1 s the first
    time); previews pass False and get the same command without touching anything."""
    def need(path, what):
        full = resolve(path)
        if not os.path.exists(full):
            raise ReidError("Can't find the %s for %s: %s. Pick it again in settings." % (what, name, show_path(full)))
        return full

    on = claude_only_on(prof)
    if on:
        listing = ", ".join(on[:-1]) + " and " + on[-1] if len(on) > 1 else on[0]
        raise ReidError("Codex can't use %s. Turn %s off for %s, or pick a Claude profile."
                        % (listing, "them" if len(on) > 1 else "it", name))
    model = prof.get("model")
    if is_claude_model(model):
        raise ReidError("%s is a Claude model. Clear the model to use Codex's default, or type a Codex model." % model)
    settings = prof.get("settings")
    if settings and not str(settings).lower().endswith(".toml"):
        raise ReidError("%s is a Claude sign-in file. Pick a Codex one, or use codex login." % settings)
    ppath = need(prof["persona"], "persona file") if prof.get("persona") else ""
    prompt_on = bool(ppath or prof.get("memory"))

    args = as_args(prof.get("args")) + list(extra)
    for a in args:
        if a in ("-C", "--cd") or a.startswith("--cd=") or (a.startswith("-C") and len(a) > 2):
            raise ReidError("Leave -C / --cd out of the extra args: Codex opens in the folder you picked.")
    if args and args[0] in ("resume", "fork"):
        raise ReidError("Leave %s out of the extra args: a Codex profile starts a new session." % args[0])
    for k in _codex_config_keys(args):
        if prompt_on and k in ("model_instructions_file", "developer_instructions"):
            raise ReidError("Leave %s out of the extra args: it would replace the persona." % k)
        if settings and k == "model_provider":
            raise ReidError("Leave model_provider out of the extra args: the sign-in file sets it.")

    pre = ["-m", model] if model else []
    if settings:
        exe, wrapper_env = find_codex()
        env = dict(os.environ)
        env.update(wrapper_env)
        pairs, penv = codex_provider(need(settings, "sign-in file"))
        for k, v in pairs:
            if not (model and k == "model"):  # the profile's own model wins
                pre += ["-c", "%s=%s" % (k, v)]
        env.update(penv)
    else:
        exe, env = codex_login_env()
        if prepare and codex_login_cached() in (None, "not signed in"):
            codex_login(refresh=True)
        if codex_login_cached() == "not signed in":
            raise ReidError("Codex isn't signed in. Run codex login in a terminal, then try again.")
    for k, v in (prof.get("env") or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = str(v)

    argv = [exe] + pre
    for ui in CODEX_UI if prof.get("statusline", True) else CODEX_UI[1:]:
        argv += ["-c", ui]  # before the extra args, so a -c of your own there still wins
    if prompt_on:
        pfile = codex_prompt_path(name)
        setting = "model_instructions_file=" + _toml_str(pfile.replace("\\", "/"))
        if prepare:
            persona = open(ppath, "r", encoding="utf-8").read() if ppath else ""
            text = (persona + memory_block(cfg, prof)).strip("\n") + "\n"
            if not (persona and prof.get("mode") == "replace"):
                # add mode: Codex's own prompt first, untouched, then the persona and memory
                base = codex_base_prompt(exe, env, pre + _codex_config_args(args), cwd)
                if base is not None:
                    text = base.rstrip("\n") + "\n\n" + text
                elif len(text) <= CODEX_INLINE_LIMIT:
                    setting, pfile = "developer_instructions=" + _toml_str(text), None
                else:
                    raise ReidError("Couldn't read Codex's own prompt to add the persona to. "
                                    "Use replace mode, or update Reidcc.")
            if pfile:
                os.makedirs(os.path.dirname(pfile), exist_ok=True)
                with open(pfile, "w", encoding="utf-8", newline="") as f:  # \n only: \r\n would change the text
                    f.write(text)
        argv += ["-c", setting]
    return argv + args, env, []


def trim_memory(text, limit):
    if len(text) <= limit:
        return text
    if PINNED in text and JOURNAL in text:
        cut = text.index(JOURNAL)
        head, journal = text[:cut], text[cut:]
        room = max(0, limit - len(head) - 40)
        tail = journal[-room:] if room else ""
        tail = tail[tail.find("\n") + 1:] if "\n" in tail else tail
        return head + JOURNAL + "\n- ...(older entries trimmed)\n" + tail
    return "...(older memory trimmed)\n" + text[-limit:]


def memory_block(cfg, prof):
    if not prof.get("memory"):
        return ""
    path = memory_path(cfg, prof)
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Long-term memory\n\n%s\n\n%s\n- %s - memory init\n"
                    % (PINNED, JOURNAL, datetime.now().strftime("%Y-%m-%d")))
    text = open(path, "r", encoding="utf-8").read().strip()
    if not text:
        return ""
    text = trim_memory(text, int(prof.get("memory_limit") or MEMORY_LIMIT))
    return (
        "\n\n# ===== LONG-TERM MEMORY =====================================\n"
        "# This is what you remember from before. Treat it as true and current.\n"
        "# Your memory file lives at:\n#   %s\n"
        "# When asked to remember something, or when something worth keeping\n"
        "# happens, append it to that file with your file tools: facts under\n"
        "# '%s', dated one-liners under '%s'. Keep it concise.\n"
        "# ------------------------------------------------------------\n\n"
        "%s\n# ============================================================\n"
        % (os.path.abspath(path), PINNED, JOURNAL, text)
    )


def _write_temp(text, prefix, suffix):
    # the pid in the name tells sweep_temps the file belongs to a session that's still running
    fd, path = tempfile.mkstemp(prefix="%s%d_" % (prefix, os.getpid()), suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def build(cfg, name, extra, cwd=None, prepare=True):
    """Return (argv, env, temp_files) for profile `name`.

    Everything that can fail is checked before any temp file is written. `prepare=False` (previews)
    only matters for Codex: it skips writing its prompt file."""
    profiles = cfg["profiles"]
    if name not in profiles:
        raise ReidError("No profile named %s. Profiles: %s." % (name, ", ".join(profiles)))
    prof = profiles[name]
    if engine_of(prof, name) == "codex":
        return build_codex(cfg, name, prof, extra, cwd, prepare)
    if str(prof.get("settings") or "").lower().endswith(".toml"):
        raise ReidError("%s is a Codex sign-in file. Pick a Claude one, or use subscription." % prof["settings"])
    argv = [find_claude()]
    env = dict(os.environ)
    temps = []

    def need(path, what):
        full = resolve(path)
        if not os.path.exists(full):
            raise ReidError("Can't find the %s for %s: %s. Pick it again in settings." % (what, name, show_path(full)))
        return full

    settings = need(prof["settings"], "settings file") if prof.get("settings") else ""
    ppath = need(prof["persona"], "persona file") if prof.get("persona") else ""
    mcp = prof.get("mcp")
    mcp_path = need(mcp, "MCP config") if mcp and mcp != "none" else ""
    extra_settings = prof.get("settings_json") or {}
    if not isinstance(extra_settings, dict):
        raise ReidError("Profile %s: settings_json has to be an object. Fix it in reid.json." % name)
    proxy_plan(prof)  # validates the proxy field

    if prof.get("model"):
        argv += ["--model", str(prof["model"])]

    # Auth: a settings file means API mode (the file carries key + base URL).
    # No settings file means your Pro/Max login, so strip inherited API creds.
    if not settings:
        for k in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL"):
            env.pop(k, None)
    statusline = prof.get("statusline", True)  # reid's telemetry line; "statusline": false opts out
    if extra_settings or statusline:
        # Claude takes one --settings, so merge the profile's extras onto the file.
        merged = {}
        if settings:
            try:
                merged = json.load(open(settings, "r", encoding="utf-8"))
            except ValueError as e:
                raise ReidError("%s isn't valid JSON (%s). Fix it, then try again." % (show_path(settings), e))
            if not isinstance(merged, dict):
                raise ReidError("%s has to hold a JSON object. Fix it, then try again." % show_path(settings))
        for k, v in extra_settings.items():
            merged[k] = {**merged[k], **v} if isinstance(v, dict) and isinstance(merged.get(k), dict) else v
        if statusline and "statusLine" not in merged:
            merged["statusLine"] = {"type": "command", "command": statusline_command()}
        settings = _write_temp(json.dumps(merged, indent=2), "reid_settings_", ".json")
        temps.append(settings)
    if settings:
        argv += ["--settings", settings]

    persona = open(ppath, "r", encoding="utf-8").read() if ppath else ""
    replace = bool(persona) and prof.get("mode") == "replace"
    if replace:
        # Replacing Claude Code's prompt drops its environment section; put the basics back.
        persona = persona.rstrip() + "\n\nWorking directory: %s. Platform: %s.\n" % (
            cwd or os.getcwd(),
            "Windows; shells: PowerShell and Git Bash" if IS_WIN else sys.platform)
    prompt = persona + memory_block(cfg, prof)
    if prompt.strip():
        pfile = _write_temp(prompt, "reid_prompt_", ".md")
        temps.append(pfile)
        argv += ["--system-prompt-file" if replace else "--append-system-prompt-file", pfile]

    if "tools" in prof:
        argv += ["--tools", ",".join(prof.get("tools") or [])]
    if mcp_path:
        argv += ["--mcp-config", mcp_path]
    if mcp or prof.get("safe"):
        argv.append("--strict-mcp-config")
    if prof.get("no_chrome"):
        argv.append("--no-chrome")
    if prof.get("no_connectors"):
        env["ENABLE_CLAUDEAI_MCP_SERVERS"] = "false"

    if prof.get("safe"):
        env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
        if prof.get("settings"):  # --bare skips OAuth, so only valid in API mode
            argv.append("--bare")

    for k, v in (prof.get("env") or {}).items():
        if v is None:
            env.pop(k, None)
        else:
            env[k] = str(v)

    argv += as_args(prof.get("args")) + list(extra)
    return argv, env, temps


def proxy_list(prof):
    p = prof.get("proxy") or []
    if isinstance(p, str):
        p = [x for x in p.replace("+", ",").split(",") if x.strip()]
    return [x.strip().lower() for x in p]


def persona_name(prof):
    """Short persona name for tags (file name without extension), or ''."""
    return os.path.splitext(os.path.basename(prof.get("persona") or ""))[0]


def summary(cfg, name):
    p = cfg["profiles"][name]
    codex = is_codex(p)
    bits = (["codex"] if codex else []) + [str(p.get("model") or ("engine default" if codex else "provider default"))]
    if p.get("settings"):
        s = os.path.splitext(os.path.basename(p["settings"]))[0]
        bits.append(("" if codex else "api ") + s + ("" if os.path.exists(resolve(p["settings"])) else " (missing)"))
    else:
        bits.append(codex_login_label() if codex else "subscription")
    if p.get("persona"):
        miss = "" if os.path.exists(resolve(p["persona"])) else " (missing)"
        bits.append("persona %s%s%s" % (persona_name(p), " (replace)" if p.get("mode") == "replace" else "", miss))
    if p.get("memory"):
        bits.append("memory")
    if proxy_list(p):
        bits.append("proxy " + "+".join(proxy_list(p)))
    if "tools" in p:
        bits.append("%d tools" % len(p.get("tools") or []) if p.get("tools") else "no tools")
    if p.get("mcp"):
        bits.append("no mcp" if p["mcp"] == "none" else "mcp " + os.path.splitext(os.path.basename(p["mcp"]))[0])
    if p.get("no_chrome"):
        bits.append("chrome off")
    if p.get("no_connectors"):
        bits.append("connectors off")
    if p.get("safe"):
        bits.append("safe mode")
    return " · ".join(bits)


def profile_check(cfg, name, cwd):
    """Can this profile start here? Returns (error or None, command preview, what's on: persona/memory).
    Shared by the GUI and the TUI so both show the same `ready · persona + memory` and preview."""
    p = cfg["profiles"][name]
    have = [w for w, on in (("persona", p.get("persona")), ("memory", p.get("memory"))) if on]
    try:
        argv, _env, temps = build(cfg, name, [], cwd, prepare=False)
        for t in temps:
            os.remove(t)
    except ReidError as e:
        return str(e), "", have
    engine = engine_of(p, name)  # build() already checked it
    home = HOME.replace("\\", "/").rstrip("/") + "/"
    shown = []
    for a in argv[1:]:
        if a in CODEX_UI and shown[-1:] == ["-c"]:  # Reidcc's own status line and title: like Claude's statusline, not shown
            shown.pop()
            continue
        shown.append(a)
    text = subprocess.list2cmdline([engine] + [a.replace(home, "") if "reid_" not in a else "<temp>" for a in shown])
    if proxy_plan(p):
        text = "via proxy %s · %s" % ("+".join(proxy_list(p)), text)
    return None, text, have


def asset(name):
    """A bundled file: next to the packaged app's data (_internal), else in the Reidcc folder
    (source runs from its python folder, one level down)."""
    for base in (getattr(sys, "_MEIPASS", None), os.path.dirname(os.path.dirname(os.path.abspath(__file__)))):
        if base and os.path.exists(os.path.join(base, name)):
            return os.path.join(base, name)
    return None


_ART = {}


def tui_art(name, max_cols, max_rows):
    """Pre-rendered terminal frames (python\\build\\make_assets.py) at the widest size that fits, or None."""
    meta_path = asset(os.path.join("assets", "tui", "tui.json"))
    if not meta_path:
        return None
    import gzip
    meta = json.load(open(meta_path))
    for cols in sorted(meta.get(name, []), reverse=True):
        path = asset(os.path.join("assets", "tui", "%s_%d.json.gz" % (name, cols)))
        if cols > max_cols or not path:
            continue
        if path not in _ART:
            with gzip.open(path, "rt", encoding="utf-8") as f:
                _ART[path] = json.load(f)
        if len(_ART[path][0]) <= max_rows:
            return {"cols": cols, "frames": _ART[path], "meta": meta}
    return None


# ================================================================= proxy ===
class Proxy:
    def __init__(self, proc, port, job, log, log_path):
        self.proc, self.port, self.job, self.log, self.log_path = proc, port, job, log, log_path


def mitmdump_path():
    for cand in (os.path.join(PROXY_DIR, ".venv", "Scripts", "mitmdump.exe"),
                 os.path.join(PROXY_DIR, ".venv", "bin", "mitmdump")):
        if os.path.exists(cand):
            return cand
    return shutil.which("mitmdump")


def mitm_ca_path():
    return os.path.join(os.path.expanduser("~"), ".mitmproxy", "mitmproxy-ca-cert.pem")


def proxy_plan(prof):
    """(scripts, env) for the profile's proxy field, or None. Raises on bad values."""
    names = proxy_list(prof)
    if not names:
        return None
    bad = [n for n in names if n not in ADDONS]
    if bad:
        raise ReidError("Unknown proxy add-on: %s. Use one of: %s." % (", ".join(bad), ", ".join(ADDONS)))
    if "slim" in names and "ultra" in names:
        raise ReidError("slim and ultra are one add-on at two levels. Pick one.")
    scripts, env = [], {}
    for n in names:
        script, e = ADDONS[n]
        scripts.append(os.path.join(PROXY_DIR, script))
        env.update(e)
    if prof.get("proxy_drop"):
        env["SLIM_DROP"] = ",".join(prof["proxy_drop"])
    return scripts, env


def _port_listening(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _job_kill_on_close(proc):
    """Put a SUSPENDED process in a kill-on-close Job Object, then resume it.

    mitmdump.exe is a launcher that spawns python.exe; starting suspended means that
    child is born inside the job too. When reid dies (terminal closed, killed), the
    job handle closes and Windows kills the whole proxy tree. Returns the job or None."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    ntdll = ctypes.WinDLL("ntdll")

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                    ("SchedulingClass", wintypes.DWORD)]

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class EXT(ctypes.Structure):
        _fields_ = [("Basic", BASIC), ("Io", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]

    k32.CreateJobObjectW.restype = wintypes.HANDLE
    k32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    k32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    ntdll.NtResumeProcess.argtypes = [wintypes.HANDLE]
    job = None
    try:
        job = k32.CreateJobObjectW(None, None)
        info = EXT()
        info.Basic.LimitFlags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not (job and k32.SetInformationJobObject(job, 9, ctypes.byref(info), ctypes.sizeof(info))
                and k32.AssignProcessToJobObject(job, int(proc._handle))):
            job = None
    finally:
        ntdll.NtResumeProcess(int(proc._handle))  # always resume, job or not
    return job


def start_proxy(name, plan):
    scripts, addon_env = plan
    mitm = mitmdump_path()
    if not mitm:
        raise ReidError("The proxy isn't set up. Build it: cd %s; python -m venv .venv; "
                        ".venv\\Scripts\\pip install --only-binary :all: mitmproxy" % PROXY_DIR)
    for s in scripts:
        if not os.path.exists(s):
            raise ReidError("Proxy add-on missing: %s. Restore it in proxy/." % show_path(s))
    port = _free_port()
    os.makedirs(os.path.join(PROXY_DIR, "logs"), exist_ok=True)
    log_path = os.path.join(PROXY_DIR, "logs", re.sub(r"[^\w.-]+", "_", name) + ".log")
    log = open(log_path, "w", encoding="utf-8", errors="replace")
    argv = [mitm]
    for s in scripts:
        argv += ["-s", s]
    argv += ["--listen-host", "127.0.0.1", "--listen-port", str(port), "-q"]
    env = dict(os.environ, **addon_env)
    flags = 0
    if IS_WIN:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000) | 0x00000004  # CREATE_SUSPENDED
    proc = subprocess.Popen(argv, cwd=PROXY_DIR, env=env, stdin=subprocess.DEVNULL,
                            stdout=log, stderr=subprocess.STDOUT, creationflags=flags)
    job = _job_kill_on_close(proc) if IS_WIN else None
    px = Proxy(proc, port, job, log, log_path)
    deadline = time.time() + 15
    while time.time() < deadline:
        if proc.poll() is not None:
            break
        if _port_listening(port) and os.path.exists(mitm_ca_path()):
            return px
        time.sleep(0.15)
    stop_proxy(px)
    tail = open(log_path, "r", encoding="utf-8", errors="replace").read().strip().splitlines()[-8:]
    raise ReidError("The proxy didn't start (%s). See %s:\n  %s" % (
        "it exited" if proc.poll() is not None else "timed out", show_path(log_path), "\n  ".join(tail) or "empty log"))


def stop_proxy(px):
    if not px:
        return
    try:
        if px.job:
            import ctypes
            k32 = ctypes.windll.kernel32
            k32.TerminateJobObject(ctypes.c_void_p(px.job), 0)
            k32.CloseHandle(ctypes.c_void_p(px.job))
        elif IS_WIN:
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(px.proc.pid)], capture_output=True)
        else:
            px.proc.terminate()
        px.proc.wait(timeout=5)
    except Exception:
        pass
    finally:
        px.log.close()


def proxy_env(px):
    return {"HTTPS_PROXY": "http://127.0.0.1:%d" % px.port,
            "NODE_EXTRA_CA_CERTS": mitm_ca_path(),
            "NO_PROXY": "localhost,127.0.0.1,::1"}


# ============================================================== terminal ===
TERM_RESET = ("\x1b[0m\x1b[?25h\x1b[?2004l\x1b[?1000l\x1b[?1002l\x1b[?1003l"
              "\x1b[?1006l\x1b[?1004l\x1b[<u")


def enable_vt():
    if not IS_WIN:
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        h = k32.GetStdHandle(-11)
        m = ctypes.c_uint32()
        if k32.GetConsoleMode(h, ctypes.byref(m)):
            k32.SetConsoleMode(h, m.value | 0x0004)  # VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass


def console_save():
    try:
        if IS_WIN:
            import ctypes
            k32 = ctypes.windll.kernel32
            saved = []
            for n in (-10, -11):
                h = k32.GetStdHandle(n)
                m = ctypes.c_uint32()
                if k32.GetConsoleMode(h, ctypes.byref(m)):
                    saved.append((h, m.value))
            return saved
        import termios
        return termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        return None


def _tty():
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


def console_restore(saved):
    """Undo whatever claude left behind (raw mode, mouse, bracketed paste...)."""
    if _tty():  # never put escape codes into piped output (reid -p ... | jq)
        sys.stdout.write(TERM_RESET)
        sys.stdout.flush()
    if saved is None:
        return
    try:
        if IS_WIN:
            import ctypes
            import msvcrt
            for h, m in saved:
                ctypes.windll.kernel32.SetConsoleMode(h, m)
            while msvcrt.kbhit():
                msvcrt.getwch()
        else:
            import termios
            fd = sys.stdin.fileno()
            termios.tcsetattr(fd, termios.TCSANOW, saved)
            termios.tcflush(fd, termios.TCIFLUSH)
    except Exception:
        pass


_SEQ = {"A": "up", "B": "down", "C": "right", "D": "left", "H": "home", "F": "end"}


def getkey():
    if IS_WIN:
        import msvcrt
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):
            return {"H": "up", "P": "down", "K": "left", "M": "right",
                    "G": "home", "O": "end"}.get(msvcrt.getwch(), "")
        if ch == "\x1b":
            time.sleep(0.01)
            if msvcrt.kbhit() and msvcrt.getwch() == "[" and msvcrt.kbhit():
                return _SEQ.get(msvcrt.getwch(), "")
            return "esc"
    else:
        import tty
        import select
        import termios
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = os.read(fd, 1).decode(errors="ignore")
            if ch == "\x1b":
                if select.select([fd], [], [], 0.03)[0]:
                    seq = os.read(fd, 8).decode(errors="ignore")
                    return _SEQ.get(seq[-1:], "") if seq.startswith(("[", "O")) else "esc"
                return "esc"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    if ch == "\x03":
        raise KeyboardInterrupt
    return {"\r": "enter", "\n": "enter", "\x08": "backspace", "\x7f": "backspace"}.get(ch, ch)


def key_waiting():
    """A key is ready to read (doesn't consume it)."""
    if IS_WIN:
        import msvcrt
        return msvcrt.kbhit()
    import select
    return bool(select.select([sys.stdin], [], [], 0)[0])


def open_file(path):
    editor = os.environ.get("EDITOR")
    if editor:
        subprocess.call([editor, path])
    elif IS_WIN:
        os.startfile(path)
    else:
        subprocess.call(["xdg-open", path])


# =============================================================== session ===
def back_flag_path():
    return os.path.join(tempfile.gettempdir(), "reid_back_%d.flag" % os.getpid())


def claude_dir():
    return os.environ.get("CLAUDE_CONFIG_DIR") or os.path.expanduser("~/.claude")


def session_exists(sid):
    return bool(sid) and bool(glob.glob(os.path.join(claude_dir(), "projects", "*", sid + ".jsonl")))


def kill_tree(proc):
    if IS_WIN:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
    else:
        proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def sweep_temps(max_age_h=6):
    """Remove prompt/settings temps left by sessions whose terminal was closed
    (Windows kills reid outright then, so its own cleanup never runs)."""
    cutoff = time.time() - max_age_h * 3600
    for pat in ("reid_prompt_*", "reid_settings_*"):
        for f in glob.glob(os.path.join(tempfile.gettempdir(), pat)):
            pid = re.match(r"reid_[a-z]+_(\d+)_", os.path.basename(f))
            if pid and pid_alive(int(pid.group(1))):
                continue  # a session running longer than max_age_h still reads its files
            try:
                if os.path.getmtime(f) < cutoff:
                    os.remove(f)
            except OSError:
                pass


def pid_alive(pid):
    if not IS_WIN:
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = ctypes.c_void_p
    k32.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    k32.CloseHandle.argtypes = [ctypes.c_void_p]
    h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return ctypes.get_last_error() == 5  # access denied: it exists
    code = ctypes.c_ulong()
    ok = k32.GetExitCodeProcess(h, ctypes.byref(code))
    k32.CloseHandle(h)
    return bool(ok) and code.value == 259  # STILL_ACTIVE


def run_session(cfg, name, cwd, extra=(), resume=None):
    """Run the profile's engine in this terminal. Returns (exit_code, came_back_via_/reid, session_id, note).
    Resume, the session id and /reid are Claude's; a Codex session is a plain new one."""
    extra = list(extra)
    claude = engine_of(cfg["profiles"].get(name, {}), name) == "claude"
    if resume and not claude:
        raise ReidError("Resume is for Claude profiles for now. Open the gate for a new Codex session.")
    sweep_temps()
    argv, env, temps = build(cfg, name, extra, cwd)
    plan = proxy_plan(cfg["profiles"][name])
    note = ""
    continuing = any(a in ("-c", "--continue", "-r", "--resume") or a.startswith("--resume=")
                     for a in extra)
    sid = None
    if claude:
        if resume == "-c":
            argv.append("-c")
        elif resume and session_exists(resume):
            argv += ["--resume", resume]
            sid = resume
        elif resume:
            note = "That session had no messages yet, so this is a new one."
        if not sid and not continuing and resume != "-c":
            sid = str(uuid.uuid4())
            argv += ["--session-id", sid]

    flag = back_flag_path()
    if os.path.exists(flag):
        os.remove(flag)
    if claude:
        env["REID_FLAG"] = flag  # only Claude has the /reid command
    env["REID_PROFILE"] = name

    saved = console_save()
    old_sigint = signal.signal(signal.SIGINT, signal.SIG_IGN)  # Ctrl+C belongs to claude
    back = False
    px = None
    try:
        # Banner goes to stderr so stdout stays clean for `reid <profile> -p ... | jq`.
        if _tty():
            sys.stdout.write(TERM_RESET + "\x1b[?1049l")
            sys.stdout.flush()
        print("%sREIDCC%s · %s %s%s%s" % (TEXT2, TEXT, name, TEXT3,
                                            "· /reid comes back here" if claude else "· codex · /quit comes back here",
                                            R), file=sys.stderr)
        if not claude and _tty():
            sys.stdout.write("\x1b]0;REIDCC · codex · %s\x07" % name)  # the tab title (Codex's own is off)
            sys.stdout.flush()
        if note:
            print("%s%s%s" % (TEXT3, note, R), file=sys.stderr)
        if plan:
            px = start_proxy(name, plan)
            env.update(proxy_env(px))
            print("%sproxy %s on 127.0.0.1:%d · log %s%s"
                  % (TEXT3, "+".join(proxy_list(cfg["profiles"][name])), px.port, show_path(px.log_path), R),
                  file=sys.stderr)
        proc = subprocess.Popen(argv, env=env, cwd=cwd)
        while True:
            try:
                rc = proc.wait(timeout=0.2)
                break
            except subprocess.TimeoutExpired:
                if os.path.exists(flag):
                    back = True
                    kill_tree(proc)
                    rc = proc.returncode
                    break
    finally:
        if not claude and _tty():
            sys.stdout.write("\x1b]0;Reidcc\x07")
            sys.stdout.flush()
        stop_proxy(px)
        signal.signal(signal.SIGINT, old_sigint)
        console_restore(saved)
        for t in temps + [flag]:
            try:
                os.remove(t)
            except OSError:
                pass
    remember_session(name, cwd, sid, last=claude)
    return rc, back, sid, note


def cmd_back():
    """Called by the /reid slash command from inside claude."""
    flag = os.environ.get("REID_FLAG")
    if not flag:
        print("This session wasn't started by Reidcc, so there's nothing to go back to. "
              "Run reid to open it.")
        return 0
    with open(flag, "w") as f:
        f.write("back")
    print("Back to Reidcc.")
    sys.stdout.flush()
    time.sleep(8)  # reid ends the session long before this finishes
    return 0


def _pct(v):
    try:
        return max(0, min(100, int(round(float(v)))))
    except (TypeError, ValueError):
        return None


def _level(p):
    return OXIDE if p >= 90 else BRONZE if p >= 75 else TEXT2


def cmd_statusline():
    """Claude Code's statusLine command for reid sessions: reads the session JSON on stdin.

    ~/kiln · PROFILE · MAIN · PERSONA · KURE   context 42% · limit 61%"""
    try:
        data = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        data = {}
    ws = data.get("workspace") or {}
    parts = ["%s%s%s" % (TEXT, show_path(ws.get("current_dir") or data.get("cwd") or os.getcwd()), R)]
    name = os.environ.get("REID_PROFILE")
    if name:
        parts.append("%sPROFILE · %s%s" % (TEXT2, name.upper(), R))
        try:
            pn = persona_name(load_config()["profiles"].get(name) or {})
        except ReidError:
            pn = ""
        if pn:
            parts.append("%sPERSONA · %s%s" % (TEXT2, pn.upper(), R))
    left = (" %s·%s " % (TEXT3, R)).join(parts)
    meters = []
    ctx = _pct((data.get("context_window") or {}).get("used_percentage")) or 0
    meters.append("%scontext %d%%%s" % (_level(ctx), ctx, R))
    rl = data.get("rate_limits") or {}
    lim = [p for p in (_pct((rl.get(w) or {}).get("used_percentage")) for w in ("five_hour", "seven_day"))
           if p is not None]
    if lim:  # only subscribers get this, and only after the first reply
        meters.append("%slimit %d%%%s" % (_level(max(lim)), max(lim), R))
    print(left + "   " + (" %s·%s " % (TEXT3, R)).join(meters))
    return 0


# =================================================================== TUI ===
# Palette from vision/reidcc-palette.md (bone text, one emerald signal).
def _fg(h):
    return "\x1b[38;2;%d;%d;%dm" % tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


TEXT, TEXT2, TEXT3 = _fg("#D6D0C8"), _fg("#9F978E"), _fg("#7F7A73")
LINE = _fg("#928A82")  # linework: the art's engraved lines
EMERALD, BRONZE, OXIDE = _fg("#00C463"), _fg("#C99A45"), _fg("#C0584B")
ACC = TEXT     # labels you act on
DIM = TEXT3    # hints, separators, detail
WARN = TEXT    # flash messages
SEL = "\x1b[48;2;41;39;35m" + TEXT  # stone-dark row, bone text
B = "\x1b[1m"
R = "\x1b[0m"


def text_banner(w):
    """The GUI banner's story (folder → persona → ●) drawn in linework, sized to the window."""
    labels = ["folder", "profile", "●"]
    bw = 11                                       # box width
    gap = max(6, min(18, (w - 2 - 3 * bw - 8) // 2))
    tail = max(2, min(8, (w - 2 - 3 * bw - 2 * gap) // 2))
    pad = " " * max(0, (w - 3 * bw - 2 * gap - 2 * tail) // 2)
    edge = " " * tail + "╭" + "─" * (bw - 2) + "╮"
    tops = edge + (" " * (gap - 1) + "╭" + "─" * (bw - 2) + "╮") * 2
    bots = tops.replace("╭", "╰").replace("╮", "╯")
    mid = "─" * tail
    for i, l in enumerate(labels):
        inner = l.center(bw - 2)
        if l == "●":
            inner = inner.replace("●", EMERALD + "●" + LINE)
        else:
            inner = TEXT2 + inner + LINE
        mid += "┤" + inner + "├" + ("─" * (gap - 2) + "→" if i < 2 else "─" * tail)
    return [pad + LINE + tops + R, pad + LINE + mid + R, pad + LINE + bots + R]


def fit(s, w):
    s = str(s)
    return s if len(s) <= w else s[:max(0, w - 1)] + "…"


def wrap_text(s, w, max_lines=3):
    """Word-wrap to w columns; the last allowed line is cut with fit()."""
    words, lines, cur = str(s).split(), [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > w:
            lines.append(cur)
            cur = word
        else:
            cur = (cur + " " + word) if cur else word
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines - 1] + [fit(" ".join(lines[max_lines - 1:]), w)]
    return [fit(l, w) for l in lines] or [""]


class TUI:
    def __init__(self, cwd, msg=""):
        self.cwd = cwd
        self.msg = msg
        self.idx = 0

    # ---------------------------------------------------------- drawing ---
    def size(self):
        ts = shutil.get_terminal_size((100, 30))
        return max(40, ts.columns), max(12, ts.lines)

    def paint(self, lines):
        w, h = self.size()
        out = "\x1b[?25l\x1b[H" + "".join(l + "\x1b[K\n" for l in lines[:h - 1]) + "\x1b[J"
        sys.stdout.write(out)
        sys.stdout.flush()

    def header(self, crumb=""):
        w, _ = self.size()
        title = " %sREIDCC%s" % (TEXT2, R) + (" %s·%s %s" % (DIM, R, fit(crumb, w - 12)) if crumb else "")
        return [title, " %sfolder%s  %s" % (DIM, R, fit(show_path(self.cwd), w - 10)), ""]

    def rule(self):
        w, _ = self.size()
        return " " + DIM + "─" * (w - 2) + R

    def help(self, text):
        w, _ = self.size()
        return " " + DIM + fit(text, w - 2) + R

    def flash(self):
        if not self.msg:
            return []
        w, _ = self.size()
        m, self.msg = self.msg, ""
        return [" " + WARN + fit(m, w - 2) + R, ""]

    def row(self, selected, left, right, lw=16):
        w, _ = self.size()
        mark = "→" if selected else " "
        plain_l = fit(left, lw).ljust(lw)
        plain_r = fit(right, max(0, w - lw - 6))
        if selected:
            return " " + SEL + (" %s %s %s" % (mark, plain_l, plain_r)).ljust(w - 2) + R
        return "  %s %s %s%s%s" % (mark, plain_l, DIM, plain_r, R)

    # ----------------------------------------------------------- inputs ---
    def check_login(self):
        """Ask `codex login status` off the main thread (about a second); key() redraws when it's back."""
        import threading
        t = getattr(self, "_login", None)
        if t is None or not t.is_alive():
            self._login = threading.Thread(target=codex_login, daemon=True)
            self._login.start()

    def key(self):
        """getkey(), or None once a pending login check finishes so the screen can show its answer."""
        t = getattr(self, "_login", None)
        if t is not None:
            while t.is_alive() and not key_waiting():
                time.sleep(0.05)
            if not t.is_alive():
                self._login = None
                if not key_waiting():
                    return None
        return getkey()

    def ask(self, label, current=""):
        """One line of text at the bottom. Empty = cancel, '-' = clear."""
        _, h = self.size()
        hint = (" [%s]" % current) if current else ""
        sys.stdout.write("\x1b[%d;1H\x1b[K\x1b[?25h" % h)
        sys.stdout.flush()
        try:
            val = input(" %s%s%s%s: " % (ACC, label, R, DIM + hint + R)).strip()
        except (EOFError, KeyboardInterrupt):
            val = ""
        sys.stdout.write("\x1b[?25l")
        return val or None

    def confirm(self, text, yes, no):
        _, h = self.size()
        sys.stdout.write("\x1b[%d;1H\x1b[K %s%s%s  %sy %s · any other key %s%s " % (h, TEXT, text, R, DIM, yes, no, R))
        sys.stdout.flush()
        return getkey() in ("y", "Y")

    def pick(self, crumb, options, current=0):
        """Arrow-key list. Returns the chosen index or None."""
        i = max(0, min(current, len(options) - 1))
        while True:
            _, h = self.size()
            room = max(3, h - 8)
            top = max(0, min(i - room // 2, len(options) - room))
            lines = self.header(crumb)
            for j in range(top, min(len(options), top + room)):
                lines.append(self.row(j == i, options[j], "", lw=self.size()[0] - 8))
            lines += ["", self.rule(), self.help("↑↓ move · ↵ choose · esc back")]
            self.paint(lines)
            k = getkey()
            if k in ("up", "k"):
                i = (i - 1) % len(options)
            elif k in ("down", "j"):
                i = (i + 1) % len(options)
            elif k == "home":
                i = 0
            elif k == "end":
                i = len(options) - 1
            elif k == "enter":
                return i
            elif k in ("esc", "q", "left"):
                return None

    # ------------------------------------------------------------- main ---
    def run(self):
        sys.stdout.write("\x1b[?1049h")
        try:
            while True:
                cfg = load_config()
                names = list(cfg["profiles"])
                self.idx = max(0, min(self.idx, len(names) - 1))
                self.draw_main(cfg, names)
                k = self.key()
                if k is None:  # the Codex login check finished: draw again with its answer
                    continue
                name = names[self.idx]
                # the key can come hours later; what we save must start from reid.json as it is now
                cfg = load_config()
                if name not in cfg["profiles"]:
                    continue  # gone meanwhile: draw the list again
                if k in ("q", "esc"):
                    return 0
                elif k in ("up", "k"):
                    self.idx = (self.idx - 1) % len(names)
                elif k in ("down", "j"):
                    self.idx = (self.idx + 1) % len(names)
                elif k.isdigit() and k != "0" and int(k) <= len(names):
                    self.idx = int(k) - 1
                elif k == "enter":
                    if self.launch(cfg, name) == "quit":
                        return 0
                elif k == "r":
                    if self.resume(cfg, name) == "quit":
                        return 0
                elif k in ("e", "right"):
                    self.edit(cfg, name)
                elif k == "n":
                    self.new_profile(cfg, name)
                elif k == "x":
                    self.delete_profile(cfg, name)
                elif k == "d":
                    cfg["default"] = name
                    save_json(CONFIG, cfg)
                    self.msg = "Default is now %s." % name
                elif k == "w":
                    self.pick_dir()
                elif k == "m":
                    open_file(memory_path(cfg))
                    self.msg = "Memory open in your editor. The next session picks it up."
        except KeyboardInterrupt:
            return 0
        finally:
            sys.stdout.write(R + "\x1b[?25h\x1b[?1049l")
            sys.stdout.flush()

    def draw_main(self, cfg, names):
        """The GUI's one screen in text: banner, folder, profiles with the selected one's fields
        beside them, the command, then `folder → profile → open gate` and the ready dot."""
        w, h = self.size()
        name = names[self.idx]
        p = cfg["profiles"][name]
        error, preview, have = profile_check(cfg, name, self.cwd)

        top = [" " + TEXT + "Folder. Profile. Gate." + R,
               " " + DIM + fit("Pick a project and a profile. Your persona, memory and settings are already there.", w - 2) + R,
               ""]
        hint = "w pick folder"
        top.append(" %sfolder%s   %s%s%s" % (DIM, R, TEXT, fit(show_path(self.cwd), w - 12 - len(hint) - 3).ljust(w - 12 - len(hint) - 3), R)
                   + DIM + hint + R)
        last = load_state().get("last")
        if last:
            when = (last.get("at") or "")[11:16]
            where = "" if os.path.normcase(last.get("cwd", "")) == os.path.normcase(self.cwd) \
                else " · " + show_path(last.get("cwd", ""))
            top.append(" %slast%s     %s · %s%s   %sr resumes it%s" % (DIM, R, last.get("profile"), when, where, DIM, R))
        top += self.flash() or [""]
        top.append(self.rule())

        # right pane: the selected profile, the same rows as the GUI form
        persona = persona_name(p) if p.get("persona") else ""
        tags = (["PERSONA · " + persona.upper()] if persona else []) + (["MEMORY · ON"] if p.get("memory") else [])
        mcp = p.get("mcp")
        box = lambda on, label: ("☒ " if on else "☐ ") + label
        codex = is_codex(p)
        tool = "Codex" if codex else "Claude Code"
        if codex and not p.get("settings") and codex_login_cached() is None:
            self.check_login()
        sign_in = p.get("settings") or (codex_login_label() if codex else "subscription")
        rows = [("name", name),
                ("engine", str(p.get("engine") or "claude")),
                ("model", str(p.get("model") or ("engine default" if codex else "provider default"))),
                ("sign-in", sign_in),
                ("persona", p.get("persona") or "none"),
                ("persona mode", ("replace %s's prompt" % tool if p.get("mode") == "replace"
                                  else "add to %s's prompt" % tool) if persona else "needs a persona"),
                ("proxy", "+".join(proxy_list(p)) or "off"),
                ("tools", "all" if "tools" not in p else ", ".join(p["tools"] or []) or "none"),
                ("mcp", "your servers" if not mcp else ("none" if mcp == "none" else mcp)),
                ("switches", None),
                ("extra args", args_text(p.get("args")))]
        LW = 22                      # profile list width
        RW = max(20, w - LW - 5)     # right pane width
        if codex:  # same as the GUI: say why the greyed rows are greyed out
            tags = [CODEX_TAG] + tags
        greyed = {"proxy", "tools", "mcp"} if codex else set()
        right = [TEXT + B + name + R + "   " + DIM + " · ".join(tags) + R, ""]
        for k, v in rows:
            if k == "switches":  # memory works for both engines; the other three are Claude's
                parts = [(box(p.get("memory"), "memory"), False),
                         (box(not p.get("no_chrome"), "chrome"), codex),
                         (box(not p.get("no_connectors"), "connectors"), codex),
                         (box(p.get("safe"), "safe mode"), codex)]
                v = "  ".join((DIM if g else TEXT) + s + R for s, g in parts)
                right.append("%s%s%s%s" % (DIM, k.ljust(14), R, v))
                continue
            col = OXIDE if (k == "sign-in" and codex and v.endswith("not signed in")) else (DIM if k in greyed else TEXT)
            right.append("%s%s%s%s" % (DIM, k.ljust(14), R, col + fit(v, RW - 14) + R))
        right += ["", DIM + "command" + R]
        if error:  # wrap it: the way out is usually at the end ("…, or pick a Claude profile.")
            right += [OXIDE + line + R for line in wrap_text(error, RW)]
        else:
            right += [DIM + fit(preview, RW) + R]

        bottom = [self.rule(),
                  self.help("↵ open gate · r resume · e edit · n new · x delete · d default · m memory · q quit"),
                  self.help((CODEX_REPLACE_HINT if p.get("persona") and p.get("mode") == "replace"
                             else "codex: /quit comes back here · resume is Claude's") if codex
                            else "in a session: /reid comes back here"),
                  ""]
        status = "ready" + (" · " + " + ".join(have) if have else "") if not error else "not ready"
        flow = "folder → profile → open gate"
        gap = max(1, w - 2 - len(flow) - len(status) - 3)
        bottom.append(" " + DIM + flow + R + " " * gap + (OXIDE if error else EMERALD) + "●" + R + " " + TEXT2 + status + R)

        # the list scrolls if the window is short; the banner only shows when everything else fits
        body_h = max(len(right), min(len(names) + 1, h - 1 - len(top) - len(bottom)))
        body_h = max(3, min(body_h, h - 1 - len(top) - len(bottom)))
        banner = text_banner(w)
        if h - 1 - len(top) - len(bottom) - body_h >= len(banner) + 1:
            top = banner + [""] + top

        room = body_h - 1
        first = max(0, min(self.idx - room // 2, len(names) - room))
        left = [" " + DIM + "profiles" + R]
        for i in range(first, min(len(names), first + room)):
            n = names[i]
            default = n == cfg.get("default")  # the one emerald: the profile `open gate` uses by default
            label = fit(n, LW - 6) + (" ●" if default else "")
            if i == self.idx:
                cell = " " + SEL + (" → " + label).ljust(LW - 1) + R
            else:
                cell = "    " + TEXT2 + label + R + " " * (LW - 4 - len(label))
            if default:
                cell = cell.replace("●", EMERALD + "●" + (SEL if i == self.idx else R), 1)
            left.append(cell)
        if len(names) > room:
            left.append(" " + DIM + ("↑↓ %d more" % (len(names) - room)).ljust(LW - 1) + R)
        body = []
        for j in range(body_h):
            l = left[j] if j < len(left) else " " * LW
            r = right[j] if j < len(right) else ""
            body.append(l + " " + DIM + "│" + R + "  " + r)
        self.paint(top + body + bottom)

    def gate(self):
        """The gate opens, in text: the screen goes to the gate's dark ground, the art fades in, the
        keystone lights, the doors open and the view pushes through the passage into the dark, where
        the session starts. About 1.2 s; any key skips. Unlike the GUI, the session can't start
        behind it: it needs this same terminal."""
        w, h = self.size()
        art = tui_art("gate", w, h - 2)
        if not art or not _tty():
            return
        frames, meta = art["frames"], art["meta"]
        pace = 1.375  # same pace as the GUI's gate (Reid: 10% slower, then "25% slower for the gui" "and tui")
        plan = []   # (frame index, ms after start): the GUI's step times
        for _, count, start, dur in meta["steps"]:
            base = len(plan)
            plan += [(base + i, (start + dur * i / count) * pace) for i in range(count)]
        dark = len(frames) - 4  # the last frames go into the dark: no tag over them
        bg = "\x1b[48;2;%d;%d;%dm" % tuple(meta["bg"])
        rows = len(frames[0])
        y0, x0 = max(0, (h - rows - 1) // 2), (w - art["cols"]) // 2
        tag = "REIDCC · OPENING"
        sys.stdout.write("\x1b[?25l" + R + bg + "\x1b[2J")  # dim everything: the gate's own ground
        t0 = time.perf_counter()
        for n, (i, at) in enumerate(plan):
            while (time.perf_counter() - t0) * 1000 < at:
                if key_waiting():
                    getkey()  # the key only skips; it must not reach the session
                    sys.stdout.write(R + "\x1b[2J")
                    return
                time.sleep(0.004)
            if n + 1 < len(plan) and (time.perf_counter() - t0) * 1000 > plan[n + 1][1]:
                continue  # running late: drop this frame, stay on time
            out = "".join("\x1b[%d;%dH%s" % (y0 + r + 1, x0 + 1, line) for r, line in enumerate(frames[i]))
            if y0 + rows + 1 <= h:
                out += "\x1b[%d;%dH%s%s%s" % (y0 + rows + 1, x0 + art["cols"] - len(tag), bg + BRONZE,
                                              tag if i < dark else " " * len(tag), R)
            sys.stdout.write("\x1b[?2026h" + out + "\x1b[?2026l")  # synchronized output: shown whole, never torn
            sys.stdout.flush()
        time.sleep(0.12 * pace)
        sys.stdout.write(R + "\x1b[2J")

    def after_session(self, rc, back, sid, codex=False):
        if codex:  # Codex has no /reid: quitting it comes back here
            self.msg = "Back from Codex." if rc == 0 else "Codex ended with code %s. See the output above." % rc
            sys.stdout.write("\x1b[?1049h")
            return None
        if back:
            self.msg = "Back from the session. r resumes it."
            sys.stdout.write("\x1b[?1049h")
            return None
        if rc == 0:
            return "quit"  # a normal /exit means you're done
        self.msg = "Session ended with code %s. See the output above." % rc
        sys.stdout.write("\x1b[?1049h")
        return None

    def launch(self, cfg, name, resume=None):
        error = profile_check(cfg, name, self.cwd)[0]
        if error:  # say it here; no gate for a session that can't start
            self.msg = error
            return None
        self.gate()
        try:
            rc, back, sid, _ = run_session(cfg, name, self.cwd, resume=resume)
        except ReidError as e:
            sys.stdout.write("\x1b[?1049h")
            self.msg = str(e)
            return None
        return self.after_session(rc, back, sid, codex=is_codex(cfg["profiles"][name]))

    def resume(self, cfg, name):
        if str(cfg["profiles"][name].get("engine") or "claude") != "claude":
            self.msg = "Resume is for Claude profiles for now. ↵ opens a new Codex session."
            return None
        last = load_state().get("last")
        if not last:
            self.msg = "Nothing to resume yet."
            return None
        if last.get("cwd") and os.path.isdir(last["cwd"]):
            self.cwd = last["cwd"]  # claude finds sessions by folder
        return self.launch(cfg, name, resume=last.get("sid") or "-c")

    def pick_dir(self):
        recents = [d for d in load_state().get("recent_dirs", []) if os.path.isdir(d)]
        opts = [show_path(d) for d in recents] + ["type a path…"]
        i = self.pick("folder", opts)
        if i is None:
            return
        if i == len(recents):
            p = self.ask("folder", show_path(self.cwd))
            if not p:
                return
            p = os.path.abspath(os.path.expanduser(p.strip('"')))
            if not os.path.isdir(p):
                self.msg = "Can't find that folder. It may have moved."
                return
            self.cwd = p
        else:
            self.cwd = recents[i]

    def new_profile(self, cfg, src):
        name = self.ask("new profile (copies %s)" % src)
        if not name:
            return
        cfg = load_config()  # fresh after the typing
        if src not in cfg["profiles"]:
            return
        if name in cfg["profiles"]:
            self.msg = "A profile named %s already exists." % name
            return
        cfg["profiles"][name] = json.loads(json.dumps(cfg["profiles"][src]))
        save_json(CONFIG, cfg)
        self.idx = list(cfg["profiles"]).index(name)
        self.edit(cfg, name)

    def delete_profile(self, cfg, name):
        if len(cfg["profiles"]) == 1:
            self.msg = "Can't delete the last profile."
            return
        if not self.confirm("Delete profile %s?" % name, "delete", "keep"):
            return
        cfg = load_config()  # fresh after the question
        if name not in cfg["profiles"] or len(cfg["profiles"]) == 1:
            return
        del cfg["profiles"][name]
        if cfg.get("default") == name:
            cfg["default"] = next(iter(cfg["profiles"]))
        save_json(CONFIG, cfg)
        self.msg = "Deleted %s." % name

    # ------------------------------------------------------------- edit ---
    def edit(self, cfg, name):
        fields = ["engine", "model", "auth", "persona", "mode", "memory", "proxy", "tools", "mcp",
                  "chrome", "connectors", "safe", "args", "name"]
        labels = {"auth": "sign-in", "mode": "persona mode", "safe": "safe mode", "args": "extra args"}
        i = 0
        while True:
            p = cfg["profiles"][name]
            persona = p.get("persona")
            mcp = p.get("mcp")
            codex = is_codex(p)
            tool = "Codex" if codex else "Claude Code"
            if codex and not p.get("settings") and codex_login_cached() is None:
                self.check_login()
            vals = {
                "engine": str(p.get("engine") or "claude"),
                "model": str(p.get("model") or ("engine default" if codex else "provider default")),
                "auth": (("" if codex else "api · ") + p["settings"]) if p.get("settings")
                else (codex_login_label() if codex else "subscription"),
                "persona": persona or "none",
                "mode": (("replace %s's prompt" % tool if p.get("mode") == "replace"
                          else "add to %s's prompt" % tool) if persona else "needs a persona"),
                "memory": "on" if p.get("memory") else "off",
                "proxy": "+".join(proxy_list(p)) or "off",
                "tools": ("all" if "tools" not in p else ", ".join(p["tools"] or []) or "none"),
                "mcp": "your servers" if not mcp else ("none" if mcp == "none" else "only " + mcp),
                "chrome": "off" if p.get("no_chrome") else "on",
                "connectors": "off · claude.ai connectors" if p.get("no_connectors") else "on",
                "safe": "on · no CLAUDE.md, no MCP" if p.get("safe") else "off",
                "args": args_text(p.get("args")) or "none",
                "name": name,
            }
            lines = self.header("settings · " + name) + self.flash()
            claude_only = self.claude_only_fields(p) if codex else set()
            for j, f in enumerate(fields):
                line = self.row(j == i, labels.get(f, f), vals[f], lw=13)
                if f in claude_only and j != i:  # greyed like the main screen
                    line = DIM + re.sub(r"\x1b\[[0-9;]*m", "", line) + R
                lines.append(line)
            lines += ["", " %s%s%s" % (DIM, fit(summary(cfg, name), self.size()[0] - 2), R),
                      "", self.rule(),
                      self.help("↵ change · o open persona · m open memory · esc back")]
            self.paint(lines)
            k = self.key()
            if k is None:
                continue
            if k in ("esc", "q", "left"):
                return
            elif k in ("up", "k"):
                i = (i - 1) % len(fields)
            elif k in ("down", "j"):
                i = (i + 1) % len(fields)
            elif k == "o":
                if persona and os.path.exists(resolve(persona)):
                    open_file(resolve(persona))
                    self.msg = "Persona open in your editor. Every session reads it fresh."
                else:
                    self.msg = "This profile has no persona."
            elif k == "m":
                open_file(memory_path(cfg, p))
            elif k == "enter":
                if codex and fields[i] in self.claude_only_fields(p) and not self.field_on(p, fields[i]):
                    # one that's on stays changeable, so it can be turned off
                    self.msg = "%s is Claude's. Switch engine to change it." % labels.get(fields[i], fields[i])
                    continue
                new = self.change(cfg, name, fields[i]) or name
                cfg, name = self.commit(cfg, name, new), new

    @staticmethod
    def commit(cfg, old, new):
        """Save this screen's copy of one profile onto reid.json as it is on disk now, so edits
        made meanwhile in the GUI or another TUI stay. `new` differs after a rename. Returns the
        fresh config."""
        fresh = load_config()
        fresh["profiles"] = {(new if k == old else k): q for k, q in fresh["profiles"].items()}
        fresh["profiles"][new] = cfg["profiles"][new]
        if fresh.get("default") == old:
            fresh["default"] = new
        save_json(CONFIG, fresh)
        return fresh

    @staticmethod
    def claude_only_fields(p):
        return {"proxy", "tools", "mcp", "chrome", "connectors", "safe"}

    @staticmethod
    def field_on(p, field):
        """Is this Claude-only field set to something a Codex launch would refuse?"""
        return {"proxy": bool(proxy_list(p)), "tools": "tools" in p, "mcp": bool(p.get("mcp")),
                "chrome": bool(p.get("no_chrome")), "connectors": bool(p.get("no_connectors")),
                "safe": bool(p.get("safe"))}.get(field, False)

    def change(self, cfg, name, field):
        p = cfg["profiles"][name]

        def setk(key, val):
            if val in (None, "", [], False):
                p.pop(key, None)
            else:
                p[key] = val

        engine = str(p.get("engine") or "claude")
        if field == "engine":
            i = self.pick("settings · %s · engine" % name, list(ENGINES),
                          ENGINES.index(engine) if engine in ENGINES else 0)
            if i is None or ENGINES[i] == engine:
                return
            setk("engine", None if ENGINES[i] == "claude" else ENGINES[i])
            # a model and a sign-in file belong to one engine; start from the new engine's defaults
            setk("model", None)
            setk("settings", None)
            on = claude_only_on(p) if ENGINES[i] == "codex" else []
            self.msg = ("Engine is now %s. Model and sign-in reset to its defaults." % ENGINES[i]
                        + (" Codex can't use %s: turn it off to open the gate." % ", ".join(on) if on else ""))

        elif field == "model":
            # each engine lists its own models: Claude's names, or the ones other Codex profiles use
            same = [q.get("model") for q in cfg["profiles"].values()
                    if q.get("model") and str(q.get("engine") or "claude") == engine]
            if engine == "claude":
                opts = BASE_MODELS + sorted(set(same) - set(BASE_MODELS)) + ["provider default", "type a model id…"]
            else:
                opts = sorted(set(same) - set(BASE_MODELS)) + ["engine default", "type a model id…"]
            cur = opts.index(p["model"]) if p.get("model") in opts else 0
            i = self.pick("settings · %s · model" % name, opts, cur)
            if i is None:
                return
            if opts[i] in ("provider default", "engine default"):
                setk("model", None)
            elif opts[i] == "type a model id…":
                v = self.ask("model id", p.get("model", ""))
                if v:
                    setk("model", v)
            else:
                setk("model", opts[i])

        elif field == "auth":
            codex = engine == "codex"
            files = signin_files(codex)
            opts = [codex_login_label() if codex else "subscription"] + files + ["type a path…"]
            cur = opts.index(p["settings"]) if p.get("settings") in opts else 0
            crumb = ("sign-in (codex login is your terminal's; a .toml file sets another provider)" if codex
                     else "sign-in (a settings file means API mode)")
            i = self.pick("settings · %s · %s" % (name, crumb), opts, cur)
            if i is None:
                return
            if i == 0:
                setk("settings", None)
            elif i == len(opts) - 1:
                v = self.ask("provider .toml path" if codex else "settings.json path")
                if v and os.path.exists(v.strip('"')):
                    setk("settings", relpath(v.strip('"')))
                elif v:
                    self.msg = "Can't find %s. Check the path." % v
            else:
                setk("settings", opts[i])

        elif field == "persona":
            files = sorted(glob.glob(os.path.join(HOME, "personas", "*.md"))) + \
                sorted(glob.glob(os.path.join(PROXY_DIR, "*-system.md"))) + \
                sorted(glob.glob(os.path.join(HOME, "mds", "*.md")))
            opts = ["none"] + [relpath(f) for f in files] + ["type a path…"]
            cur = opts.index(p["persona"]) if p.get("persona") in opts else 0
            i = self.pick("settings · %s · persona" % name, opts, cur)
            if i is None:
                return
            if i == 0:
                setk("persona", None)
                setk("mode", None)
            elif i == len(opts) - 1:
                v = self.ask("persona file path")
                if v and os.path.exists(v.strip('"')):
                    setk("persona", relpath(v.strip('"')))
                elif v:
                    self.msg = "Can't find %s. Check the path." % v
            else:
                setk("persona", opts[i])

        elif field == "mode":
            if not p.get("persona"):
                self.msg = "Pick a persona first. Persona mode only applies to it."
                return
            p["mode"] = "append" if p.get("mode") == "replace" else "replace"
            tool = "Codex" if engine == "codex" else "Claude Code"
            self.msg = (("The persona now replaces %s's prompt, including its tool guidance. "
                         "Add is the safe one." % tool)
                        if p["mode"] == "replace" else "The persona now adds to %s's prompt." % tool)

        elif field in ("memory", "safe"):
            setk(field, not p.get(field))

        elif field in ("chrome", "connectors"):
            key = "no_" + field
            setk(key, not p.get(key))

        elif field == "proxy":
            opts = ["off"] + PROXY_CHOICES
            cur = "+".join(proxy_list(p)) or "off"
            i = self.pick("settings · %s · proxy (slim and ultra rewrite requests, unsupported)" % name,
                          opts, opts.index(cur) if cur in opts else 0)
            if i is not None:
                setk("proxy", None if i == 0 else opts[i])

        elif field == "tools":
            presets = [("all", None), ("core · " + " ".join(CORE_TOOLS), CORE_TOOLS),
                       ("core + web", CORE_TOOLS + WEB_TOOLS), ("web only", WEB_TOOLS),
                       ("none · plain chat", [])]
            opts = [o for o, _ in presets] + ["type a list…"]
            cur = next((j for j, (_, v) in enumerate(presets) if v == p.get("tools", None)), 0)
            i = self.pick("settings · %s · tools" % name, opts, cur)
            if i is None:
                return
            if i < len(presets):
                if presets[i][1] is None:
                    p.pop("tools", None)
                else:
                    p["tools"] = list(presets[i][1])  # [] is meaningful: no tools
            else:
                v = self.ask("tools, comma separated", ",".join(p.get("tools") or []))
                if v:
                    p["tools"] = [t.strip() for t in v.split(",") if t.strip()]

        elif field == "mcp":
            files = sorted(glob.glob(os.path.join(PROXY_DIR, "*mcp*.json")))
            opts = ["your servers", "none"] + [relpath(f) for f in files] + ["type a path…"]
            cur = opts.index(p["mcp"]) if p.get("mcp") in opts else 0
            i = self.pick("settings · %s · mcp" % name, opts, cur)
            if i is None:
                return
            if i == 0:
                setk("mcp", None)
            elif i == len(opts) - 1:
                v = self.ask("MCP config path")
                if v and os.path.exists(v.strip('"')):
                    setk("mcp", relpath(v.strip('"')))
                elif v:
                    self.msg = "Can't find %s. Check the path." % v
            else:
                setk("mcp", opts[i])

        elif field == "args":
            v = self.ask("extra args (− or - clears)", args_text(p.get("args")))
            if v in ("-", "−"):
                setk("args", None)
            elif v:
                setk("args", args_parse(v))

        elif field == "name":
            v = self.ask("rename to", name)
            if not v or v == name:
                return
            if v in cfg["profiles"]:
                self.msg = "A profile named %s already exists." % v
                return
            cfg["profiles"] = {(v if k == name else k): q for k, q in cfg["profiles"].items()}
            if cfg.get("default") == name:
                cfg["default"] = v
            return v


# ================================================================== main ===
def launched_from_terminal():
    """True when a shell started us (tool mode), False for double-click/shortcut/pythonw (app mode)."""
    if sys.stdin is None or sys.stdout is None:  # pythonw: no console at all
        return False
    if IS_WIN:
        try:
            import ctypes
            procs = (ctypes.c_uint32 * 16)()
            # A console we share with a shell lists 2+ processes; one Windows made
            # just for us (double-clicked reid.py) lists only us.
            return ctypes.windll.kernel32.GetConsoleProcessList(procs, 16) > 1
        except Exception:
            pass
    try:
        return sys.stdin.isatty()
    except Exception:
        return False


def open_gui(from_terminal):
    """Run the GUI. From a terminal, detach it (Reidcc.exe / pythonw) so the shell gets its prompt back."""
    if from_terminal and IS_WIN:
        gui = gui_command()
        if os.path.exists(gui[0]) and gui[0] != sys.executable:
            subprocess.Popen(gui + ["--gui", "--cwd", os.getcwd()],
                             creationflags=0x00000008 | 0x00000200,  # DETACHED | NEW_GROUP
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True)
            print("Reidcc window opened.")
            return 0
    if IS_WIN and sys.stdout is not None and not from_terminal:
        try:  # double-clicked with python.exe: drop the console Windows made for us
            import ctypes
            ctypes.windll.kernel32.FreeConsole()
        except Exception:
            pass
    cwd = None
    if "--cwd" in sys.argv:
        i = sys.argv.index("--cwd")
        cwd = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    import reid_gui
    return reid_gui.run(sys.modules[__name__], cwd)


def main(args):
    refresh_path()  # before anything looks for claude, wt, git...
    enable_vt()
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        if args and args[0] == "--statusline":
            return cmd_statusline()
        if FROZEN and sys.stdout is None:
            # Reidcc.exe (windowed build) is always the app; terminal work goes to reidcc.com.
            return open_gui(from_terminal=False)
        if args and args[0] == "--tui":
            return TUI(os.getcwd()).run()
        if args and args[0] == "--gui":
            return open_gui(from_terminal=launched_from_terminal())
        if not args:
            # No args: typed in a terminal -> tool (TUI); double-clicked / shortcut -> app (GUI).
            if launched_from_terminal():
                return TUI(os.getcwd()).run()
            return open_gui(from_terminal=False)
        a0 = args[0]
        if a0 == "--resume":
            # reid --resume [profile]: continue the last session (the GUI's Resume button uses this)
            cfg = load_config()
            last = load_state().get("last") or {}
            name = args[1] if len(args) > 1 and args[1] in cfg["profiles"] else last.get("profile") or cfg["default"]
            cwd = last.get("cwd") if last.get("cwd") and os.path.isdir(last["cwd"]) else os.getcwd()
            rc, back, _sid, _ = run_session(cfg, name, cwd, resume=last.get("sid") or "-c")
            if back:
                return TUI(cwd, "Back from the session. r resumes it.").run()
            return rc
        if a0 in ("-h", "--help"):
            print(__doc__.strip())
            return 0
        if a0 == "--back":
            return cmd_back()
        cfg = load_config()
        if a0 in ("-l", "--list"):
            for n in cfg["profiles"]:
                print("%s %-14s %s" % ("*" if n == cfg["default"] else " ", n, summary(cfg, n)))
            return 0
        if a0 == "--edit":
            open_file(CONFIG)
            return 0
        if a0 == "--mem":
            open_file(memory_path(cfg))
            return 0
        dry = a0 == "--dry"
        if dry:
            args = args[1:]
        if args and args[0] in cfg["profiles"]:
            name, extra = args[0], args[1:]
        else:
            name, extra = cfg["default"], args
        if dry:
            argv, env, temps = build(cfg, name, extra, os.getcwd())
            print("profile: %s  (%s)" % (name, summary(cfg, name)))
            plan = proxy_plan(cfg["profiles"][name])
            if plan:
                print("proxy:   %s -s %s on a free port%s" % (
                    mitmdump_path() or "mitmdump (not set up)",
                    " -s ".join(relpath(s) for s in plan[0]),
                    "  [%s]" % " ".join("%s=%s" % kv for kv in plan[1].items()) if plan[1] else ""))
            for k in ("ENABLE_CLAUDEAI_MCP_SERVERS", "CLAUDE_CODE_DISABLE_CLAUDE_MDS"):
                if env.get(k) and env.get(k) != os.environ.get(k):
                    print("env:     %s=%s" % (k, env[k]))
            print(subprocess.list2cmdline(argv))
            if is_codex(cfg["profiles"][name]) and os.path.exists(codex_prompt_path(name)) and \
                    any("model_instructions_file=" in a for a in argv):
                print("  prompt file: %s, %d chars" % (show_path(codex_prompt_path(name)),
                                                      os.path.getsize(codex_prompt_path(name))))
            for t in temps:
                kind = "settings file" if "reid_settings_" in t else "prompt file"
                print("  %s: %d chars" % (kind, os.path.getsize(t)))
                os.remove(t)
            return 0
        rc, back, sid, _ = run_session(cfg, name, os.getcwd(), extra)
        if is_codex(cfg["profiles"][name]) and not extra and _tty():  # no /reid in Codex: quitting it comes back
            return TUI(os.getcwd(), "Back from Codex." if rc == 0
                       else "Codex ended with code %s. See the output above." % rc).run()
        if back:
            return TUI(os.getcwd(), "Back from the session. r resumes it.").run()
        return rc
    except ReidError as e:
        print(e, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
