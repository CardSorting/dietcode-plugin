"""Quality gate orchestration for kanban_complete."""
from __future__ import annotations

from typing import Any, Optional

from plugins.dietcode.lib.agent.audit.completion_gate import (
    CompletionGateDecision,
    build_gate_block_message,
    evaluate_completion_gate,
)
from plugins.dietcode.lib.agent.audit.config import get_completion_gate_config
from plugins.dietcode.lib.agent.audit.session_store import (
    append_violations,
    get_session_metadata,
    increment_block_count,
    record_spider_gate,
    record_verify_passed,
    spider_gate_fresh,
    update_session_metadata,
)
from plugins.dietcode.lib.agent.audit.spider_runner import run_spider_gate


def _resolve_scope(scope_id: Optional[str] = None) -> str:
    if scope_id and str(scope_id).strip():
        return str(scope_id).strip()
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import resolve_scope_id

        return resolve_scope_id(None)
    except Exception:
        return "default"


def _sync_verify_state(scope_id: str) -> None:
    """Mirror joyzoning journal verify state into audit metadata."""
    try:
        from plugins.dietcode.lib.agent.joyzoning.convergence import ConvergenceState, get_convergence_state
        from plugins.dietcode.lib.agent.joyzoning.journal import get_journal

        state = get_convergence_state(scope_id)
        passed = state in (
            ConvergenceState.VERIFYING,
            ConvergenceState.READY_FOR_REVIEW,
            ConvergenceState.CONVERGED,
        )
        active = get_journal().get_active_mutation(scope_id) or {}
        if active.get("state") == "verified":
            passed = True
        record_verify_passed(scope_id, passed=passed)
    except Exception:
        pass


def record_governance_block(scope_id: str, payload: dict[str, Any]) -> None:
    violations: list[str] = []
    for item in payload.get("violations") or []:
        if isinstance(item, dict):
            file_path = item.get("file") or "unknown"
            layer = item.get("layer") or "unknown"
            for err in item.get("errors") or []:
                violations.append(f"joy_zoning:{file_path}:{layer}:{err}")
        elif isinstance(item, str):
            violations.append(f"joy_zoning:{item}")
    if violations:
        append_violations(scope_id, violations)
    else:
        append_violations(scope_id, ["governance_layer_violation"])


def record_tool_quality_result(scope_id: str, tool_name: str, result: str) -> None:
    """Capture quality gate signals from broccolidb / joyzoning tool outputs."""
    if not result or not isinstance(result, str):
        return
    try:
        import json

        data = json.loads(result)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return

    quality = str(data.get("qualityGate") or "").upper()
    if tool_name in ("mutation_verify",) or "verify" in tool_name:
        record_verify_passed(scope_id, passed=bool(data.get("success")) and quality != "FAILED")
        return

    if quality == "FAILED":
        append_violations(scope_id, [f"spider_warning:{tool_name}"])
    elif quality == "WARNING":
        append_violations(scope_id, [f"spider_warning:{tool_name}:warning"])

    if tool_name in ("broccolidb_violations", "broccolidb_joyzoning_audit", "joyzoning"):
        total = int(data.get("totalViolations") or data.get("violationCount") or 0)
        if total >= 5:
            append_violations(scope_id, ["spider_gate_blocked"])


def build_quality_metadata(scope_id: str) -> dict[str, Any]:
    cfg = get_completion_gate_config()
    _sync_verify_state(scope_id)
    meta = get_session_metadata(scope_id)

    if cfg.enabled and cfg.spider_gate_required and not spider_gate_fresh(scope_id):
        spider = run_spider_gate(scope=cfg.spider_scope)
        record_spider_gate(scope_id, spider)
        meta = get_session_metadata(scope_id)

    return meta


def evaluate_quality_gate(scope_id: str) -> CompletionGateDecision:
    cfg = get_completion_gate_config()
    meta = build_quality_metadata(scope_id)
    return evaluate_completion_gate(
        meta,
        config=cfg,
        baseline_metadata=meta.get("baseline_metadata"),
        advisory_metadata=meta.get("advisory_metadata"),
    )


def kanban_complete_allowed(scope_id: Optional[str] = None) -> tuple[bool, Optional[str], CompletionGateDecision | None]:
    cfg = get_completion_gate_config()
    if not cfg.enabled:
        return True, None, None
    sid = _resolve_scope(scope_id)
    decision = evaluate_quality_gate(sid)
    if not decision.blocked:
        return True, None, decision
    count = increment_block_count(sid)
    if count >= cfg.max_block_count:
        return False, (
            f"Quality gate circuit breaker ({count} blocks). "
            "Resolve structural violations or set joyzoning.governance.completion_gate.enabled: false."
        ), decision
    return False, build_gate_block_message(decision, get_session_metadata(sid)), decision


def explain_quality_gate(scope_id: Optional[str] = None) -> dict[str, Any]:
    from plugins.dietcode.lib.agent.recovery_catalog import (
        quality_recovery_steps,
        recovery_steps_as_dicts,
        resolve_kanban_complete_flow,
        resolve_mutation_context,
    )

    sid = _resolve_scope(scope_id)
    ctx = resolve_mutation_context(sid)
    cfg = get_completion_gate_config()
    meta = build_quality_metadata(sid)
    decision = evaluate_completion_gate(meta, config=cfg)
    parts = __import__(
        "plugins.dietcode.lib.agent.audit.severity",
        fromlist=["partition_violations"],
    ).partition_violations(meta.get("violations"))
    steps = quality_recovery_steps(ctx=ctx)
    return {
        "enabled": cfg.enabled,
        "scope_id": sid,
        "hardening_score": decision.score,
        "hardening_grade": decision.grade,
        "effective_threshold": decision.effective_threshold,
        "kanban_complete_allowed": not decision.blocked,
        "blocked": decision.blocked,
        "reasons": [{"code": r.code, "message": r.message} for r in decision.reasons],
        "violations": meta.get("violations") or [],
        "violation_tiers": parts,
        "spider_gate": meta.get("spider_gate"),
        "recent_verify_passed": meta.get("recent_verify_passed"),
        "block_count": meta.get("block_count") or 0,
        "recovery": recovery_steps_as_dicts(steps),
        "agent_next_call": (
            steps[0].command if decision.blocked else resolve_kanban_complete_flow(ctx=ctx)
        ),
    }
