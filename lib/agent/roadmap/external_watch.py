"""Detect ROADMAP.md edits outside Hermes tool hooks — no VS Code file watcher."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# workspace (resolved str) -> {baseline, handled} mtimes for the active session
_SESSION_TRACK: dict[str, dict[str, float]] = {}


def _workspace_key(workspace: str | Path) -> str:
    return str(Path(workspace).expanduser().resolve())


def roadmap_mtime(workspace: str | Path) -> Optional[float]:
    path = Path(workspace).expanduser().resolve() / "ROADMAP.md"
    if not path.is_file():
        return None
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def begin_session_roadmap_watch(workspace: str | Path) -> None:
    """Record ROADMAP.md mtime at session start (Hermes session hook)."""
    key = _workspace_key(workspace)
    mtime = roadmap_mtime(key)
    if mtime is None:
        _SESSION_TRACK.pop(key, None)
        return
    _SESSION_TRACK[key] = {"baseline": mtime, "handled": mtime}


def note_tool_roadmap_mutation(workspace: str | Path) -> None:
    """Call after a tool-mediated ROADMAP.md write so session-end scan does not double-count."""
    key = _workspace_key(workspace)
    entry = _SESSION_TRACK.get(key)
    mtime = roadmap_mtime(key)
    if entry is not None and mtime is not None:
        entry["handled"] = mtime


def handle_external_roadmap_change(
    workspace: str | Path,
    *,
    source: str = "external",
    tool: str = "external",
) -> dict[str, Any]:
    """Invalidate caches and mark validation_pending — mirrors codemarie handleExternalRoadmapChange."""
    root = Path(workspace).expanduser().resolve()
    try:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import invalidate_fingerprint_cache
        from plugins.dietcode.lib.agent.roadmap.snapshot import invalidate_snapshot
        from plugins.dietcode.lib.agent.roadmap.workspace_state import record_file_mutation

        invalidate_snapshot(root)
        invalidate_fingerprint_cache(root)
        state = record_file_mutation(root, tool=tool, path="ROADMAP.md")
        return {
            "ok": True,
            "workspace": str(root),
            "source": source,
            "validation_pending": state.get("validation_pending"),
            "roadmap_path": str(root / "ROADMAP.md"),
        }
    except Exception as exc:
        logger.debug("handle_external_roadmap_change failed: %s", exc)
        return {"ok": False, "workspace": str(root), "source": source, "error": str(exc)}


def scan_session_roadmap_changes(
    workspace: str | Path,
    *,
    source: str = "external",
) -> bool:
    """Return True when ROADMAP.md changed since last tool-handled mtime this session."""
    key = _workspace_key(workspace)
    entry = _SESSION_TRACK.get(key)
    if not entry:
        return False

    current = roadmap_mtime(key)
    if current is None:
        return False

    handled = entry.get("handled", entry.get("baseline", 0.0))
    if current <= handled:
        return False

    result = handle_external_roadmap_change(workspace, source=source, tool="external")
    if not result.get("ok"):
        return False

    entry["handled"] = current
    return True


def end_session_roadmap_watch(
    workspace: str | Path,
    *,
    session_id: str = "",
    emit_events: bool = True,
) -> bool:
    """Session-end scan for out-of-band ROADMAP edits; clears session tracking."""
    changed = scan_session_roadmap_changes(workspace, source="session_end")
    _SESSION_TRACK.pop(_workspace_key(workspace), None)

    if not changed or not emit_events:
        return changed

    try:
        from plugins.dietcode.lib.agent.roadmap.progress import emit_progress
        from plugins.dietcode.lib.agent.roadmap.session import emit_roadmap_event

        payload = {
            "source": "external",
            "path": "ROADMAP.md",
            "followup": "roadmap(action='validate')",
        }
        emit_roadmap_event("roadmap_file_mutated", session_id=session_id, payload=payload)
        emit_progress("roadmap.watch", action="external_edit", payload=payload, success=True)
    except Exception as exc:
        logger.debug("external roadmap session-end event skipped: %s", exc)

    return changed
