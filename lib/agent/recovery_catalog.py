"""Central recovery command catalog — concrete operator/agent next steps."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class RecoveryStep:
    id: str
    command: str
    detail: str


def resolve_mutation_context(scope_id: Optional[str] = None) -> dict[str, Any]:
    """Load scope + active mutation for concrete recovery commands."""
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import resolve_scope_id
        from plugins.dietcode.lib.agent.joyzoning.journal import get_journal
        from plugins.dietcode.lib.agent.joyzoning.workflow import _resolve_cluster

        sid = resolve_scope_id(scope_id)
        state, anchor, _cluster = _resolve_cluster(sid)
        active = get_journal().get_active_mutation(anchor) or {}
        mutation_id = str(active.get("id") or active.get("mutation_id") or "").strip()
        return {
            "scope_id": sid,
            "anchor_scope_id": anchor,
            "convergence_state": state.value,
            "mutation_id": mutation_id or None,
        }
    except Exception:
        return {"scope_id": scope_id or "default", "mutation_id": None, "convergence_state": "unknown"}


def kanban_complete_command(*, scope_id: str) -> str:
    task = (scope_id or "").strip() or "default"
    return f"kanban_complete(task_id='{task}')"


def joyzoning_begin_command(*, goal: str = "address gate blockers before kanban_complete") -> str:
    safe_goal = goal.replace("'", "\\'")
    return f"joyzoning(action='begin', goal='{safe_goal}')"


def joyzoning_verify_command(
    *,
    mutation_id: Optional[str],
    report: str = "tests and structural gate cleared",
) -> str:
    safe_report = report.replace("'", "\\'")
    if mutation_id:
        return (
            f"joyzoning(action='verify', mutation_id='{mutation_id}', "
            f"report='{safe_report}', passed=true)"
        )
    return joyzoning_begin_command(goal="open mutation scope before verification")


def joyzoning_request_review_command(*, summary: str = "ready for operator review") -> str:
    safe_summary = summary.replace("'", "\\'")
    return f"joyzoning(action='request_review', summary='{safe_summary}')"


def convergence_mark_converged_command(*, summary: str = "operator approved") -> str:
    safe_summary = summary.replace("'", "\\'")
    return f"convergence_mark_converged(summary='{safe_summary}')"


def quality_recovery_steps(*, ctx: Optional[dict[str, Any]] = None) -> list[RecoveryStep]:
    ctx = ctx or resolve_mutation_context()
    mutation_id = ctx.get("mutation_id")
    return [
        RecoveryStep(
            "broccolidb_violations",
            "broccolidb_violations()",
            "List structural Spider findings for the active scope",
        ),
        RecoveryStep(
            "joyzoning_verify",
            joyzoning_verify_command(mutation_id=mutation_id),
            "Record verification evidence after structural fixes",
        ),
        RecoveryStep(
            "broccolidb_heal",
            "broccolidb_heal()",
            "Prune ghost graph nodes when BroccoliDB is available",
        ),
    ]


def joyzoning_recovery_steps(*, ctx: Optional[dict[str, Any]] = None) -> list[RecoveryStep]:
    ctx = ctx or resolve_mutation_context()
    mutation_id = ctx.get("mutation_id")
    steps = [
        RecoveryStep(
            "joyzoning_status",
            "joyzoning(action='status')",
            "Read convergence state and block reason",
        ),
    ]
    if mutation_id:
        steps.append(
            RecoveryStep(
                "joyzoning_verify",
                joyzoning_verify_command(mutation_id=mutation_id),
                "Record verification before request_review",
            )
        )
    else:
        steps.append(
            RecoveryStep(
                "joyzoning_begin",
                joyzoning_begin_command(),
                "Open a bounded mutation scope before verify",
            )
        )
    steps.append(
        RecoveryStep(
            "joyzoning_request_review",
            joyzoning_request_review_command(),
            "Move to ready_for_review before kanban_complete",
        )
    )
    return steps


def roadmap_recovery_steps() -> list[RecoveryStep]:
    return [
        RecoveryStep("explain_gate", "roadmap(action='explain_gate')", "Closed roadmap steering gates"),
        RecoveryStep("checkpoint", "roadmap(action='checkpoint')", "Refresh evidence before edits"),
        RecoveryStep("validate", "roadmap(action='validate')", "Confirm schema after ROADMAP.md edits"),
    ]


def recovery_steps_as_dicts(steps: list[RecoveryStep]) -> list[dict[str, str]]:
    return [{"id": s.id, "command": s.command, "detail": s.detail} for s in steps]


def resolve_primary_recovery_command(*, layer: str, ctx: Optional[dict[str, Any]] = None) -> str:
    ctx = ctx or resolve_mutation_context()
    if layer == "quality":
        return quality_recovery_steps(ctx=ctx)[0].command
    if layer == "joyzoning":
        steps = joyzoning_recovery_steps(ctx=ctx)
        return steps[1].command if len(steps) > 1 else steps[0].command
    if layer == "roadmap":
        return roadmap_recovery_steps()[0].command
    return "joyzoning(action='context')"


def kanban_ready_steps(*, ctx: Optional[dict[str, Any]] = None) -> list[RecoveryStep]:
    ctx = ctx or resolve_mutation_context()
    return [
        RecoveryStep(
            "kanban_complete",
            resolve_kanban_complete_flow(ctx=ctx),
            "Mark converged after operator review, then complete the kanban task",
        )
    ]
def resolve_kanban_complete_flow(*, ctx: Optional[dict[str, Any]] = None) -> str:
    ctx = ctx or resolve_mutation_context()
    scope = str(ctx.get("anchor_scope_id") or ctx.get("scope_id") or "default")
    return (
        f"{convergence_mark_converged_command()} then {kanban_complete_command(scope_id=scope)}"
    )

