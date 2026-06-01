"""Plan → patch → verify → converge mutation lifecycle (Hermes runtime)."""
from __future__ import annotations

import uuid
from typing import Any, Optional

from plugins.dietcode.lib.agent.joyzoning.convergence import ConvergenceState, transition_convergence
from plugins.dietcode.lib.agent.joyzoning.config import resolve_scope_id
from plugins.dietcode.lib.agent.joyzoning.runtime_events import emit_runtime_event
from plugins.dietcode.lib.agent.joyzoning.journal import get_journal


def _latest_mutation_state(scope_id: str) -> Optional[str]:
    row = get_journal()._conn().execute(
        "SELECT state FROM mutation_scopes WHERE scope_id = ? ORDER BY updated_at DESC LIMIT 1",
        (scope_id,),
    ).fetchone()
    return str(row["state"]) if row else None


def begin_mutation(goal: str, *, scope_id: Optional[str] = None) -> dict[str, Any]:
    sid = resolve_scope_id(scope_id)
    mid = f"mut_{uuid.uuid4().hex[:12]}"
    get_journal().upsert_mutation_scope(mid, sid, state="proposed", goal=goal)
    result = transition_convergence(ConvergenceState.PROPOSED, scope_id=sid, summary=goal)
    if not result.get("success"):
        return result
    return {**result, "mutation_id": mid}


def _assert_mutation_scope(mutation_id: str, scope_id: str) -> Optional[dict[str, Any]]:
    row = get_journal()._conn().execute(
        "SELECT scope_id FROM mutation_scopes WHERE id = ?",
        (mutation_id,),
    ).fetchone()
    if not row:
        return {
            "success": False,
            "error": "unknown_mutation",
            "message": f"mutation_id {mutation_id!r} not found",
            "mutation_id": mutation_id,
        }
    owner = str(row["scope_id"] or "").strip()
    from plugins.dietcode.lib.agent.joyzoning.scope_registry import expand_scope_cluster
    cluster = expand_scope_cluster(scope_id)
    if owner not in cluster:
        return {
            "success": False,
            "error": "mutation_scope_mismatch",
            "message": f"mutation {mutation_id!r} belongs to scope {owner!r}, not {scope_id!r}",
            "mutation_id": mutation_id,
            "scope_id": scope_id,
        }
    return None


def record_patch(mutation_id: str, *, summary: str = "", scope_id: Optional[str] = None) -> dict[str, Any]:
    sid = resolve_scope_id(scope_id)
    bad = _assert_mutation_scope(mutation_id, sid)
    if bad:
        return bad
    get_journal().upsert_mutation_scope(mutation_id, sid, state="patching", goal=summary)
    return transition_convergence(
        ConvergenceState.PATCHING,
        scope_id=sid,
        summary=summary,
        metadata={"mutation_id": mutation_id},
    )


def record_verification(
    mutation_id: str,
    *,
    report: str,
    passed: bool = True,
    scope_id: Optional[str] = None,
) -> dict[str, Any]:
    sid = resolve_scope_id(scope_id)
    bad = _assert_mutation_scope(mutation_id, sid)
    if bad:
        return bad
    state = ConvergenceState.VERIFYING if passed else ConvergenceState.REJECTED
    get_journal().upsert_mutation_scope(
        mutation_id,
        sid,
        state="verified" if passed else "rejected",
        goal=report[:500],
        metadata={"passed": passed},
    )
    emit_runtime_event(
        "mutation.verified",
        scope_id=sid,
        payload={"mutation_id": mutation_id, "passed": passed, "report": report[:2000]},
    )
    if passed:
        return transition_convergence(
            ConvergenceState.VERIFYING,
            scope_id=sid,
            summary=report,
            metadata={"mutation_id": mutation_id},
        )
    return transition_convergence(
        ConvergenceState.REJECTED,
        scope_id=sid,
        summary=report,
        metadata={"mutation_id": mutation_id},
    )


def request_review(summary: str, *, scope_id: Optional[str] = None) -> dict[str, Any]:
    sid = resolve_scope_id(scope_id)
    from plugins.dietcode.lib.agent.joyzoning.convergence import get_convergence_state

    conv = get_convergence_state(sid)
    mut_state = _latest_mutation_state(sid)
    if mut_state not in ("verified", "verifying") and conv != ConvergenceState.VERIFYING:
        return {
            "success": False,
            "error": "verify_required",
            "message": (
                "Call mutation_verify with passed=true before convergence_request_review."
            ),
            "scope_id": sid,
            "mutation_state": mut_state,
            "convergence_state": conv.value,
        }

    emit_runtime_event(
        "convergence.review_requested",
        scope_id=sid,
        payload={"summary": summary},
    )
    try:
        from plugins.dietcode.lib.agent.joyzoning.jsdp_protocol import validate_handoff_sections
        handoff = validate_handoff_sections(summary)
        if handoff.get("success"):
            emit_runtime_event(
                "jsdp.handoff_validated",
                scope_id=sid,
                payload={"sections": handoff.get("found_sections", [])},
            )
    except Exception:
        pass

    return transition_convergence(
        ConvergenceState.READY_FOR_REVIEW,
        scope_id=sid,
        summary=summary,
    )
