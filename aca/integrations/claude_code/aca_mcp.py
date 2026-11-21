"""MCP server exposing ACA memory to Claude Code as explicit tools.

Register (user scope):
    claude mcp add --scope user aca -- python "<path>/aca_mcp.py"

Uses the same ACA_URL / ACA_API_KEY / ACA_API_KEY_FILE settings as the hook.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path
from typing import Literal

from mcp.server.fastmcp import FastMCP

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aca_client  # noqa: E402

# Claude Code starts stdio MCP servers in the project folder
SCOPE = aca_client.scope_for(os.getcwd())
SESSION = "cc-mcp-" + hashlib.sha256(SCOPE.encode("utf-8")).hexdigest()
mcp = FastMCP("aca")

KIND_SIGNALS = {
    # kind -> (source trust, node type)
    "rule": ("user_constraint", "constraint"),
    "decision": ("verified_decision", "decision"),
    "fact": ("direct_code", "fragment"),
    "procedure": ("verified_decision", "procedure"),
}


@mcp.tool()
def aca_remember(
    text: str, kind: Literal["rule", "decision", "fact", "procedure"] = "fact", everywhere: bool = False
) -> str:
    """Store something in ACA long-term memory so later sessions recall it.

    Use 'rule' for hard constraints that must always apply (they are pinned into every
    recall), 'decision' for agreed design choices, 'fact' for observations about the code or
    environment, and 'procedure' for how-to steps. Keep each memory to one self-contained idea.
    Memories belong to the current project unless everywhere=True (e.g. personal preferences).
    """
    source_type, node_type = KIND_SIGNALS[kind]
    signals = (
        {"pin_constraint": True}
        if kind == "rule"
        else {"seed_fragment": True, "source_type": source_type, "node_type": node_type}
    )
    can = aca_client.request(
        "POST",
        "/v1/ingest",
        {"session_id": SESSION, "raw_payload": text, "caller": "claude_code_mcp",
         "event_type": "system_alert", "external_signals": signals,
         "scope": "global" if everywhere else SCOPE},
    )
    where = "all projects" if everywhere else SCOPE
    return f"Stored as {kind} for {where} (turn {can.get('turn_id')})."


@mcp.tool()
def aca_recall(query: str, token_budget: int = 800) -> str:
    """Ask ACA which stored memories are relevant to a topic, task or question."""
    can = aca_client.request(
        "POST",
        "/v1/ingest",
        {"session_id": SESSION, "raw_payload": query, "caller": "claude_code_mcp",
         "event_type": "tool_output", "token_budget": token_budget, "scope": SCOPE},
    )
    return aca_client.render_can(can, SESSION) or "No relevant memories."


@mcp.tool()
def aca_report_outcome(status: Literal["passed", "failed"], output: str = "", command: str = "") -> str:
    """Report the result of a test/build/command run. Surprising failures are stored as memories."""
    resp = aca_client.request(
        "POST",
        "/v1/outcome",
        {"session_id": SESSION, "caller": "claude_code_mcp", "command_or_action": command[:500],
         "exit_code": 0 if status == "passed" else 1, "test_status": status, "raw_output": output[-4000:], "scope": SCOPE},
    )
    stored = f" Stored: {resp.get('write_reason')}." if resp.get("write_gate_triggered") else ""
    return f"Surprise {resp.get('surprise'):.2f}.{stored}"


@mcp.tool()
def aca_status() -> str:
    """List what ACA holds for this project (plus global memories), with ids, pinned rules first."""
    state = aca_client.request("GET", f"/v1/inspect/state?session_id={SESSION}")
    nodes = [
        n for n in state.get("nodes", [])
        if not n["provenance"].get("superseded_by") and n["provenance"].get("scope") in (SCOPE, "global", "*")
    ]
    by_type: dict = {}
    for n in nodes:
        by_type[n.get("node_type")] = by_type.get(n.get("node_type"), 0) + 1
    counts = ", ".join(f"{v} {k}" for k, v in sorted(by_type.items())) or "none"
    lines = [f"Scope {SCOPE} (+ global): {len(nodes)} memories: {counts}"]
    for n in sorted(nodes, key=lambda n: not n["dynamics"].get("pinned")):
        text = aca_client.expand(n["resolutions"]["full"], SESSION).replace("\n", " ")
        text = text if len(text) <= 160 else text[:157] + "..."
        pin = "PINNED " if n["dynamics"].get("pinned") else ""
        lines.append(f"- {n['id']} [{pin}{n['node_type']}] {text}")
    return "\n".join(lines)


@mcp.tool()
def aca_forget(node_id: str) -> str:
    """Remove a memory so it is never recalled again (use an id from aca_status).

    Use for memories that are wrong, outdated, or were stored by mistake.
    """
    aca_client.request("DELETE", f"/v1/memory/{node_id}")
    return f"Forgot {node_id}."


if __name__ == "__main__":
    mcp.run()
