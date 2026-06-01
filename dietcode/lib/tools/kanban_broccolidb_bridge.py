"""Bridge between Hermes Kanban (``kanban.db``) and BroccoliQ/BroccoliDB hive tables.

Production responsibilities:
  - Workspace-aware broccolidb root/db resolution (via runner helpers)
  - Debounced, optionally async sync so agent loops stay responsive
  - Merge-safe hive upserts through ``infrastructure/kanban/hive_sync.ts``
  - Structured JSON results for tools and plugins
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger(__name__)

_TASK_ID_RE = re.compile(r"^t_[a-z0-9]{6,32}$", re.IGNORECASE)

_KANBAN_AUTO_SYNC_TOOLS = frozenset({
    "kanban_complete",
    "kanban_block",
    "kanban_heartbeat",
    "kanban_broccolidb_sync",
    "kanban_broccolidb_record",
})

# kanban_create handled separately — task_id only exists in tool result.
_FORCE_SYNC_EVENTS = frozenset({"complete", "block", "create", "start", "record", "context"})
_MAX_DEBOUNCE_ENTRIES = 500
_MAX_INFLIGHT_ENTRIES = 200


@dataclass(frozen=True)
class BroccolidbKanbanConfig:
    enabled: bool = True
    auto_sync: bool = True
    async_sync: bool = True
    shard_id: str = "kanban"
    sync_debounce_seconds: float = 2.0
    max_sync_workers: int = 4
    signal_events: tuple[str, ...] = ("create", "complete", "block", "start")

    @classmethod
    def load(cls) -> "BroccolidbKanbanConfig":
        try:
            from hermes_cli.config import load_config
            cfg = load_config()
            kanban_cfg = cfg.get("kanban", {}) if isinstance(cfg, dict) else {}
            raw = kanban_cfg.get("broccolidb", {})
            if not isinstance(raw, dict):
                return cls()
            events = raw.get("signal_events")
            if isinstance(events, list) and events:
                signal_events = tuple(str(e) for e in events)
            else:
                signal_events = cls.signal_events
            debounce = raw.get("sync_debounce_seconds", cls.sync_debounce_seconds)
            try:
                debounce_f = max(0.0, float(debounce))
            except (TypeError, ValueError):
                debounce_f = cls.sync_debounce_seconds
            workers_raw = raw.get("max_sync_workers", cls.max_sync_workers)
            try:
                max_workers = max(1, min(int(workers_raw), 16))
            except (TypeError, ValueError):
                max_workers = cls.max_sync_workers
            return cls(
                enabled=bool(raw.get("enabled", True)),
                auto_sync=bool(raw.get("auto_sync", True)),
                async_sync=bool(raw.get("async_sync", True)),
                shard_id=str(raw.get("shard_id") or "kanban"),
                sync_debounce_seconds=debounce_f,
                max_sync_workers=max_workers,
                signal_events=signal_events,
            )
        except Exception:
            return cls()


_config_cache: Optional[BroccolidbKanbanConfig] = None
_config_cache_at: float = 0.0
_CONFIG_TTL_SECONDS = 30.0

_requirements_ok: Optional[bool] = None
_requirements_at: float = 0.0
_requirements_key: Optional[tuple[Optional[str], str, str]] = None
_REQUIREMENTS_TTL_SECONDS = 60.0

_debounce_lock = threading.Lock()
_last_sync_at: dict[str, float] = {}
_inflight: set[str] = set()
_sync_executor: Optional[ThreadPoolExecutor] = None
_sync_executor_workers: int = 0


def invalidate_config_cache() -> None:
    """Clear cached ``kanban.broccolidb`` config (tests / hot reload)."""
    global _config_cache, _config_cache_at, _requirements_ok, _requirements_at, _requirements_key
    _config_cache = None
    _config_cache_at = 0.0
    _requirements_ok = None
    _requirements_at = 0.0
    _requirements_key = None


def get_config() -> BroccolidbKanbanConfig:
    global _config_cache, _config_cache_at
    now = time.monotonic()
    if _config_cache is None or (now - _config_cache_at) > _CONFIG_TTL_SECONDS:
        _config_cache = BroccolidbKanbanConfig.load()
        _config_cache_at = now
    return _config_cache


def _scope_env(key: str) -> str:
    from plugins.dietcode.lib.agent.joyzoning.config import read_scope_env
    return read_scope_env(key)


def _skip_result(reason: str, **extra: Any) -> str:
    return json.dumps({"success": False, "skipped": True, "reason": reason, **extra})


def _debounced_result(task_id: str, event: str) -> str:
    return json.dumps({
        "success": True,
        "skipped": True,
        "reason": "debounced",
        "task_id": task_id,
        "event": event,
    })


def broccolidb_enabled() -> bool:
    return get_config().enabled


def broccolidb_available() -> bool:
    """Config enabled and ``broccolidb/`` present in the active workspace."""
    if not broccolidb_enabled():
        return False
    global _requirements_ok, _requirements_at, _requirements_key
    from plugins.dietcode.lib.tools.broccolidb_tools.runner import check_requirements, resolve_broccolidb_root

    # Cache key must be sensitive to common test/workspace switches within one
    # Python process (xdist workers). Tool registry caching doesn't cover this.
    key = (resolve_broccolidb_root(), os.environ.get("HERMES_HOME", ""), str(Path.cwd()))
    now = time.monotonic()
    if _requirements_key != key:
        _requirements_ok = None
        _requirements_at = 0.0
        _requirements_key = key
    if _requirements_ok is None or (now - _requirements_at) > _REQUIREMENTS_TTL_SECONDS:
        _requirements_ok = check_requirements()
        _requirements_at = now
    return bool(_requirements_ok)


def auto_sync_enabled() -> bool:
    cfg = get_config()
    return cfg.enabled and cfg.auto_sync and broccolidb_available()


def validate_task_id(task_id: Optional[str]) -> Optional[str]:
    if not task_id or not isinstance(task_id, str):
        return None
    tid = task_id.strip().lower()
    if not tid:
        return None
    if not _TASK_ID_RE.match(tid):
        return None
    return tid


def _joyzoning_forensic_fields() -> dict[str, Any]:
    """Scope linkage for BroccoliQ hive rows (kanban task + convergence state)."""
    fields: dict[str, Any] = {}
    scope = _scope_env("JOYZONING_SCOPE_ID")
    if scope:
        fields["joyzoning_scope"] = scope
    if not (scope or _scope_env("HERMES_KANBAN_TASK")):
        return fields
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import resolve_scope_id
        from plugins.dietcode.lib.agent.joyzoning.convergence import get_convergence_state
        sid = resolve_scope_id(_scope_env("HERMES_KANBAN_TASK") or scope)
        if sid and sid != "default":
            fields["convergence_state"] = get_convergence_state(sid).value
    except Exception:
        pass
    return fields


def resolve_board_slug(board: Optional[str] = None) -> Optional[str]:
    if board and str(board).strip():
        return str(board).strip()
    return _scope_env("HERMES_KANBAN_BOARD") or None


def _safe_priority(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _serialize_result(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _shutdown_sync_executor() -> None:
    global _sync_executor, _sync_executor_workers
    if _sync_executor is not None:
        _sync_executor.shutdown(wait=False, cancel_futures=True)
        _sync_executor = None
        _sync_executor_workers = 0


def _get_sync_executor() -> ThreadPoolExecutor:
    global _sync_executor, _sync_executor_workers
    workers = get_config().max_sync_workers
    if _sync_executor is None or _sync_executor_workers != workers:
        _shutdown_sync_executor()
        _sync_executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="kanban-hive-sync",
        )
        _sync_executor_workers = workers
    return _sync_executor


atexit.register(_shutdown_sync_executor)


def task_row_to_payload(task: Any, *, event: str = "sync") -> dict[str, Any]:
    """Convert a ``kanban_db.Task`` (or dict) into a hive sync payload."""
    cfg = get_config()
    if isinstance(task, dict):
        src = task
    else:
        src = {
            "id": task.id,
            "title": task.title,
            "body": task.body,
            "assignee": task.assignee,
            "status": task.status,
            "priority": task.priority,
            "result": task.result,
            "created_at": task.created_at,
            "started_at": task.started_at,
            "completed_at": task.completed_at,
            "tenant": getattr(task, "tenant", None),
            "current_run_id": getattr(task, "current_run_id", None),
        }

    created_raw = src.get("created_at")
    try:
        created_at = int(created_raw) if created_raw is not None else int(time.time())
    except (TypeError, ValueError):
        created_at = int(time.time())

    raw_tid = src.get("id") or src.get("task_id")
    task_id = validate_task_id(str(raw_tid) if raw_tid is not None else None)

    if not task_id:
        logger.debug(
            "kanban_broccolidb: invalid task id %r — sync will reject payload",
            raw_tid,
        )

    payload = {
        "task_id": task_id,
        "title": (src.get("title") or "").strip() or str(task_id or raw_tid or "untitled"),
        "body": src.get("body") or "",
        "assignee": src.get("assignee") or "hermes",
        "status": src.get("status") or "unknown",
        "priority": _safe_priority(src.get("priority")),
        "result": _serialize_result(src.get("result")),
        "created_at": created_at,
        "started_at": src.get("started_at"),
        "completed_at": src.get("completed_at"),
        "board": resolve_board_slug() or "default",
        "event": event,
        "shard_id": cfg.shard_id,
        "signal_events": list(cfg.signal_events),
        "run_id": (
            str(src.get("current_run_id"))
            if src.get("current_run_id") is not None
            else _scope_env("HERMES_KANBAN_RUN_ID")
        ),
        "tenant": src.get("tenant") or _scope_env("HERMES_TENANT"),
        **_joyzoning_forensic_fields(),
    }
    return {k: v for k, v in payload.items() if v is not None}


def _should_debounce(task_id: str, event: str) -> bool:
    """Skip noisy syncs (heartbeats) when inside debounce window."""
    if event in _FORCE_SYNC_EVENTS:
        return False
    cfg = get_config()
    if cfg.sync_debounce_seconds <= 0:
        return False
    with _debounce_lock:
        last = _last_sync_at.get(task_id, 0.0)
        return (time.monotonic() - last) < cfg.sync_debounce_seconds


def _mark_sync(task_id: str) -> None:
    with _debounce_lock:
        _last_sync_at[task_id] = time.monotonic()
        if len(_last_sync_at) <= _MAX_DEBOUNCE_ENTRIES:
            return
        cfg = get_config()
        cutoff = time.monotonic() - max(cfg.sync_debounce_seconds * 4, 30.0)
        stale = [k for k, v in _last_sync_at.items() if v < cutoff]
        for key in stale:
            _last_sync_at.pop(key, None)


def sync_task_payload(payload: dict[str, Any], *, force: bool = False) -> str:
    """Upsert a kanban task snapshot into ``hive_tasks`` via hive_sync.ts."""
    from plugins.dietcode.lib.tools.broccolidb_tools.runner import run_hive_sync

    if not broccolidb_enabled():
        return _skip_result("disabled in config")
    if not broccolidb_available():
        return _skip_result("broccolidb package not found in workspace")

    tid = validate_task_id(payload.get("task_id"))
    if not tid:
        return json.dumps({"success": False, "error": "invalid or missing task_id"})

    event = str(payload.get("event") or "sync")
    if not force and _should_debounce(tid, event):
        return _debounced_result(tid, event)

    clean = {k: v for k, v in {**payload, "task_id": tid}.items() if v is not None}
    raw = run_hive_sync(clean)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("kanban_broccolidb: non-JSON hive sync output: %s", raw[:200])
        return json.dumps({"success": False, "error": "invalid hive sync response", "raw": raw[:500]})

    if data.get("success"):
        _mark_sync(tid)
        logger.info(
            "kanban_broccolidb: synced %s event=%s shard=%s",
            tid,
            event,
            payload.get("shard_id"),
        )
    else:
        logger.warning(
            "kanban_broccolidb: sync failed task=%s event=%s err=%s",
            tid,
            event,
            data.get("error") or data.get("reason"),
        )
    return raw


def sync_kanban_task(task: Any, *, event: str = "sync", force: bool = False) -> str:
    if not broccolidb_available():
        return _skip_result(
            "disabled in config"
            if not broccolidb_enabled()
            else "broccolidb package not found in workspace",
        )
    return sync_task_payload(task_row_to_payload(task, event=event), force=force)


def sync_kanban_task_id(
    task_id: str,
    *,
    event: str = "sync",
    board: Optional[str] = None,
    force: bool = False,
) -> str:
    """Load a task from kanban.db and sync it to the hive layer."""
    if not broccolidb_available():
        return _skip_result(
            "disabled in config"
            if not broccolidb_enabled()
            else "broccolidb package not found in workspace",
        )

    tid = validate_task_id(task_id)
    if not tid:
        return json.dumps({"success": False, "error": f"invalid task_id: {task_id!r}"})

    if not force and _should_debounce(tid, event):
        return _debounced_result(tid, event)

    try:
        from hermes_cli import kanban_db as kb
        conn = kb.connect(board=resolve_board_slug(board))
        try:
            task = kb.get_task(conn, tid)
            if task is None:
                return json.dumps({"success": False, "error": f"task {tid} not found"})
            return sync_kanban_task(task, event=event, force=force)
        finally:
            conn.close()
    except Exception as exc:
        logger.warning("kanban_broccolidb sync failed for %s: %s", tid, exc)
        return json.dumps({"success": False, "error": str(exc)})


def _trim_inflight_locked() -> None:
    if len(_inflight) <= _MAX_INFLIGHT_ENTRIES:
        return
    # Drop arbitrary excess — inflight is best-effort dedupe, not authoritative state.
    overflow = len(_inflight) - _MAX_INFLIGHT_ENTRIES
    for key in list(_inflight)[:overflow]:
        _inflight.discard(key)


def _sync_worker(task_id: str, event: str, board: Optional[str], *, force: bool = False) -> None:
    key = f"{task_id}:{event}"
    with _debounce_lock:
        if key in _inflight:
            return
        _inflight.add(key)
        _trim_inflight_locked()
    try:
        sync_kanban_task_id(task_id, event=event, board=board, force=force)
    except Exception as exc:
        logger.warning("kanban_broccolidb async sync failed %s: %s", key, exc)
    finally:
        with _debounce_lock:
            _inflight.discard(key)


def schedule_sync(
    task_id: str,
    *,
    event: str = "sync",
    board: Optional[str] = None,
    force: bool = False,
) -> None:
    """Schedule hive sync — async when configured, inline otherwise."""
    tid = validate_task_id(task_id)
    if not tid or not auto_sync_enabled():
        return

    force_sync = force or event in _FORCE_SYNC_EVENTS
    cfg = get_config()
    if cfg.async_sync:
        _get_sync_executor().submit(_sync_worker, tid, event, board, force=force_sync)
    else:
        sync_kanban_task_id(tid, event=event, board=board, force=force_sync)


def maybe_auto_sync_tool(tool_name: str, args: dict | None) -> None:
    """Best-effort hive sync after kanban lifecycle tool calls."""
    if not auto_sync_enabled():
        return
    if tool_name not in _KANBAN_AUTO_SYNC_TOOLS:
        return

    args = args or {}
    task_id = validate_task_id(args.get("task_id")) or validate_task_id(
        _scope_env("HERMES_KANBAN_TASK")
    )
    if not task_id:
        return

    event_map = {
        "kanban_complete": "complete",
        "kanban_block": "block",
        "kanban_heartbeat": "heartbeat",
        "kanban_broccolidb_sync": str(args.get("event") or "sync"),
        "kanban_broccolidb_record": "record",
    }
    event = event_map.get(tool_name, "sync")
    force = tool_name in (
        "kanban_complete",
        "kanban_block",
        "kanban_broccolidb_sync",
        "kanban_broccolidb_record",
    )
    schedule_sync(task_id, event=event, force=force)


def sync_on_worker_start() -> None:
    """Sync the dispatcher-assigned task when a kanban worker session starts."""
    if not auto_sync_enabled():
        return
    task_id = validate_task_id(_scope_env("HERMES_KANBAN_TASK"))
    if not task_id:
        return
    try:
        from plugins.dietcode.lib.agent.joyzoning.scope_registry import register_from_scope_env
        register_from_scope_env()
    except Exception as exc:
        logger.warning("kanban_broccolidb scope alias registration failed: %s", exc)
    schedule_sync(task_id, event="start")


def compute_drift(board: Optional[str] = None, limit: int = 200) -> dict[str, Any]:
    """Compare kanban.db tasks with hive_tasks rows (orchestrator diagnostics)."""
    from plugins.dietcode.lib.tools.broccolidb_tools.runner import run_hive_drift

    if not broccolidb_available():
        return {"success": False, "skipped": True, "reason": "broccolidb unavailable"}

    lim = max(1, min(limit, 500))
    try:
        from hermes_cli import kanban_db as kb
        conn = kb.connect(board=resolve_board_slug(board))
        try:
            tasks = kb.list_tasks(conn, limit=lim)
            kanban_map = {
                validate_task_id(t.id): t.status
                for t in tasks
                if validate_task_id(t.id)
            }
        finally:
            conn.close()
    except Exception as exc:
        return {"success": False, "error": f"kanban read failed: {exc}"}

    cfg = get_config()
    raw = run_hive_drift({
        "shard_id": cfg.shard_id,
        "task_ids": list(kanban_map.keys()),
    })
    try:
        hive_data = json.loads(raw)
    except json.JSONDecodeError:
        return {"success": False, "error": "hive read failed", "raw": raw[:300]}

    if not hive_data.get("success"):
        return hive_data

    hive_rows = hive_data.get("rows")
    if not isinstance(hive_rows, list):
        hive_rows = []

    hive_map = {
        str(r["task_id"]).lower(): r["status"]
        for r in hive_rows
        if isinstance(r, dict) and r.get("task_id")
    }

    missing_in_hive = [tid for tid in kanban_map if tid not in hive_map]
    status_mismatch = [
        {"task_id": tid, "kanban": kanban_map[tid], "hive": hive_map[tid]}
        for tid in kanban_map
        if tid in hive_map and kanban_map[tid] != hive_map[tid]
    ]

    return {
        "success": True,
        "limit": lim,
        "shard_id": cfg.shard_id,
        "kanban_tasks": len(kanban_map),
        "hive_tasks_matched": len(hive_map),
        "missing_in_hive": missing_in_hive[:50],
        "status_mismatch": status_mismatch[:50],
        "in_sync": not missing_in_hive and not status_mismatch,
    }
