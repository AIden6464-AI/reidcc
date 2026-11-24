"""
mitmproxy addon: READ-ONLY capture of the prompt setup Codex sends (SPEC-codex-proxy.md).
Traffic is not modified.

Codex's model call is a WebSocket (chatgpt.com/backend-api/codex/responses, or
api.openai.com/v1/responses with an API key); each request is one client message
{"type": "response.create", "input": [...]}. Only the first real request of a session
carries the setup (an "additional_tools" input item); follow-ups send deltas.

For each distinct setup, saves to ./codex_prompts/<time>_<model>_<hash>/:
    instructions.txt  developer messages in order, verbatim (Codex's prompt or the persona,
                      permissions, mode blocks)
    tools.json        the additional_tools item, verbatim
    context.txt       the user messages Codex injected (<environment_context>, AGENTS.md)
    messages.json     the whole input verbatim, including what you typed (local file only)
    summary.md        size per part, and input tokens from response.completed when seen

Never saved: headers (auth tokens), server messages other than the usage numbers.

Run:
    mitmdump -s codex_capture_addon.py --listen-port 8080 -q
"""
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path

from mitmproxy import http

OUT_DIR = Path("codex_prompts")
HOSTS_PATHS = {("chatgpt.com", "/backend-api/codex/responses"), ("api.openai.com", "/v1/responses")}

logger = logging.getLogger(__name__)
_seen: set[str] = set()


def is_model_endpoint(flow: http.HTTPFlow) -> bool:
    return (flow.request.pretty_host, flow.request.path.split("?")[0]) in HOSTS_PATHS


def texts(item) -> str:
    content = item.get("content")
    if isinstance(content, str):
        return content
    return "".join(c.get("text", "") for c in content or [] if isinstance(c, dict))


def split_setup(payload):
    """(tools item, developer texts, user context texts) or None if this request carries no setup."""
    items = [i for i in payload.get("input") or [] if isinstance(i, dict)]
    tools = next((i for i in items if i.get("type") == "additional_tools"), None)
    if tools is None:
        return None
    dev = [texts(i) for i in items if i.get("type") == "message" and i.get("role") == "developer"]
    # Injected context is the user messages that open with a tag (<environment_context>, AGENTS.md
    # blocks); what you typed is plain text and is left out of the hash.
    ctx = [t for t in (texts(i) for i in items if i.get("type") == "message" and i.get("role") == "user")
           if t.lstrip().startswith("<") or t.lstrip().startswith("# AGENTS.md")]
    return tools, dev, ctx


