"""Tests for slim_tools_addon: shorten built-in tool docs without changing the contract."""
import copy
import json

from mitmproxy import http
from mitmproxy.test import tflow, tutils

import slim_tools_addon as slim


def schema(**props):
    return {"type": "object", "properties": props, "required": list(props)[:1], "additionalProperties": False}


TOOLS = [
    {"name": "Grep", "description": "x" * 500, "eager_input_streaming": True,
     "input_schema": schema(pattern={"type": "string", "description": "p" * 60},
                            output_mode={"type": "string", "enum": ["content", "files_with_matches", "count"],
                                         "description": "o" * 246})},
    {"name": "Agent", "description": "lists agent types: Explore, Plan", "input_schema": schema(prompt={"type": "string"})},
    {"name": "mcp__x__y", "description": "third party", "input_schema": schema(a={"type": "string"})},
    {"name": "ScheduleWakeup", "description": "w" * 3000, "input_schema": schema(d={"type": "number"}),
     "cache_control": {"type": "ephemeral"}},
]


def test_slim_replaces_docs_but_keeps_contract():
    out = slim.slim_tools(copy.deepcopy(TOOLS))
    grep = out[0]
    assert grep["description"] == slim.SLIM["Grep"]["description"]
    props = grep["input_schema"]["properties"]
    assert props["output_mode"]["description"] == slim.SLIM["Grep"]["params"]["output_mode"]
    assert props["output_mode"]["enum"] == ["content", "files_with_matches", "count"]
    assert props["pattern"]["description"] == "p" * 60  # params not in SLIM keep their docs
    assert grep["input_schema"]["required"] == ["pattern"]
    assert grep["input_schema"]["additionalProperties"] is False
    assert grep["eager_input_streaming"] is True


def test_unlisted_tools_untouched_and_input_not_mutated():
    original = copy.deepcopy(TOOLS)
    out = slim.slim_tools(original)
    assert original == TOOLS
    assert out[1:] == TOOLS[1:]


def test_drop_list_removes_tools():
    out = slim.slim_tools(copy.deepcopy(TOOLS), drop={"ScheduleWakeup"})
    assert [t["name"] for t in out] == ["Grep", "Agent", "mcp__x__y"]


def test_deterministic_output():
    a = json.dumps(slim.slim_tools(copy.deepcopy(TOOLS)))
    b = json.dumps(slim.slim_tools(copy.deepcopy(TOOLS)))
    assert a == b


def make_flow(body, host="api.anthropic.com"):
    req = tutils.treq(host=host, port=443, scheme=b"https", method=b"POST", path=b"/v1/messages",
                      headers=http.Headers(content_type="application/json"), content=json.dumps(body).encode())
    return tflow.tflow(req=req)


def test_request_hook_rewrites_only_tools(monkeypatch):
    monkeypatch.delenv("SLIM_DROP", raising=False)
    body = {"model": "m", "system": [{"type": "text", "text": "sys"}], "tools": copy.deepcopy(TOOLS),
            "messages": [{"role": "user", "content": "hi"}]}
    flow = make_flow(body)
    slim.request(flow)
    sent = json.loads(flow.request.get_text())
    assert sent["system"] == body["system"] and sent["messages"] == body["messages"]
    assert sent["tools"][0]["description"] == slim.SLIM["Grep"]["description"]
    assert len(flow.request.content) < len(json.dumps(body))


def test_request_hook_ignores_other_hosts():
    flow = make_flow({"tools": copy.deepcopy(TOOLS), "messages": []}, host="example.com")
    before = flow.request.content
    slim.request(flow)
    assert flow.request.content == before


def test_ultra_covers_slim_and_is_shorter():
    ultra = slim.LEVELS["ultra"]
    assert set(slim.SLIM) <= set(ultra)
    for name, spec in slim.SLIM.items():
        assert len(ultra[name]["description"]) <= len(spec["description"]), name


def test_ultra_level_rewrites_meta_tools_but_keeps_contract():
    out = slim.slim_tools(copy.deepcopy(TOOLS), spec=slim.LEVELS["ultra"])
    agent, mcp, wake = out[1], out[2], out[3]
    assert agent["description"] == slim.ULTRA["Agent"]["description"]
    assert agent["input_schema"] == TOOLS[1]["input_schema"]
    assert wake["description"] == slim.ULTRA["ScheduleWakeup"]["description"]
    assert wake["cache_control"] == {"type": "ephemeral"}
    assert wake["input_schema"]["required"] == ["d"]
    assert mcp == TOOLS[2]  # unknown tools pass through


def test_default_level_is_slim():
    out = slim.slim_tools(copy.deepcopy(TOOLS))
    assert out[1] == TOOLS[1]  # Agent untouched without ultra


def test_level_env(monkeypatch):
    monkeypatch.setenv("SLIM_LEVEL", "ultra")
    assert slim._spec() is slim.LEVELS["ultra"]
    monkeypatch.setenv("SLIM_LEVEL", "bogus")
    assert slim._spec() is slim.SLIM
    monkeypatch.delenv("SLIM_LEVEL")
    assert slim._spec() is slim.SLIM


def test_request_hook_ultra(monkeypatch):
    monkeypatch.delenv("SLIM_DROP", raising=False)
    monkeypatch.setenv("SLIM_LEVEL", "ultra")
    flow = make_flow({"model": "m", "tools": copy.deepcopy(TOOLS), "messages": []})
    slim.request(flow)
    sent = json.loads(flow.request.get_text())
    assert sent["tools"][1]["description"] == slim.ULTRA["Agent"]["description"]
