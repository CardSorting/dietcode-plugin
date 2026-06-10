"""Normalized roadmap error envelopes — kernel-style operator recovery."""
from __future__ import annotations

import json
from typing import Any, Optional


def error_envelope(
    *,
    code: str,
    message: str,
    action: str = "",
    detail: str = "",
    safe_to_retry: bool = True,
    phase: str = "error",
) -> dict[str, Any]:
    next_action = _recovery_for_code(code, action)
    return {
        "success": False,
        "ok": False,
        "action": action or None,
        "phase": phase,
        "string_code": code,
        "human_message": message,
        "detail": detail or None,
        "operator_action": next_action,
        "safe_to_retry": safe_to_retry,
        "retry_command": f"roadmap(action='{action or 'guide'}')" if safe_to_retry else None,
        "diagnostic_command": "/roadmap explain-gate" if code in {"gate_closed", "schema_invalid", "checkpoint_stale", "validation_pending"} else "/roadmap doctor",
        "suggested_slash_command": "/roadmap cockpit",
        "_roadmap_error_envelope": True,
        "_roadmap_operator_hints": {
            "preferred_tool": "roadmap",
            "next_action": next_action,
            "recovery_suggestion": message,
            "suggested_slash_command": "/roadmap cockpit",
        },
    }


def _recovery_for_code(code: str, action: str) -> str:
    mapping = {
        "roadmap_disabled": "Set dietcode.roadmap.enabled: true in Hermes config",
        "workspace_unresolved": "Set HERMES_KANBAN_WORKSPACE or run from project root",
        "roadmap_missing": "roadmap(action='checkpoint') to bootstrap ROADMAP.md",
        "schema_invalid": "roadmap(action='validate') then repair reported issues",
        "checkpoint_stale": "roadmap(action='checkpoint', context='stale refresh')",
        "gate_closed": "/roadmap explain-gate — review closed steering gates",
        "validation_pending": "roadmap(action='validate') — ROADMAP.md mutated since last validate",
        "module_unavailable": "/dietcode doctor — verify plugin registration",
        "unknown_action": "roadmap(action='guide') for phase and next call",
    }
    return mapping.get(code, f"roadmap(action='{action or 'guide'}')")


def gate_closed_envelope(*, message: str, action: str = "explain_gate") -> dict[str, Any]:
    return error_envelope(
        code="gate_closed",
        message=message,
        action=action,
        safe_to_retry=True,
        phase="gate.blocked",
    )


def validation_pending_envelope(*, workspace: str = "") -> dict[str, Any]:
    return {
        **error_envelope(
            code="validation_pending",
            message="ROADMAP.md mutated — schema re-validation required",
            action="validate",
            phase="validate.pending",
        ),
        "workspace": workspace or None,
        "diagnostic_command": "/roadmap explain-gate",
        "retry_command": "roadmap(action='validate')",
    }


def as_tool_error(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def from_exception(exc: Exception, *, action: str = "") -> dict[str, Any]:
    return error_envelope(
        code="roadmap_failed",
        message=str(exc),
        action=action,
        detail=type(exc).__name__,
        safe_to_retry=True,
    )
