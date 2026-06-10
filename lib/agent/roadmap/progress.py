"""Roadmap checkpoint progress telemetry — operator observability."""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

_write_lock = threading.Lock()
MAX_LOG_BYTES = 1 * 1024 * 1024
MAX_LOG_LINES = 2000
DEFAULT_TAIL = 20


def session_dir() -> Path:
    raw = os.environ.get("DIETCODE_SESSION_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".dietcode" / "session"


def progress_jsonl_path() -> Path:
    return session_dir() / "roadmap-progress.jsonl"


def progress_current_path() -> Path:
    return session_dir() / "roadmap-progress-current.json"


def emit_progress(
    phase: str,
    *,
    action: str = "",
    workspace: str = "",
    payload: Optional[dict[str, Any]] = None,
    success: bool = True,
) -> dict[str, Any]:
    """Append structured roadmap operator event."""
    from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config

    if not get_roadmap_config().progress_enabled:
        return {}

    event = {
        "event_id": str(uuid.uuid4()),
        "ts_mono": time.monotonic(),
        "ts_iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "phase": phase,
        "action": action or None,
        "workspace": workspace or None,
        "success": success,
        "payload": payload or {},
    }

    line = json.dumps(event, ensure_ascii=False)
    path = progress_jsonl_path()
    current = progress_current_path()

    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        _trim_jsonl(path)
        current.write_text(json.dumps(event, indent=2), encoding="utf-8")

    return event


def _trim_jsonl(path: Path) -> None:
    try:
        if not path.is_file() or path.stat().st_size <= MAX_LOG_BYTES:
            return
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) <= MAX_LOG_LINES:
            return
        path.write_text("\n".join(lines[-MAX_LOG_LINES:]) + "\n", encoding="utf-8")
    except OSError:
        pass


def read_tail(*, lines: int = DEFAULT_TAIL) -> list[dict[str, Any]]:
    path = progress_jsonl_path()
    if not path.is_file():
        return []
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in raw_lines[-lines:]:
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                out.append(parsed)
        except json.JSONDecodeError:
            continue
    return out


def read_current() -> dict[str, Any]:
    """Latest roadmap tool event snapshot (kernel progress-current analogue)."""
    path = progress_current_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def read_progress_current() -> dict[str, Any]:
    """Alias for kernel ergonomics parity."""
    return read_current()


def summarize_recent_events(*, last: int = 5) -> list[dict[str, Any]]:
    """Compact timeline rows for operator reports."""
    rows: list[dict[str, Any]] = []
    for event in read_tail(lines=last):
        rows.append({
            "ts_iso": event.get("ts_iso"),
            "phase": event.get("phase"),
            "action": event.get("action"),
            "success": event.get("success"),
            "workspace": event.get("workspace"),
        })
    return rows


def build_progress_snapshot(*, workspace: Optional[str] = None) -> dict[str, Any]:
    """Full progress + steering snapshot (kernel progress --current analogue)."""
    from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace_root
    from plugins.dietcode.lib.agent.roadmap.operator import recommend_next_action
    from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot
    from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state

    root = resolve_workspace_root(workspace)
    current = read_current()
    snap = get_workspace_snapshot(root, tier="light")
    ws_state = read_state(root)
    gate = snap.gate_state
    freshness = gate.get("checkpoint_stale")
    last_err = read_last_error() or None
    next_rec = recommend_next_action(
        phase=str(ws_state.get("phase") or ""),
        roadmap_exists=bool(gate.get("roadmap_present")),
        schema_valid=gate.get("schema_valid"),
        stale=bool(freshness),
        validation_pending=bool(ws_state.get("validation_pending")),
        last_error=last_err,
    )
    return {
        "success": True,
        "ok": True,
        "workspace": root,
        "current": current or None,
        "current_path": str(progress_current_path()),
        "jsonl_path": str(progress_jsonl_path()),
        "current_exists": progress_current_path().is_file(),
        "jsonl_exists": progress_jsonl_path().is_file(),
        "workspace_state": ws_state or None,
        "roadmap_gate": gate,
        "kanban_complete_allowed": gate.get("kanban_complete_allowed"),
        "recommended_next_action": next_rec,
        "last_error": last_err,
        "recent_events": summarize_recent_events(last=5),
    }


