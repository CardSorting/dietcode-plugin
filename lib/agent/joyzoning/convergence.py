"""Convergence state — Hermes-owned operational state (not habitat representation)."""
from __future__ import annotations

import json
import time
from enum import Enum
from typing import Any, Optional

from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, resolve_scope_id


class ConvergenceState(str, Enum):
    IDLE = "idle"
    PROPOSED = "proposed"
    PATCHING = "patching"
    VERIFYING = "verifying"
    READY_FOR_REVIEW = "ready_for_review"
    CONVERGED = "converged"
    REJECTED = "rejected"


_VALID_TRANSITIONS: dict[ConvergenceState, frozenset[ConvergenceState]] = {
    ConvergenceState.IDLE: frozenset({ConvergenceState.PROPOSED, ConvergenceState.PATCHING}),
    ConvergenceState.PROPOSED: frozenset({
        ConvergenceState.PATCHING,
        ConvergenceState.VERIFYING,
        ConvergenceState.READY_FOR_REVIEW,
        ConvergenceState.REJECTED,
    }),
    ConvergenceState.PATCHING: frozenset({
        ConvergenceState.VERIFYING,
        ConvergenceState.READY_FOR_REVIEW,
        ConvergenceState.REJECTED,
    }),
    ConvergenceState.VERIFYING: frozenset({
        ConvergenceState.READY_FOR_REVIEW,
        ConvergenceState.REJECTED,
        ConvergenceState.PATCHING,
    }),
    ConvergenceState.READY_FOR_REVIEW: frozenset({
        ConvergenceState.CONVERGED,
        ConvergenceState.REJECTED,
        ConvergenceState.PATCHING,
    }),
    ConvergenceState.CONVERGED: frozenset({ConvergenceState.IDLE, ConvergenceState.PROPOSED}),
    ConvergenceState.REJECTED: frozenset({ConvergenceState.IDLE, ConvergenceState.PROPOSED, ConvergenceState.PATCHING}),
}


def get_convergence_state(scope_id: Optional[str] = None) -> ConvergenceState:
    from plugins.dietcode.lib.agent.joyzoning.journal import get_journal
    sid = resolve_scope_id(scope_id)
    row = get_journal().get_convergence(sid)
    if not row:
        return ConvergenceState.IDLE
    try:
        return ConvergenceState(row["state"])
    except ValueError:
        return ConvergenceState.IDLE


def transition_convergence(
    new_state: ConvergenceState,
    *,
    scope_id: Optional[str] = None,
    summary: str = "",
    metadata: Optional[dict[str, Any]] = None,
    force: bool = False,
) -> dict[str, Any]:
    """Transition convergence state with validation and journaling."""
    from plugins.dietcode.lib.agent.joyzoning.journal import get_journal
    from plugins.dietcode.lib.agent.joyzoning.runtime_events import emit_runtime_event

    sid = resolve_scope_id(scope_id)
    current = get_convergence_state(sid)

    if not force and new_state not in _VALID_TRANSITIONS.get(current, frozenset()):
        return {
            "success": False,
            "error": f"invalid transition {current.value} → {new_state.value}",
            "scope_id": sid,
            "current_state": current.value,
        }

    now = time.time()
    get_journal().upsert_convergence(
        sid,
        state=new_state.value,
        summary=summary,
        metadata=metadata or {},
        updated_at=now,
    )

    event_type = {
        ConvergenceState.READY_FOR_REVIEW: "convergence.ready_for_review",
        ConvergenceState.CONVERGED: "convergence.converged",
        ConvergenceState.REJECTED: "convergence.rejected",
        ConvergenceState.PROPOSED: "mutation.proposed",
        ConvergenceState.VERIFYING: "mutation.verified",
        ConvergenceState.PATCHING: "mutation.patched",
    }.get(new_state, "convergence.state_changed")

    emit_runtime_event(
        event_type,
        scope_id=sid,
        payload={
            "from_state": current.value,
            "to_state": new_state.value,
            "summary": summary,
            "metadata": metadata or {},
        },
    )

    return {
        "success": True,
        "scope_id": sid,
        "previous_state": current.value,
        "state": new_state.value,
        "updated_at": now,
    }


def require_review_before_complete(scope_id: Optional[str] = None) -> Optional[str]:
    """Return block message if kanban_complete should wait for convergence."""
    cfg = get_joyzoning_config()
    if not cfg.enabled or not cfg.review_before_complete:
        return None

    from plugins.dietcode.lib.agent.joyzoning.scope_registry import cluster_convergence_state, expand_scope_cluster

    sid = resolve_scope_id(scope_id)
    state, _ = cluster_convergence_state(expand_scope_cluster(sid))
    if state == ConvergenceState.READY_FOR_REVIEW:
        return (
            "Convergence gate: task is ready for review. "
            "Call convergence_mark_converged (or operator approval flow) before kanban_complete."
        )

    if state == ConvergenceState.CONVERGED:
        return None

    if state == ConvergenceState.IDLE:
        return (
            "Convergence gate: no mutation lifecycle recorded for this scope. "
            "Use mutation_begin → mutation_verify → convergence_request_review, "
            "then operator accept-merge in JoyZoning before kanban_complete."
        )

    return (
        f"Convergence gate: scope is in state '{state.value}'. "
        "Complete mutation → verify → convergence_request_review → "
        "convergence_mark_converged before kanban_complete."
    )
