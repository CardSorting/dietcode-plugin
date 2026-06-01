"""JoyZoning workflow hints — what the agent should do next (Hermes authority)."""
from __future__ import annotations

from typing import Any, Optional

from plugins.dietcode.lib.agent.joyzoning.convergence import ConvergenceState
from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, read_scope_env, resolve_scope_id


def _scope_bindings() -> dict[str, str]:
    keys = (
        "JOYZONING_SCOPE_ID",
        "HERMES_KANBAN_TASK",
        "HERMES_KANBAN_BOARD",
        "HERMES_KANBAN_RUN_ID",
        "HERMES_SESSION_ID",
    )
    out: dict[str, str] = {}
    for key in keys:
        val = read_scope_env(key)
        if val:
            out[key] = val
    return out


def _merge_harness_next_actions(
    base: list[str],
    harness: dict[str, Any] | None,
) -> list[str]:
    if not harness or not harness.get("harness_present"):
        return base
    hint = "jsdp(action='start') — autonomous rolling horizon (see jsdp_autonomous in context)"
    if hint in base:
        return base
    return [hint, *base]


def recommended_next_actions(state: ConvergenceState) -> list[str]:
    """Human- and model-readable next steps for the governed mutation lifecycle."""
    if state == ConvergenceState.IDLE:
        return [
            "joyzoning(action='begin', goal='…') or mutation_begin(goal=…)",
            "If JSDP: joyzoning(action='role_context') first",
        ]
    if state == ConvergenceState.PROPOSED:
        return [
            "Implement the plan (patch/write tools)",
            "joyzoning(action='patch', mutation_id=…, summary='…') after substantive edits",
        ]
    if state == ConvergenceState.PATCHING:
        return [
            "Run verification (tests, lint)",
            "joyzoning(action='verify', mutation_id=…, report='…')",
        ]
    if state == ConvergenceState.VERIFYING:
        return [
            "joyzoning(action='request_review', summary='…')",
        ]
    if state == ConvergenceState.READY_FOR_REVIEW:
        return [
            "Stop — operator reviews the change out-of-band",
            "After approval: convergence_mark_converged(...) then kanban_complete(...)",
        ]
    if state == ConvergenceState.CONVERGED:
        return [
            "kanban_complete(...) is allowed when review gate satisfied",
        ]
    if state == ConvergenceState.REJECTED:
        return [
            "joyzoning(action='begin', goal='…') to start a new mutation scope",
        ]
    return ["joyzoning(action='context') to refresh state"]


def _resolve_cluster(scope_id: str) -> tuple[ConvergenceState, str, list[str]]:
    from plugins.dietcode.lib.agent.joyzoning.convergence import get_convergence_state
    from plugins.dietcode.lib.agent.joyzoning.scope_registry import cluster_convergence_state, expand_scope_cluster

    cluster = expand_scope_cluster(scope_id)
    state, anchor = cluster_convergence_state(cluster)
    if state == ConvergenceState.IDLE and anchor:
        state = get_convergence_state(anchor)
    return state, anchor or scope_id, cluster


def build_operational_context(*, scope_id: str | None = None) -> dict[str, Any]:
    """Unified situational snapshot for the joyzoning primitive tool."""
    cfg = get_joyzoning_config()
    sid = resolve_scope_id(scope_id)
    state, anchor_scope, scope_cluster = _resolve_cluster(sid)
    bindings = _scope_bindings()

    journal_row = None
    active_mutation: Optional[dict[str, Any]] = None
    journal_integrity: dict[str, Any] = {"success": True}
    try:
        from plugins.dietcode.lib.agent.joyzoning.journal import get_journal
        journal = get_journal()
        journal_row = journal.get_convergence(anchor_scope)
        active_mutation = journal.get_active_mutation(anchor_scope)
        journal_integrity = journal.integrity_check()
    except Exception as exc:
        journal_integrity = {"success": False, "error": str(exc)}

    gate_message = None
    try:
        from plugins.dietcode.lib.agent.joyzoning.convergence import require_review_before_complete
        gate_message = require_review_before_complete(anchor_scope)
    except Exception:
        pass

    jsdp_harness: dict[str, Any] | None = None
    try:
        from plugins.dietcode.lib.agent.joyzoning.jsdp_autonomous import session_brief
        jsdp_harness = session_brief()
    except Exception:
        pass

    return {
        "success": True,
        "scope_id": sid,
        "anchor_scope_id": anchor_scope,
        "scope_cluster": scope_cluster,
        "convergence_state": state.value,
        "kanban_complete_allowed": gate_message is None,
        "kanban_complete_block_reason": gate_message,
        "scope_bindings": bindings,
        "active_mutation": active_mutation,
        "config": {
            "enabled": cfg.enabled,
            "review_before_complete": cfg.review_before_complete,
            "execution_journal": cfg.execution_journal,
            "jsdp_enabled": cfg.jsdp_enabled,
            "jsdp_role": cfg.jsdp_role or None,
            "jsdp_harness_enabled": cfg.jsdp_harness_enabled,
        },
        "jsdp_harness": jsdp_harness,
        "convergence_record": journal_row,
        "journal_integrity": journal_integrity,
        "next_actions": _merge_harness_next_actions(recommended_next_actions(state), jsdp_harness),
        "authority": {
            "execution": "hermes",
            "convergence": "hermes_journal",
            "merge_gate": "convergence_mark_converged",
        },
    }
