"""Roadmap operator ergonomics — next-action recommendations (kernel cockpit pattern)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

ACTION_CHECKPOINT = "run_checkpoint"
ACTION_VALIDATE = "run_validate"
ACTION_BOOTSTRAP = "bootstrap_roadmap"
ACTION_BOOTSTRAP_FILL = "bootstrap_fill"
ACTION_APPLY_BOOTSTRAP_FILL = "apply_bootstrap_fill"
ACTION_REPAIR_SCHEMA = "repair_schema"
ACTION_COHERENCE_RECOVERY = "coherence_recovery"
ACTION_COCKPIT = "open_cockpit"
ACTION_EXPLAIN_STALE = "explain_stale"
ACTION_RUN_EXPLAIN_GATE = "run explain-gate"
ACTION_DOCTOR = "run_doctor"
ACTION_GUIDE = "run_guide"
ACTION_CONFIGURE_WORKSPACE = "configure_workspace"
ACTION_WAIT = "wait"


def is_bootstrap_incomplete(
    *,
    roadmap_exists: bool = False,
    workspace_state: Optional[dict[str, Any]] = None,
    bootstrap_complete: Optional[bool] = None,
    bootstrap_placeholder_count: Optional[int] = None,
) -> bool:
    """True when ROADMAP.md exists but evidence-driven template phrases remain."""
    if not roadmap_exists:
        return False
    ws = workspace_state or {}
    complete = bootstrap_complete if bootstrap_complete is not None else ws.get("bootstrap_complete")
    count = (
        bootstrap_placeholder_count
        if bootstrap_placeholder_count is not None
        else ws.get("bootstrap_placeholder_count")
    )
    if complete is False:
        return True
    if complete is True:
        return False
    return bool(count and int(count) > 0)


def recommend_next_action(
    *,
    phase: str = "",
    roadmap_exists: bool = False,
    schema_valid: Optional[bool] = None,
    stale: bool = False,
    validation_pending: bool = False,
    bootstrap_incomplete: bool = False,
    last_error: Optional[dict[str, Any]] = None,
) -> dict[str, str]:
    """Return exactly one operator next action with command and detail."""
    if last_error:
        return {
            "action": ACTION_DOCTOR,
            "command": "/roadmap last-error",
            "detail": last_error.get("operator_action") or "Review last roadmap error before continuing.",
        }

    if validation_pending:
        return {
            "action": ACTION_VALIDATE,
            "command": "roadmap(action='validate')",
            "detail": "ROADMAP.md mutated since last validate — confirm schema before closing pass.",
        }

    if bootstrap_incomplete or phase == "bootstrap_fill":
        return {
            "action": ACTION_APPLY_BOOTSTRAP_FILL,
            "command": "roadmap(action='apply_bootstrap_fill', context='write')",
            "detail": (
                "Apply per-project evidence replacements to resolve bootstrap placeholders, then validate. "
                "Preview first: roadmap(action='apply_bootstrap_fill')."
            ),
        }

    if not roadmap_exists:
        return {
            "action": ACTION_BOOTSTRAP,
            "command": "roadmap(action='checkpoint')",
            "detail": "ROADMAP.md missing — run a checkpoint pass to create the steering surface.",
        }

    if schema_valid is False:
        return {
            "action": ACTION_RUN_EXPLAIN_GATE,
            "command": "/roadmap explain-gate",
            "detail": "Schema gate closed — review closed gates, fix ROADMAP.md, then validate.",
        }

    if stale:
        return {
            "action": ACTION_RUN_EXPLAIN_GATE,
            "command": "/roadmap explain-gate",
            "detail": "Freshness gate closed — checkpoint outdated vs project activity.",
        }

    if phase == "structure_repair":
        return {
            "action": ACTION_REPAIR_SCHEMA,
            "command": "roadmap(action='checkpoint', context='repair schema')",
            "detail": "ROADMAP.md schema incomplete — repair missing sections without losing history.",
        }

    if phase == "coherence_recovery":
        return {
            "action": ACTION_COHERENCE_RECOVERY,
            "command": "roadmap(action='checkpoint', context='coherence recovery')",
            "detail": "Roadmap health degraded — demote overloaded Now items and strengthen section 9 audit.",
        }

    if phase == "validate_pending":
        return {
            "action": ACTION_VALIDATE,
            "command": "roadmap(action='validate')",
            "detail": "Validation pending — confirm schema before closing the checkpoint pass.",
        }

    if phase == "bootstrap":
        return {
            "action": ACTION_CHECKPOINT,
            "command": "roadmap(action='checkpoint')",
            "detail": "Bootstrap ROADMAP.md from gathered evidence.",
        }

    return {
        "action": ACTION_WAIT,
        "command": "/roadmap cockpit",
        "detail": "Roadmap steering surface current — checkpoint after meaningful direction shifts.",
    }


def format_explain_gate_report(
    *,
    validation: Optional[dict[str, Any]] = None,
    freshness: Optional[dict[str, Any]] = None,
    workspace: str = "",
    closed_gates: Optional[list[dict[str, Any]]] = None,
    open_gates: Optional[list[str]] = None,
    kanban_complete_allowed: Optional[bool] = None,
) -> str:
    """Explain closed schema/freshness gates (kernel explain-gate analogue)."""
    lines = [
        "🗺️ Roadmap gate explanation",
        f"Workspace: {workspace or '(auto)'}",
        "",
    ]

    if closed_gates is not None:
        lines.append(f"closed_gates={len(closed_gates)} open_gates={len(open_gates or [])}")
        if closed_gates:
            lines.append("")
            for item in closed_gates:
                mark = "⚠️ " if item.get("blocks_kanban_complete") else "• "
                lines.append(f"{mark}{item.get('label')}: {item.get('why')}")
                lines.append(f"   fix ({'safe' if item.get('safe_to_apply') else 'caution'}): {item.get('fix')}")
        else:
            lines.append("✅ All roadmap steering gates open")
        lines.append("")
        if kanban_complete_allowed is False:
            lines.append("⛔ kanban_complete blocked — resolve blocking gates above")
        elif kanban_complete_allowed is True:
            lines.append("✅ kanban_complete allowed")
        else:
            lines.append(
                f"kanban_complete: {'allowed' if not any(g.get('blocks_kanban_complete') for g in (closed_gates or [])) else 'blocked'}"
            )
        lines.append("Slash: /roadmap progress --current | progress --timeline")
        return "\n".join(lines)

    if validation:
        lines.append(f"Schema valid: {validation.get('valid')}")
        lines.append(f"Schema complete: {validation.get('schema_complete')}")
        issues = validation.get("issues") or []
        if issues:
            lines.append("")
            lines.append("Schema issues:")
            for issue in issues[:8]:
                lines.append(f"  • [{issue.get('severity')}] {issue.get('message')}")
            if len(issues) > 8:
                lines.append(f"  … +{len(issues) - 8} more")
        lines.append("")
        lines.append("Fix: edit ROADMAP.md, then roadmap(action='validate')")

    if freshness:
        lines.append("")
        lines.append(f"Checkpoint stale: {freshness.get('stale')}")
        lines.append(f"Reason: {freshness.get('reason')}")
        lines.append(freshness.get("summary") or "")
        if freshness.get("stale"):
            lines.append("Fix: roadmap(action='checkpoint', context='stale refresh')")

    if not validation and not freshness:
        lines.append("No validation or freshness data — run /roadmap doctor")

    return "\n".join(lines)


def build_agent_operator_hints(
    *,
    action: str = "",
    gate: Optional[dict[str, Any]] = None,
    string_code: str = "",
    workspace: str = "",
    last_error: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Kernel-style agent/operator hint bundle for roadmap tool responses."""
    from plugins.dietcode.lib.agent.roadmap.gate import build_roadmap_gate_state

    if gate is not None:
        snap = gate
    elif workspace and str(workspace).strip():
        snap = build_roadmap_gate_state(workspace=workspace)
    else:
        snap = {
            "roadmap_present": False,
            "schema_valid": False,
            "kanban_complete_allowed": False,
            "validation_pending": False,
            "checkpoint_stale": False,
            "workspace_state": {},
        }
    ws_state = snap.get("workspace_state") or {}
    bootstrap_inc = is_bootstrap_incomplete(
        roadmap_exists=bool(snap.get("roadmap_present")),
        workspace_state=ws_state,
        bootstrap_complete=snap.get("bootstrap_complete"),
        bootstrap_placeholder_count=snap.get("bootstrap_placeholder_count"),
    )
    roadmap_path = (
        str(Path(str(snap.get("workspace") or "")).expanduser().resolve() / "ROADMAP.md")
        if snap.get("workspace")
        else snap.get("roadmap_path")
    )
    next_rec = recommend_next_action(
        phase=str(ws_state.get("phase") or ""),
        roadmap_exists=bool(snap.get("roadmap_present")),
        schema_valid=snap.get("schema_valid"),
        stale=bool(snap.get("checkpoint_stale")),
        validation_pending=bool(snap.get("validation_pending") or ws_state.get("validation_pending")),
        bootstrap_incomplete=bootstrap_inc,
        last_error=last_error,
    )
    hints: dict[str, Any] = {
        "preferred_tool": "roadmap",
        "skill": "auto-rolling-roadmap",
        "workspace": snap.get("workspace"),
        "roadmap_path": roadmap_path,
        "write_guard": (
            f"ROADMAP.md lives only at {roadmap_path}"
            if roadmap_path
            else "Set HERMES_KANBAN_WORKSPACE before editing ROADMAP.md"
        ),
        "kanban_complete_allowed": snap.get("kanban_complete_allowed"),
        "validation_pending": bool(snap.get("validation_pending")),
        "preferred_command": next_rec.get("command"),
        "slash_commands": [
            "/roadmap cockpit",
            "/roadmap explain-gate",
            "/roadmap progress --current",
            "/roadmap watch",
        ],
        "next_action": next_rec.get("command"),
        "recovery_suggestion": next_rec.get("detail"),
        "suggested_slash_command": (
            next_rec.get("command") if str(next_rec.get("command") or "").startswith("/") else "/roadmap cockpit"
        ),
        "diagnostic_command": "/roadmap explain-gate",
    }
    if string_code:
        from plugins.dietcode.lib.agent.roadmap.errors import error_envelope

        envelope = error_envelope(code=string_code, message=string_code, action=action or "guide")
        hints["error"] = envelope
        hints["recovery_suggestion"] = envelope.get("operator_action")
        hints["retry_command"] = envelope.get("retry_command")
        hints["safe_to_retry"] = envelope.get("safe_to_retry")
    elif snap.get("kanban_complete_allowed") is False:
        blocking = snap.get("blocking_gates") or []
        if blocking:
            hints["missing_gate"] = blocking[0].get("id")
            hints["recovery_suggestion"] = blocking[0].get("fix")
    if bootstrap_inc and workspace and str(workspace).strip():
        try:
            from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import (
                attach_bootstrap_steering_fields,
                format_bootstrap_fill_hint,
            )
            from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

            steering = build_steering_context(workspace=workspace)
            attached = attach_bootstrap_steering_fields(steering, tier="light")
            plan = attached.get("bootstrap_fill_plan") or {}
            hint = format_bootstrap_fill_hint(plan)
            if hint:
                hints["bootstrap_fill_hint"] = hint
                if not hints.get("recovery_suggestion"):
                    hints["recovery_suggestion"] = hint
        except Exception:
            pass
    return hints
