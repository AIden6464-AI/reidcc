"""
mitmproxy addon: replace Claude Code's long built-in tool descriptions with short
ones, in flight. Tool names, parameter names, types, required fields and every
other key are kept exactly, so Claude Code still executes its own native tools.

Only tools listed in SLIM are touched; everything else (Agent, Skill, ToolSearch,
MCP tools, tools added by future Claude Code versions) passes through unchanged.
The rewrite is deterministic, so the slimmed prefix caches normally.

Optional: SLIM_DROP=ScheduleWakeup,ReportFindings removes whole tools.
Optional: SLIM_LEVEL=ultra applies ULTRA on top of SLIM: terser docs for the core
tools, plus short docs for Agent, ScheduleWakeup, Skill, ToolSearch and friends.
Artifact, MCP tools and anything else not listed are still passed through.

Run (add -s capture_addon.py after it to save what's actually sent):
    mitmdump -s slim_tools_addon.py --listen-port 8080
"""
import copy
import json
import logging
import os

from mitmproxy import http

logger = logging.getLogger(__name__)

BG = "Run detached; you're notified when it exits."

# tool name -> short description + short replacements for long parameter docs
SLIM = {
    "Read": {
        "description": "Read a file by absolute path. Output lines are prefixed 'N<tab>' (not file content). "
                       "Also reads images and PDFs.",
        "params": {"offset": "Start line, for large files.", "limit": "Max lines, for large files.",
                   "pages": "PDF page range, e.g. 1-5 (max 20).",
                   "allow_large": "Read past the size limit; only if you need the whole file."},
    },
    "Edit": {
        "description": "Replace exact old_string with new_string in a file. Read the file first. "
                       "old_string must be unique unless replace_all.",
        "params": {},
    },
    "Write": {
        "description": "Create or overwrite a file. Read existing files first; prefer Edit for changes.",
        "params": {},
    },
    "Glob": {
        "description": "Find files by glob pattern; newest first.",
        "params": {"path": "Directory to search; omit for cwd."},
    },
    "Grep": {
        "description": "ripgrep content search.",
        "params": {
            "output_mode": "files_with_matches (default), content, or count.",
            "-A": "Lines after match (content mode).", "-B": "Lines before match (content mode).",
            "context": "Lines around match (content mode).", "-n": "Line numbers (content mode, default on).",
            "-o": "Only matched parts.", "type": "rg --type, e.g. py.",
            "head_limit": "Max lines/entries returned.", "offset": "Skip first N lines/entries.",
            "multiline": "Patterns can span lines (rg -U).",
        },
    },
    "Bash": {
        "description": "Run a bash command (Git Bash on Windows). Prefer Read/Edit/Grep/Glob for files. "
                       "Ask before destructive or outward-facing commands (rm -rf, git push, deploys).",
        "params": {"description": "Short active-voice description of what the command does.",
                   "run_in_background": BG},
    },
    "PowerShell": {
        "description": "Run a Windows PowerShell 5.1 command. 5.1 lacks && || ?: ?? ?. (use ; and if/else). "
                       "Avoid 2>&1 on native exes. No interactive prompts (Read-Host etc.). "
                       "Ask before destructive or outward-facing commands.",
        "params": {"run_in_background": BG},
    },
}


