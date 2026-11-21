"""Universal FastAPI + WebSocket Server for ACA & The Firing System.

Exposes:
- GET  /inspector                  (Self-contained dark-mode Brain Inspector UI)
- POST /v1/ingest                  (4-stage dynamical pass + declarative constraint detection)
- POST /v1/settle                  (Recurrent settling loop)
- POST /v1/outcome                 (Surprise & progress modulation, POTENTIATE, Write Gate)
- POST /v1/proxy/chat/completions  (OpenAI-compatible drop-in proxy with SSE StreamHydrator)
- POST /v1/gc/compress & /v1/gc/expand
- GET  /v1/inspect/state & WS /v1/inspect/stream
- DELETE /v1/memory/{node_id}      (forget a memory)
- POST /v1/auth/login & /v1/auth/logout, GET /v1/auth/me
- GET/POST /v1/auth/keys, DELETE /v1/auth/keys/{key_id}   (admin)

Engine work is CPU-bound (and may call a remote embedding endpoint), so handlers run in the
threadpool and serialize on `engine.lock` instead of blocking the event loop.

Access control (the API exposes raw logs and unmasked GC values, so browsers must not reach it
from other sites):
- Every /v1 endpoint requires an API key (see src/api/auth.py for roles and the key CLI).
  /health and the static /inspector page are public; the inspector logs in with a key.
- ACA_API_KEYS: optional comma-separated admin keys supplied from the environment.
- ACA_UPSTREAM_API_KEY: key the proxy sends upstream (the caller's ACA key is never forwarded).
- ACA_ALLOWED_HOSTS: comma-separated Host header allowlist (default "127.0.0.1,localhost";
  "*" disables the check). Blocks DNS-rebinding.
- ACA_CORS_ORIGINS: comma-separated origins allowed cross-origin access (default: none).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import sys
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import urlsplit

import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from src.api.auth import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    AuthStore,
    Principal,
    bearer_or_header_key,
    redact_secrets,
)
from src.firing.firing_engine import FiringEngine
from src.gc.gc_engine import GCEngine
from src.gc.stream_hydrator import StreamHydrator
from src.schemas import (
    ApiKeyCreateRequest,
    CANPacket,
    ChatCompletionRequest,
    GCCompressRequest,
    GCCompressResponse,
    GCExpandRequest,
    GCExpandResponse,
    IngestRequest,
    LoginRequest,
    NodeType,
    OutcomeRequest,
    OutcomeResponse,
    ProjectScopeRequest,
    SettleRequest,
    SettleResponse,
    SourceTrustType,
)
from src.storage.store import CognitiveStorage


# Auto-pinning is for short statements a user makes, not pasted logs or tool output
MAX_AUTO_PIN_CHARS = 500
MAX_AUTO_PIN_LINES = 6
LOG_LINE_RE = re.compile(
    r"^\s*(?:INFO|DEBUG|WARN(?:ING)?|ERROR|TRACE|FATAL|CRITICAL)\b|^\s*\d{4}-\d{2}-\d{2}[ T]\d"
)


def _auto_pin_eligible(text: str) -> bool:
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(text) > MAX_AUTO_PIN_CHARS or len(lines) > MAX_AUTO_PIN_LINES:
        return False
    return not any(LOG_LINE_RE.match(ln) for ln in lines)


def _env_list(name: str, default: str) -> List[str]:
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


class WebSocketHub:
    """Manages connected WebSocket clients for `/v1/inspect/stream`.

    Events are produced on threadpool workers, so broadcasts are handed to the event loop
    that owns the sockets.
    """

    def __init__(self) -> None:
        self.connections: List[WebSocket] = []
        self.principals: Dict[int, Principal] = {}
        self.event_history: List[Dict[str, Any]] = []
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self._pending: Set[Any] = set()

    async def connect(self, ws: WebSocket, principal: Principal) -> None:
        await ws.accept()
        self.loop = asyncio.get_running_loop()
        self.connections.append(ws)
        self.principals[id(ws)] = principal

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.connections:
            self.connections.remove(ws)
        self.principals.pop(id(ws), None)

    def record_and_schedule_broadcast(self, event: Dict[str, Any]) -> None:
        self.event_history.append(event)
        if len(self.event_history) > 200:
            self.event_history = self.event_history[-200:]

        loop = self.loop
        if loop is None or loop.is_closed() or not self.connections:
            return
        try:
            running: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
        except RuntimeError:
            running = None

        pending: Any
        if running is loop:
            pending = loop.create_task(self.broadcast(event))
        else:
            pending = asyncio.run_coroutine_threadsafe(self.broadcast(event), loop)
        # Keep a reference until done so the task is not garbage-collected mid-flight
        self._pending.add(pending)
        pending.add_done_callback(self._pending.discard)

    async def broadcast(self, event: Dict[str, Any]) -> None:
        stale: List[WebSocket] = []
        redacted: Optional[Dict[str, Any]] = None
        for ws in list(self.connections):
            principal = self.principals.get(id(ws))
            if principal is not None and principal.can("admin"):
                outgoing = event
            else:
                redacted = redacted if redacted is not None else redact_secrets(event)
                outgoing = redacted
            try:
                await ws.send_json(outgoing)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)


def create_app(
    data_dir: Optional[str | Path] = None,
    upstream_transport: Optional[httpx.AsyncBaseTransport] = None,
    env_api_keys: Optional[List[str]] = None,
) -> FastAPI:
    """Build the app. `upstream_transport` lets tests substitute the upstream LLM transport;
    `env_api_keys` overrides ACA_API_KEYS."""
    resolved_dir = Path(
        data_dir or os.environ.get("ACA_DATA_DIR", Path(__file__).resolve().parents[2] / "data")
    )
    storage = CognitiveStorage(resolved_dir)
    auth = AuthStore(
        resolved_dir,
        env_keys=env_api_keys if env_api_keys is not None else _env_list("ACA_API_KEYS", ""),
    )
    ws_hub = WebSocketHub()
    engine = FiringEngine(
        storage=storage,
        event_broadcaster=ws_hub.record_and_schedule_broadcast,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Bootstrap on server start (not at import) so the key is printed where the operator sees it
        if not auth.has_any_key():
            key, row = auth.create_key("bootstrap-admin", role="admin")
            print(
                "\n" + "=" * 72 + "\n"
                "ACA: no API keys existed, so an admin key was created. It is shown only once:\n\n"
                f"    {key}\n\n"
                f"Use it to sign in at /inspector, then create per-client keys there.\n"
                f"Lost it? Run: python -m src.api.auth create --name admin --role admin\n"
                + "=" * 72 + "\n",
                file=sys.stderr,
                flush=True,
            )
        yield

    api = FastAPI(
        lifespan=lifespan,
        title="ACA + The Firing System Universal Cognitive API",
        version="2.0.0",
        description=(
            "Universal HTTP + WebSocket service implementing The Firing System "
            "(INJECT -> FIRE -> ADMIT -> COMPOSE) and Associative Context Activation (ACA) "
            "with the 4-tier CAN + GC wire data layout and Live Brain Inspector UI."
        ),
    )

    allowed_hosts = _env_list("ACA_ALLOWED_HOSTS", "127.0.0.1,localhost")
    cors_origins = _env_list("ACA_CORS_ORIGINS", "")
    if "*" not in allowed_hosts:
        api.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts)
    if cors_origins:
        api.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _origin_allowed(headers: Any) -> bool:
        origin = headers.get("origin")
        if not origin:
            return True  # non-browser client
        if origin in cors_origins:
            return True
        return urlsplit(origin).netloc == headers.get("host", "")

    def _authenticate(conn: Request | WebSocket) -> Optional[Principal]:
        key = bearer_or_header_key(conn.headers)
        if key:
            return auth.authenticate_key(key)
        return auth.authenticate_session(conn.cookies.get(SESSION_COOKIE, ""))

    def require(scope: str) -> Callable[[Request], Principal]:
        def dependency(request: Request) -> Principal:
            principal = _authenticate(request)
            if principal is None:
                raise HTTPException(
                    status_code=401,
                    detail="Missing or invalid API key",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            # Cookie sessions are ambient credentials: refuse state changes from other origins
            if request.method not in ("GET", "HEAD", "OPTIONS") and not _origin_allowed(request.headers):
                raise HTTPException(status_code=403, detail="Cross-origin request refused")
            if not principal.can(scope):
                raise HTTPException(
                    status_code=403, detail=f"This key's role ({principal.role}) lacks '{scope}' access"
                )
            return principal

        return dependency

    can_read = Depends(require("read"))
    can_write = Depends(require("write"))
    can_admin = Depends(require("admin"))

    def _scrub(model: BaseModel, principal: Principal) -> Any:
        """Entropy-mask values (tokens, GUIDs, hashes) are shown only to admin keys."""
        return model if principal.can("admin") else redact_secrets(model.model_dump())

    api.state.storage = storage
    api.state.engine = engine
    api.state.ws_hub = ws_hub
    api.state.auth = auth

    ui_path = Path(__file__).resolve().parents[1] / "ui" / "inspector.html"

    @api.get("/health")
    def health() -> Dict[str, Any]:
        return {"status": "ok", "service": "aca-firing-api", "version": api.version}

    # -------------------------------------------------------------------------
    # Auth: browser sessions and API key management
    # -------------------------------------------------------------------------
    def _principal_view(p: Principal) -> Dict[str, Any]:
        return {"key_id": p.key_id, "name": p.name, "role": p.role, "scopes": sorted(p.scopes)}

    @api.post("/v1/auth/login")
    def login(req: LoginRequest, request: Request, response: Response) -> Dict[str, Any]:
        if not _origin_allowed(request.headers):
            raise HTTPException(status_code=403, detail="Cross-origin request refused")
        principal = auth.authenticate_key(req.api_key.strip())
        if principal is None:
            raise HTTPException(status_code=401, detail="That API key is not valid or has been revoked")
        response.set_cookie(
            SESSION_COOKIE,
            auth.open_session(principal),
            max_age=SESSION_TTL_SECONDS,
            httponly=True,
            samesite="strict",
            secure=request.url.scheme == "https",
            path="/",
        )
        return _principal_view(principal)

    @api.post("/v1/auth/logout")
    def logout(request: Request, response: Response) -> Dict[str, str]:
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            auth.close_session(token)
        response.delete_cookie(SESSION_COOKIE, path="/")
        return {"status": "signed_out"}

    @api.get("/v1/auth/me")
    def whoami(principal: Principal = can_read) -> Dict[str, Any]:
        return _principal_view(principal)

    @api.get("/v1/auth/keys")
    def list_keys(_: Principal = can_admin) -> List[Dict[str, Any]]:
        return auth.list_keys()

    @api.post("/v1/auth/keys", status_code=201)
    def create_key(req: ApiKeyCreateRequest, _: Principal = can_admin) -> Dict[str, Any]:
        key, row = auth.create_key(req.name, req.role, req.expires_in_days)
        return {**row, "api_key": key}

    @api.delete("/v1/auth/keys/{key_id}")
    def revoke_key(key_id: str, _: Principal = can_admin) -> Dict[str, str]:
        target = next((k for k in auth.list_keys() if k["key_id"] == key_id and not k["revoked_at"]), None)
        if target is None:
            raise HTTPException(status_code=404, detail=f"No active key {key_id}")
        if target["role"] == "admin" and auth.active_admin_count() <= 1:
            raise HTTPException(status_code=409, detail="Refusing to revoke the last admin key")
        auth.revoke_key(key_id)
        return {"status": "revoked", "key_id": key_id}

    # -------------------------------------------------------------------------
    # 0. GET /inspector (Self-Contained Dark-Mode Brain Inspector Dashboard)
    # -------------------------------------------------------------------------
    @api.get("/inspector", response_class=HTMLResponse)
    async def serve_inspector_ui() -> HTMLResponse:
        if ui_path.exists():
            return HTMLResponse(content=ui_path.read_text(encoding="utf-8"), status_code=200)
        return HTMLResponse(content="<h1>Inspector UI file not found</h1>", status_code=404)

    # -------------------------------------------------------------------------
    # 1. POST /v1/ingest
    # -------------------------------------------------------------------------
    @api.post("/v1/ingest", response_model=CANPacket)
    def ingest_event(req: IngestRequest, principal: Principal = can_write) -> Any:
        seed_source_type: Optional[SourceTrustType] = None
        seed_node_type: Optional[NodeType] = None
        if req.external_signals.get("seed_fragment"):
            try:
                seed_source_type = SourceTrustType(
                    req.external_signals.get("source_type", SourceTrustType.DIRECT_CODE_OBSERVATION.value)
                )
                seed_node_type = NodeType(req.external_signals.get("node_type", NodeType.FRAGMENT.value))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"Invalid external_signals: {exc}") from exc

        with engine.lock:
            turn_id = storage.next_turn_id(req.session_id, req.turn_id)
            gc = engine.get_gc(req.session_id)
            compressed_payload = gc.compress(req.raw_payload)

            if req.prediction:
                engine.predictions[req.session_id] = req.prediction

            log_entry = storage.append_raw_log(
                session_id=req.session_id,
                turn_id=turn_id,
                caller=req.caller,
                event_type=req.event_type,
                raw_payload=req.raw_payload,
                gc_compressed_payload=compressed_payload,
                external_signals=req.external_signals,
            )

            # Upgraded Jev Constraint & Declarative Architectural Fact Detector
            is_decl_fact, decl_category, decl_score = engine.aca.classify_declarative_constraint(
                req.raw_payload
            )
            if req.external_signals.get("pin_constraint") or (
                req.event_type == "user_turn" and is_decl_fact and _auto_pin_eligible(req.raw_payload)
            ):
                is_hard_pin = bool(
                    req.external_signals.get("pin_constraint")
                    or "imperative_rule" in decl_category
                    or "runtime_os_constraint" in decl_category
                )
                engine.encode_or_refine_fragment(
                    session_id=req.session_id,
                    turn_id=turn_id,
                    raw_text=req.raw_payload,
                    source_event_id=log_entry.event_id,
                    source_type=(
                        SourceTrustType.USER_CONSTRAINT
                        if is_hard_pin
                        else SourceTrustType.VERIFIED_DECISION
                    ),
                    node_type=NodeType.CONSTRAINT if is_hard_pin else NodeType.DECISION,
                    pinned=is_hard_pin,
                    scope=req.scope,
                    initial_activation=max(0.85, decl_score),
                    persist_immediately=False,
                    compressed_text=compressed_payload,
                )
            elif seed_source_type is not None and seed_node_type is not None:
                engine.encode_or_refine_fragment(
                    session_id=req.session_id,
                    turn_id=turn_id,
                    raw_text=req.raw_payload,
                    source_event_id=log_entry.event_id,
                    source_type=seed_source_type,
                    node_type=seed_node_type,
                    pinned=bool(req.external_signals.get("pinned", False)),
                    scope=req.scope,
                    initial_activation=float(req.external_signals.get("initial_activation", 0.80)),
                    persist_immediately=False,
                    compressed_text=compressed_payload,
                )

            can_packet = engine.run_firing_pass(
                session_id=req.session_id,
                turn_id=turn_id,
                compressed_input=compressed_payload,
                raw_input=req.raw_payload,
                engine_mode=req.engine_mode,
                scope=req.scope,
                token_budget=req.token_budget,
                temperature_tau=req.temperature_tau,
                sample_fields_count=req.sample_fields_count,
            )

            if req.auto_settle:
                settle_res = engine.settle_recurrent(
                    session_id=req.session_id,
                    intermediate_reasoning=can_packet.can_state.full_narrative,
                    max_passes=req.max_settle_passes,
                    token_budget=req.token_budget,
                    scope=req.scope,
                    engine_mode=req.engine_mode,
                )
                can_packet = settle_res.final_can_packet

            return _scrub(can_packet, principal)

    # -------------------------------------------------------------------------
    # 2. POST /v1/settle
    # -------------------------------------------------------------------------
    @api.post("/v1/settle", response_model=SettleResponse)
    def settle_endpoint(req: SettleRequest, principal: Principal = can_write) -> Any:
        with engine.lock:
            result = engine.settle_recurrent(
                session_id=req.session_id,
                intermediate_reasoning=req.intermediate_reasoning,
                self_cue_gain=req.self_cue_gain,
                max_passes=req.max_passes,
                stability_jaccard_threshold=req.stability_jaccard_threshold,
                token_budget=req.token_budget,
                scope=req.scope,
            )
        return _scrub(result, principal)

    # -------------------------------------------------------------------------
    # 3. POST /v1/outcome
    # -------------------------------------------------------------------------
    @api.post("/v1/outcome", response_model=OutcomeResponse)
    def outcome_endpoint(req: OutcomeRequest, principal: Principal = can_write) -> Any:
        with engine.lock:
            result = engine.process_outcome(req, unmask=principal.can("admin"))
        return _scrub(result, principal)

    # -------------------------------------------------------------------------
    # 4. POST /v1/proxy/chat/completions (Supports Both Sync & SSE StreamHydrator)
    # -------------------------------------------------------------------------
    def _prepare_proxy_turn(
        req: ChatCompletionRequest,
    ) -> Tuple[List[Dict[str, str]], CANPacket, GCEngine]:
        """Run the firing pass for the latest message and build the pruned upstream prompt."""
        with engine.lock:
            gc = engine.get_gc(req.session_id)

            # Clients resend the full history every call; tally each message into the GC only once
            seen = engine.proxy_seen_messages.setdefault(req.session_id, set())
            for m in req.messages:
                key = hashlib.sha256(f"{m.role}\x00{m.content}".encode("utf-8")).hexdigest()
                if key not in seen:
                    gc.compress(m.content)
                    seen.add(key)
            compressed = [gc.compress(m.content, tally=False) for m in req.messages]

            latest_idx = next(
                (i for i in range(len(req.messages) - 1, -1, -1) if req.messages[i].role in ("user", "tool")),
                len(req.messages) - 1,
            )
            latest_raw = req.messages[latest_idx].content
            compressed_latest = compressed[latest_idx]

            turn_id = storage.next_turn_id(req.session_id)
            storage.append_raw_log(
                session_id=req.session_id,
                turn_id=turn_id,
                caller="openai_proxy",
                event_type="user_turn",
                raw_payload=latest_raw,
                gc_compressed_payload=compressed_latest,
            )

            can_packet = engine.run_firing_pass(
                session_id=req.session_id,
                turn_id=turn_id,
                compressed_input=compressed_latest,
                raw_input=latest_raw,
                engine_mode=req.engine_mode,
                token_budget=req.token_budget,
            )

            gc_directive = gc.build_system_prompt_directive()
            can_block = (
                "=== EPHEMERAL CANONICALIZED ATOMIC NARRATIVE (CAN) ===\n"
                f"PINNED CORE:\n- " + "\n- ".join(can_packet.can_state.pinned_core) + "\n"
                f"FULL NARRATIVE:\n{can_packet.can_state.full_narrative}\n"
                f"SUMMARIES:\n- " + ("\n- ".join(can_packet.can_state.summary_fragments) or "None") + "\n"
                f"AMBIENT POINTERS: {', '.join(can_packet.can_state.ambient_pointers) or 'None'}"
            )

            pruned_messages: List[Dict[str, str]] = [
                {"role": "system", "content": f"{gc_directive}\n\n{can_block}"}
            ]
            # Keep the client's own system prompt(s); prune only conversational history
            conversation: List[Dict[str, str]] = []
            for m, text in zip(req.messages, compressed):
                if m.role == "system":
                    pruned_messages.append({"role": "system", "content": text})
                else:
                    conversation.append({"role": m.role, "content": text})
            # Always forward at least the latest turn so the model has something to answer
            pruned_messages.extend(conversation[-max(1, req.keep_last_n_raw_turns) :])

            engine.persist_gc()
            return pruned_messages, can_packet, gc.snapshot()

    @api.post("/v1/proxy/chat/completions", response_model=None)
    async def proxy_chat_completions(req: ChatCompletionRequest, principal: Principal = can_write) -> Any:
        # A per-request upstream lets the caller point the server at arbitrary URLs (SSRF)
        if req.upstream_base_url and not principal.can("admin"):
            raise HTTPException(
                status_code=403, detail="Only admin keys may override upstream_base_url; set ACA_UPSTREAM_LLM_URL"
            )
        upstream_url = req.upstream_base_url or os.environ.get("ACA_UPSTREAM_LLM_URL")
        if not upstream_url:
            raise HTTPException(
                status_code=503,
                detail="No upstream LLM configured: set ACA_UPSTREAM_LLM_URL or pass upstream_base_url.",
            )
        if not req.messages:
            raise HTTPException(status_code=422, detail="messages must not be empty")

        pruned_messages, can_packet, gc_view = await run_in_threadpool(_prepare_proxy_turn, req)
        unmask = principal.can("admin")

        endpoint = f"{upstream_url.rstrip('/')}/chat/completions"
        headers = {"Content-Type": "application/json"}
        upstream_key = req.upstream_api_key or os.environ.get("ACA_UPSTREAM_API_KEY")
        if upstream_key:
            headers["Authorization"] = f"Bearer {upstream_key}"
        body: Dict[str, Any] = {
            "model": req.model,
            "messages": pruned_messages,
            "temperature": req.temperature,
        }
        if req.max_tokens is not None:
            body["max_tokens"] = req.max_tokens

        # SSE Streaming mode: relay upstream deltas through the stateful StreamHydrator
        if req.stream:
            client = httpx.AsyncClient(
                timeout=httpx.Timeout(60.0, connect=10.0), transport=upstream_transport
            )
            try:
                resp = await client.send(
                    client.build_request("POST", endpoint, headers=headers, json={**body, "stream": True}),
                    stream=True,
                )
            except httpx.HTTPError as exc:
                await client.aclose()
                raise HTTPException(status_code=502, detail=f"Upstream request failed: {exc}") from exc
            if resp.status_code >= 400:
                detail = (await resp.aread()).decode("utf-8", errors="replace")[:500]
                await resp.aclose()
                await client.aclose()
                raise HTTPException(
                    status_code=502, detail=f"Upstream returned HTTP {resp.status_code}: {detail}"
                )

            hydrator = StreamHydrator(gc_engine=gc_view, max_buffer_len=24, unmask=unmask)
            completion_id = f"chatcmpl-{uuid.uuid4().hex[:10]}"
            created_ts = int(time.time())

            def _frame(content: Optional[str], finish_reason: Optional[str]) -> str:
                delta = {"content": content} if content is not None else {}
                frame = {
                    "id": completion_id,
                    "object": "chat.completion.chunk",
                    "created": created_ts,
                    "model": req.model,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
                }
                return f"data: {json.dumps(frame)}\n\n"

            async def _sse_generator() -> AsyncIterator[str]:
                finish_reason = "stop"
                try:
                    async for line in resp.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line[len("data:") :].strip()
                        if data == "[DONE]":
                            break
                        try:
                            chunk_obj = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = chunk_obj.get("choices") or []
                        if not choices:
                            continue
                        piece = (choices[0].get("delta") or {}).get("content") or ""
                        hydrated_piece = hydrator.push_chunk(piece)
                        if hydrated_piece:
                            yield _frame(hydrated_piece, None)
                        if choices[0].get("finish_reason"):
                            finish_reason = choices[0]["finish_reason"]

                    tail_piece = hydrator.flush()
                    if tail_piece:
                        yield _frame(tail_piece, None)
                    yield _frame(None, finish_reason)
                    yield "data: [DONE]\n\n"
                finally:
                    await resp.aclose()
                    await client.aclose()

            return StreamingResponse(_sse_generator(), media_type="text/event-stream")

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0), transport=upstream_transport
            ) as client:
                resp = await client.post(endpoint, headers=headers, json=body)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Upstream request failed: {exc}") from exc
        if resp.status_code >= 400:
            raise HTTPException(
                status_code=502, detail=f"Upstream returned HTTP {resp.status_code}: {resp.text[:500]}"
            )
        try:
            data = resp.json()
            raw_assistant_reply = data["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise HTTPException(
                status_code=502, detail="Upstream response missing choices[0].message.content"
            ) from exc

        hydrated_reply = gc_view.expand(raw_assistant_reply, unmask=unmask)
        usage = data.get("usage") or {
            "prompt_tokens": can_packet.budget.used_tokens,
            "completion_tokens": len(hydrated_reply.split()),
            "total_tokens": can_packet.budget.used_tokens + len(hydrated_reply.split()),
        }

        return {
            "id": data.get("id", f"chatcmpl-{uuid.uuid4().hex[:10]}"),
            "object": "chat.completion",
            "created": int(time.time()),
            "model": req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": hydrated_reply,
                        "raw_gc_content": raw_assistant_reply,
                    },
                    "finish_reason": data["choices"][0].get("finish_reason", "stop"),
                }
            ],
            "usage": usage,
            "aca_metadata": {
                "can_id": can_packet.can_id,
                "pruned_messages_sent": len(pruned_messages),
                "original_messages_received": len(req.messages),
                "can_packet": can_packet.model_dump() if principal.can("admin") else redact_secrets(can_packet.model_dump()),
            },
        }

    # -------------------------------------------------------------------------
    # 5. POST /v1/gc/compress & POST /v1/gc/expand
    # -------------------------------------------------------------------------
    @api.post("/v1/gc/compress", response_model=GCCompressResponse)
    def gc_compress(req: GCCompressRequest, principal: Principal = can_write) -> Any:
        with engine.lock:
            gc = engine.get_gc(req.session_id)
            compressed = gc.compress(req.text, register_states=req.register_semantic_states)
            engine.persist_gc()
            orig_len = max(1, len(req.text))
            comp_len = len(compressed)
            result = GCCompressResponse(
                compressed_text=compressed,
                original_char_len=len(req.text),
                compressed_char_len=comp_len,
                compression_ratio=round(comp_len / orig_len, 4),
                global_context=gc.get_state(),
                system_prompt_directive=gc.build_system_prompt_directive(),
            )
        return _scrub(result, principal)

    @api.post("/v1/gc/expand", response_model=GCExpandResponse)
    def gc_expand(req: GCExpandRequest, principal: Principal = can_read) -> GCExpandResponse:
        with engine.lock:
            expanded = engine.get_gc(req.session_id).expand(
                req.compressed_text, unmask=req.unmask and principal.can("admin")
            )
        return GCExpandResponse(expanded_text=expanded)

    # -------------------------------------------------------------------------
    # 5b. DELETE /v1/memory/{node_id} (soft delete: superseded nodes are never recalled)
    # -------------------------------------------------------------------------
    @api.delete("/v1/memory/{node_id}")
    def forget_memory(node_id: str, principal: Principal = can_write) -> Dict[str, str]:
        with engine.lock:
            node = storage.get_node(node_id)
            if node is None or node.provenance.superseded_by:
                raise HTTPException(status_code=404, detail=f"No active memory {node_id}")
            node.provenance.superseded_by = f"forgotten_by:{principal.key_id}"
            node.dynamics.pinned = False
            node.dynamics.is_resident = False
            storage.upsert_node(node)
            for ids in (*engine.resident_sets.values(), *engine.prior_fired_sets.values()):
                ids.discard(node_id)
        return {"status": "forgotten", "node_id": node_id}

    @api.patch("/v1/memory/{node_id}/scope")
    def assign_project_scope(
        node_id: str, req: ProjectScopeRequest, principal: Principal = can_admin
    ) -> Dict[str, str]:
        """Assign a legacy memory to its verified project folder."""
        with engine.lock:
            node = storage.get_node(node_id)
            if node is None or node.provenance.superseded_by:
                raise HTTPException(status_code=404, detail=f"No active memory {node_id}")
            if node.provenance.scope != req.scope:
                if not node.provenance.scope.startswith("repo:"):
                    raise HTTPException(status_code=409, detail="Only legacy project memories can be reassigned")
                moved = node.model_copy(deep=True)
                moved.provenance.scope = req.scope
                storage.upsert_node(moved)
        return {"node_id": node_id, "scope": req.scope}

    # -------------------------------------------------------------------------
    # 6. GET /v1/inspect/state & WS /v1/inspect/stream
    # -------------------------------------------------------------------------
    @api.get("/v1/inspect/state")
    def inspect_state(session_id: str = "sess_01", principal: Principal = can_read) -> Dict[str, Any]:
        with engine.lock:
            nodes = storage.list_nodes(include_superseded=True)
            gc = engine.get_gc(session_id)
            mod = engine.get_modulation(session_id)
            last_can = engine.last_can_packets.get(session_id)
            raw_log = [e.model_dump() for e in storage.get_recent_raw_entries(session_id)]
            if not principal.can("admin"):
                # The raw ledger holds the original secrets; show the masked form instead
                for entry in raw_log:
                    entry["raw_payload"] = gc.expand(entry.get("gc_compressed_payload") or "", unmask=False)
            state = {
                "session_id": session_id,
                "turn_id": storage.get_current_turn_id(session_id),
                "wal_status": storage.get_wal_status(),
                "modulation": mod.model_dump(),
                "global_context": gc.get_state().model_dump(),
                "resident_ids": sorted(list(engine.resident_sets.get(session_id, set()))),
                "prior_fired_ids": sorted(list(engine.prior_fired_sets.get(session_id, set()))),
                "nodes": [n.model_dump() for n in nodes],
                "mmap_snapshot": storage.read_mmap_snapshot(),
                "last_can_packet": last_can.model_dump() if last_can else None,
                "recent_raw_log": raw_log,
                "viewer": _principal_view(principal),
            }
        return state if principal.can("admin") else redact_secrets(state)

    @api.websocket("/v1/inspect/stream")
    async def inspect_stream(websocket: WebSocket) -> None:
        # Browsers do not apply CORS to WebSockets, so check Origin explicitly
        if not _origin_allowed(websocket.headers):
            await websocket.close(code=1008)
            return
        principal = _authenticate(websocket)
        if principal is None or not principal.can("read"):
            await websocket.close(code=1008, reason="Missing or invalid API key")
            return
        await ws_hub.connect(websocket, principal)
        try:
            await websocket.send_json(
                {
                    "event": "connected",
                    "session_id": "all",
                    "recent_events_count": len(ws_hub.event_history),
                }
            )
            while True:
                msg = await websocket.receive_text()
                if msg == "ping":
                    await websocket.send_json({"event": "pong"})
        except WebSocketDisconnect:
            ws_hub.disconnect(websocket)

    return api


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.api.server:app", host="127.0.0.1", port=8420, reload=False)