def fingerprint(tools, dev, ctx) -> str:
    stable = {k: v for k, v in tools.items() if k != "id"}  # the item id changes every session
    raw = json.dumps({"dev": dev, "tools": stable, "ctx": ctx}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


def tool_rows(tools_item):
    rows = []
    for ns in tools_item.get("tools") or []:
        if not isinstance(ns, dict):
            continue
        inner = ns.get("tools")
        if isinstance(inner, list):
            for t in inner:
                if isinstance(t, dict):
                    rows.append((f"{ns.get('name', '?')}.{t.get('name', '?')}", len(json.dumps(t, ensure_ascii=False))))
        else:
            rows.append((str(ns.get("name", "?")), len(json.dumps(ns, ensure_ascii=False))))
    return sorted(rows, key=lambda r: r[1], reverse=True)


def build_summary(model, tools, dev, ctx, input_chars, measured=None) -> str:
    tool_chars = len(json.dumps(tools, ensure_ascii=False))
    dev_chars = sum(len(d) for d in dev)
    ctx_chars = sum(len(c) for c in ctx)
    other = max(input_chars - tool_chars - dev_chars - ctx_chars, 0)
    total = input_chars
    if measured and total:
        tpc = measured / total
        note = (f"Request used **{measured:,} input tokens** (response.completed usage). Per-part tokens are that "
                f"total spread by character count ({1 / tpc:.2f} chars/token here).")
    else:
        tpc = 0.25
        note = "Not calibrated yet (no usage seen): tokens are chars/4."

    def tok(c):
        return f"{round(c * tpc):,}"

    lines = [f"# Codex prompt capture: {model}", "", note, "",
             "| part | chars | tokens | share |", "|---|---:|---:|---:|"]
    for name, c in [("tools (additional_tools)", tool_chars), (f"developer messages ({len(dev)})", dev_chars),
                    (f"injected context ({len(ctx)})", ctx_chars), ("other (your prompt, JSON framing)", other)]:
        lines.append(f"| {name} | {c:,} | {tok(c)} | {f'{100 * c / total:.0f}%' if total else '-'} |")
    lines.append(f"| **total** | **{total:,}** | **{tok(total)}** | |")
    lines += ["", "## Developer messages", "", "| # | chars | starts with |", "|---:|---:|---|"]
    for i, d in enumerate(dev):
        lines.append(f"| {i} | {len(d):,} | {' '.join(d.split())[:70].replace('|', '/')} |")
    lines += ["", "## Tools (largest first)", "", "| tool | chars | tokens |", "|---|---:|---:|"]
    for name, c in tool_rows(tools):
        lines.append(f"| {name} | {c:,} | {tok(c)} |")
    return "\n".join(lines) + "\n"


def capture(payload, flow_meta: dict) -> None:
    if not isinstance(payload, dict) or payload.get("type", "response.create") != "response.create":
        return
    setup = split_setup(payload)
    if setup is None:
        return  # warm-ups and follow-up deltas
    tools, dev, ctx = setup
    fp = fingerprint(tools, dev, ctx)
    if fp in _seen:
        return
    _seen.add(fp)
    model = str(payload.get("model", "unknown")).replace("/", "_")
    out = OUT_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_{model}_{fp}"
    out.mkdir(parents=True, exist_ok=True)
    sep = "\n\n" + "=" * 30 + " message {} " + "=" * 30 + "\n\n"
    (out / "instructions.txt").write_text("".join(sep.format(i) + d for i, d in enumerate(dev)).lstrip(), encoding="utf-8")
    (out / "tools.json").write_text(json.dumps(tools, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "context.txt").write_text("\n\n".join(ctx), encoding="utf-8")
    inp = payload.get("input") or []
    (out / "messages.json").write_text(json.dumps(inp, indent=2, ensure_ascii=False), encoding="utf-8")
    args = (model, tools, dev, ctx, len(json.dumps(inp, ensure_ascii=False)))
    (out / "summary.md").write_text(build_summary(*args), encoding="utf-8")
    flow_meta["codex_capture"] = (out, args)
    logger.warning("captured %s (%d developer messages, %d tool namespaces) -> %s",
                   model, len(dev), len(tools.get("tools") or []), out)


def input_tokens(event) -> int | None:
    resp = event.get("response") if isinstance(event, dict) else None
    usage = (resp or {}).get("usage") or event.get("usage") if isinstance(event, dict) else None
    if isinstance(usage, dict) and isinstance(usage.get("input_tokens"), int):
        return usage["input_tokens"]
    return None


def calibrate(flow_meta: dict, measured) -> None:
    cap = flow_meta.pop("codex_capture", None)
    if cap and measured:
        out, args = cap
        (out / "summary.md").write_text(build_summary(*args, measured=measured), encoding="utf-8")


def websocket_message(flow: http.HTTPFlow) -> None:
    if not is_model_endpoint(flow) or flow.websocket is None:
        return
    msg = flow.websocket.messages[-1]
    if not msg.is_text:
        return
    try:
        data = json.loads(msg.text)
    except ValueError:
        return
    if msg.from_client:
        capture(data, flow.metadata)
    elif isinstance(data, dict) and data.get("type") == "response.completed":
        calibrate(flow.metadata, input_tokens(data))


def request(flow: http.HTTPFlow) -> None:
    # Codex can fall back to plain HTTP: a JSON POST with the same body.
    if flow.request.method != "POST" or not is_model_endpoint(flow):
        return
    try:
        capture(json.loads(flow.request.get_text() or ""), flow.metadata)
    except (ValueError, UnicodeDecodeError):
        return


def response(flow: http.HTTPFlow) -> None:
    if "codex_capture" not in flow.metadata or not flow.response:
        return
    measured = None
    for line in (flow.response.get_text(strict=False) or "").splitlines():
        if line.startswith("data:"):
            try:
                ev = json.loads(line[5:])
            except ValueError:
                continue
            if isinstance(ev, dict) and ev.get("type") == "response.completed":
                measured = input_tokens(ev)
    calibrate(flow.metadata, measured)
