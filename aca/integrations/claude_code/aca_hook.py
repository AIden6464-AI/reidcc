"""Claude Code hook that connects sessions to ACA memory.

- UserPromptSubmit: sends the prompt to /v1/ingest (which also auto-pins stated rules such as
  "never deploy on Fridays") and adds the recalled memories to Claude's context.
- PostToolUse / PostToolUseFailure on Bash: reports test/build/lint runs to /v1/outcome so
  surprising failures become memories. Other commands are ignored to keep the graph clean.

Fails open: if the server is down or anything goes wrong, it exits 0 with no output, so
Claude Code is never blocked. Set ACA_HOOK_DEBUG=1 to print errors to stderr.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aca_client  # noqa: E402

MAX_PROMPT_CHARS = 8000
MAX_OUTPUT_CHARS = 4000
PASTED_BLOCK_RE = re.compile(r"<pasted_content\b[^>]*>(.*?)</pasted_content\b[^>]*>", re.DOTALL)
OUTCOME_COMMAND_RE = re.compile(
    os.environ.get(
        "ACA_OUTCOME_COMMANDS",
        r"\b(pytest|unittest|tox|nox|npm (run )?(test|build|lint)|yarn (test|build|lint)|pnpm (test|build|lint)"
        r"|bun test|jest|vitest|mocha|cargo (test|build|check|clippy)|go (test|build|vet)|make\b|cmake --build"
        r"|tsc\b|mvn|gradle|dotnet (test|build)|ruff|mypy|eslint|flake8|pylint)",
    ),
    re.IGNORECASE,
)


def _session(payload: Dict[str, Any]) -> str:
    return "cc-" + str(payload.get("session_id") or "default")[:12]


def on_prompt(payload: Dict[str, Any]) -> None:
    prompt = str(payload.get("prompt") or "").strip()
    if not prompt or prompt.startswith("/"):
        return
    # Only the user's own words may create rules; pasted logs/files are used for recall only
    own_words = PASTED_BLOCK_RE.sub(" ", prompt).strip()
    if own_words:
        text, event_type = own_words, "user_turn"
    else:
        text = "\n".join(m.group(1).strip() for m in PASTED_BLOCK_RE.finditer(prompt))
        event_type = "tool_output"
    session = _session(payload)
    can = aca_client.request(
        "POST",
        "/v1/ingest",
        {
            "session_id": session,
            "raw_payload": text[:MAX_PROMPT_CHARS],
            "caller": "claude_code",
            "event_type": event_type,
            "token_budget": int(os.environ.get("ACA_HOOK_BUDGET", "600")),
            "scope": aca_client.scope_for(payload.get("cwd")),
        },
    )
    memory = aca_client.render_can(can, session)
    if not memory:
        return
    context = (
        "ACA memory recalled for this prompt (from the local ACA server; may be stale, "
        "verify before relying on it):\n\n" + memory
    )
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "UserPromptSubmit", "additionalContext": context}}))


def on_bash_result(payload: Dict[str, Any], failed: bool) -> None:
    command = str((payload.get("tool_input") or {}).get("command") or "")
    if not OUTCOME_COMMAND_RE.search(command):
        return
    response = payload.get("tool_response")
    if isinstance(response, dict):
        output = "\n".join(str(response.get(k) or "") for k in ("stdout", "stderr")).strip()
        code = response.get("exit_code", response.get("returnCode"))
        if isinstance(code, int) and code != 0:
            failed = True
    else:
        output = str(response or "")
    if failed:
        output = str(payload.get("error") or output)
    aca_client.request(
        "POST",
        "/v1/outcome",
        {
            "session_id": _session(payload),
            "caller": "claude_code",
            "command_or_action": command[:500],
            "exit_code": 1 if failed else 0,
            "test_status": "failed" if failed else "passed",
            "raw_output": output[-MAX_OUTPUT_CHARS:],
            "scope": aca_client.scope_for(payload.get("cwd")),
        },
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        event = payload.get("hook_event_name")
        if event == "UserPromptSubmit":
            on_prompt(payload)
        elif event in ("PostToolUse", "PostToolUseFailure") and payload.get("tool_name") == "Bash":
            on_bash_result(payload, failed=event == "PostToolUseFailure")
    except Exception as exc:  # never block Claude Code
        if os.environ.get("ACA_HOOK_DEBUG"):
            print(f"aca_hook: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
