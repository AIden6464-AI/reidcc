"""API-key auth: roles, browser sessions, key lifecycle, secret redaction, upstream override."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from src.api.auth import main as auth_cli
from src.api.server import create_app

BASE_URL = "http://127.0.0.1:8420"
WS_URL = "ws://127.0.0.1:8420/v1/inspect/stream"
ADMIN_KEY = "aca_test_admin_key"
SECRET = "5c3cc550-61de-4c6b-9198-83ee138c230a"


def _bearer(key: str) -> dict:
    return {"Authorization": f"Bearer {key}"}


@pytest.fixture
def app(tmp_path: Path):
    upstream = httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    )
    application = create_app(data_dir=tmp_path, upstream_transport=upstream, env_api_keys=[ADMIN_KEY])
    yield application
    application.state.storage.close()
    application.state.auth.close()


@pytest.fixture
def client(app):
    with TestClient(app, base_url=BASE_URL) as c:
        yield c


def _make_key(client: TestClient, role: str) -> str:
    resp = client.post("/v1/auth/keys", json={"name": f"{role}-key", "role": role}, headers=_bearer(ADMIN_KEY))
    assert resp.status_code == 201, resp.text
    return resp.json()["api_key"]


def test_endpoints_require_a_key(client: TestClient) -> None:
    assert client.get("/v1/inspect/state").status_code == 401
    assert client.post("/v1/ingest", json={"raw_payload": "x"}).status_code == 401
    assert client.get("/v1/inspect/state", headers=_bearer("aca_wrong")).status_code == 401
    assert client.get("/health").status_code == 200
    assert client.get("/inspector").status_code == 200


def test_x_api_key_header_accepted(client: TestClient) -> None:
    assert client.get("/v1/auth/me", headers={"X-API-Key": ADMIN_KEY}).json()["role"] == "admin"


def test_read_key_cannot_write_and_write_key_cannot_manage_keys(client: TestClient) -> None:
    read_key, write_key = _make_key(client, "read"), _make_key(client, "write")
    assert client.get("/v1/inspect/state", headers=_bearer(read_key)).status_code == 200
    assert client.post("/v1/ingest", json={"raw_payload": "x"}, headers=_bearer(read_key)).status_code == 403
    assert client.post("/v1/ingest", json={"raw_payload": "x"}, headers=_bearer(write_key)).status_code == 200
    assert client.get("/v1/auth/keys", headers=_bearer(write_key)).status_code == 403


def test_key_is_stored_hashed_and_shown_once(client: TestClient, app) -> None:
    key = _make_key(client, "write")
    listing = client.get("/v1/auth/keys", headers=_bearer(ADMIN_KEY)).json()
    assert key not in json.dumps(listing)
    assert key.encode() not in (Path(app.state.auth.db_path)).read_bytes()


def test_revoked_key_and_its_sessions_stop_working(client: TestClient) -> None:
    key = _make_key(client, "write")
    assert client.post("/v1/auth/login", json={"api_key": key}).status_code == 200
    assert client.get("/v1/auth/me").status_code == 200  # cookie session
    key_id = client.get("/v1/auth/me").json()["key_id"]
    assert client.delete(f"/v1/auth/keys/{key_id}", headers=_bearer(ADMIN_KEY)).status_code == 200
    assert client.get("/v1/auth/me").status_code == 401
    assert client.get("/v1/auth/me", headers=_bearer(key)).status_code == 401


def test_session_cookie_flags_and_logout(client: TestClient) -> None:
    resp = client.post("/v1/auth/login", json={"api_key": ADMIN_KEY})
    cookie = resp.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.post("/v1/auth/logout").status_code == 200
    assert client.get("/v1/auth/me").status_code == 401


def test_bad_login_rejected(client: TestClient) -> None:
    assert client.post("/v1/auth/login", json={"api_key": "aca_nope"}).status_code == 401


def test_cookie_session_refuses_cross_origin_writes(client: TestClient) -> None:
    client.post("/v1/auth/login", json={"api_key": ADMIN_KEY})
    resp = client.post("/v1/ingest", json={"raw_payload": "x"}, headers={"Origin": "https://evil.example"})
    assert resp.status_code == 403


def test_last_admin_key_cannot_be_revoked(tmp_path: Path) -> None:
    app = create_app(data_dir=tmp_path, env_api_keys=[])
    key, row = app.state.auth.create_key("only-admin", role="admin")
    with TestClient(app, base_url=BASE_URL, headers=_bearer(key)) as c:
        assert c.delete(f"/v1/auth/keys/{row['key_id']}").status_code == 409
    app.state.storage.close()
    app.state.auth.close()


def test_bootstrap_admin_key_created_on_first_start(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    app = create_app(data_dir=tmp_path, env_api_keys=[])
    with TestClient(app, base_url=BASE_URL):
        pass
    printed = capsys.readouterr().err
    key = next(w for w in printed.split() if w.startswith("aca_"))
    assert app.state.auth.authenticate_key(key).role == "admin"
    app.state.storage.close()
    app.state.auth.close()


def test_entropy_masks_redacted_for_non_admin(client: TestClient) -> None:
    write_key = _make_key(client, "write")
    client.post("/v1/ingest", json={"raw_payload": f"session {SECRET} expired"}, headers=_bearer(write_key))
    as_writer = client.get("/v1/inspect/state", headers=_bearer(write_key)).text
    as_admin = client.get("/v1/inspect/state", headers=_bearer(ADMIN_KEY)).text
    assert SECRET not in as_writer
    assert SECRET in as_admin


def test_only_admin_can_expand_masked_values(client: TestClient) -> None:
    read_key, write_key = _make_key(client, "read"), _make_key(client, "write")
    masked = client.post("/v1/gc/compress", json={"text": SECRET}, headers=_bearer(ADMIN_KEY))
    assert masked.status_code == 200
    pointer = masked.json()["compressed_text"]
    assert pointer != SECRET

    for key, expected in ((read_key, pointer), (write_key, pointer), (ADMIN_KEY, SECRET)):
        resp = client.post("/v1/gc/expand", json={"compressed_text": pointer}, headers=_bearer(key))
        assert resp.json()["expanded_text"] == expected

    for key, expected in ((write_key, pointer), (ADMIN_KEY, SECRET)):
        resp = client.post("/v1/outcome", json={"model_output_to_expand": pointer}, headers=_bearer(key))
        assert resp.json()["hydrated_model_output"] == expected


def test_only_admin_can_assign_legacy_memory_to_project(client: TestClient) -> None:
    write_key = _make_key(client, "write")
    body = {
        "raw_payload": "Freeze production changes",
        "scope": "repo:app",
        "external_signals": {"pin_constraint": True},
    }
    assert client.post("/v1/ingest", json=body, headers=_bearer(write_key)).status_code == 200
    node = client.get("/v1/inspect/state", headers=_bearer(ADMIN_KEY)).json()["nodes"][0]
    url = f"/v1/memory/{node['id']}/scope"
    target = {"scope": "repo-path:e:/work/app"}
    assert client.patch(url, json=target, headers=_bearer(write_key)).status_code == 403
    assert client.patch(url, json=target, headers=_bearer(ADMIN_KEY)).status_code == 200
    assert client.patch(url, json=target, headers=_bearer(ADMIN_KEY)).status_code == 200
    assert client.patch(
        url, json={"scope": "repo-path:e:/other/app"}, headers=_bearer(ADMIN_KEY)
    ).status_code == 409

    for scope, should_recall in ((target["scope"], True), ("repo-path:e:/other/app", False), ("repo:app", False)):
        resp = client.post(
            "/v1/ingest", json={"raw_payload": "deploy", "scope": scope}, headers=_bearer(write_key)
        )
        pinned = resp.json()["can_state"]["pinned_core"]
        assert any("Freeze production changes" in rule for rule in pinned) is should_recall


def test_websocket_requires_key_and_redacts_for_non_admin(client: TestClient) -> None:
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(WS_URL) as ws:
            ws.receive_json()
    assert exc.value.code == 1008

    read_key = _make_key(client, "read")
    with client.websocket_connect(WS_URL, headers=_bearer(read_key)) as ws:
        assert ws.receive_json()["event"] == "connected"
        client.post("/v1/ingest", json={"raw_payload": f"token {SECRET}"}, headers=_bearer(ADMIN_KEY))
        assert SECRET not in json.dumps(ws.receive_json())


def test_upstream_override_is_admin_only(client: TestClient) -> None:
    write_key = _make_key(client, "write")
    body = {"upstream_base_url": "http://169.254.169.254/latest", "messages": [{"role": "user", "content": "hi"}]}
    assert client.post("/v1/proxy/chat/completions", json=body, headers=_bearer(write_key)).status_code == 403
    assert client.post("/v1/proxy/chat/completions", json=body, headers=_bearer(ADMIN_KEY)).status_code == 200


def test_cli_creates_and_revokes_keys(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert auth_cli(["--data-dir", str(tmp_path), "create", "--name", "ci", "--role", "read"]) == 0
    key = next(w for w in capsys.readouterr().out.split() if w.startswith("aca_"))
    app = create_app(data_dir=tmp_path, env_api_keys=[])
    principal = app.state.auth.authenticate_key(key)
    assert principal.role == "read"
    assert auth_cli(["--data-dir", str(tmp_path), "revoke", principal.key_id]) == 0
    assert app.state.auth.authenticate_key(key) is None
    app.state.storage.close()
    app.state.auth.close()


def test_read_key_cannot_forget(client: TestClient) -> None:
    read_key = _make_key(client, "read")
    assert client.delete("/v1/memory/frag_x", headers=_bearer(read_key)).status_code == 403
