"""
mitmproxy addon: READ-ONLY capture of the prompts Claude Code sends to
api.anthropic.com /v1/messages. Traffic is not modified.

For each distinct prompt setup (system + tools), saves to
./claude_prompts/<time>_<model>_<hash>/:
    system.txt      system prompt blocks, verbatim
    tools.json      tool definitions, verbatim
    reminders.txt   <system-reminder> blocks Claude Code injected into user messages
    messages.json   the captured request's messages verbatim: Claude Code's injected
                    context AND whatever you typed in that request (local file only)
    summary.md      size breakdown (chars and tokens, calibrated from API usage)

Never saved: request headers (auth tokens), responses.

Run:
    mitmdump -s capture_addon.py --listen-port 8080 -q
"""
import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path

from mitmproxy import http

OUT_DIR = Path("claude_prompts")
REMINDER_RX = re.compile(r"<system-reminder>.*?</system-reminder>", re.S)
# Per-request values that would defeat de-duplication.
VOLATILE_RX = re.compile(r"x-anthropic-billing-header:[^\n]*")
# Billing-header field marking a request that continues an earlier one server-side.
CONTINUATION_MARK = "cc_prev_req="

logger = logging.getLogger(__name__)
_seen: set[str] = set()


def system_blocks(system) -> list[str]:
    if isinstance(system, str):
        return [system]
    return [b.get("text", "") for b in system or [] if isinstance(b, dict)]


def injected_reminders(messages) -> list[str]:
    found = []
    for msg in messages or []:
        if msg.get("role") != "user":
            continue
        content = msg.get("content")
        texts = [content] if isinstance(content, str) else [
            b.get("text", "") for b in content or [] if isinstance(b, dict) and b.get("type") == "text"]
        for t in texts:
            for r in REMINDER_RX.findall(t):
                if r not in found:
                    found.append(r)
    return found


def fingerprint(blocks: list[str], tools: list) -> str:
    stable = [VOLATILE_RX.sub("", b) for b in blocks]
    raw = json.dumps({"system": stable, "tools": tools}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:10]


def preview(text: str, n: int = 70) -> str:
    one_line = " ".join(text.split())
    return (one_line[:n] + "...") if len(one_line) > n else one_line


def build_summary(model, blocks, tools, reminders, msg_chars, measured_input=None) -> str:
    """measured_input: total input tokens from the API response. When given, per-section
    tokens are that total spread by character count (assumes uniform density)."""
    tool_rows = sorted(((t.get("name", "?"), len(json.dumps(t, ensure_ascii=False))) for t in tools),
                       key=lambda r: r[1], reverse=True)
    sys_chars = sum(len(b) for b in blocks)
    tool_chars = sum(c for _, c in tool_rows)
    rem_chars = sum(len(r) for r in reminders)
    other_chars = max(msg_chars - rem_chars, 0)
    total = sys_chars + tool_chars + msg_chars

    if any(CONTINUATION_MARK in b for b in blocks) and not tools:
        # Claude Code sent only the new messages and referenced an earlier request; the server
        # rebuilt system/tools/history from it, so a per-section split of this payload is meaningless.
        tpc = 0.25
        billed = f"{measured_input:,} input tokens billed" if measured_input else "tokens billed: not seen yet"
        note = ("**Continuation request** (`cc_prev_req` in billing header, no tools): Claude Code sent only "
                "the new message(s); the server reused the earlier request's system prompt, tools and history. "
                f"{billed}. The table below covers only the bytes actually sent (chars/4 estimate).")
    elif measured_input:
        tpc = measured_input / total if total else 0
        note = (f"Request used **{measured_input:,} input tokens** (API usage). Per-section tokens are that "
                f"total spread by character count ({1 / tpc:.2f} chars/token here), so they're calibrated "
                "estimates, not tokenizer output.") if tpc else "No content."
    else:
        tpc = 0.25
        note = "Not calibrated yet (no response seen): tokens are chars/4, which undercounts JSON/code."

    def tok(chars):
        return f"{round(chars * tpc):,}"

    lines = [f"# Claude Code prompt capture: {model}", "", note, "",
             "| section | chars | tokens | share |", "|---|---:|---:|---:|"]
    for name, chars in [("system prompt", sys_chars), (f"tools ({len(tools)})", tool_chars),
                        (f"injected reminders ({len(reminders)})", rem_chars),
                        ("other message content (your prompt, history, JSON framing)", other_chars)]:
        share = f"{100 * chars / total:.0f}%" if total else "-"
        lines.append(f"| {name} | {chars:,} | {tok(chars)} | {share} |")
    lines.append(f"| **total** | **{total:,}** | **{tok(total)}** | |")

    lines += ["", "## System blocks", "", "| # | chars | tokens | starts with |", "|---:|---:|---:|---|"]
    for i, b in enumerate(blocks):
        lines.append(f"| {i} | {len(b):,} | {tok(len(b))} | {preview(b).replace('|', '/')} |")

    lines += ["", "## Tools (largest first)", "", "| tool | chars | tokens |", "|---|---:|---:|"]
    for name, chars in tool_rows:
        lines.append(f"| {name} | {chars:,} | {tok(chars)} |")

    if reminders:
        lines += ["", "## Injected reminders", "", "| # | chars | tokens | starts with |", "|---:|---:|---:|---|"]
        for i, r in enumerate(reminders):
            body = r.removeprefix("<system-reminder>")
            lines.append(f"| {i} | {len(r):,} | {tok(len(r))} | {preview(body).replace('|', '/')} |")
    return "\n".join(lines) + "\n"