_ERROR_RECOVERY: dict[str, dict[str, Any]] = {
    "validate.failed": {
        "operator_action": "roadmap(action='validate') — fix schema issues",
        "retry_command": "roadmap(action='validate')",
        "diagnostic_command": "/roadmap explain-gate",
        "suggested_slash_command": "/roadmap validate",
    },
    "roadmap.file_mutated": {
        "operator_action": "ROADMAP.md mutated — validate before closing checkpoint pass",
        "retry_command": "roadmap(action='validate')",
        "diagnostic_command": "/roadmap explain-gate",
        "suggested_slash_command": "/roadmap validate",
    },
    "tool.error": {
        "operator_action": "roadmap(action='guide') or /roadmap doctor",
        "retry_command": "roadmap(action='guide')",
        "diagnostic_command": "/roadmap explain-gate",
        "suggested_slash_command": "/roadmap cockpit",
    },
}


def _enrich_error(event: dict[str, Any], *, code: str) -> dict[str, Any]:
    recovery = _ERROR_RECOVERY.get(code, _ERROR_RECOVERY["tool.error"])
    payload = event.get("payload") or {}
    return {
        "phase": event.get("phase"),
        "action": event.get("action"),
        "workspace": event.get("workspace"),
        "payload": payload,
        "ts_iso": event.get("ts_iso"),
        "string_code": code,
        "safe_to_retry": True,
        **recovery,
        "validation": payload.get("validation"),
        "error": payload.get("error"),
    }


def read_last_error() -> dict[str, Any]:
    for event in reversed(read_tail(lines=100)):
        validation = (event.get("payload") or {}).get("validation")
        if isinstance(validation, dict) and validation.get("valid") is False:
            enriched = _enrich_error(event, code="validate.failed")
            enriched["phase"] = "validate.failed"
            enriched["action"] = "validate"
            return enriched
        if event.get("phase") == "roadmap.file_mutated":
            return _enrich_error(event, code="roadmap.file_mutated")
        if not event.get("success"):
            code = "tool.error"
            if (event.get("payload") or {}).get("error"):
                code = str((event.get("payload") or {}).get("error"))
            return _enrich_error(event, code=code)
    return {}


def format_progress_report(
    *,
    tail: bool = False,
    timeline: bool = False,
    current_snapshot: bool = False,
    last: int = 5,
    workspace: Optional[str] = None,
) -> str:
    if current_snapshot:
        return json.dumps(build_progress_snapshot(workspace=workspace), indent=2, ensure_ascii=False)

    if tail:
        events = read_tail(lines=last)
        return json.dumps(events, indent=2, ensure_ascii=False)

    current = read_current()
    if not current:
        return "🗺️ Roadmap progress: idle (no roadmap tool activity this session)"

    phase = current.get("phase") or "idle"
    action = current.get("action") or "—"
    ok = current.get("success")
    mark = "✓" if ok else "✕"
    lines = [
        f"🗺️ Roadmap progress {mark}",
        f"Phase: {phase} | action: {action}",
    ]
    if current.get("workspace"):
        lines.append(f"Workspace: {current['workspace']}")
    payload = current.get("payload") or {}
    if payload.get("phase"):
        lines.append(f"Roadmap phase: {payload['phase']}")
    if payload.get("stale") is not None:
        lines.append(f"Checkpoint stale: {payload['stale']}")
    if payload.get("valid") is False:
        lines.append("Schema: invalid — /roadmap explain-gate")

    snap = build_progress_snapshot(workspace=workspace)
    next_rec = snap.get("recommended_next_action") or {}
    if next_rec.get("command"):
        lines.append(f"Next: {next_rec.get('command')}")
    if snap.get("kanban_complete_allowed") is False:
        lines.append("⚠️  kanban_complete blocked")

    if timeline:
        lines.append("")
        lines.append("Timeline:")
        for event in read_tail(lines=last):
            lines.append(
                f"  • {event.get('ts_iso')} {event.get('phase')} "
                f"action={event.get('action')} success={event.get('success')}"
            )
    lines.append("")
    lines.append("Full snapshot: /roadmap progress --current")
    return "\n".join(lines)


def format_watch_report(*, workspace: Optional[str] = None) -> str:
    snap = build_progress_snapshot(workspace=workspace)
    current = snap.get("current") or {}
    if not current:
        next_rec = snap.get("recommended_next_action") or {}
        hint = next_rec.get("command") or "/roadmap cockpit"
        return f"🗺️ ROADMAP … idle — next: {hint}"

    phase = current.get("phase") or "idle"
    action = current.get("action") or "guide"
    ok = "ok" if current.get("success") else "ERR"
    gate = snap.get("roadmap_gate") or {}
    gate_mark = "" if gate.get("kanban_complete_allowed") else " ⛔"
    next_rec = snap.get("recommended_next_action") or {}
    cmd = next_rec.get("command") or ""
    suffix = f" → {cmd}" if cmd else ""
    return f"🗺️ ROADMAP [{ok}]{gate_mark} {phase} — {action}{suffix}"
