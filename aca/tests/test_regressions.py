"""Regression tests for the code-review findings (contradictions, persistence, origin checks,
surprise cues, refractory, GC tallying, proxy forwarding, stream hydration, validation)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from integrations.claude_code.aca_client import scope_for
from src.api.server import create_app
from src.gc.gc_engine import GCEngine
from src.gc.stream_hydrator import StreamHydrator
from src.storage.store import CognitiveStorage

BASE_URL = "http://127.0.0.1:8420"
UPSTREAM = "http://mock-llm/v1"
ADMIN_KEY = "aca_test_admin_key"
AUTH = {"Authorization": f"Bearer {ADMIN_KEY}"}


class MockUpstream:
    """Records requests and answers like an OpenAI-compatible server."""

    def __init__(self, reply: str = "ok") -> None:
        self.reply = reply
        self.requests: List[Dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append(body)
        if body.get("stream"):
            frames = [
                json.dumps({"choices": [{"index": 0, "delta": {"content": self.reply[i : i + 3]}}]})
                for i in range(0, len(self.reply), 3)
            ]
            sse = "".join(f"data: {f}\n\n" for f in frames) + "data: [DONE]\n\n"
            return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
        return httpx.Response(
            200, json={"choices": [{"index": 0, "message": {"role": "assistant", "content": self.reply}}]}
        )


@pytest.fixture
def upstream() -> MockUpstream:
    return MockUpstream()


@pytest.fixture
def client(tmp_path: Path, upstream: MockUpstream):
    app = create_app(
        data_dir=tmp_path, upstream_transport=httpx.MockTransport(upstream), env_api_keys=[ADMIN_KEY]
    )
    with TestClient(app, base_url=BASE_URL, headers=AUTH) as c:
        yield c
    app.state.storage.close()


def _ingest(client: TestClient, text: str, session: str = "s", **extra: Any) -> Dict[str, Any]:
    resp = client.post("/v1/ingest", json={"session_id": session, "raw_payload": text, **extra})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_settling_preserves_project_scope(client: TestClient, tmp_path: Path) -> None:
    project_scope = scope_for(str(tmp_path / "one" / "app"))
    other_scope = scope_for(str(tmp_path / "two" / "app"))
    assert project_scope != other_scope
    assert project_scope == scope_for(str(tmp_path / "one" / "app" / ".." / "app"))
    signals = {"pin_constraint": True}
    _ingest(client, "Freeze production releases", scope=project_scope, external_signals=signals)
    _ingest(client, "Encrypt archival snapshots", scope=other_scope, external_signals=signals)
    _ingest(client, "Limit compiler parallelism", external_signals=signals)

    auto = _ingest(client, "What rules apply?", scope=project_scope, auto_settle=True)
    explicit = client.post(
        "/v1/settle", json={"session_id": "s", "intermediate_reasoning": "What rules apply?", "scope": project_scope}
    )
    assert explicit.status_code == 200
    for packet in (auto, explicit.json()["final_can_packet"]):
        pinned = "\n".join(packet["can_state"]["pinned_core"])
        assert "Freeze production releases" in pinned
        assert "Encrypt archival snapshots" not in pinned
        assert "Limit compiler parallelism" not in pinned


@pytest.mark.parametrize("stream", [False, True])
def test_proxy_unmasks_only_for_admin(client: TestClient, upstream: MockUpstream, monkeypatch, stream: bool) -> None:
    monkeypatch.setenv("ACA_UPSTREAM_LLM_URL", UPSTREAM)
    value = "5c3cc550-61de-4c6b-9198-83ee138c230a"
    pointer = client.post("/v1/gc/compress", json={"text": value}).json()["compressed_text"]
    upstream.reply = pointer
    key, _ = client.app.state.auth.create_key("test-writer", role="write")
    body = {"stream": stream, "messages": [{"role": "user", "content": "Return the pointer"}]}

    for key, expected in ((key, pointer), (ADMIN_KEY, value)):
        resp = client.post("/v1/proxy/chat/completions", json=body, headers={"Authorization": f"Bearer {key}"})
        assert resp.status_code == 200
        if stream:
            content = "".join(
                json.loads(line[6:])["choices"][0]["delta"].get("content", "")
                for line in resp.text.splitlines() if line.startswith("data: {")
            )
        else:
            content = resp.json()["choices"][0]["message"]["content"]
        assert content == expected


def test_recent_raw_log_offsets_survive_restart_and_partial_tail(tmp_path: Path, monkeypatch) -> None:
    def append(storage: CognitiveStorage, session: str, turn: int) -> None:
        storage.append_raw_log(session, turn, "test", "user_turn", f"Turn {turn} — ✓")

    storage = CognitiveStorage(tmp_path)
    try:
        for turn in range(1, 8):
            append(storage, "one", turn)
            append(storage, "two", turn)
        assert [entry.turn_id for entry in storage.get_recent_raw_entries("one", limit=6)] == list(range(2, 8))
        legacy_log = storage.raw_log_path.read_bytes().replace(b"\n", b"\r\n")
        storage.raw_log_path.write_bytes(legacy_log + b'{"session_id":')
    finally:
        storage.close()

    storage = CognitiveStorage(tmp_path)
    try:
        def fail_on_scan():
            pytest.fail("Recent reads should seek directly to the indexed records")

        with monkeypatch.context() as patch:
            patch.setattr(storage, "_iter_raw_entries", fail_on_scan)
            append(storage, "one", 8)
            entries = storage.get_recent_raw_entries("one")
            assert [entry.turn_id for entry in entries] == list(range(4, 9))
            assert entries[-1].raw_payload == "Turn 8 — ✓"
            assert [entry.turn_id for entry in storage.get_recent_raw_entries("two", limit=2)] == [6, 7]
    finally:
        storage.close()
    storage = CognitiveStorage(tmp_path)
    try:
        assert storage.get_recent_raw_entries("one", limit=1)[0].turn_id == 8
    finally:
        storage.close()


# 1. Contradictions must not be merged as near-duplicates
def test_conflicting_port_facts_are_kept_and_inhibit_each_other(client: TestClient) -> None:
    _ingest(client, "Postgres listens on port 5432 in dev")
    can = _ingest(client, "Postgres listens on port 5433 in dev")
    nodes = client.get("/v1/inspect/state", params={"session_id": "s"}).json()["nodes"]
    assert len(nodes) == 2
    assert all(n["links"]["inhibitory"] for n in nodes)
    assert can["can_state"]["contradictions"]


def test_identical_negative_constraint_is_merged_not_flagged(client: TestClient) -> None:
    text = "You must not deploy the billing service without explicit approval"
    _ingest(client, text)
    _ingest(client, text)
    nodes = client.get("/v1/inspect/state", params={"session_id": "s"}).json()["nodes"]
    assert len(nodes) == 1
    assert nodes[0]["links"]["inhibitory"] == {}


def test_short_fact_not_absorbed_into_longer_one(client: TestClient) -> None:
    _ingest(client, "Never deploy to production on Fridays or during the release freeze window")
    _ingest(client, "Never deploy to production")
    nodes = client.get("/v1/inspect/state", params={"session_id": "s"}).json()["nodes"]
    assert len(nodes) == 2


# 2. GC dictionary, turn counter and modulation survive a restart
def test_state_survives_restart(tmp_path: Path) -> None:
    path_text = "E:/workspace/some-long-project-name/src/module/file.py"
    app = create_app(data_dir=tmp_path, env_api_keys=[ADMIN_KEY])
    with TestClient(app, base_url=BASE_URL, headers=AUTH) as c:
        for _ in range(3):
            compressed = c.post("/v1/gc/compress", json={"text": path_text}).json()["compressed_text"]
        assert "<P_1>" in compressed
        _ingest(c, "first turn")
        _ingest(c, "second turn")
        c.post("/v1/outcome", json={"session_id": "s", "exit_code": 1, "test_status": "failed", "raw_output": "boom"})
        theta_before = c.get("/v1/inspect/state", params={"session_id": "s"}).json()["modulation"]["theta_in"]
    app.state.storage.close()

    app2 = create_app(data_dir=tmp_path, env_api_keys=[ADMIN_KEY])
    with TestClient(app2, base_url=BASE_URL, headers=AUTH) as c2:
        expanded = c2.post("/v1/gc/expand", json={"compressed_text": compressed}).json()["expanded_text"]
        assert expanded == path_text
        state = c2.get("/v1/inspect/state", params={"session_id": "s"}).json()
        assert state["modulation"]["theta_in"] == theta_before != 0.55
        assert _ingest(c2, "after restart")["turn_id"] == 4
    app2.state.storage.close()


def test_gc_is_shared_across_sessions(client: TestClient) -> None:
    for _ in range(3):
        client.post("/v1/gc/compress", json={"session_id": "a", "text": "E:/workspace/some-long-project-name/src/x.py"})
    compressed = client.post(
        "/v1/gc/compress", json={"session_id": "a", "text": "E:/workspace/some-long-project-name/src/x.py"}
    ).json()["compressed_text"]
    expanded = client.post("/v1/gc/expand", json={"session_id": "b", "compressed_text": compressed}).json()
    assert expanded["expanded_text"] == "E:/workspace/some-long-project-name/src/x.py"


# 3. Cross-origin browser access is refused
def test_no_cors_grant_for_foreign_origin(client: TestClient) -> None:
    resp = client.get("/v1/inspect/state", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in resp.headers


def test_foreign_host_header_rejected(client: TestClient) -> None:
    resp = client.get("/health", headers={"Host": "evil.example"})
    assert resp.status_code == 400


WS_URL = "ws://127.0.0.1:8420/v1/inspect/stream"  # websocket_connect ignores base_url


def test_websocket_rejects_foreign_origin(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS_URL, headers={"Origin": "https://evil.example", **AUTH}) as ws:
            ws.receive_json()
    assert exc.value.code == 1008


def test_websocket_accepts_same_origin(client: TestClient) -> None:
    with client.websocket_connect(WS_URL, headers={"Origin": BASE_URL, **AUTH}) as ws:
        assert ws.receive_json()["event"] == "connected"
        _ingest(client, "anything")
        assert ws.receive_json()["event"] == "firing_pass_completed"


# 4. Passing output that mentions "report"/"import" is not surprising
def test_passing_output_with_port_substring_not_surprising(client: TestClient) -> None:
    resp = client.post(
        "/v1/outcome",
        json={"session_id": "s", "test_status": "passed", "exit_code": 0, "raw_output": "12 passed; coverage report written"},
    ).json()
    assert resp["surprise"] < 0.5
    assert resp["write_gate_triggered"] is False


def test_prediction_is_consumed_by_one_outcome(client: TestClient) -> None:
    _ingest(client, "run the suite", prediction="tests will fail")
    first = client.post("/v1/outcome", json={"session_id": "s", "test_status": "failed", "exit_code": 1}).json()
    second = client.post("/v1/outcome", json={"session_id": "s", "test_status": "failed", "exit_code": 1}).json()
    assert first["surprise"] < 0.5  # failure was predicted
    assert second["surprise"] > 0.8  # stale prediction no longer applies


# 5. Refractory blocks firing on the next turn, then releases
def test_refractory_blocks_consecutive_turn(client: TestClient) -> None:
    _ingest(client, "Postgres listens on port 5432 in dev")
    fired = []
    for _ in range(3):
        can = _ingest(client, "postgres port listens dev")
        fired.append(any(t["fired"] for t in can["trace"]))
    assert fired[0] != fired[1]
    assert fired[1] != fired[2]


# 6. Resent history is tallied once
def test_single_message_does_not_promote_prefix(client: TestClient) -> None:
    msg = {"role": "user", "content": "look at E:/proj/some-long-folder-name/src/module/a.py"}
    resp = client.post(
        "/v1/proxy/chat/completions", json={"session_id": "p", "upstream_base_url": UPSTREAM, "messages": [msg]}
    )
    assert resp.status_code == 200, resp.text
    resp = client.post(
        "/v1/proxy/chat/completions",
        json={"session_id": "p", "upstream_base_url": UPSTREAM, "messages": [msg, {"role": "user", "content": "and?"}]},
    )
    assert client.get("/v1/inspect/state", params={"session_id": "p"}).json()["global_context"]["prefixes"] == {}


# 7. Proxy forwards to a real upstream, keeps the client system prompt, never fabricates
def test_proxy_without_upstream_is_503(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ACA_UPSTREAM_LLM_URL", raising=False)
    resp = client.post("/v1/proxy/chat/completions", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 503


def test_proxy_keeps_client_system_prompt(client: TestClient, upstream: MockUpstream) -> None:
    messages = [
        {"role": "system", "content": "You are a terse assistant."},
        *[{"role": "user", "content": f"message {i}"} for i in range(6)],
    ]
    resp = client.post(
        "/v1/proxy/chat/completions",
        json={"upstream_base_url": UPSTREAM, "messages": messages, "keep_last_n_raw_turns": 2},
    )
    assert resp.status_code == 200, resp.text
    sent = upstream.requests[-1]["messages"]
    assert any(m["role"] == "system" and m["content"] == "You are a terse assistant." for m in sent)
    assert [m["content"] for m in sent if m["role"] == "user"] == ["message 4", "message 5"]


def test_proxy_streams_upstream_and_hydrates_all_pointers(client: TestClient, upstream: MockUpstream) -> None:
    gc = client.app.state.engine.gc
    gc.compress("ran python script")  # interns C1 = python
    for _ in range(3):
        gc.compress("E:/workspace/some-long-project-name/src/x.py")
    upstream.reply = "Use C1 on <P_1>x.py now"
    text = ""
    with client.stream(
        "POST",
        "/v1/proxy/chat/completions",
        json={"upstream_base_url": UPSTREAM, "stream": True, "messages": [{"role": "user", "content": "go"}]},
    ) as resp:
        assert resp.status_code == 200
        for line in resp.iter_lines():
            if line.startswith("data: ") and line != "data: [DONE]":
                text += json.loads(line[6:])["choices"][0]["delta"].get("content", "")
    assert text == "Use python on E:/workspace/some-long-project-name/src/x.py now"
    assert upstream.requests[-1]["stream"] is True


# 8. Streaming hydration matches non-streaming expansion for plain entities
@pytest.mark.parametrize("chunks", [["use C1 now"], ["use C", "1 now"], ["use ", "C1", " now"]])
def test_stream_hydrator_expands_plain_entities(chunks: List[str]) -> None:
    gc = GCEngine()
    gc.compress("ran python script")
    hydrator = StreamHydrator(gc)
    assert "".join(hydrator.stream_hydrate(iter(chunks))) == gc.expand("use C1 now") == "use python now"


def test_stream_hydrator_does_not_expand_inside_long_words() -> None:
    gc = GCEngine()
    gc.compress("ran python script")
    word = "x" * 40 + "C1"
    hydrator = StreamHydrator(gc)
    assert "".join(hydrator.stream_hydrate(iter([word[:20], word[20:], " end"]))) == word + " end"


# 10. Input validation
def test_auto_settle_zero_passes_rejected(client: TestClient) -> None:
    resp = client.post("/v1/ingest", json={"raw_payload": "x", "auto_settle": True, "max_settle_passes": 0})
    assert resp.status_code == 422


def test_bad_seed_source_type_rejected(client: TestClient) -> None:
    resp = client.post(
        "/v1/ingest",
        json={"raw_payload": "x", "external_signals": {"seed_fragment": True, "source_type": "nonsense"}},
    )
    assert resp.status_code == 422


# Pasted logs must not become pinned rules; bad memories can be forgotten
def test_log_output_is_not_auto_pinned(client: TestClient) -> None:
    log = (
        'INFO:     Uvicorn running on http://127.0.0.1:8420 (Press CTRL+C to quit)\n'
        'INFO:     127.0.0.1:58102 - "WebSocket /v1/inspect/stream" 403\n'
        "INFO:     connection rejected (403 Forbidden)"
    )
    _ingest(client, log)
    nodes = client.get("/v1/inspect/state", params={"session_id": "s"}).json()["nodes"]
    assert not any(n["dynamics"]["pinned"] for n in nodes)


def test_long_text_with_rule_words_is_not_auto_pinned(client: TestClient) -> None:
    _ingest(client, "You must never do this. " + "filler text " * 60)
    nodes = client.get("/v1/inspect/state", params={"session_id": "s"}).json()["nodes"]
    assert not any(n["dynamics"]["pinned"] for n in nodes)


def test_forget_removes_memory_from_recall(client: TestClient) -> None:
    _ingest(client, "Never deploy the billing service on Fridays")
    node_id = client.get("/v1/inspect/state", params={"session_id": "s"}).json()["nodes"][0]["id"]
    assert client.delete(f"/v1/memory/{node_id}").status_code == 200
    can = _ingest(client, "deploy the billing service")
    assert not any("Fridays" in p for p in can["can_state"]["pinned_core"])
    assert client.delete(f"/v1/memory/{node_id}").status_code == 404
