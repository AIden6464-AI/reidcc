"""Flow tests for the mitmproxy request/response hooks in claude_optimizer_addon."""
import json

import pytest
from mitmproxy import http
from mitmproxy.test import tflow, tutils

import claude_optimizer_addon as addon

DATE = "Today's date is 2026-11-01."


@pytest.fixture(autouse=True)
def audit_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(addon, "AUDIT_DIR", tmp_path)
    return tmp_path


def read_log(audit_dir):
    lines = []
    for f in audit_dir.glob("*.jsonl"):
        lines += [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line]
    return lines


def make_flow(body, *, host="api.anthropic.com", method=b"POST", path=b"/v1/messages",
              content_type="application/json", resp=None):
    content = body if isinstance(body, bytes) else json.dumps(body).encode()
    req = tutils.treq(
        host=host, port=443, scheme=b"https", method=method, path=path,
        headers=http.Headers(content_type=content_type), content=content,
    )
    return tflow.tflow(req=req, resp=resp or False)


PAYLOAD = {
    "model": "claude-x",
    "system": [{"type": "text", "text": "You are Claude."}, {"type": "text", "text": DATE}],
    "messages": [{"role": "user", "content": [{"type": "text", "text": "hi"}]}],
}


def test_request_hook_rewrites_body_and_logs(audit_dir):
    flow = make_flow(PAYLOAD)
    original_bytes = len(flow.request.content)

    addon.request(flow)

    body = json.loads(flow.request.get_text())
    assert body["system"] == [{"type": "text", "text": "You are Claude."}]
    assert body["messages"][-1]["content"][0] == {"type": "text", "text": DATE}

    (entry,) = read_log(audit_dir)
    assert entry["phase"] == "request"
    assert entry["optimized"] is True
    assert entry["original_bytes"] == original_bytes
    assert entry["optimized_bytes"] == len(flow.request.content)


@pytest.mark.parametrize("kwargs", [
    {"host": "example.com"},
    {"method": b"GET"},
    {"path": b"/v1/models"},
    {"content_type": "text/plain"},
], ids=["other-host", "get", "other-path", "non-json"])
def test_request_hook_ignores_non_messages_traffic(audit_dir, kwargs):
    flow = make_flow(PAYLOAD, **kwargs)
    before = flow.request.content

    addon.request(flow)

    assert flow.request.content == before
    assert read_log(audit_dir) == []


def test_request_hook_survives_invalid_json(audit_dir):
    flow = make_flow(b"{not json")

    addon.request(flow)  # must not raise

    assert flow.request.content == b"{not json"
    assert read_log(audit_dir) == []


def test_response_hook_logs_usage(audit_dir):
    usage = {"input_tokens": 10, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 900}
    resp = tutils.tresp(
        headers=http.Headers(content_type="application/json"),
        content=json.dumps({"type": "message", "usage": usage}).encode(),
    )
    flow = make_flow(PAYLOAD, resp=resp)

    addon.response(flow)

    (entry,) = read_log(audit_dir)
    assert entry["phase"] == "response"
    assert entry["status_code"] == 200
    assert entry["usage"] == usage


def test_response_hook_streaming_body_logs_null_usage(audit_dir):
    sse = b'event: message_start\ndata: {"type":"message_start"}\n\n'
    resp = tutils.tresp(headers=http.Headers(content_type="text/event-stream"), content=sse)
    flow = make_flow(PAYLOAD, resp=resp)

    addon.response(flow)

    (entry,) = read_log(audit_dir)
    assert entry["usage"] is None
