"""Scope alias registry — links kanban task ids and session scopes."""
from __future__ import annotations

from typing import Iterable

_ALIAS_SCHEMA = """
CREATE TABLE IF NOT EXISTS scope_aliases (
    scope_id TEXT NOT NULL,
    alias_scope_id TEXT NOT NULL,
    PRIMARY KEY (scope_id, alias_scope_id)
);
CREATE INDEX IF NOT EXISTS idx_scope_alias_reverse ON scope_aliases(alias_scope_id);
"""


def _ensure_alias_schema(conn) -> None:
    conn.executescript(_ALIAS_SCHEMA)
    conn.commit()


def register_from_scope_env() -> None:
    """Link JoyZoning scope and kanban task id when both are present."""
    from plugins.dietcode.lib.agent.joyzoning.config import read_scope_env

    ids = [
        x
        for x in (
            read_scope_env("HERMES_KANBAN_TASK"),
            read_scope_env("JOYZONING_SCOPE_ID"),
            read_scope_env("HERMES_SESSION_ID"),
        )
        if x
    ]
    if len(ids) >= 2:
        register_scope_aliases(*ids)


def register_scope_aliases(*scope_ids: str) -> None:
    """Bidirectionally link all non-empty scope ids in a convergence cluster."""
    ids = [str(s).strip() for s in scope_ids if s and str(s).strip()]
    unique = list(dict.fromkeys(ids))
    if len(unique) < 2:
        return

    from plugins.dietcode.lib.agent.joyzoning.journal import get_journal

    conn = get_journal()._conn()
    _ensure_alias_schema(conn)
    for a in unique:
        for b in unique:
            if a == b:
                continue
            conn.execute(
                """
                INSERT OR IGNORE INTO scope_aliases (scope_id, alias_scope_id)
                VALUES (?, ?)
                """,
                (a, b),
            )
    conn.commit()


def expand_scope_cluster(scope_id: str) -> list[str]:
    """Return scope_id plus any registered aliases (for gates and bridge)."""
    sid = str(scope_id or "").strip()
    if not sid:
        return ["default"]

    from plugins.dietcode.lib.agent.joyzoning.journal import get_journal

    conn = get_journal()._conn()
    _ensure_alias_schema(conn)
    rows = conn.execute(
        """
        SELECT alias_scope_id FROM scope_aliases WHERE scope_id = ?
        UNION
        SELECT scope_id FROM scope_aliases WHERE alias_scope_id = ?
        """,
        (sid, sid),
    ).fetchall()
    cluster = [sid]
    for row in rows:
        alias = str(row[0]).strip()
        if alias and alias not in cluster:
            cluster.append(alias)
    return cluster


def cluster_convergence_state(scope_ids: Iterable[str]):
    """Best convergence state across a scope cluster (prefer most advanced)."""
    from plugins.dietcode.lib.agent.joyzoning.convergence import ConvergenceState, get_convergence_state

    order = [
        ConvergenceState.CONVERGED,
        ConvergenceState.READY_FOR_REVIEW,
        ConvergenceState.VERIFYING,
        ConvergenceState.PATCHING,
        ConvergenceState.PROPOSED,
        ConvergenceState.REJECTED,
        ConvergenceState.IDLE,
    ]
    seen: dict[ConvergenceState, str] = {}
    for raw in scope_ids:
        for sid in expand_scope_cluster(raw):
            st = get_convergence_state(sid)
            seen[st] = sid
    for st in order:
        if st in seen:
            return st, seen[st]
    return ConvergenceState.IDLE, str(next(iter(scope_ids), "default"))
