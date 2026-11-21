"""Tier 2 (Immutable Raw Log) & Tier 3 (SQLite WAL + Debounced Memory-Mapped Graph State) Storage."""

from __future__ import annotations

from collections import defaultdict, deque
import json
import mmap
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from src.schemas import (
    EngineMode,
    FragmentDynamics,
    FragmentLinks,
    FragmentProvenance,
    FragmentResolutions,
    MemoryNode,
    NodeType,
    RawLogEntry,
)


class CognitiveStorage:
    """Manages the append-only `raw_log.jsonl` (Tier 2) and SQLite WAL + mmap graph store (Tier 3)."""

    RECENT_RAW_LIMIT = 5

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.raw_log_path = self.data_dir / "raw_log.jsonl"
        self.db_path = self.data_dir / "cognitive_store.db"
        self.mmap_path = self.data_dir / "graph_state.mmap"
        self._lock = threading.RLock()
        self._nodes_cache: Dict[str, MemoryNode] = {}
        self._turn_counters: Dict[str, int] = {}
        self._session_metadata: Dict[str, Dict[str, Any]] = {}
        self._recent_raw_offsets: dict[str, deque[int]] = defaultdict(
            lambda: deque(maxlen=self.RECENT_RAW_LIMIT)
        )
        self.mmap_sync_count: int = 0
        self.sqlite_tx_count: int = 0
        self._last_mmap_sync_ts: float = 0.0

        # Persistent connection with WAL mode enabled for low-latency batch transactions
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._init_sqlite()
        self._init_mmap()
        self._load_all_nodes()
        self._load_session_metadata()
        for offset, entry in self._iter_raw_entries():
            self._recent_raw_offsets[entry.session_id].append(offset)

    def _configure_wal_pragmas(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.execute("PRAGMA temp_store=MEMORY;")
        conn.execute("PRAGMA cache_size=-16000;")

    def _init_sqlite(self) -> None:
        with self._lock:
            self._configure_wal_pragmas(self._conn)
            self._conn.execute("BEGIN IMMEDIATE;")
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_nodes (
                    id TEXT PRIMARY KEY,
                    engine_mode TEXT NOT NULL,
                    node_type TEXT NOT NULL,
                    resolutions_json TEXT NOT NULL,
                    dynamics_json TEXT NOT NULL,
                    provenance_json TEXT NOT NULL,
                    links_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_metadata (
                    session_id TEXT PRIMARY KEY,
                    turn_id INTEGER NOT NULL,
                    modulation_json TEXT NOT NULL,
                    last_prediction TEXT
                )
                """
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS gc_state (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    state_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute("COMMIT;")

    def get_wal_status(self) -> Dict[str, Any]:
        with self._lock:
            journal_mode = self._conn.execute("PRAGMA journal_mode;").fetchone()[0]
            synchronous = self._conn.execute("PRAGMA synchronous;").fetchone()[0]
            return {
                "journal_mode": str(journal_mode).lower(),
                "synchronous": synchronous,
                "sqlite_tx_count": self.sqlite_tx_count,
                "mmap_sync_count": self.mmap_sync_count,
            }

    def _init_mmap(self, size_bytes: int = 262144) -> None:
        """Initialize memory-mapped file for fast activation/link vector state snapshots."""
        if not self.mmap_path.exists() or self.mmap_path.stat().st_size < size_bytes:
            with open(self.mmap_path, "wb") as f:
                f.write(b"\x00" * size_bytes)

    def _sync_mmap_state(self, force: bool = True, debounce_ms: float = 0.0) -> None:
        """Write compact activation and adjacency matrix snapshot to memory-mapped buffer once per pass."""
        now_ts = time.perf_counter()
        if not force and debounce_ms > 0.0 and (now_ts - self._last_mmap_sync_ts) * 1000.0 < debounce_ms:
            return

        snapshot = {
            nid: {
                "a": round(node.dynamics.activation, 4),
                "ref": node.dynamics.refractory_remaining,
                "res": node.dynamics.is_resident,
                "pin": node.dynamics.pinned,
                "exc": {k: round(v, 4) for k, v in node.links.excitatory.items()},
                "inh": {k: round(v, 4) for k, v in node.links.inhibitory.items()},
            }
            for nid, node in self._nodes_cache.items()
        }
        payload = json.dumps(snapshot, separators=(",", ":")).encode("utf-8")
        file_size = self.mmap_path.stat().st_size
        if len(payload) + 8 > file_size:
            new_size = max(file_size * 2, len(payload) + 65536)
            with open(self.mmap_path, "wb") as f:
                f.write(b"\x00" * new_size)

        with open(self.mmap_path, "r+b") as f:
            with mmap.mmap(f.fileno(), 0) as mm:
                mm.seek(0)
                length_header = f"{len(payload):08d}".encode("ascii")
                mm.write(length_header + payload)

        self._last_mmap_sync_ts = now_ts
        self.mmap_sync_count += 1

    def read_mmap_snapshot(self) -> Dict[str, Any]:
        """Read the memory-mapped graph state directly."""
        with self._lock:
            if not self.mmap_path.exists():
                return {}
            with open(self.mmap_path, "r+b") as f:
                with mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
                    header = mm[:8].decode("ascii", errors="ignore").strip("\x00").strip()
                    if not header or not header.isdigit():
                        return {}
                    length = int(header)
                    if length <= 0:
                        return {}
                    data = mm[8 : 8 + length].decode("utf-8", errors="ignore")
                    return json.loads(data)

    def _load_all_nodes(self) -> None:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT id, engine_mode, node_type, resolutions_json, dynamics_json, provenance_json, links_json FROM memory_nodes"
            )
            for row in cursor.fetchall():
                node = MemoryNode(
                    id=row[0],
                    engine_mode=EngineMode(row[1]),
                    node_type=NodeType(row[2]),
                    resolutions=FragmentResolutions(**json.loads(row[3])),
                    dynamics=FragmentDynamics(**json.loads(row[4])),
                    provenance=FragmentProvenance(**json.loads(row[5])),
                    links=FragmentLinks(**json.loads(row[6])),
                )
                self._nodes_cache[node.id] = node

    # -------------------------------------------------------------------------
    # Session metadata & GC dictionary persistence
    # -------------------------------------------------------------------------
    def _load_session_metadata(self) -> None:
        with self._lock:
            rows = self._conn.execute(
                "SELECT session_id, turn_id, modulation_json, last_prediction FROM session_metadata"
            ).fetchall()
            for session_id, turn_id, modulation_json, last_prediction in rows:
                self._turn_counters[session_id] = int(turn_id)
                self._session_metadata[session_id] = {
                    "modulation": json.loads(modulation_json) if modulation_json else {},
                    "last_prediction": last_prediction,
                }

    def get_session_metadata(self, session_id: str) -> Dict[str, Any]:
        return self._session_metadata.get(session_id, {})

    def _write_session_metadata(self, session_meta: Dict[str, Dict[str, Any]]) -> None:
        """Caller holds the lock and an open transaction."""
        for session_id, meta in session_meta.items():
            self._session_metadata[session_id] = meta
            self._conn.execute(
                """
                INSERT INTO session_metadata (session_id, turn_id, modulation_json, last_prediction)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    turn_id=excluded.turn_id,
                    modulation_json=excluded.modulation_json,
                    last_prediction=excluded.last_prediction
                """,
                (
                    session_id,
                    self._turn_counters.get(session_id, 0),
                    json.dumps(meta.get("modulation", {})),
                    meta.get("last_prediction"),
                ),
            )

    def _write_gc_state(self, gc_state: Dict[str, Any]) -> None:
        """Caller holds the lock and an open transaction."""
        self._conn.execute(
            "INSERT INTO gc_state (id, state_json) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET state_json=excluded.state_json",
            (json.dumps(gc_state, separators=(",", ":")),),
        )

    def load_gc_state(self) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT state_json FROM gc_state WHERE id = 1").fetchone()
            return json.loads(row[0]) if row else None

    def save_gc_state(self, gc_state: Dict[str, Any]) -> None:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE;")
            try:
                self._write_gc_state(gc_state)
                self._conn.execute("COMMIT;")
            except Exception:
                self._conn.execute("ROLLBACK;")
                raise

    # -------------------------------------------------------------------------
    # Tier 2: Immutable Append-Only Raw Log (`raw_log.jsonl`)
    # -------------------------------------------------------------------------
    def next_turn_id(self, session_id: str, explicit_turn_id: Optional[int] = None) -> int:
        with self._lock:
            if explicit_turn_id is not None:
                self._turn_counters[session_id] = max(
                    self._turn_counters.get(session_id, 0), explicit_turn_id
                )
                return explicit_turn_id
            self._turn_counters[session_id] = self._turn_counters.get(session_id, 0) + 1
            return self._turn_counters[session_id]

    def get_current_turn_id(self, session_id: str) -> int:
        return self._turn_counters.get(session_id, 0)

    def append_raw_log(
        self,
        session_id: str,
        turn_id: int,
        caller: str,
        event_type: str,
        raw_payload: str,
        gc_compressed_payload: str = "",
        external_signals: Optional[Dict[str, Any]] = None,
    ) -> RawLogEntry:
        """Append an immutable entry to `raw_log.jsonl`."""
        entry = RawLogEntry(
            event_id=f"evt_{uuid.uuid4().hex[:8]}",
            session_id=session_id,
            turn_id=turn_id,
            timestamp=datetime.now(timezone.utc).isoformat(),
            caller=caller,
            event_type=event_type,  # type: ignore[arg-type]
            raw_payload=raw_payload,
            gc_compressed_payload=gc_compressed_payload,
            external_signals=external_signals or {},
        )
        with self._lock:
            with self.raw_log_path.open("a+b") as f:
                f.seek(0, 2)
                if f.tell():
                    f.seek(-1, 2)
                    if f.read(1) != b"\n":
                        f.write(b"\n")
                offset = f.tell()
                f.write(entry.model_dump_json().encode("utf-8") + b"\n")
            self._recent_raw_offsets[session_id].append(offset)
        return entry

    def _iter_raw_entries(self) -> Iterator[tuple[int, RawLogEntry]]:
        if not self.raw_log_path.exists():
            return
        offset = 0
        with self.raw_log_path.open("rb") as f:
            for line in f:
                try:
                    entry = RawLogEntry.model_validate_json(line)
                except ValueError:
                    pass  # An interrupted append can leave an incomplete record
                else:
                    yield offset, entry
                offset += len(line)

    def get_recent_raw_entries(self, session_id: str, limit: int = RECENT_RAW_LIMIT) -> List[RawLogEntry]:
        """Read recent session records directly from the ledger by byte offset."""
        if limit <= 0:
            return []
        with self._lock:
            if limit > self.RECENT_RAW_LIMIT:
                return list(deque(
                    (entry for _, entry in self._iter_raw_entries() if entry.session_id == session_id),
                    maxlen=limit,
                ))
            offsets = list(self._recent_raw_offsets.get(session_id, ()))
            if not offsets:
                return []
            with self.raw_log_path.open("rb") as f:
                entries = []
                for offset in offsets[-limit:]:
                    f.seek(offset)
                    entries.append(RawLogEntry.model_validate_json(f.readline()))
                return entries

    # -------------------------------------------------------------------------
    # Tier 3: Persistent Memory Nodes (Single & Batch Transactional Writes)
    # -------------------------------------------------------------------------
    def upsert_nodes_batch(
        self,
        nodes: Optional[List[MemoryNode]] = None,
        sync_mmap: bool = True,
        debounce_ms: float = 0.0,
        gc_state: Optional[Dict[str, Any]] = None,
        session_meta: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[MemoryNode]:
        """Commit all node updates (plus optional GC dictionary and session metadata) in a single
        WAL SQLite transaction and sync `graph_state.mmap` once.
        """
        with self._lock:
            target_nodes = nodes if nodes is not None else list(self._nodes_cache.values())

            if target_nodes or gc_state is not None or session_meta:
                now = datetime.now(timezone.utc).isoformat()
                rows = [
                    (
                        n.id,
                        n.engine_mode.value,
                        n.node_type.value,
                        n.resolutions.model_dump_json(),
                        n.dynamics.model_dump_json(),
                        n.provenance.model_dump_json(),
                        n.links.model_dump_json(),
                        now,
                    )
                    for n in target_nodes
                ]
                self._conn.execute("BEGIN IMMEDIATE;")
                try:
                    self._conn.executemany(
                        """
                        INSERT INTO memory_nodes (
                            id, engine_mode, node_type, resolutions_json, dynamics_json, provenance_json, links_json, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(id) DO UPDATE SET
                            engine_mode=excluded.engine_mode,
                            node_type=excluded.node_type,
                            resolutions_json=excluded.resolutions_json,
                            dynamics_json=excluded.dynamics_json,
                            provenance_json=excluded.provenance_json,
                            links_json=excluded.links_json,
                            updated_at=excluded.updated_at
                        """,
                        rows,
                    )
                    if gc_state is not None:
                        self._write_gc_state(gc_state)
                    if session_meta:
                        self._write_session_metadata(session_meta)
                    self._conn.execute("COMMIT;")
                    self.sqlite_tx_count += 1
                except Exception:
                    self._conn.execute("ROLLBACK;")
                    raise

            for node in target_nodes:
                self._nodes_cache[node.id] = node

            if sync_mmap:
                self._sync_mmap_state(force=(debounce_ms <= 0.0), debounce_ms=debounce_ms)
            return target_nodes

    def upsert_node(self, node: MemoryNode, sync_mmap: bool = True) -> MemoryNode:
        self.upsert_nodes_batch([node], sync_mmap=sync_mmap)
        return node

    def bulk_save_nodes(self, nodes: Optional[List[MemoryNode]] = None, **persist_extras: Any) -> None:
        self.upsert_nodes_batch(nodes, sync_mmap=True, **persist_extras)

    def cache_node(self, node: MemoryNode) -> None:
        """Register a node in memory; it is written on the next batch commit."""
        with self._lock:
            self._nodes_cache[node.id] = node

    def get_node(self, node_id: str) -> Optional[MemoryNode]:
        return self._nodes_cache.get(node_id)

    def list_nodes(self, scope: Optional[str] = None, include_superseded: bool = False) -> List[MemoryNode]:
        nodes = list(self._nodes_cache.values())
        if scope:
            nodes = [n for n in nodes if n.provenance.scope in (scope, "global", "*")]
        if not include_superseded:
            nodes = [n for n in nodes if n.provenance.superseded_by is None]
        return nodes

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
