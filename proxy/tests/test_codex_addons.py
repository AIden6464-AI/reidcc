"""Codex add-ons (SPEC-codex-proxy.md): slim keeps every name, schema and exec declaration,
is deterministic, drops on request; capture saves one folder per distinct setup."""
import json

import codex_capture_addon as cap
import codex_slim_addon as slim

DECL_EXEC = ("exec tool declaration:\n```ts\ndeclare const tools: { web__run(args: {\n  q?: string;\n}): "
             "Promise<unknown>; };\n```\n")
EXEC_DOC = ("Run JavaScript code\n- header kept\n\n### `apply_patch`\nFreeform patch tool.\n\n"
            "exec tool declaration:\n```ts\ndeclare const tools: { apply_patch(input: string): Promise<unknown>; };\n```\n\n"
            "## web\nTools in the web namespace.\n\n### `web__run`\nTool for accessing the internet.\n" + "long rule\n" * 500
            + "\n" + DECL_EXEC + "\n### `future_tool`\nUnknown prose stays.\n")


def tools_item():
    return {"type": "additional_tools", "id": "at_1", "role": "developer", "tools": [
        {"type": "namespace", "name": "functions", "description": "", "tools": [
            {"type": "custom", "name": "exec", "description": EXEC_DOC, "format": {"type": "grammar"}},
            {"type": "function", "name": "wait", "description": "long wait doc " * 50, "strict": False,
             "parameters": {"type": "object", "properties": {"cell_id": {"type": "string", "description": "id"}},
                            "required": ["cell_id"]}}]},
        {"type": "namespace", "name": "mcp__x", "description": "an MCP server", "tools": [
            {"type": "function", "name": "go", "description": "mcp doc", "parameters": {"type": "object"}}]},
    ]}


def payload(item=None, typed="hi"):
    return {"type": "response.create", "model": "m", "input": [
        item or tools_item(),
        {"type": "message", "role": "developer", "content": [{"type": "input_text", "text": "You are Codex"}]},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": "<environment_context>x"}]},
        {"type": "message", "role": "user", "content": [{"type": "input_text", "text": typed}]}]}


def strip_docs(item):
    item = json.loads(json.dumps(item))
    for ns in item["tools"]:
        for t in ns["tools"]:
            t.pop("description", None)
            for p in (t.get("parameters") or {}).get("properties", {}).values():
                p.pop("description", None)
    return item


def test_slim_keeps_schemas_and_declarations():
    new = slim.rewrite(payload(), frozenset(), slim.LEVELS["slim"])
    item = new["input"][0]
    assert strip_docs(item) == strip_docs(tools_item())
    doc = item["tools"][0]["tools"][0]["description"]
    assert DECL_EXEC in doc and "apply_patch(input: string)" in doc
    assert "long rule" not in doc and "Internet access" in doc
    assert "Unknown prose stays." in doc and "- header kept" in doc and "## web" in doc
    assert item["tools"][0]["tools"][1]["description"].startswith("Wait on a yielded")
    assert item["tools"][1] == tools_item()["tools"][1]  # MCP untouched
    assert new["input"][1:] == payload()["input"][1:]


def test_slim_is_deterministic_and_skips_deltas():
    a = slim.rewrite(payload(), frozenset(), slim.LEVELS["ultra"])
    b = slim.rewrite(payload(), frozenset(), slim.LEVELS["ultra"])
    assert json.dumps(a) == json.dumps(b)
    delta = {"type": "response.create", "previous_response_id": "r", "input": [{"type": "custom_tool_call_output"}]}
    assert slim.rewrite(delta, frozenset(), slim.LEVELS["slim"]) is None
    assert slim.rewrite({"type": "response.create", "input": []}, frozenset(), slim.LEVELS["slim"]) is None


def test_slim_drop_namespace_and_tool():
    new = slim.rewrite(payload(), frozenset({"mcp__x", "functions.wait"}), slim.LEVELS["slim"])
    names = [(ns["name"], [t["name"] for t in ns["tools"]]) for ns in new["input"][0]["tools"]]
    assert names == [("functions", ["exec"])]


def test_capture_saves_one_folder_per_setup(tmp_path, monkeypatch):
    monkeypatch.setattr(cap, "OUT_DIR", tmp_path)
    monkeypatch.setattr(cap, "_seen", set())
    meta = {}
    cap.capture(payload(typed="first"), meta)
    cap.capture(payload(typed="second"), {})  # same setup, other prompt: not saved again
    other = tools_item()
    other["id"] = "at_2"  # the item id changes per session and must not count
    cap.capture(payload(other), {})
    dirs = list(tmp_path.iterdir())
    assert len(dirs) == 1
    files = sorted(p.name for p in dirs[0].iterdir())
    assert files == ["context.txt", "instructions.txt", "messages.json", "summary.md", "tools.json"]
    assert json.loads((dirs[0] / "tools.json").read_text(encoding="utf-8")) == tools_item()
    assert "You are Codex" in (dirs[0] / "instructions.txt").read_text(encoding="utf-8")
    assert "<environment_context>" in (dirs[0] / "context.txt").read_text(encoding="utf-8")
    cap.calibrate(meta, 1234)
    assert "1,234 input tokens" in (dirs[0] / "summary.md").read_text(encoding="utf-8")
    cap.capture({"type": "response.create", "input": []}, {})  # warm-up
    assert len(list(tmp_path.iterdir())) == 1
