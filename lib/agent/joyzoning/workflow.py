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


def _merge_steering_next_actions(
    base: list[str],
    *,
    jsdp_harness: dict[str, Any] | None = None,
    roadmap_brief: dict[str, Any] | None = None,
) -> list[str]:
    hints: list[str] = []
    if jsdp_harness and jsdp_harness.get("harness_present"):
        jsdp_hint = "jsdp(action='start') — autonomous rolling horizon (see jsdp_harness in context)"
        if jsdp_hint not in base:
            hints.append(jsdp_hint)

    if roadmap_brief and roadmap_brief.get("enabled"):
        phase = roadmap_brief.get("phase")
        first_call = roadmap_brief.get("first_call") or "roadmap(action='guide')"
        roadmap_path = roadmap_brief.get("roadmap_path")
        if roadmap_path:
            path_hint = f"ROADMAP.md lives at {roadmap_path} — out-of-workspace writes blocked"
            if path_hint not in base and path_hint not in hints:
                hints.append(path_hint)

        identity = roadmap_brief.get("steering_brief") or roadmap_brief.get("steering_identity") or roadmap_brief.get("project_name")
        if identity:
            id_hint = f"Project steering: {identity}"
            if id_hint not in base and id_hint not in hints:
                hints.append(id_hint)

        ci = roadmap_brief.get("ci_systems") or []
        if ci:
            ci_hint = f"CI: {ci[0]}"
            if ci_hint not in base and ci_hint not in hints:
                hints.append(ci_hint)

        git_remote = roadmap_brief.get("git_remote")
        if git_remote:
            origin_hint = f"Origin: {git_remote}"
            if origin_hint not in base and origin_hint not in hints:
                hints.append(origin_hint)

        stack = roadmap_brief.get("stack_summary")
        if stack:
            stack_hint = f"Stack: {stack}"
            if stack_hint not in base and stack_hint not in hints:
                hints.append(stack_hint)

        digest = roadmap_brief.get("project_steering_digest") or {}
        id_line = digest.get("identity_line")
        if id_line:
            id_hint = f"Identity: {id_line}"
            if id_hint not in base and id_hint not in hints:
                hints.append(id_hint)
        remaining = digest.get("bootstrap_remaining")
        verify_cmds = digest.get("verification_commands") or []
        if verify_cmds:
            verify_hint = f"Project verify: {verify_cmds[0]}"
            if verify_hint not in base and verify_hint not in hints:
                hints.append(verify_hint)
        if remaining and int(remaining) > 0:
            fill_hint = (
                f"Bootstrap fill: {remaining} template phrase(s) — "
                "roadmap(action='apply_bootstrap_fill') or checkpoint bootstrap_fill_plan"
            )
            if fill_hint not in base and fill_hint not in hints:
                hints.append(fill_hint)

        steering_line = roadmap_brief.get("steering_line")
        if steering_line and steering_line not in base and steering_line not in hints:
            hints.append(steering_line)

        if phase in {"bootstrap", "bootstrap_fill", "structure_repair", "coherence_recovery", "validate_pending"}:
            if first_call not in base and first_call not in hints:
                hints.append(first_call)
            if phase == "bootstrap_fill":
                fill_hint = (
                    "roadmap(action='apply_bootstrap_fill', context='write') — "
                    "apply evidence-backed replacements to bootstrap template text"
                )
                if fill_hint not in base and fill_hint not in hints:
                    hints.append(fill_hint)
        elif not roadmap_brief.get("roadmap_exists"):
            roadmap_hint = "roadmap(action='checkpoint') — create project steering surface"
            if roadmap_hint not in base and roadmap_hint not in hints:
                hints.append(roadmap_hint)

        freshness = roadmap_brief.get("checkpoint_freshness") or {}
        if freshness.get("stale"):
            stale_hint = "roadmap(action='explain_stale') — checkpoint outdated vs project activity"
            if stale_hint not in base and stale_hint not in hints:
                hints.append(stale_hint)

        gates = (roadmap_brief.get("recommended_next_action") or {}).get("action")
        if gates in {"apply_bootstrap_fill", "bootstrap_fill"}:
            fill_hint = (
                roadmap_brief.get("first_call")
                or "roadmap(action='apply_bootstrap_fill', context='write') — apply evidence-backed bootstrap fill"
            )
            if fill_hint not in base and fill_hint not in hints:
                hints.append(fill_hint)
        elif gates in {"repair_schema", "explain_stale"}:
            gate_hint = roadmap_brief.get("first_call") or "roadmap(action='explain_gate')"
            if gate_hint not in base and gate_hint not in hints:
                hints.append(gate_hint)

    if not hints:
        return base
    return [*hints, *base]


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
    roadmap_gate_message = None
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

    roadmap_brief: dict[str, Any] | None = None
    roadmap_gate_state: dict[str, Any] | None = None
    try:
        from plugins.dietcode.lib.agent.roadmap.gate import build_roadmap_gate_state
        from plugins.dietcode.lib.agent.roadmap.session import session_brief as roadmap_session_brief

        roadmap_brief = roadmap_session_brief()
        roadmap_gate_state = build_roadmap_gate_state()
        if roadmap_gate_state.get("enabled") and not roadmap_gate_state.get("kanban_complete_allowed"):
            roadmap_gate_message = (
                f"ROADMAP steering gate closed — {roadmap_gate_state.get('stale_summary') or roadmap_gate_state.get('stale_reason')}. "
                "Run roadmap(action='checkpoint') before kanban_complete. "
                "Diagnostic: /roadmap explain-gate"
            )
    except Exception:
        pass

    return {
        "success": True,
        "scope_id": sid,
        "anchor_scope_id": anchor_scope,
        "scope_cluster": scope_cluster,
        "convergence_state": state.value,
        "kanban_complete_allowed": gate_message is None and roadmap_gate_message is None,
        "kanban_complete_block_reason": gate_message or roadmap_gate_message,
        "roadmap_complete_block_reason": roadmap_gate_message,
        "roadmap_gate": roadmap_gate_state,
        "roadmap_steering_line": (roadmap_brief or {}).get("steering_line"),
        "project_steering_digest": (roadmap_brief or {}).get("project_steering_digest"),
        "project_identity_line": ((roadmap_brief or {}).get("project_steering_digest") or {}).get("identity_line"),
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
        "roadmap_checkpoint": roadmap_brief,
        "convergence_record": journal_row,
        "journal_integrity": journal_integrity,
        "next_actions": _merge_steering_next_actions(
            recommended_next_actions(state),
            jsdp_harness=jsdp_harness,
            roadmap_brief=roadmap_brief,
        ),
        "authority": {
            "execution": "hermes",
            "convergence": "hermes_journal",
            "merge_gate": "convergence_mark_converged",
        },
    }
