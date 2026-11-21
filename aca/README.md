# ACA + The Firing System — Universal Cognitive API (`ACA-api` v2.0)

Universal, language-agnostic **HTTP + WebSocket API service** unifying **The Firing System** (`INJECT -> FIRE -> ADMIT -> COMPOSE`) and **Associative Context Activation (ACA)** (Typed Synapse Graph, Provenance Trust Calibration, Contradiction Networks, and Parallel **Jev** Decision Neurons) over the **4-Tier CAN + GC (Global Context)** wire data layout, complete with a **Live Brain Inspector UI**.

---

## Module Layout

- [`src/schemas.py`](file:///E:/Reidcc/aca/src/schemas.py) — Pydantic models for all 4 tiers (`GlobalContextState`, `RawLogEntry`, `MemoryNode`, `CANPacket`), Jev decisions, trace breakdowns, and API request/response contracts.
- [`src/gc/gc_engine.py`](file:///E:/Reidcc/aca/src/gc/gc_engine.py) — **Tier 1 (`GCEngine`)**:
  - `maskNarrativeData`: Regex entropy masking for GUIDs, Windows SIDs, `.tmp` files, Ansible/JWT tokens, hex hashes, and long numeric IDs.
  - `tallyPrefixes` & `promotePrefixes`: Hierarchical path prefix promotion (`> 30` chars, `>= 3` occurrences, longest common prefix wins) into `<P_1>`, `<P_2>`.
  - `internEntities`: Commands `> 50` chars (`[CMD_1]`), Users (`U1..Un`), Processes (`C1..Cn`), IPs (`I1..In`), Hosts (`W1..Wn`), and Compound Targets (`R1..Rn`).
  - `injectSemanticPointers` & `expand`: Maps recurring explanations and active states into `[STATE_1]` and hydrates them back on API egress.
- [`src/gc/stream_hydrator.py`](file:///E:/Reidcc/aca/src/gc/stream_hydrator.py) — **Streaming SSE Pointer Hydrator (`StreamHydrator`)**:
  - Stateful 24-character token-boundary ring buffer for `POST /v1/proxy/chat/completions` (`stream=True`). Buffers `<` and `[` openings across SSE delta boundaries until `>` or `]` arrives, hydrates matched GC pointers (`<P_x>`, `[STATE_x]`, `[CMD_x]`, `<GUID_x>`), and flushes immediately when a non-pointer character invalidates the pattern.
- [`src/firing/embedding_provider.py`](file:///E:/Reidcc/aca/src/firing/embedding_provider.py) — **Pluggable Hybrid Embedding Matcher (`EmbeddingProvider`)**:
  - `SemanticProjectionEmbeddingProvider`: Local 128-dim concept-subspace + stemmed subword/char-ngram projection that captures semantic paraphrases without exact lexical overlap.
  - `OpenAICompatibleEmbeddingProvider`: Pluggable client for `/v1/embeddings` (OpenAI, `llama-server`, vLLM, Ollama) with automatic local fallback.
- [`src/storage/store.py`](file:///E:/Reidcc/aca/src/storage/store.py) — **Tier 2 & Tier 3 (`CognitiveStorage`)**:
  - Append-only `raw_log.jsonl` ledger (never fed directly to the LLM).
  - Persistent SQLite store (`cognitive_store.db`) with `PRAGMA journal_mode=WAL;` and `PRAGMA synchronous=NORMAL;`, single-transaction batch writes (`upsert_nodes_batch`), and debounced once-per-pass `graph_state.mmap` synchronization.
- [`src/aca/aca_graph.py`](file:///E:/Reidcc/aca/src/aca/aca_graph.py) — **ACA Layer (`ACAGraphEngine`)**:
  - Calibrated provenance trust weights (`0.31`–`0.99`), mutual contradiction detection/inhibition, deterministic multi-field sampling (`sample_fields_for_agreement`), declarative architectural fact detection (`classify_declarative_constraint`), and parallel **Jev** decision neurons (`Noul`, `Choice`, `Score`).
- [`src/firing/firing_engine.py`](file:///E:/Reidcc/aca/src/firing/firing_engine.py) — **4-Stage Dynamical Pass (`FiringEngine`)**:
  - Hybrid `INJECT` matcher (GC exact hits + BM25 + trigram Jaccard + 128-dim feature-hash cosine + pluggable `EmbeddingProvider` semantic cosine).
  - Directed & row-normalized `POTENTIATE` ($W_{t-1} \to F_t$) with out-degree hub penalty and multiplicative link decay $\delta_w$.
  - Hybrid Write Gate combining Surprise encoding with imperative and declarative architectural fact admission.
  - Proportional token shares $\text{share}(f) = B \cdot \frac{w_f^{1/\tau}}{\sum w_g^{1/\tau}}$ with resolution hysteresis (`1.12` / `0.72`).
- [`src/ui/inspector.html`](file:///E:/Reidcc/aca/src/ui/inspector.html) & [`src/api/server.py`](file:///E:/Reidcc/aca/src/api/server.py) — **FastAPI + WebSocket Server & Brain Inspector Dashboard**:
  - Serves the zero-build dark-mode HTML/Canvas/JS dashboard at `GET /inspector` (`http://127.0.0.1:8420/inspector`), with key sign-in, a graph/list view, and an admin key manager.
- [`src/api/auth.py`](file:///E:/Reidcc/aca/src/api/auth.py) — API keys (hashed, role-scoped), browser sessions, secret redaction, and the `python -m src.api.auth` CLI.
- [`tests/verify_pipeline.py`](file:///E:/Reidcc/aca/tests/verify_pipeline.py) — Full Phase 1 & Phase 2 verification suite.

---

## Quickstart

### 1. Run the Test Suite
```powershell
cd "E:\Reidcc\aca"
pip install -e ".[dev]"
python -m pytest -q
```
`tests/test_regressions.py` covers persistence across restarts, contradiction handling, origin checks, refractory, proxy forwarding and stream hydration; `tests/verify_pipeline.py` is the end-to-end walkthrough (also runnable directly).

### 2. Start the Universal API Server & Brain Inspector UI
```powershell
cd "E:\Reidcc\aca"
uvicorn src.api.server:app --host 127.0.0.1 --port 8420
# Open http://127.0.0.1:8420/inspector in your browser
```
Or double-click `start.bat` (optionally `start.bat 8421` for another port). It runs the same app through `run.py`, which fixes the working directory and shuts the server down when you close its window. The module path is `src.api.server`, not `Api.server`, and uvicorn must be started from the repo root.
On first start the server prints a one-time **bootstrap admin key** to its console. Paste it into the inspector's sign-in screen, then use **API keys** (top right) to create a separate key per client.

### Authentication & API keys

Every `/v1/*` endpoint requires a key; `/health` and the `/inspector` page itself are public.

```bash
curl -H "Authorization: Bearer aca_..." http://127.0.0.1:8420/v1/inspect/state
# or: -H "X-API-Key: aca_..."
```

OpenAI-compatible clients pointed at `/v1/proxy/chat/completions` send their ACA key as the normal `api_key`. That key is **not** forwarded; the upstream key comes from `ACA_UPSTREAM_API_KEY` (or `upstream_api_key` in the request body).

| Role | Can |
|---|---|
| `read` | View state, the live stream, and `gc/expand` (masked values stay masked) |
| `write` | `read` + ingest, settle, outcome, `gc/compress`, proxy. Hydrated text keeps masked values as placeholders. |
| `admin` | `write` + manage keys, see unmasked secrets (tokens, GUIDs, hashes), override `upstream_base_url` |

Keys are stored only as SHA-256 hashes in `data/auth.db`, so a key is shown once, when created. Manage them from the inspector or the CLI:

```powershell
python -m src.api.auth create --name ci-runner --role write [--expires-in-days 90]
python -m src.api.auth list
python -m src.api.auth revoke key_1a2b3c4d5e6f
```

The browser inspector exchanges a key for an `HttpOnly`, `SameSite=Strict` session cookie (12 h). Revoking a key ends its sessions immediately. The last admin key cannot be revoked through the API.

### Claude Code integration

`integrations/claude_code/` connects Claude Code sessions to ACA:

- **`aca_hook.py`**: a hook script.
  - `UserPromptSubmit`: ingests each prompt (stated rules such as "never…" get pinned) and adds the recalled memories to Claude's context.
  - `PostToolUse`/`PostToolUseFailure` on `Bash`: reports test, build and lint runs as outcomes. Override which commands count with `ACA_OUTCOME_COMMANDS`.
  - The hook fails open: if the server is down, it does nothing.
- **`aca_mcp.py`**: an MCP server with tools `aca_remember`, `aca_recall`, `aca_report_outcome` and `aca_status`.
- **Scope** uses the resolved absolute project folder (`repo-path:e:/work/my-project` on Windows). `aca_remember(..., everywhere=true)` stores a global memory.
- **Existing project memories** retain their legacy `repo:<folder name>` scope and are visible in the inspector. A basename can belong to multiple folders, so an admin can assign each verified memory with `PATCH /v1/memory/{node_id}/scope` and the body `{"scope":"repo-path:e:/work/my-project"}`. Use the scope shown by `aca_status` in the destination folder.
- **Key:** both read the key from `ACA_API_KEY` or `~/.aca/claude_code.key` (use a `write` key), and the server URL from `ACA_URL` (default `http://127.0.0.1:8420`).

Setup:
```powershell
python -m src.api.auth create --name claude-code --role write   # save the key to ~/.aca/claude_code.key
claude mcp add --scope user aca -- python "E:/Reidcc/aca/integrations/claude_code/aca_mcp.py"
# and add the three hooks (UserPromptSubmit, PostToolUse/Bash, PostToolUseFailure/Bash) running aca_hook.py
```

### Configuration

| Env var | Default | Purpose |
|---|---|---|
| `ACA_API_KEYS` | — | Comma-separated admin keys from the environment (use long random values; not revocable via the API). |
| `ACA_UPSTREAM_API_KEY` | — | Bearer key the proxy sends to the upstream LLM. |
| `ACA_DATA_DIR` | `./data` | SQLite store, raw log, mmap snapshot. The GC dictionary, turn counters and modulation are persisted here too. |
| `ACA_UPSTREAM_LLM_URL` | — | Upstream for `/v1/proxy/chat/completions` (admin keys may pass `upstream_base_url` instead). Without one the proxy returns 503. |
| `ACA_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Host header allowlist (blocks DNS rebinding). Add your LAN IP/hostname if serving beyond localhost; `*` disables. |
| `ACA_CORS_ORIGINS` | none | Origins allowed cross-origin browser access. The inspector is same-origin and needs nothing here. |
| `ACA_EMBEDDING_URL` / `ACA_EMBEDDING_API_KEY` | — | Optional remote `/v1/embeddings` provider. |

The GC dictionary is **store-wide**, not per session: stored nodes hold GC-compressed text and are shared across sessions, so all sessions resolve pointers against one dictionary.
