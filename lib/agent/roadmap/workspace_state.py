"""Workspace-local roadmap state — durable validate/checkpoint memory."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def state_path(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".dietcode" / "roadmap-state.json"


def read_state(workspace: str | Path) -> dict[str, Any]:
    path = state_path(workspace)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def write_state(workspace: str | Path, patch: dict[str, Any]) -> dict[str, Any]:
    path = state_path(workspace)
    current = read_state(workspace)
    merged = {**current, **patch, "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    except OSError:
        pass
    return merged


def record_file_mutation(
    workspace: str | Path,
    *,
    tool: str = "",
    path: str = "",
) -> dict[str, Any]:
    """Mark ROADMAP.md as pending re-validation after a native write."""
    state = write_state(
        workspace,
        {
            "validation_pending": True,
            "schema_valid": None,
            "last_mutated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "last_mutation_tool": tool or None,
            "last_mutation_path": path or None,
        },
    )
    try:
        from plugins.dietcode.lib.agent.roadmap.snapshot import invalidate_snapshot

        invalidate_snapshot(workspace)
    except Exception:
        pass
    return state


def record_validation(
    workspace: str | Path,
    *,
    valid: bool,
    health_status: Optional[str] = None,
    recent_checkpoint_date: Optional[str] = None,
    phase: str = "",
    issue_count: int = 0,
) -> dict[str, Any]:
    state = write_state(
        workspace,
        {
            "last_validated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "schema_valid": valid,
            "health_status": health_status,
            "recent_checkpoint_date": recent_checkpoint_date,
            "phase": phase or None,
            "validation_issue_count": issue_count,
            "validation_pending": False,
        },
    )
    try:
        from plugins.dietcode.lib.agent.roadmap.snapshot import invalidate_snapshot

        invalidate_snapshot(workspace)
    except Exception:
        pass
    return state
