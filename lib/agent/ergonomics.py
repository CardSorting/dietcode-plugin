"""Unified agent/operator ergonomics — single next-call surface across gate tiers."""
from __future__ import annotations

from typing import Any, Optional

from plugins.dietcode.lib.agent.recovery_catalog import (
    joyzoning_recovery_steps,
    kanban_ready_steps,
    quality_recovery_steps,
    recovery_steps_as_dicts,
    resolve_kanban_complete_flow,
    resolve_mutation_context,
    resolve_primary_recovery_command,
    roadmap_recovery_steps,
)
from plugins.dietcode.lib.agent.roadmap.phase_guide import AGENT_PLAYBOOK, OPERATOR_PLAYBOOK


def resolve_agent_next_call(*, gates: dict[str, Any], ctx: Optional[dict[str, Any]] = None) -> str:
    """Pick one concrete next tool/slash command from unified gate state."""
    ctx = ctx or resolve_mutation_context()
    if gates.get("kanban_complete_allowed"):
        return resolve_kanban_complete_flow(ctx=ctx)

    layers = gates.get("layers") or {}
    if layers.get("joyzoning", {}).get("allowed") is False:
        steps = joyzoning_recovery_steps(ctx=ctx)
        for step in steps:
            if step.id in {"joyzoning_verify", "joyzoning_begin"}:
                return step.command
        return steps[0].command
    if layers.get("roadmap", {}).get("allowed") is False:
        detail = (layers.get("roadmap") or {}).get("detail") or {}
        preferred = detail.get("preferred_command") if isinstance(detail, dict) else None
        return str(preferred or resolve_primary_recovery_command(layer="roadmap", ctx=ctx))
    if layers.get("quality", {}).get("allowed") is False:
        return resolve_primary_recovery_command(layer="quality", ctx=ctx)
    return "joyzoning(action='context')"


def build_operator_summary(*, gates: dict[str, Any]) -> str:
    if gates.get("kanban_complete_allowed"):
        return "All kanban_complete gate tiers open — complete when operator approves."
    reason = gates.get("kanban_complete_block_reason")
    if reason:
        return str(reason)
    return "kanban_complete blocked — run joyzoning(action='operator') for recovery steps."


def _recovery_for_gates(*, gates: dict[str, Any], ctx: dict[str, Any]) -> list[dict[str, str]]:
    if gates.get("kanban_complete_allowed"):
        return recovery_steps_as_dicts(kanban_ready_steps(ctx=ctx))
    layers = gates.get("layers") or {}
    if layers.get("joyzoning", {}).get("allowed") is False:
        return recovery_steps_as_dicts(joyzoning_recovery_steps(ctx=ctx))
    if layers.get("roadmap", {}).get("allowed") is False:
        return recovery_steps_as_dicts(roadmap_recovery_steps())
    quality_gate = gates.get("quality_gate") or {}
    if quality_gate:
        recovery = quality_gate.get("recovery")
        if isinstance(recovery, list) and recovery and isinstance(recovery[0], dict):
            return recovery
    return recovery_steps_as_dicts(quality_recovery_steps(ctx=ctx))


def build_operator_brief(*, scope_id: Optional[str] = None) -> dict[str, Any]:
    """Unified operator/agent brief — gates, features, config, and next call."""
    from plugins.dietcode.lib.agent.features import build_runtime_snapshot

    ctx = resolve_mutation_context(scope_id)
    snapshot = build_runtime_snapshot(scope_id=ctx.get("anchor_scope_id") or scope_id)
    gates = snapshot.get("gates") or {}
    recovery_steps = _recovery_for_gates(gates=gates, ctx=ctx)

    return {
        "success": True,
        "scope_id": ctx.get("scope_id"),
        "anchor_scope_id": ctx.get("anchor_scope_id"),
        "mutation_id": ctx.get("mutation_id"),
        "convergence_state": ctx.get("convergence_state"),
        "kanban_complete_allowed": gates.get("kanban_complete_allowed"),
        "kanban_complete_block_reason": gates.get("kanban_complete_block_reason"),
        "operator_summary": build_operator_summary(gates=gates),
        "agent_next_call": resolve_agent_next_call(gates=gates, ctx=ctx),
        "gate_layers": gates.get("layers"),
        "quality_gate": gates.get("quality_gate") or None,
        "roadmap_gate": gates.get("roadmap_gate"),
        "features": snapshot.get("features"),
        "config": snapshot.get("config"),
        "recovery_steps": recovery_steps,
        "playbooks": {
            "operator": OPERATOR_PLAYBOOK,
            "agent": AGENT_PLAYBOOK,
        },
    }
