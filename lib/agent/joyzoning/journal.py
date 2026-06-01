"""Append-only execution journal — Hermes operational record (replayable)."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from hermes_constants import get_hermes_home

_SCHEMA = """
CREATE TABLE IF NOT EXISTS joyzoning_events (
    id TEXT PRIMARY KEY,
    timestamp REAL NOT NULL,
    layer TEXT NOT NULL,
    event_type TEXT NOT NULL,
    scope_id TEXT,
    session_id TEXT,
    run_id TEXT,
    correlation_id TEXT,
    payload TEXT
);
CREATE INDEX IF NOT EXISTS idx_jz_events_ts ON joyzoning_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_jz_events_scope ON joyzoning_events(scope_id, timestamp);

CREATE TABLE IF NOT EXISTS convergence_records (
    scope_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    summary TEXT,
    metadata TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS mutation_scopes (
    id TEXT PRIMARY KEY,
    scope_id TEXT NOT NULL,
    state TEXT NOT NULL,
    goal TEXT,
    metadata TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mut_scope ON mutation_scopes(scope_id);
"""

_journal: Optional["ExecutionJournal"] = None
_journal_lock = threading.Lock()


def _default_journal_path() -> Path:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config
        cfg = get_joyzoning_config()
        if cfg.journal_path:
            return Path(cfg.journal_path).expanduser()
    except Exception:
        pass
    return get_hermes_home() / "joyzoning" / "journal.db"


class ExecutionJournal:
    """SQLite-backed operational journal (Hermes authority — not habitat UI state)."""

    def __init__(self, db_path: Path):
        self._path = db_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript(_SCHEMA)
            conn.commit()
            self._local.conn = conn
        return conn

    def integrity_check(self) -> dict[str, Any]:
        """Lightweight PRAGMA integrity_check for operational diagnostics."""
        row = self._conn().execute("PRAGMA integrity_check").fetchone()
        ok = row is not None and str(row[0]).lower() == "ok"
        return {"success": ok, "result": str(row[0]) if row else "unknown"}

    def append_event(
        self,
        *,
        event_type: str,
        layer: str,
        scope_id: str = "",
        session_id: str = "",
        run_id: str = "",
        correlation_id: str = "",
        payload: Optional[dict[str, Any]] = None,
    ) -> str:
        eid = str(uuid.uuid4())
        now = time.time()
        self._conn().execute(
            """
            INSERT INTO joyzoning_events
            (id, timestamp, layer, event_type, scope_id, session_id, run_id, correlation_id, payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                eid,
                now,
                layer,
                event_type,
                scope_id or None,
                session_id or None,
                run_id or None,
                correlation_id or None,
                json.dumps(payload or {}, ensure_ascii=False),
            ),
        )
        self._conn().commit()
        return eid

    def list_events(
        self,
        *,
        since: float = 0.0,
        scope_id: Optional[str] = None,
        limit: int = 100,
        event_types: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        lim = max(1, min(limit, 500))
        query = "SELECT * FROM joyzoning_events WHERE timestamp >= ?"
        params: list[Any] = [since]
        if scope_id:
            query += " AND scope_id = ?"
            params.append(scope_id)
        if event_types:
            placeholders = ",".join("?" * len(event_types))
            query += f" AND event_type IN ({placeholders})"
            params.extend(event_types)
        query += " ORDER BY timestamp ASC LIMIT ?"
        params.append(lim)
        rows = self._conn().execute(query, params).fetchall()
        out = []
        for row in rows:
            item = dict(row)
            try:
                item["payload"] = json.loads(item.get("payload") or "{}")
            except json.JSONDecodeError:
                item["payload"] = {}
            out.append(item)
        return out

    def upsert_convergence(
        self,
        scope_id: str,
        *,
        state: str,
        summary: str = "",
        metadata: dict[str, Any],
        updated_at: float,
    ) -> None:
        conn = self._conn()
        existing = conn.execute(
            "SELECT created_at FROM convergence_records WHERE scope_id = ?",
            (scope_id,),
        ).fetchone()
        created = float(existing["created_at"]) if existing else updated_at
        conn.execute(
            """
            INSERT INTO convergence_records (scope_id, state, summary, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope_id) DO UPDATE SET
                state = excluded.state,
                summary = excluded.summary,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (scope_id, state, summary, json.dumps(metadata), created, updated_at),
        )
        conn.commit()

    def get_convergence(self, scope_id: str) -> Optional[dict[str, Any]]:
        row = self._conn().execute(
            "SELECT * FROM convergence_records WHERE scope_id = ?",
            (scope_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["metadata"] = json.loads(data.get("metadata") or "{}")
        except json.JSONDecodeError:
            data["metadata"] = {}
        return data

    def get_active_mutation(self, scope_id: str) -> Optional[dict[str, Any]]:
        """Most recently updated mutation scope row for a convergence scope."""
        row = self._conn().execute(
            """
            SELECT * FROM mutation_scopes
            WHERE scope_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (scope_id,),
        ).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["metadata"] = json.loads(data.get("metadata") or "{}")
        except json.JSONDecodeError:
            data["metadata"] = {}
        return data

    def upsert_mutation_scope(
        self,
        mutation_id: str,
        scope_id: str,
        *,
        state: str,
        goal: str = "",
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        now = time.time()
        meta = json.dumps(metadata or {}, ensure_ascii=False)
        self._conn().execute(
            """
            INSERT INTO mutation_scopes (id, scope_id, state, goal, metadata, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                state = excluded.state,
                goal = excluded.goal,
                metadata = excluded.metadata,
                updated_at = excluded.updated_at
            """,
            (mutation_id, scope_id, state, goal, meta, now, now),
        )
        self._conn().commit()


def get_journal() -> ExecutionJournal:
    global _journal
    if _journal is None:
        with _journal_lock:
            if _journal is None:
                _journal = ExecutionJournal(_default_journal_path())
    return _journal