# SLIM_LEVEL=ultra: entries here replace/extend SLIM. Keep the behavioral rules
# (when to call, what not to do); drop examples and rationale.
ULTRA = {
    "Read": {
        "description": "Read a file (absolute path). Lines prefixed 'N<tab>'. Images/PDFs too.",
        "params": {"offset": "Start line.", "limit": "Max lines.", "pages": "PDF pages, e.g. 1-5 (max 20).",
                   "allow_large": "Bypass the size limit."},
    },
    "Edit": {
        "description": "Exact string replace. Read first; old_string must be unique unless replace_all.",
        "params": {},
    },
    "Write": {"description": "Create/overwrite a file. Read existing files first.", "params": {}},
    "Glob": {"description": "Glob file search, newest first.", "params": {"path": "Default: cwd."}},
    "Grep": {
        "description": "ripgrep search.",
        "params": {**SLIM["Grep"]["params"], "path": "File/dir; default cwd.", "glob": "File filter, e.g. *.py."},
    },
    "Bash": {
        "description": "Run bash (Git Bash on Windows). Prefer the file tools for files. "
                       "Ask before destructive or outward-facing commands.",
        "params": {"description": "What it does, 5-10 words.", "run_in_background": "Run detached; notified on exit."},
    },
    "PowerShell": {
        "description": "Run Windows PowerShell 5.1: no && || ?: ?? ?. (use ; and if). Avoid 2>&1 on native exes. "
                       "No interactive prompts. Ask before destructive or outward-facing commands.",
        "params": {"run_in_background": "Run detached; notified on exit."},
    },
    "Agent": {
        "description": "Launch a subagent. Only when the user asks for one or names an agent type "
                       "(types are listed in system-reminders). subagent_type \"fork\" inherits your context; "
                       "others start cold. Agents notify you when done; relay what matters, since their report "
                       "isn't shown to the user. Never fabricate a pending agent's result. "
                       "Continue an agent with SendMessage.",
        "params": {"model": "Model override; usually omit.",
                   "effort": "Only if the user or instructions ask for a specific effort.",
                   "run_in_background": "false only if your next step needs the result.",
                   "isolation": "\"worktree\": work on an isolated git worktree copy."},
    },
    "ScheduleWakeup": {
        "description": "/loop dynamic mode only: schedule the next iteration. Don't poll harness-tracked "
                       "background work (you're re-invoked when it finishes); use a 1200s+ fallback instead. "
                       "For external state (CI, deploys) match the delay to how fast it changes. "
                       "Idle default 1200-1800s. stop:true ends the loop.",
        "params": {"delaySeconds": "60-3600. Required unless stop.",
                   "reason": "One specific sentence on why this delay; shown to the user.",
                   "prompt": "The /loop input verbatim, or '<<autonomous-loop-dynamic>>' for autonomous loops.",
                   "stop": "End the loop; omit other fields.",
                   "noop": "true if nothing changed this tick, false if you did or found something."},
    },
    "ReportFindings": {
        "description": "Report code-review findings, only when code-review instructions say to. "
                       "Call once, most severe first (empty if none); don't also print them. "
                       "Set outcome only when re-reporting after fixes.",
        "params": {},
    },
    "Skill": {
        "description": "Invoke a skill from the system-reminder listing, or one the user typed as /name. "
                       "When a listed skill covers the task, call it first and follow its instructions. "
                       "A background skill returns an agent name; its result arrives later, don't re-invoke. "
                       "Plugin skills: plugin:skill. Built-in CLI commands aren't skills. If a <command-name> "
                       "block is already present this turn, the skill is loaded.",
        "params": {},
    },
    "ToolSearch": {
        "description": "Load schemas for deferred tools (named in system-reminders) so they can be called. "
                       "Query \"select:A,B\" for exact names, keywords to search, \"+word rest\" to require "
                       "word in the name. Load everything you need in one call.",
        "params": {},
    },
    "ListAgents": {
        "description": "List agents and sessions you can SendMessage to. Send with "
                       "SendMessage({to: \"<name>\"}) using the name exactly; add the row's [ref] only if "
                       "names collide.",
        "params": {},
    },
    "AskUserQuestion": {
        "description": "Ask 1-4 multiple-choice questions, only for a blocking decision that is the user's to "
                       "make. Put a recommended option first with \" (Recommended)\". \"Other\" is added "
                       "automatically. Each question must stand alone. Not for asking if a plan is ready "
                       "(use ExitPlanMode).",
        "params": {},
    },
    "SendFeedback": {
        "description": "Queue a local feedback draft about Claude Code (never sent without user approval; no UI; "
                       "don't announce it). Only at high-signal moments: a tool failure resolved or abandoned, "
                       "user frustration, a missing capability, or your own behavior went wrong. One per issue. "
                       "details: labeled bullets in order What happened / What the user said (exact quote, or "
                       "\"User didn't comment; observed by the model.\") / Repro / Evidence. Facts only; no "
                       "secrets, no names or emails (use roles), no exploit steps.",
        "params": {},
    },
}

LEVELS = {"slim": SLIM, "ultra": {**SLIM, **ULTRA}}


def _drop_list():
    return {x.strip() for x in os.environ.get("SLIM_DROP", "").split(",") if x.strip()}


def _spec():
    return LEVELS.get(os.environ.get("SLIM_LEVEL", "slim").strip().lower(), SLIM)


def slim_tools(tools, drop=frozenset(), spec=None):
    spec_map = SLIM if spec is None else spec
    out = []
    for tool in tools:
        if not isinstance(tool, dict):
            out.append(tool)
            continue
        name = tool.get("name")
        if name in drop:
            continue
        spec = spec_map.get(name)
        if not spec or not isinstance(tool.get("input_schema"), dict):
            out.append(tool)
            continue
        tool = copy.deepcopy(tool)
        tool["description"] = spec["description"]
        props = tool["input_schema"].get("properties") or {}
        for param, doc in spec["params"].items():
            if isinstance(props.get(param), dict):
                props[param]["description"] = doc
        out.append(tool)
    return out


def _is_messages_call(flow: http.HTTPFlow) -> bool:
    req = flow.request
    return (req.method == "POST"
            and req.pretty_host == "api.anthropic.com"
            and req.path.split("?")[0] == "/v1/messages")


def request(flow: http.HTTPFlow) -> None:
    if not _is_messages_call(flow):
        return
    try:
        payload = json.loads(flow.request.get_text() or "")
    except (ValueError, UnicodeDecodeError):
        return
    if not isinstance(payload, dict) or not isinstance(payload.get("tools"), list):
        return
    before = len(json.dumps(payload["tools"], ensure_ascii=False))
    payload["tools"] = slim_tools(payload["tools"], _drop_list(), _spec())
    after = len(json.dumps(payload["tools"], ensure_ascii=False))
    flow.request.set_text(json.dumps(payload, ensure_ascii=False))
    logger.warning("slimmed tools: %d -> %d chars", before, after)
