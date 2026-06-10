"""Roadmap explain-gate — schema and freshness gate diagnostics."""
from __future__ import annotations

from typing import Any, Optional

from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace_root
from plugins.dietcode.lib.agent.roadmap.gate import evaluate_gate_checks
from plugins.dietcode.lib.agent.roadmap.operator import format_explain_gate_report
from plugins.dietcode.lib.agent.roadmap.phase_guide import clarity_envelope
from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot


def build_explain_gate_payload(*, workspace: Optional[str] = None) -> dict[str, Any]:
    root = resolve_workspace_root(workspace)
    snap = get_workspace_snapshot(root, tier="light")
    from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

    steering = build_steering_context(workspace=root)
    inputs = snap.gate_inputs
    gate = snap.gate_state
    closed, open_ids = evaluate_gate_checks(inputs)
    validation = inputs.get("validation")
    freshness = inputs.get("freshness")

    blocking = gate.get("blocking_gates") or []
    kanban_allowed = gate.get("kanban_complete_allowed")
    next_call = gate.get("preferred_command") or "roadmap(action='guide')"

    payload = {
        "action": "explain_gate",
        "success": bool(kanban_allowed),
        "ok": bool(kanban_allowed),
        "workspace": root,
        "steering_brief": steering.get("steering_brief"),
        "project_archetype": steering.get("project_archetype"),
        "gate": gate,
        "validation": validation,
        "checkpoint_freshness": freshness,
        "workspace_state": inputs.get("workspace_state"),
        "closed_gates": closed,
        "open_gates": open_ids,
        "kanban_complete_allowed": gate.get("kanban_complete_allowed"),
        "report": format_explain_gate_report(
            validation=validation,
            freshness=freshness,
            workspace=root,
            closed_gates=closed,
            open_gates=open_ids,
            kanban_complete_allowed=kanban_allowed,
        ),
        "gates_closed": {
            "schema_valid": (validation or {}).get("valid") is False,
            "checkpoint_stale": bool((freshness or {}).get("stale")),
            "roadmap_missing": not inputs.get("roadmap_present"),
            "validation_pending": bool((inputs.get("workspace_state") or {}).get("validation_pending")),
            "bootstrap_incomplete": inputs.get("bootstrap_complete") is False,
            "kanban_complete_blocked": not bool(kanban_allowed),
        },
        "agent_next_call": next_call,
        "operator_summary": (
            "All roadmap steering gates open."
            if not closed
            else f"{len(closed)} gate(s) closed — see closed_gates and report"
        ),
    }
    report = payload.get("report") or ""
    from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_bootstrap_steering_fields

    attached = attach_bootstrap_steering_fields(steering, tier="light")
    payload.update(attached)
    if inputs.get("bootstrap_complete") is False:
        remaining = (payload.get("project_steering_digest") or {}).get("bootstrap_remaining")
        suffix = (
            f"\nBootstrap fill: {remaining} template phrase(s) remain — "
            "roadmap(action='apply_bootstrap_fill', context='write') then validate."
            if remaining
            else "\nBootstrap fill: roadmap(action='apply_bootstrap_fill', context='write') then validate."
        )
        payload["report"] = report + suffix
    return clarity_envelope(payload)