def input_tokens_from_response(text: str):
    """Total input tokens (fresh + cache write + cache read) from a JSON or SSE response."""
    usage = None
    try:
        data = json.loads(text)
        usage = data.get("usage") if isinstance(data, dict) else None
    except ValueError:
        for line in text.splitlines():
            if not line.startswith("data:"):
                continue
            try:
                event = json.loads(line[5:])
            except ValueError:
                continue
            if event.get("type") == "message_start":
                usage = (event.get("message") or {}).get("usage")
                break
    if not isinstance(usage, dict):
        return None
    return sum(usage.get(k) or 0 for k in
               ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")) or None


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
    if not isinstance(payload, dict):
        return

    blocks = system_blocks(payload.get("system"))
    tools = payload.get("tools") or []
    fp = fingerprint(blocks, tools)
    if fp in _seen:
        return
    _seen.add(fp)

    model = str(payload.get("model", "unknown")).replace("/", "_")
    reminders = injected_reminders(payload.get("messages"))
    out = OUT_DIR / f"{datetime.now():%Y%m%d-%H%M%S}_{model}_{fp}"
    out.mkdir(parents=True, exist_ok=True)

    sep = "\n\n" + "=" * 30 + " block {} " + "=" * 30 + "\n\n"
    (out / "system.txt").write_text(
        "".join(sep.format(i) + b for i, b in enumerate(blocks)).lstrip(), encoding="utf-8")
    (out / "tools.json").write_text(json.dumps(tools, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "reminders.txt").write_text("\n\n".join(reminders), encoding="utf-8")
    (out / "messages.json").write_text(
        json.dumps(payload.get("messages") or [], indent=2, ensure_ascii=False), encoding="utf-8")
    msg_chars = len(json.dumps(payload.get("messages") or [], ensure_ascii=False))
    args = (model, blocks, tools, reminders, msg_chars)
    (out / "summary.md").write_text(build_summary(*args), encoding="utf-8")
    flow.metadata["prompt_capture"] = (out, args)
    logger.warning("captured %s (%d system blocks, %d tools, %d reminders) -> %s",
                   model, len(blocks), len(tools), len(reminders), out)


def response(flow: http.HTTPFlow) -> None:
    cap = flow.metadata.get("prompt_capture")
    if not cap or not flow.response:
        return
    out, args = cap
    measured = input_tokens_from_response(flow.response.get_text(strict=False) or "")
    if measured:
        (out / "summary.md").write_text(build_summary(*args, measured_input=measured), encoding="utf-8")
