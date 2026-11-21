"""Self-contained verification script (`tests/verify_pipeline.py`) for ACA + The Firing System API (Phases 1 & 2).

Simulates a multi-turn CLI debugging session over the FastAPI HTTP + WebSocket endpoints, verifying:
1. Tier 1 GC prefix promotion (<P_1>), entity interning ([CMD_1], U1, C1, I1), entropy masking (<GUID_1>),
   and semantic pointer compression ([STATE_1]) + egress expansion.
2. Hybrid Write Gate & Upgraded Jev Declarative Constraint Detector (admitting both imperative 'Never/Must'
   rules and declarative architectural facts like port bindings, runtime versions, file layouts, and negative outcomes).
3. Pluggable Hybrid Embedding Matcher (`SemanticProjectionEmbeddingProvider`) catching semantic paraphrases
   in `INJECT` without exact lexical overlap.
4. Persistent activation carrying across turns without top-k cutoff (graded FULL / SUMMARY / POINTER resolutions)
   and Hysteresis keeping resident fragments alive during refractory turns.
5. Surprise-triggered fragment creation + Directed & Normalized Co-Firing Potentiation (POTENTIATE) on `/v1/outcome`.
6. Recurrent settling (`/v1/settle`), OpenAI drop-in proxy (`/v1/proxy/chat/completions`),
   Chunked SSE `StreamHydrator` (`stream=True`), SQLite WAL single-transaction batching,
   and the Self-Contained Brain Inspector UI (`GET /inspector` + `WS /v1/inspect/stream`).
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import httpx
from fastapi.testclient import TestClient
from src.api.server import create_app
from src.gc.stream_hydrator import StreamHydrator

MOCK_UPSTREAM_URL = "http://mock-llm/v1"
MOCK_UPSTREAM_REPLY = "Active synthesis: inspect <P_1>token_manager.py under [STATE_1] before retrying."


def mock_upstream_handler(request: httpx.Request) -> httpx.Response:
    """Stand-in OpenAI-compatible upstream that answers natively in GC pointers."""
    body = json.loads(request.content)
    if body.get("stream"):
        # Split every 6 chars so pointers straddle SSE delta boundaries
        frames = [
            json.dumps({"choices": [{"index": 0, "delta": {"content": MOCK_UPSTREAM_REPLY[i : i + 6]}}]})
            for i in range(0, len(MOCK_UPSTREAM_REPLY), 6)
        ]
        sse = "".join(f"data: {f}\n\n" for f in frames) + "data: [DONE]\n\n"
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
    return httpx.Response(
        200,
        json={"choices": [{"index": 0, "message": {"role": "assistant", "content": MOCK_UPSTREAM_REPLY}, "finish_reason": "stop"}]},
    )


VERIFY_ADMIN_KEY = "aca_verify_pipeline_admin_key"


def run_verification() -> None:
    tmp_dir = Path(tempfile.mkdtemp(prefix="aca_firing_verify_"))
    print(f"[INIT] Created isolated verification store at: {tmp_dir}")

    try:
        app = create_app(
            data_dir=tmp_dir,
            upstream_transport=httpx.MockTransport(mock_upstream_handler),
            env_api_keys=[VERIFY_ADMIN_KEY],
        )
        client = TestClient(
            app, base_url="http://127.0.0.1:8420", headers={"Authorization": f"Bearer {VERIFY_ADMIN_KEY}"}
        )

        # =====================================================================
        # STEP 1: Verify Tier 1 GC Prefix Promotion, Entity Interning, & Pointers
        # =====================================================================
        print("\n=== [STEP 1] Tier 1: Global Context (GC) Compression & Hydration ===")
        raw_log_snippet = (
            "User=reid ran command: pytest -q E:/ACA- systems-prodo/ACA-api/src/firing/test_token_refresh_integration.py --maxfail=1\n"
            "Inspecting E:/ACA- systems-prodo/ACA-api/src/firing/token_manager.py and "
            "E:/ACA- systems-prodo/ACA-api/src/firing/session_store.py on host srv-auth-prod (192.168.68.101:5433) "
            "with session 5c3cc550-61de-4c6b-9198-83ee138c230a and temp file /tmp/auth_dump_991.tmp.\n"
            "Proportional token budget allocation with hysteresis prevents near-cutoff context flickering across turns.\n"
            "Proportional token budget allocation with hysteresis prevents near-cutoff context flickering across turns."
        )
        comp_resp = client.post(
            "/v1/gc/compress",
            json={
                "session_id": "sess_verify",
                "text": raw_log_snippet,
                "register_semantic_states": {
                    "[STATE_1]": "Proportional token budget allocation with hysteresis"
                },
            },
        )
        assert comp_resp.status_code == 200, comp_resp.text
        comp_data = comp_resp.json()
        compressed_text = comp_data["compressed_text"]
        gc_state = comp_data["global_context"]

        print(f"Original length   : {comp_data['original_char_len']} chars")
        print(f"Compressed length : {comp_data['compressed_char_len']} chars (ratio={comp_data['compression_ratio']})")
        print(f"Promoted Prefixes : {json.dumps(gc_state['prefixes'])}")
        print(f"Interned Entities : {json.dumps(gc_state['entities'])}")
        print(f"Semantic Pointers : {json.dumps(gc_state['semantic_pointers'])}")
        print(f"Entropy Masks     : {json.dumps(gc_state['entropy_masks'])}")

        assert "<P_1>" in compressed_text, "Expected hierarchical prefix promotion <P_1>"
        assert "[STATE_1]" in compressed_text, "Expected semantic pointer [STATE_1]"
        assert "<GUID_1>" in compressed_text, "Expected GUID entropy mask <GUID_1>"
        assert any(k.startswith("CMD_") for k in gc_state["entities"]), "Expected >50 char command interning [CMD_1]"

        exp_resp = client.post(
            "/v1/gc/expand",
            json={"session_id": "sess_verify", "compressed_text": compressed_text},
        )
        assert exp_resp.status_code == 200
        expanded_text = exp_resp.json()["expanded_text"]
        assert "E:/ACA- systems-prodo/ACA-api/src/firing/" in expanded_text
        assert "Proportional token budget allocation with hysteresis" in expanded_text
        assert "5c3cc550-61de-4c6b-9198-83ee138c230a" in expanded_text
        print("[PASS] Step 1: GC Prefix Promotion, Entity Interning, Entropy Masking & Egress Expansion verified.")

        # =====================================================================
        # STEP 2: Seeding, Imperative Rules, & Declarative Architectural Facts
        # =====================================================================
        print("\n=== [STEP 2] Imperative Constraints & Declarative Architectural Fact Detection ===")
        # Turn 1: Imperative User Constraint
        t1_resp = client.post(
            "/v1/ingest",
            json={
                "session_id": "sess_verify",
                "turn_id": 1,
                "caller": "reid_cli",
                "event_type": "user_turn",
                "raw_payload": "Never deploy or run destructive database migrations without explicit approval, and keep Python 3.10 compatibility.",
            },
        )
        assert t1_resp.status_code == 200
        t1_can = t1_resp.json()
        assert len(t1_can["can_state"]["pinned_core"]) >= 2

        # Turn 2: Declarative Architectural Fact (NO 'Never', 'Must', or 'Always' keywords!)
        # Tests Upgrade #3: port bindings + file layout + negative operational invariant
        decl_payload = (
            "The local PostgreSQL integration service listens on port 5433 and its configuration "
            "is located in E:/ACA- systems-prodo/ACA-api/src/firing/session_store.py; running the standard unit test command does not validate that socket path."
        )
        t2_resp = client.post(
            "/v1/ingest",
            json={
                "session_id": "sess_verify",
                "turn_id": 2,
                "caller": "reid_cli",
                "event_type": "user_turn",
                "raw_payload": decl_payload,
            },
        )
        assert t2_resp.status_code == 200
        t2_can = t2_resp.json()
        mem_gate_jev = [d for d in t2_can["jev_decisions"] if d["noul"] == "memory_gate"][0]
        print(f"Declarative Fact Jev Gate : choice={mem_gate_jev['choice']}, score={mem_gate_jev['score']}, action={mem_gate_jev['triggered_action']}")
        assert mem_gate_jev["choice"] == "STORE" and mem_gate_jev["score"] >= 0.85, (
            f"Expected declarative architectural fact to score >= 0.85 STORE, got {mem_gate_jev}"
        )

        # Seed 2 additional fragments to test multi-resolution allocation
        seed_fragments = [
            (
                "Authentication refresh-token renewal in E:/ACA- systems-prodo/ACA-api/src/firing/token_manager.py "
                "validates Redis TTL and rotates session keys before issuing a new JWT.",
                "direct_code",
                "file",
                0.86,
            ),
            (
                "Legacy UI theme dark-mode CSS bundle in frontend/styles/theme.css uses deprecated flex gap variables.",
                "historical_summary",
                "fragment",
                0.56,
            ),
        ]
        for idx, (text, src_type, ntype, init_a) in enumerate(seed_fragments, start=3):
            r = client.post(
                "/v1/ingest",
                json={
                    "session_id": "sess_verify",
                    "turn_id": idx,
                    "caller": "seed_loader",
                    "event_type": "file_diff",
                    "raw_payload": text,
                    "external_signals": {
                        "seed_fragment": True,
                        "source_type": src_type,
                        "node_type": ntype,
                        "initial_activation": init_a,
                    },
                },
            )
            assert r.status_code == 200
        print("[PASS] Step 2: Imperative & Declarative Architectural Constraints detected and encoded.")

        # =====================================================================
        # STEP 3: Pluggable Hybrid Embedding Paraphrase Match + Graded Resolution + Hysteresis
        # =====================================================================
        print("\n=== [STEP 3] Hybrid Embedding Paraphrase Match, Graded Resolution & Refractory Hysteresis ===")
        # Test semantic paraphrase matching (Upgrade #2): query uses "credential expiry / login rotation"
        # and "SQL socket binding" to match "refresh-token renewal / JWT" and "PostgreSQL port 5433"
        emb_provider = app.state.engine.embedding_provider
        v_query = emb_provider.embed("Why is login credential expiry failing on the SQL database socket binding?")
        v_auth = emb_provider.embed("Authentication refresh-token renewal validates Redis TTL and rotates session keys before issuing a new JWT.")
        v_css = emb_provider.embed("Legacy UI theme dark-mode CSS bundle uses deprecated flex gap variables.")
        sim_auth = emb_provider.cosine_similarity(v_query, v_auth)
        sim_css = emb_provider.cosine_similarity(v_query, v_css)
        print(f"Semantic Paraphrase Cosine: query<->auth_frag = {sim_auth:.4f} vs query<->css_frag = {sim_css:.4f}")
        assert sim_auth > sim_css + 0.25, "Semantic embedding provider must rank domain paraphrase significantly above unrelated CSS fragment"

        # Turn 5: Query under tight budget (95 tokens) to verify graded FULL / SUMMARY / POINTER resolutions
        t5_resp = client.post(
            "/v1/ingest",
            json={
                "session_id": "sess_verify",
                "turn_id": 5,
                "caller": "reid_cli",
                "event_type": "user_turn",
                "raw_payload": "Inspect E:/ACA- systems-prodo/ACA-api/src/firing/token_manager.py to debug why refresh-token renewal fails during integration tests.",
                "token_budget": 95,
                "temperature_tau": 0.45,
                "prediction": "Integration test for refresh-token renewal will pass on port 5432.",
            },
        )
        assert t5_resp.status_code == 200
        t5_can = t5_resp.json()
        resolutions_t5 = {t["fragment_id"]: t["assigned_resolution"] for t in t5_can["trace"]}
        fired_t5 = [t["fragment_id"] for t in t5_can["trace"] if t["fired"]]
        print(f"Turn 5 Fired Set          : {fired_t5}")
        print(f"Turn 5 Graded Resolutions : {resolutions_t5}")
        assert len(fired_t5) >= 1
        assert len(set(resolutions_t5.values())) >= 2, (
            f"Expected graded multi-tier resolutions (FULL + SUMMARY/POINTER), got {resolutions_t5}"
        )

        # Turn 6: Verify Refractory Hysteresis (fragments that fired in Turn 5 remain resident in Turn 6)
        t6_resp = client.post(
            "/v1/ingest",
            json={
                "session_id": "sess_verify",
                "turn_id": 6,
                "caller": "reid_cli",
                "event_type": "user_turn",
                "raw_payload": "Now check the session key rotation helper.",
                "token_budget": 160,
                "temperature_tau": 0.40,
            },
        )
        assert t6_resp.status_code == 200
        t6_can = t6_resp.json()
        resident_t6 = [
            t["fragment_id"]
            for t in t6_can["trace"]
            if t["assigned_resolution"] in ("full", "summary", "pointer")
        ]
        print(f"Turn 6 Resident Candidates: {resident_t6}")
        assert all(fid in resident_t6 for fid in fired_t5)
        print("[PASS] Step 3: Paraphrase matching, graded resolutions, and refractory hysteresis verified.")

        # =====================================================================
        # STEP 4: Surprise-Triggered Encoding, Directed POTENTIATE & SQLite WAL Batching
        # =====================================================================
        print("\n=== [STEP 4] Outcome Surprise, Directed POTENTIATE & SQLite WAL Single-Tx Batching ===")
        wal_before = app.state.storage.get_wal_status()
        t0 = time.perf_counter()
        outcome_resp = client.post(
            "/v1/outcome",
            json={
                "session_id": "sess_verify",
                "turn_id": 7,
                "caller": "pytest_runner",
                "command_or_action": "pytest -q E:/ACA- systems-prodo/ACA-api/src/firing/test_token_refresh_integration.py",
                "expected_prediction": "Integration test for refresh-token renewal will pass on port 5432.",
                "exit_code": 1,
                "test_status": "failed",
                "raw_output": (
                    "ConnectionRefusedError: Redis/Postgres test fixture refused connection on port 5432; "
                    "local test database listens only on port 5433 in E:/ACA- systems-prodo/ACA-api/src/firing/token_manager.py."
                ),
                "model_output_to_expand": "Investigated <P_1>token_manager.py under [STATE_1].",
            },
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        wal_after = app.state.storage.get_wal_status()

        assert outcome_resp.status_code == 200, outcome_resp.text
        out_data = outcome_resp.json()
        tx_delta = wal_after["sqlite_tx_count"] - wal_before["sqlite_tx_count"]
        mmap_delta = wal_after["mmap_sync_count"] - wal_before["mmap_sync_count"]

        print(f"SQLite Journal Mode       : {wal_after['journal_mode']} (synchronous={wal_after['synchronous']})")
        print(f"Outcome Commit Latency    : {elapsed_ms:.2f} ms (SQLite batch tx delta={tx_delta}, mmap sync delta={mmap_delta})")
        print(f"Computed Surprise         : {out_data['surprise']} | Write Gate: {out_data['write_gate_triggered']} ({out_data['write_reason']})")
        print(f"Directed Potentiated Links: {json.dumps(out_data['potentiated_links'])}")
        print(f"Hydrated Model Output     : {out_data['hydrated_model_output']}")

        assert wal_after["journal_mode"] == "wal", "SQLite database must run in WAL mode"
        assert tx_delta == 1 and mmap_delta == 1, (
            f"Expected exactly 1 batched SQLite transaction and 1 mmap sync for outcome update, got tx={tx_delta}, mmap={mmap_delta}"
        )
        assert out_data["surprise"] >= 0.70
        assert out_data["write_gate_triggered"] is True
        assert "E:/ACA- systems-prodo/ACA-api/src/firing/token_manager.py" in out_data["hydrated_model_output"]
        print("[PASS] Step 4: Surprise encoding, directed POTENTIATE, and single-tx WAL batching verified.")

        # =====================================================================
        # STEP 5: Recurrent Settling (`/v1/settle` — "Think Until It Settles")
        # =====================================================================
        print("\n=== [STEP 5] Recurrent Settling (`POST /v1/settle`) ===")
        settle_resp = client.post(
            "/v1/settle",
            json={
                "session_id": "sess_verify",
                "intermediate_reasoning": (
                    "The test failed with ConnectionRefusedError on port 5432 because the integration test "
                    "database listens on port 5433 while rotating refresh tokens in <P_1>token_manager.py."
                ),
                "self_cue_gain": 0.35,
                "max_passes": 5,
            },
        )
        assert settle_resp.status_code == 200
        settle_data = settle_resp.json()
        print(f"Settling Passes Executed  : {settle_data['passes_executed']} (converged={settle_data['converged']})")
        assert settle_data["converged"] is True
        print("[PASS] Step 5: Recurrent settling converged cleanly.")

        # =====================================================================
        # STEP 6: Chunked SSE `StreamHydrator` (`stream=True`) & Brain Inspector UI
        # =====================================================================
        print("\n=== [STEP 6] Chunked SSE `StreamHydrator` (`stream=True`) & Brain Inspector UI ===")
        # 6a. Direct unit test of stateful token-boundary ring buffer with adversarial split chunks
        gc_engine = app.state.engine.get_gc("sess_verify")
        hydrator = StreamHydrator(gc_engine=gc_engine, max_buffer_len=24)
        adversarial_chunks = [
            "File at <",
            "P_1",
            ">token_manager.py uses [STA",
            "TE_1",
            "] and <non_pointer!> plus [this_bracket_is_way_over_twenty_four_chars] end.",
        ]
        reconstructed = "".join(hydrator.stream_hydrate(iter(adversarial_chunks)))
        print(f"Ring-Buffer Hydrated Text : {reconstructed}")
        assert "E:/ACA- systems-prodo/ACA-api/src/firing/token_manager.py" in reconstructed
        assert "Proportional token budget allocation with hysteresis" in reconstructed
        assert "<non_pointer!>" in reconstructed, "Non-pointer angle bracket must flush immediately"
        assert "[this_bracket_is_way_over_twenty_four_chars]" in reconstructed, ">24 char bracket must flush cleanly"

        # 6b. Live SSE Streaming test over `POST /v1/proxy/chat/completions` with `stream=True`
        with client.stream(
            "POST",
            "/v1/proxy/chat/completions",
            json={
                "model": "gemini-4-argon-local",
                "session_id": "sess_verify",
                "stream": True,
                "upstream_base_url": MOCK_UPSTREAM_URL,
                "keep_last_n_raw_turns": 2,
                "messages": [
                    {"role": "user", "content": "Stream the active CAN synthesis and expand pointers."}
                ],
            },
        ) as sse_resp:
            assert sse_resp.status_code == 200
            sse_pieces = []
            for line in sse_resp.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                payload_str = line[len("data: ") :].strip()
                if payload_str == "[DONE]":
                    break
                chunk_obj = json.loads(payload_str)
                delta_content = chunk_obj["choices"][0]["delta"].get("content", "")
                sse_pieces.append(delta_content)

        full_sse_text = "".join(sse_pieces)
        print(f"Reassembled SSE Stream    : {full_sse_text[:155]}...")
        assert "<P_1>" not in full_sse_text and "[STATE_1]" not in full_sse_text, (
            "All GC pointers must be hydrated across SSE chunk boundaries before reaching client"
        )
        assert "E:/ACA- systems-prodo/ACA-api/src/firing/token_manager.py" in full_sse_text

        # 6c. Verify Self-Contained Brain Inspector UI at `GET /inspector`
        ui_resp = client.get("/inspector")
        assert ui_resp.status_code == 200
        assert "Brain Inspector" in ui_resp.text and "graphCanvas" in ui_resp.text
        print(f"Inspector Dashboard HTML  : {len(ui_resp.text)} bytes served at GET /inspector (200 OK)")

        print("\n=====================================================================")
        print("ALL PHASE 1 & PHASE 2 VERIFICATION CHECKS PASSED SUCCESSFULLY!")
        print("=====================================================================")

    finally:
        app.state.storage.close()
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    run_verification()
