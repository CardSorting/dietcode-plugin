"""Unified operator response envelope — industry-style next-action fields on tool payloads."""
from __future__ import annotations

from typing import Any, Optional


def attach_operator_envelope(
    payload: dict[str, Any],
    *,
    scope_id: Optional[str] = None,
) -> dict[str, Any]:
    """Attach operator_summary, agent_next_call, and recovery_steps to any DietCode payload."""
    from plugins.dietcode.lib.agent.ergonomics import build_operator_brief

    brief = build_operator_brief(scope_id=scope_id)
    enriched = {
        **payload,
        "kanban_complete_allowed": brief.get("kanban_complete_allowed", payload.get("kanban_complete_allowed")),
        "kanban_complete_block_reason": brief.get("kanban_complete_block_reason")
        or payload.get("kanban_complete_block_reason"),
        "operator_summary": brief.get("operator_summary") or payload.get("operator_summary"),
        "agent_next_call": brief.get("agent_next_call") or payload.get("agent_next_call"),
        "recovery_steps": brief.get("recovery_steps") or payload.get("recovery_steps") or [],
        "gate_layers": brief.get("gate_layers") or payload.get("gate_layers"),
    }
    enriched["_dietcode_operator_hints"] = {
        "next_action": enriched.get("agent_next_call"),
        "operator_summary": enriched.get("operator_summary"),
        "recovery_steps": enriched.get("recovery_steps"),
        "kanban_complete_allowed": enriched.get("kanban_complete_allowed"),
        "preferred_tool": _preferred_tool_for_call(str(enriched.get("agent_next_call") or "")),
    }
    return enriched


def _preferred_tool_for_call(command: str) -> str:
    lowered = command.lower()
    if lowered.startswith("roadmap"):
        return "roadmap"
    if lowered.startswith("broccolidb"):
        return "broccolidb"
    if lowered.startswith("kanban_complete"):
        return "kanban"
    if lowered.startswith("convergence_"):
        return "joyzoning"
    return "joyzoning"
