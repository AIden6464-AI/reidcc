"""Tests for the read-only prompt capture addon."""
import json

import pytest
from mitmproxy import http
from mitmproxy.test import tflow, tutils

import capture_addon as cap

PAYLOAD = {
    "model": "claude-x",
    "system": [{"type": "text", "text": "x-anthropic-billing-header: cch=1"},
               {"type": "text", "text": "You are Claude Code."}],
    "tools": [{"name": "Read", "description": "read files", "input_schema": {}}],
    "messages": [{"role": "user", "content": [
        {"type": "text", "text": "<system-reminder>ctx</system-reminder>"},
        {"type": "text", "text": "secret user text"}]}],
}


@pytest.fixture(autouse=True)
def out_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cap, "OUT_DIR", tmp_path)
    cap._seen.clear()
    return tmp_path


def make_flow(payload, host="api.anthropic.com", path=b"/v1/messages", resp=None):
    req = tutils.treq(host=host, port=443, scheme=b"https", method=b"POST", path=path,
                      headers=http.Headers(content_type="application/json", authorization="Bearer SECRET"),
                      content=json.dumps(payload).encode())
    return tflow.tflow(req=req, resp=resp or False)


def test_capture_writes_files_without_modifying_or_leaking(out_dir):
    flow = make_flow(PAYLOAD)
    before = flow.request.content
    cap.request(flow)

    assert flow.request.content == before  # read-only
    (d,) = list(out_dir.iterdir())
    assert "You are Claude Code." in (d / "system.txt").read_text(encoding="utf-8")
    assert json.loads((d / "tools.json").read_text(encoding="utf-8"))[0]["name"] == "Read"
    assert (d / "reminders.txt").read_text(encoding="utf-8") == "<system-reminder>ctx</system-reminder>"
    everything = "".join(p.read_text(encoding="utf-8") for p in d.iterdir())
    assert "SECRET" not in everything  # auth header never written
    assert "secret user text" in (d / "messages.json").read_text(encoding="utf-8")


def test_dedup_ignores_billing_header_and_other_hosts_paths(out_dir):
    cap.request(make_flow(PAYLOAD))
    other = json.loads(json.dumps(PAYLOAD))
    other["system"][0]["text"] = "x-anthropic-billing-header: cch=2"
    cap.request(make_flow(other))
    cap.request(make_flow(PAYLOAD, host="example.com"))
    cap.request(make_flow(PAYLOAD, path=b"/v1/messages/count_tokens"))
    assert len(list(out_dir.iterdir())) == 1


@pytest.mark.parametrize("body", [
    json.dumps({"usage": {"input_tokens": 5, "cache_creation_input_tokens": 10, "cache_read_input_tokens": 85}}),
    'event: message_start\ndata: {"type":"message_start","message":{"usage":{"input_tokens":5,'
    '"cache_creation_input_tokens":10,"cache_read_input_tokens":85}}}\n\n'
    'event: message_delta\ndata: {"type":"message_delta","usage":{"output_tokens":3}}\n\n',
], ids=["json", "sse"])
def test_input_tokens_from_response(body):
    assert cap.input_tokens_from_response(body) == 100


def test_continuation_request_not_calibrated(out_dir):
    body = {"model": "claude-x",
            "system": [{"type": "text", "text": "x-anthropic-billing-header: cch=1; cc_prev_req=req_abc;"}],
            "messages": [{"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}]}]}
    sse = ('event: message_start\ndata: {"type":"message_start","message":{"usage":'
           '{"input_tokens":5,"cache_creation_input_tokens":0,"cache_read_input_tokens":20000}}}\n\n')
    resp = tutils.tresp(headers=http.Headers(content_type="text/event-stream"), content=sse.encode())
    flow = make_flow(body, resp=resp)
    cap.request(flow)
    cap.response(flow)
    (d,) = list(out_dir.iterdir())
    summary = (d / "summary.md").read_text(encoding="utf-8")
    assert "**Continuation request**" in summary and "20,005 input tokens billed" in summary
    assert "chars/token here" not in summary


def test_response_calibrates_summary(out_dir):
    sse = ('event: message_start\ndata: {"type":"message_start","message":{"usage":'
           '{"input_tokens":1000,"cache_creation_input_tokens":0,"cache_read_input_tokens":0}}}\n\n')
    resp = tutils.tresp(headers=http.Headers(content_type="text/event-stream"), content=sse.encode())
    flow = make_flow(PAYLOAD, resp=resp)
    cap.request(flow)
    cap.response(flow)
    (d,) = list(out_dir.iterdir())
    summary = (d / "summary.md").read_text(encoding="utf-8")
    assert "**1,000 input tokens**" in summary
    assert "| **total** |" in summary and "**1,000** |" in summary
