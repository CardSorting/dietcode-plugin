"""Session-native roadmap brief — injected into JoyZoning context and session.start."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config, resolve_workspace_root


def session_brief(*, workspace: Optional[str] = None) -> dict[str, Any] | None:
    """Lightweight roadmap snapshot for session start (no checkpoint side effects)."""
    cfg = get_roadmap_config()
    if not cfg.enabled:
        return None

    from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

    steering = build_steering_context(workspace=workspace)
    if not steering.get("ok") and not (workspace and str(workspace).strip()):
        return {
            "enabled": True,
            "success": False,
            **steering,
            "first_call": steering.get("agent_next_call"),
        }

    try:
        from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import operational_status

        root = steering.get("workspace") or resolve_workspace_root(workspace)
        status = operational_status(workspace=root, tier="light")
        ws_state = status.get("workspace_state") or {}
        gate_state = status.get("roadmap_gate") or {}
        next_rec = status.get("recommended_next_action") or {}
        from plugins.dietcode.lib.agent.roadmap.agent_steering import format_agent_steering_line
        from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints

        hints = build_agent_operator_hints(
            action="session",
            gate=gate_state if isinstance(gate_state, dict) else None,
            workspace=str(root),
        )
        result = {
            "enabled": True,
            "success": True,
            "workspace": root,
            "workspace_source": steering.get("workspace_source") or status.get("workspace_source"),
            "roadmap_path": steering.get("roadmap_path"),
            "workspace_safe": steering.get("workspace_safe", True),
            "bootstrap_complete": steering.get("bootstrap_complete"),
            "bootstrap_placeholder_count": steering.get("bootstrap_placeholder_count"),
            "steering_identity": steering.get("steering_identity"),
            "steering_brief": steering.get("steering_brief"),
            "stack_summary": steering.get("stack_summary"),
            "project_archetype": steering.get("project_archetype"),
            "agent_rules_files": steering.get("agent_rules_files"),
            "makefile_targets": steering.get("makefile_targets"),
            "verification_commands": steering.get("verification_commands"),
            "has_backstage_catalog": steering.get("has_backstage_catalog"),
            "readme_tagline": steering.get("readme_tagline"),
            "center_of_gravity_excerpt": steering.get("center_of_gravity_excerpt"),
            "health_status": steering.get("health_status") or status.get("health_status") or ws_state.get("health_status"),
            "now_item_count": steering.get("now_item_count"),
            "phase": status.get("phase"),
            "roadmap_exists": status.get("roadmap_exists"),
            "code_soup_risk": status.get("code_soup_risk") or steering.get("code_soup_risk"),
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
            "steering_line": format_agent_steering_line(workspace=str(root)),
            "_roadmap_operator_hints": hints,
        }
        if steering.get("bootstrap_complete") is False:
            from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_bootstrap_steering_fields

            result.update(attach_bootstrap_steering_fields(steering, tier="light"))
        else:
            from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_steering_digest_fields

            result.update(attach_steering_digest_fields(steering))
        return result
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
