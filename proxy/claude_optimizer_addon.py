"""
mitmproxy addon: transparently optimizes Anthropic /v1/messages payloads
for prompt-cache efficiency, then logs orig/optimized bytes + Anthropic
usage tokens to ./claude_audit/YYYY-MM-DD.jsonl.

Run:
    mitmdump -s claude_optimizer_addon.py --listen-port 8080 -q

Claude Code shell:
    export HTTPS_PROXY=http://127.0.0.1:8080
    export NODE_EXTRA_CA_CERTS=~/.mitmproxy/mitmproxy-ca-cert.pem
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from mitmproxy import http

logger = logging.getLogger(__name__)


def optimize_payload(payload: dict, enable_pruning: bool = False) -> dict:
    """
    Normalizes the payload structure to guarantee static prefix alignment
    for KV-cache efficiency. Tools pruning ONLY if enable_pruning=True.
    Dynamic state is shifted to the trailing message block, after any
    leading tool_result blocks (Anthropic API correctness invariant).
    """
    if not isinstance(payload, dict) or "messages" not in payload:
        return payload

    if enable_pruning and "tools" in payload:
        bloat_signatures = [
            "mcp__claude_ai_Gmail",
            "mcp__claude_ai_Google_Calendar",
            "mcp__claude_ai_Google_Drive",
            "NotebookEdit",
            "PowerShell",
            "RemoteTrigger",
            "CronCreate",
        ]
        payload["tools"] = [
            tool for tool in payload["tools"]
            if not any(
                sig in tool.get("function", {}).get("name", tool.get("name", ""))
                for sig in bloat_signatures
            )
        ]

    saboteurs = []

    if "system" in payload:
        static_system = []
        system_blocks = (
            payload["system"]
            if isinstance(payload["system"], list)
            else [{"type": "text", "text": payload["system"]}]
        )

        for block in system_blocks:
            text_content = block.get("text", "") if isinstance(block, dict) else block
            if "x-anthropic-billing-header" in text_content or "Today's date is" in text_content:
                saboteurs.append(text_content)
            else:
                static_system.append(block)

        payload["system"] = static_system

    clean_messages = []
    for msg in payload.get("messages", []):
        content = msg.get("content", "")

        if isinstance(content, str):
            if "<system-reminder>" in content:
                saboteurs.append(content)
                continue
        elif isinstance(content, list):
            clean_content = []
            for block in content:
                if block.get("type") == "text" and "<system-reminder>" in block.get("text", ""):
                    saboteurs.append(block.get("text", ""))
                else:

                    clean_content.append(block)

            if not clean_content:
                continue
            msg["content"] = clean_content

        clean_messages.append(msg)

    payload["messages"] = clean_messages

    if saboteurs and payload["messages"]:
        final_message = payload["messages"][-1]
        saboteur_text = "\n\n".join(saboteurs)

        if isinstance(final_message.get("content"), str):
            final_message["content"] = f"{saboteur_text}\n\n{final_message['content']}"
        elif isinstance(final_message.get("content"), list):
            insert_idx = 0
            for block in final_message["content"]:
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    insert_idx += 1
                else:
                    break

            final_message["content"].insert(
                insert_idx, {"type": "text", "text": saboteur_text}
            )

    return payload


# ---------- mitmproxy hooks ----------

AUDIT_DIR = Path("claude_audit")
AUDIT_DIR.mkdir(parents=True, exist_ok=True)


def _is_anthropic_messages(flow: http.HTTPFlow) -> bool:
    if not flow.request:
        return False
    if "api.anthropic.com" not in flow.request.host:
        return False
    if flow.request.method != "POST":
        return False
    if "/v1/messages" not in flow.request.path:
        return False
    if "application/json" not in flow.request.headers.get("content-type", ""):
        return False
    return True


def _log(entry: dict) -> None:
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    log_file = AUDIT_DIR / f"{date_str}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def request(flow: http.HTTPFlow) -> None:
    if not _is_anthropic_messages(flow):
        return

    try:
        body_str = flow.request.get_text()
        if not body_str:
            return

        original_bytes = len(body_str.encode("utf-8"))
        payload = json.loads(body_str)
        optimized = optimize_payload(payload)
        new_body = json.dumps(optimized, ensure_ascii=False)
        flow.request.set_text(new_body)
        optimized_bytes = len(new_body.encode("utf-8"))

        _log({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": "request",
            "url": flow.request.pretty_url,
            "method": flow.request.method,
            "optimized": True,
            "original_bytes": original_bytes,
            "optimized_bytes": optimized_bytes,
        })
        logger.info(
            "OPTIMIZED Anthropic request: %d -> %d bytes",
            original_bytes,
            optimized_bytes,
        )
    except Exception as e:
        logger.error("optimize_payload failed: %s", e)


def response(flow: http.HTTPFlow) -> None:
    if not _is_anthropic_messages(flow):
        return
    if not flow.response or not flow.response.text:
        return

    usage = None
    try:
        data = json.loads(flow.response.text)
        if isinstance(data, dict) and "usage" in data:
            usage = data["usage"]
    except Exception:
        pass

    _log({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase": "response",
        "url": flow.request.pretty_url,
        "status_code": flow.response.status_code,
        "usage": usage,
    })
