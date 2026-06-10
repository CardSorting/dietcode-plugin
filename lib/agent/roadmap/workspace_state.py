"""Workspace-local roadmap state — durable validate/checkpoint memory."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

_STATE_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def state_path(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".dietcode" / "roadmap-state.json"


def _state_cache_key(workspace: str | Path) -> str:
    return str(Path(workspace).expanduser().resolve())


def _state_file_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime if path.is_file() else 0.0
    except OSError:
        return 0.0


def invalidate_state_cache(workspace: str | Path) -> None:
    _STATE_CACHE.pop(_state_cache_key(workspace), None)


def read_state(workspace: str | Path) -> dict[str, Any]:
    path = state_path(workspace)
    key = _state_cache_key(workspace)
    mtime = _state_file_mtime(path)
    cached = _STATE_CACHE.get(key)
    if cached is not None and cached[0] == mtime:
        return dict(cached[1])

    if not path.is_file():
        data: dict[str, Any] = {}
        _STATE_CACHE[key] = (mtime, data)
        return data

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        data = raw if isinstance(raw, dict) else {}
    except (OSError, json.JSONDecodeError):
        data = {}

    _STATE_CACHE[key] = (mtime, data)
    return dict(data)


def write_state(workspace: str | Path, patch: dict[str, Any]) -> dict[str, Any]:
    path = state_path(workspace)
    current = read_state(workspace)
    merged = {**current, **patch, "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    except OSError:
        pass
    invalidate_state_cache(workspace)
    _STATE_CACHE[_state_cache_key(workspace)] = (_state_file_mtime(path), merged)
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
