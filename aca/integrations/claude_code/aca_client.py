"""Tiny stdlib client for the ACA API, shared by the Claude Code hook and MCP server.

Configuration (environment, all optional):
- ACA_URL           base URL of the server (default http://127.0.0.1:8420)
- ACA_API_KEY       key to send; otherwise read from ACA_API_KEY_FILE
- ACA_API_KEY_FILE  file holding the key (default ~/.aca/claude_code.key)
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_URL = "http://127.0.0.1:8420"
DEFAULT_KEY_FILE = Path.home() / ".aca" / "claude_code.key"


class ACAError(Exception):
    pass


def _api_key() -> str:
    key = os.environ.get("ACA_API_KEY", "").strip()
    if key:
        return key
    path = Path(os.environ.get("ACA_API_KEY_FILE", DEFAULT_KEY_FILE))
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ACAError(f"No ACA API key: set ACA_API_KEY or create {path}") from exc


def request(method: str, path: str, body: Optional[Dict[str, Any]] = None, timeout: float = 4.0) -> Any:
    url = os.environ.get("ACA_URL", DEFAULT_URL).rstrip("/") + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {_api_key()}")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise ACAError(f"ACA returned HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
        raise ACAError(f"ACA server not reachable at {url}: {exc}") from exc


def scope_for(cwd: Optional[str]) -> str:
    """Use the resolved project folder as the recall scope."""
    folder = Path(cwd or os.getcwd()).resolve()
    normalized = Path(os.path.normcase(folder)).as_posix()
    return f"repo-path:{normalized}"


def expand(text: str, session_id: str) -> str:
    """Hydrate GC pointers but keep masked secrets as placeholders."""
    if not text:
        return text
    resp = request("POST", "/v1/gc/expand", {"session_id": session_id, "compressed_text": text, "unmask": False})
    return resp["expanded_text"]


# Text the engine adds to every packet; it carries no stored memory
ENGINE_BOILERPLATE = {
    "Never overwrite raw log assertions with reconstructed CAN prose.",
    "No non-pinned fragments required full-resolution narrative expansion on this turn.",
}
FRAGMENT_TAG_RE = re.compile(r"\[[a-z_]+:frag_[0-9a-f]+\|trust=[\d.]+\]\s*")


def _clean(text: str) -> str:
    return FRAGMENT_TAG_RE.sub("", text or "").strip()


def render_can(can: Dict[str, Any], session_id: str) -> str:
    """Turn a CAN packet into a short plain-text memory block ('' when nothing was recalled)."""
    state = can.get("can_state") or {}
    pinned: List[str] = [
        _clean(p) for p in state.get("pinned_core") or [] if p and p not in ENGINE_BOILERPLATE
    ]
    narrative = _clean(state.get("full_narrative") or "")
    if narrative in ENGINE_BOILERPLATE:
        narrative = ""
    summaries: List[str] = [_clean(s) for s in state.get("summary_fragments") or [] if s]
    if not (pinned or narrative or summaries):
        return ""
    parts: List[str] = []
    if pinned:
        parts.append("Pinned rules:\n" + "\n".join(f"- {p}" for p in pinned))
    if narrative:
        parts.append("Relevant memory:\n" + narrative)
    if summaries:
        parts.append("Related:\n" + "\n".join(f"- {s}" for s in summaries))
    return expand("\n\n".join(parts), session_id)
