"""API-key authentication for the ACA API.

Keys look like `aca_<43 url-safe chars>` (256 bits). Only a SHA-256 digest is stored, so the
plaintext is shown exactly once, when the key is created. Each key has a role:

- read:  GET /v1/inspect/state, WS /v1/inspect/stream, POST /v1/gc/expand
- write: read + ingest, settle, outcome, gc/compress, proxy
- admin: write + key management, unmasked entropy values, per-request `upstream_base_url`

Clients authenticate with `Authorization: Bearer <key>` or `X-API-Key: <key>`. The browser
inspector exchanges a key for an HttpOnly, SameSite=Strict session cookie via /v1/auth/login.

Keys can also be supplied through ACA_API_KEYS (comma-separated, admin role, not revocable over
the API). If neither exists on first start, a bootstrap admin key is created and printed once.

CLI (works while the server is stopped or running):
    python -m src.api.auth create --name ci --role write
    python -m src.api.auth list
    python -m src.api.auth revoke <key_id>
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

KEY_PREFIX = "aca_"
SESSION_COOKIE = "aca_session"
SESSION_TTL_SECONDS = 12 * 3600

ROLE_SCOPES: Dict[str, FrozenSet[str]] = {
    "read": frozenset({"read"}),
    "write": frozenset({"read", "write"}),
    "admin": frozenset({"read", "write", "admin"}),
}


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


@dataclass(frozen=True)
class Principal:
    key_id: str
    name: str
    role: str

    @property
    def scopes(self) -> FrozenSet[str]:
        return ROLE_SCOPES[self.role]

    def can(self, scope: str) -> bool:
        return scope in self.scopes


class AuthStore:
    """SQLite-backed key registry plus in-memory browser sessions."""

    def __init__(self, data_dir: str | Path, env_keys: Optional[List[str]] = None) -> None:
        self.db_path = Path(data_dir) / "auth.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                key_hash TEXT NOT NULL UNIQUE,
                display_prefix TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL,
                last_used_at REAL,
                revoked_at REAL
            )
            """
        )
        # Env keys are admin; compared by digest so the plaintext is not kept around
        self._env_digests: List[Tuple[str, str]] = [
            (f"env_{i + 1}", _digest(k)) for i, k in enumerate(env_keys or []) if k
        ]
        self._sessions: Dict[str, Tuple[Principal, float]] = {}

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------ keys
    def create_key(
        self, name: str, role: str = "write", expires_in_days: Optional[float] = None
    ) -> Tuple[str, Dict[str, Any]]:
        if role not in ROLE_SCOPES:
            raise ValueError(f"role must be one of {sorted(ROLE_SCOPES)}")
        key = generate_key()
        now = time.time()
        row = {
            "key_id": "key_" + secrets.token_hex(6),
            "name": name.strip() or "unnamed",
            "role": role,
            "display_prefix": key[: len(KEY_PREFIX) + 6],
            "created_at": now,
            "expires_at": now + expires_in_days * 86400 if expires_in_days else None,
            "last_used_at": None,
            "revoked_at": None,
        }
        with self._lock:
            self._conn.execute(
                "INSERT INTO api_keys (key_id, name, role, key_hash, display_prefix, created_at, expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (row["key_id"], row["name"], role, _digest(key), row["display_prefix"], now, row["expires_at"]),
            )
        return key, row

    def list_keys(self) -> List[Dict[str, Any]]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT key_id, name, role, display_prefix, created_at, expires_at, last_used_at, revoked_at"
                " FROM api_keys ORDER BY created_at"
            )
            cols = [c[0] for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]

    def active_admin_count(self) -> int:
        now = time.time()
        with self._lock:
            (n,) = self._conn.execute(
                "SELECT COUNT(*) FROM api_keys WHERE role = 'admin' AND revoked_at IS NULL"
                " AND (expires_at IS NULL OR expires_at > ?)",
                (now,),
            ).fetchone()
        return n + len(self._env_digests)

    def has_any_key(self) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM api_keys WHERE revoked_at IS NULL LIMIT 1"
            ).fetchone()
        return bool(row) or bool(self._env_digests)

    def revoke_key(self, key_id: str) -> bool:
        with self._lock:
            cur = self._conn.execute(
                "UPDATE api_keys SET revoked_at = ? WHERE key_id = ? AND revoked_at IS NULL",
                (time.time(), key_id),
            )
            # Drop browser sessions opened with this key
            for token, (p, _) in list(self._sessions.items()):
                if p.key_id == key_id:
                    del self._sessions[token]
            return cur.rowcount > 0

    def authenticate_key(self, key: str) -> Optional[Principal]:
        if not key:
            return None
        digest = _digest(key)
        for key_id, env_digest in self._env_digests:
            if hmac.compare_digest(digest, env_digest):
                return Principal(key_id=key_id, name=key_id, role="admin")
        if not key.startswith(KEY_PREFIX):
            return None
        now = time.time()
        with self._lock:
            row = self._conn.execute(
                "SELECT key_id, name, role, expires_at, revoked_at FROM api_keys WHERE key_hash = ?",
                (digest,),
            ).fetchone()
            if row is None:
                return None
            key_id, name, role, expires_at, revoked_at = row
            if revoked_at is not None or (expires_at is not None and expires_at <= now):
                return None
            self._conn.execute("UPDATE api_keys SET last_used_at = ? WHERE key_id = ?", (now, key_id))
        return Principal(key_id=key_id, name=name, role=role)

    # -------------------------------------------------------------- sessions
    def open_session(self, principal: Principal) -> str:
        token = secrets.token_urlsafe(32)
        with self._lock:
            self._sessions[_digest(token)] = (principal, time.time() + SESSION_TTL_SECONDS)
        return token

    def close_session(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(_digest(token), None)

    def authenticate_session(self, token: str) -> Optional[Principal]:
        if not token:
            return None
        with self._lock:
            entry = self._sessions.get(_digest(token))
            if entry is None:
                return None
            principal, expires_at = entry
            # Re-check the key so a revoke from the CLI (another process) ends sessions too
            if expires_at <= time.time() or not self._key_active(principal.key_id):
                del self._sessions[_digest(token)]
                return None
        return principal

    def _key_active(self, key_id: str) -> bool:
        if any(key_id == env_id for env_id, _ in self._env_digests):
            return True
        row = self._conn.execute(
            "SELECT 1 FROM api_keys WHERE key_id = ? AND revoked_at IS NULL"
            " AND (expires_at IS NULL OR expires_at > ?)",
            (key_id, time.time()),
        ).fetchone()
        return row is not None


def bearer_or_header_key(headers: Any) -> Optional[str]:
    auth = headers.get("authorization", "")
    if auth[:7].lower() == "bearer ":
        return auth[7:].strip()
    return headers.get("x-api-key") or None


def redact_secrets(obj: Any) -> Any:
    """Replace every `entropy_masks` value (tokens, GUIDs, hashes) with a placeholder."""
    if isinstance(obj, dict):
        return {
            k: ({tok: "[redacted]" for tok in v} if k == "entropy_masks" and isinstance(v, dict) else redact_secrets(v))
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [redact_secrets(v) for v in obj]
    return obj


def _default_data_dir() -> Path:
    return Path(os.environ.get("ACA_DATA_DIR", Path(__file__).resolve().parents[2] / "data"))


def _fmt_ts(ts: Optional[float]) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)) if ts else "-"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.api.auth", description="Manage ACA API keys")
    parser.add_argument("--data-dir", default=None, help="defaults to ACA_DATA_DIR or ./data")
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="create a key and print it once")
    c.add_argument("--name", required=True)
    c.add_argument("--role", choices=sorted(ROLE_SCOPES), default="write")
    c.add_argument("--expires-in-days", type=float, default=None)
    sub.add_parser("list", help="list keys (never prints secrets)")
    r = sub.add_parser("revoke", help="revoke a key by id")
    r.add_argument("key_id")
    args = parser.parse_args(argv)

    store = AuthStore(args.data_dir or _default_data_dir())
    try:
        if args.cmd == "create":
            key, row = store.create_key(args.name, args.role, args.expires_in_days)
            print(f"Created {row['key_id']} ({row['role']}) for '{row['name']}'.")
            print("Store this key now; it cannot be shown again:\n")
            print(f"  {key}\n")
        elif args.cmd == "list":
            rows = store.list_keys()
            if not rows:
                print("No keys.")
            for k in rows:
                status = "revoked" if k["revoked_at"] else "active"
                print(
                    f"{k['key_id']}  {k['display_prefix']}…  {k['role']:<5}  {status:<7}  "
                    f"created {_fmt_ts(k['created_at'])}  last used {_fmt_ts(k['last_used_at'])}  {k['name']}"
                )
        elif args.cmd == "revoke":
            if not store.revoke_key(args.key_id):
                print(f"No active key {args.key_id}.")
                return 1
            print(f"Revoked {args.key_id}.")
    finally:
        store.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
