"""
mitmproxy addon: shorten Codex's long built-in tool docs in flight (SPEC-codex-proxy.md).

Codex sends its tools once per session, in the "additional_tools" input item of the first real
response.create (a WebSocket message on chatgpt.com/backend-api/codex/responses, or a JSON POST
/ api.openai.com/v1/responses). Follow-up requests carry only deltas, so nothing else is touched.

Two kinds of tool docs are shortened:
  - top-level function tools (functions.wait, ...): description and parameter docs replaced,
    like slim_tools_addon.py does for Claude Code. Names, schemas and every other key stay.
  - nested tools inside functions.exec: its description is one long doc with a "### `name`"
    section per nested tool. Only the prose of listed sections is replaced; every
    "exec tool declaration:" block (the TypeScript signatures Codex parses calls against)
    is kept byte for byte, and unlisted sections pass through unchanged.

Anything not listed (MCP namespaces, tools a future Codex adds) passes through unchanged.
The rewrite is deterministic, so the prompt cache hits from a thread's second turn. A fresh thread starts
cold: additional_tools is input item 0, so plain Codex's prefix (warm from every other Codex request on the
account) never matches. Measured on 0.172.0: 0 cached on turn 1, 17.5k-30.5k on turn 2 (site/docs/proxy.md).

Optional: SLIM_LEVEL=ultra adds terser docs for more tools.
Optional: SLIM_DROP=mcp__cua_repl,collaboration.spawn_agent removes whole namespaces or tools
          (a tool as namespace.name).

Run (add -s codex_capture_addon.py after it to save what's actually sent):
    mitmdump -s codex_slim_addon.py --listen-port 8080
"""
import copy
import json
import logging
import os
import re

from mitmproxy import http

logger = logging.getLogger(__name__)

HOSTS_PATHS = {("chatgpt.com", "/backend-api/codex/responses"), ("api.openai.com", "/v1/responses")}
DECL = "exec tool declaration:"
SECTION_RX = re.compile(r"^### `([^`]+)`[^\n]*\n", re.M)

# Top-level tools, "namespace.name" -> short description + parameter docs.
SLIM_TOOLS = {
    "functions.wait": {
        "description": "Wait on a yielded `exec` cell (only after exec returns `Script running with cell ID ...`). "
                       "Returns new output since the last yield, or the final result (which closes the cell).",
        "params": {},
    },
    "functions.request_user_input_async": {
        "description": "Ask the user questions during work, only for missing info, preferences, constraints or "
                       "approval. Returns at once; any reply arrives later as a user message. Keep questions short "
                       "and self-contained; free-text answers are always allowed.",
        "params": {},
    },
    "functions.send_message_to_user_async": {
        "description": "Send a short message that needs the user's attention now (a critical blocker, a "
                       "direction-changing finding, or an answer to a question asked mid-work). Returns at once. "
                       "Use commentary for routine progress.",
        "params": {},
    },
}

# Nested tools inside exec: section name -> replacement prose (the declaration block stays).
SLIM_EXEC = {
    "create_goal": "Create a goal only when the user or instructions explicitly ask; never infer one. Set "
                   "token_budget only if a budget is requested. Fails if an unfinished goal exists.",
    "update_goal": "Update the goal's status. `paused` only on the user's explicit request. `complete` only when "
                   "the objective is achieved and no required work remains (not because the budget is nearly "
                   "spent). `blocked` only after the same blocker repeats for 3 consecutive goal turns with no way "
                   "forward; a resumed blocked goal starts a fresh count. Can't resume or budget-limit a goal. "
                   "When completing a budgeted goal, report its final token usage.",
    "request_plugin_install": "Suggest installing a plugin only when the user explicitly asks for a specific plugin "
                              "that isn't available, tool search found nothing, and it is in "
                              "`<recommended_plugins>`. Never for adjacent or merely useful plugins. Give a one-line "
                              "`suggest_reason`. Never call it in parallel with other tools.",
    "list_mcp_resource_templates": "List MCP resource templates (parameterized resources). Prefer them over web "
                                   "search when they fit.",
    "list_mcp_resources": "List MCP resources (files, schemas, app data). Prefer them over web search when they fit.",
    "image_gen__imagegen": "Generate a new image or edit one. It takes minutes: start the exec with "
                           "`// @exec: {\"yield_time_ms\": 120000}` and use the same yield for waits; return it with "
                           "generatedImage(result), never print its base64. transparent_background true only when "
                           "asked (cutouts, background removal); keep existing transparency on edits. New image: omit "
                           "both image inputs. Edits: referenced_image_paths when every target has a local path "
                           "(view_image it first if unseen), else num_last_images_to_include (smallest count that "
                           "covers the targets, max 5); never both. Don't reconfirm; use this, not python, for edits.",
    "web__run": "Internet access: search_query (max 4 per call; >3 needs response_length medium/long), image_query, "
                "open, click, find, screenshot (PDF pages), finance, weather, sports, time. Batch several commands "
                "in one call; write only required params.\n"
                "Browse when the user asks to, or when facts may have changed (news, prices, laws, schedules, "
                "versions, people in roles), for costly recommendations, for quotes/links, for a referenced page "
                "you haven't read, when unsure or the topic is niche, and for medical/legal/financial accuracy. "
                "Obey an explicit request not to browse. For OpenAI products check local code first, then only "
                "official OpenAI domains. Technical answers: primary sources only; mark inferences.\n"
                "Never show internal ref ids (turn2search5) in the answer. Cite as Markdown links "
                "`[title](url)` to the supporting page, near the claim, not in code fences, not on their own line, "
                "not collected at the end.\n"
                "Quotes: at most 25 words verbatim per source (lyrics 10); reddit may be quoted longer as a "
                "linked blockquote. Respect each source's [wordlim N] (default 200 words); no full articles.",
}

