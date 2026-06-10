"""Session-native roadmap brief — injected into JoyZoning context and session.start."""
from __future__ import annotations

from typing import Any, Optional

from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config, resolve_workspace_root


def session_brief(*, workspace: Optional[str] = None) -> dict[str, Any] | None:
    """Lightweight roadmap snapshot for session start (no checkpoint side effects)."""
    cfg = get_roadmap_config()
    if not cfg.enabled:
        return None

    try:
        from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import operational_status

        root = resolve_workspace_root(workspace)
        status = operational_status(workspace=root, tier="light")
        ws_state = status.get("workspace_state") or {}
        gate_state = status.get("roadmap_gate") or {}
        next_rec = status.get("recommended_next_action") or {}
        return {
            "enabled": True,
            "success": True,
            "workspace": root,
            "phase": status.get("phase"),
            "roadmap_exists": status.get("roadmap_exists"),
            "health_status": status.get("health_status") or ws_state.get("health_status"),
            "code_soup_risk": status.get("code_soup_risk"),
            "sections_missing_count": len(status.get("sections_missing") or []),
            "recent_checkpoint_date": status.get("recent_checkpoint_date") or ws_state.get("recent_checkpoint_date"),
            "checkpoint_freshness": status.get("checkpoint_freshness"),
            "schema_valid": status.get("schema_valid") if status.get("schema_valid") is not None else ws_state.get("schema_valid"),
            "validation_pending": ws_state.get("validation_pending"),
            "last_validated_at": ws_state.get("last_validated_at"),
            "last_mutated_at": ws_state.get("last_mutated_at"),
            "first_call": next_rec.get("command") or status.get("agent_next_call") or "roadmap(action='guide')",
            "recommended_next_action": next_rec,
            "roadmap_gate": gate_state,
            "kanban_complete_allowed": gate_state.get("kanban_complete_allowed"),
            "operator_summary": status.get("operator_summary"),
            "skill_path": status.get("skill_path"),
        }
    except Exception as exc:
        return {"enabled": True, "success": False, "error": str(exc)}


def emit_roadmap_event(
    event_suffix: str,
    *,
    payload: dict[str, Any] | None = None,
    session_id: str = "",
) -> Optional[str]:
    """Emit roadmap.* events through JoyZoning runtime journal when available."""
    if not get_roadmap_config().enabled:
        return None
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import resolve_scope_id
        from plugins.dietcode.lib.agent.joyzoning.runtime_events import emit_runtime_event

        return emit_runtime_event(
            f"roadmap.{event_suffix}",
            scope_id=resolve_scope_id(),
            session_id=session_id,
            payload=payload or {},
        )
    except Exception:
        return None