ULTRA_TOOLS = {
    "functions.request_user_input": {
        "description": "Plan mode only: ask 1-3 short questions and wait for the answers.",
        "params": {},
    },
    "clock.sleep": {"description": "Sleep for duration_ms; ends early on new input. Returns elapsed time.", "params": {}},
    "collaboration.followup_task": {
        "description": "Send a follow-up task to an existing non-root agent; starts a turn if it is idle.",
        "params": {},
    },
    "collaboration.wait_agent": {
        "description": "Wait for any live agent's mailbox update (messages, final status) or new user input. "
                       "Returns a summary of who has updates, not the content.",
        "params": {},
    },
}

ULTRA_EXEC = {
    "exec_command": "Run a command in a PTY; returns output, or a session_id for a running process (use "
                    "write_stdin). Windows: use one shell end to end for deletes/moves (PowerShell cmdlets with "
                    "-LiteralPath, no string-built commands, never pipe paths into cmd /c); check resolved targets "
                    "stay in the workspace before any recursive delete or move; Start-Process background helpers "
                    "with -WindowStyle Hidden.",
    "write_stdin": "Write to a running exec_command session and return recent output; empty chars polls.",
    "read_mcp_resource": "Read one MCP resource by server name and a URI from list_mcp_resources.",
    "view_image": "View a local image file.",
}

LEVELS = {"slim": (SLIM_TOOLS, SLIM_EXEC), "ultra": ({**SLIM_TOOLS, **ULTRA_TOOLS}, {**SLIM_EXEC, **ULTRA_EXEC})}


def _drop_list():
    return {x.strip() for x in os.environ.get("SLIM_DROP", "").split(",") if x.strip()}


def _level():
    return LEVELS.get(os.environ.get("SLIM_LEVEL", "slim").strip().lower(), LEVELS["slim"])


def slim_exec_doc(doc: str, exec_spec: dict) -> str:
    """Replace the prose of listed "### `name`" sections; keep each declaration block and the rest."""
    marks = list(SECTION_RX.finditer(doc))
    if not marks:
        return doc
    out = [doc[:marks[0].start()]]
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(doc)
        section = doc[m.start():end]
        short = exec_spec.get(m.group(1))
        decl = section.find(DECL)
        if short is None or decl < 0:
            out.append(section)
            continue
        out.append(m.group(0) + short + "\n\n" + section[decl:])
    return "".join(out)


def slim_tools_item(item: dict, drop=frozenset(), level=None) -> dict:
    tools_spec, exec_spec = level or LEVELS["slim"]
    item = copy.deepcopy(item)
    namespaces = []
    for ns in item.get("tools") or []:
        if not isinstance(ns, dict) or not isinstance(ns.get("tools"), list):
            namespaces.append(ns)
            continue
        nsname = ns.get("name")
        if nsname in drop:
            continue
        kept = []
        for t in ns["tools"]:
            if not isinstance(t, dict):
                kept.append(t)
                continue
            full = f"{nsname}.{t.get('name')}"
            if full in drop:
                continue
            if full == "functions.exec" and isinstance(t.get("description"), str):
                t["description"] = slim_exec_doc(t["description"], exec_spec)
            spec = tools_spec.get(full)
            if spec and isinstance(t.get("parameters"), dict):
                t["description"] = spec["description"]
                props = t["parameters"].get("properties") or {}
                for p, d in spec["params"].items():
                    if isinstance(props.get(p), dict):
                        props[p]["description"] = d
            kept.append(t)
        ns["tools"] = kept
        namespaces.append(ns)
    item["tools"] = namespaces
    return item


def rewrite(payload, drop=None, level=None):
    """The payload with its additional_tools item slimmed, or None if there's nothing to change."""
    if not isinstance(payload, dict) or payload.get("type", "response.create") != "response.create":
        return None
    items = payload.get("input")
    if not isinstance(items, list):
        return None
    idx = next((i for i, it in enumerate(items) if isinstance(it, dict) and it.get("type") == "additional_tools"), None)
    if idx is None:
        return None
    new_item = slim_tools_item(items[idx], _drop_list() if drop is None else drop, level or _level())
    if new_item == items[idx]:
        return None
    payload = dict(payload)
    payload["input"] = items[:idx] + [new_item] + items[idx + 1:]
    return payload


def _size(payload):
    it = next(i for i in payload["input"] if isinstance(i, dict) and i.get("type") == "additional_tools")
    return len(json.dumps(it, ensure_ascii=False))


def _is_model_endpoint(flow: http.HTTPFlow) -> bool:
    return (flow.request.pretty_host, flow.request.path.split("?")[0]) in HOSTS_PATHS


def websocket_message(flow: http.HTTPFlow) -> None:
    if not _is_model_endpoint(flow) or flow.websocket is None:
        return
    msg = flow.websocket.messages[-1]
    if not msg.from_client or not msg.is_text:
        return
    try:
        payload = json.loads(msg.text)
    except ValueError:
        return
    new = rewrite(payload)
    if new is None:
        return
    msg.text = json.dumps(new, ensure_ascii=False, separators=(",", ":"))
    logger.warning("slimmed codex tools: %d -> %d chars", _size(payload), _size(new))


def request(flow: http.HTTPFlow) -> None:
    if flow.request.method != "POST" or not _is_model_endpoint(flow):
        return
    try:
        payload = json.loads(flow.request.get_text() or "")
    except (ValueError, UnicodeDecodeError):
        return
    new = rewrite(payload)
    if new is None:
        return
    flow.request.set_text(json.dumps(new, ensure_ascii=False, separators=(",", ":")))
    logger.warning("slimmed codex tools: %d -> %d chars", _size(payload), _size(new))
