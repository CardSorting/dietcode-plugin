"""Kanban ↔ BroccoliQ first-class orchestration tools."""
from __future__ import annotations

import json
from typing import Any, Optional

from tools.registry import registry, tool_error
from tools.kanban_tools import (
    _check_kanban_mode,
    _check_kanban_orchestrator_mode,
    _connect,
    _default_task_id,
    _enforce_worker_task_ownership,
    _require_orchestrator_tool,
)
from plugins.dietcode.lib.tools.kanban_broccolidb_bridge import (
    broccolidb_available,
    compute_drift,
    sync_kanban_task_id,
    validate_task_id,
)
from plugins.dietcode.lib.tools.broccolidb_tools.agent_rpc import run_agent_rpc
from plugins.dietcode.lib.tools.broccolidb_tools.runner import (
    resolve_broccolidb_root,
    run_db_rpc_batch,
)


def _drift_report_from_hive_rows(
    board_summary: dict[str, Any],
    hive_rows: list[dict[str, Any]],
    *,
    shard_id: str,
    limit: int,
) -> dict[str, Any]:
    """Build drift report from kanban board summary + hive_drift rows (batch RPC path)."""
    kanban_map = {
        str(t["id"]).lower(): t["status"]
        for t in board_summary.get("tasks", [])
        if isinstance(t, dict) and t.get("id")
    }
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
        "limit": limit,
        "shard_id": shard_id,
        "kanban_tasks": len(kanban_map),
        "hive_tasks_matched": len(hive_map),
        "missing_in_hive": missing_in_hive[:50],
        "status_mismatch": status_mismatch[:50],
        "in_sync": not missing_in_hive and not status_mismatch,
        "batched": True,
    }


def _check_kanban_broccolidb_mode() -> bool:
    return _check_kanban_mode() and broccolidb_available()


def _check_kanban_broccolidb_orchestrator_mode() -> bool:
    # Orchestrator-only visibility is primarily a Kanban authorization concern.
    # BroccoliDB availability can vary per workspace, and the handler surfaces
    # a structured error if the package is missing.
    return _check_kanban_orchestrator_mode()


def _parse_sync_result(raw: str, *, context: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return tool_error(f"{context}: invalid JSON response")
    if not data.get("success") and not data.get("skipped"):
        err = data.get("error") or data.get("reason") or "unknown error"
        return tool_error(f"{context}: {err}")
    return raw


def kanban_broccolidb_context(task_id: str = None, sync_first: bool = True) -> str:
    tid = _default_task_id(task_id)
    if not validate_task_id(tid):
        return tool_error("task_id is required (or set HERMES_KANBAN_TASK in the env)")
    guard = _enforce_worker_task_ownership(tid)
    if guard:
        return guard

    if sync_first:
        sync_raw = sync_kanban_task_id(tid, event="context", force=True)
        parsed = json.loads(sync_raw)
        if not parsed.get("success") and not parsed.get("skipped"):
            return tool_error(f"pre-sync failed: {parsed.get('error', sync_raw)}")

    raw = run_agent_rpc("get_task_context", {"task_id": tid}, flush=False)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(data, dict) and data.get("success"):
        data["broccolidb_root"] = resolve_broccolidb_root()
        return json.dumps(data)
    return raw


def kanban_broccolidb_sync(task_id: str = None, event: str = "sync") -> str:
    tid = _default_task_id(task_id)
    if not validate_task_id(tid):
        return tool_error("task_id is required (or set HERMES_KANBAN_TASK in the env)")
    guard = _enforce_worker_task_ownership(tid)
    if guard:
        return guard
    raw = sync_kanban_task_id(tid, event=event or "sync", force=True)
    return _parse_sync_result(raw, context="kanban_broccolidb_sync")


def kanban_broccolidb_record(
    summary: str,
    task_id: str = None,
    tags: str = None,
    kb_type: str = "kanban_handoff",
) -> str:
    tid = _default_task_id(task_id)
    if not validate_task_id(tid):
        return tool_error("task_id is required (or set HERMES_KANBAN_TASK in the env)")
    guard = _enforce_worker_task_ownership(tid)
    if guard:
        return guard
    if not summary or not summary.strip():
        return tool_error("summary is required")

    tag_list = [t.strip() for t in (tags or "").split(",") if t.strip()]
    tag_list.extend(["kanban", tid])
    kb_key = f"kanban_{tid}_{kb_type}"
    result = run_agent_rpc(
        "add_knowledge",
        {
            "kb_id": kb_key,
            "type": kb_type,
            "content": summary.strip(),
            "tags": ",".join(tag_list),
        },
    )
    try:
        data = json.loads(result)
        if isinstance(data, dict) and data.get("success"):
            data["taskId"] = tid
            result = json.dumps(data)
    except json.JSONDecodeError:
        pass
    sync_kanban_task_id(tid, event="record", force=True)
    return result


def kanban_broccolidb_board_intel(board: str = None, limit: int = 25) -> str:
    guard = _require_orchestrator_tool("kanban_broccolidb_board_intel")
    if guard:
        return guard

    lim = max(1, min(int(limit or 25), 100))
    try:
        kb_mod, conn = _connect(board=board)
        try:
            kb_mod.recompute_ready(conn)
            tasks = kb_mod.list_tasks(conn, limit=lim)
            by_status: dict[str, int] = {}
            for t in tasks:
                by_status[t.status] = by_status.get(t.status, 0) + 1
            board_summary = {
                "task_count": len(tasks),
                "by_status": by_status,
                "tasks": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "status": t.status,
                        "assignee": t.assignee,
                        "priority": t.priority,
                    }
                    for t in tasks
                ],
            }
        finally:
            conn.close()
    except Exception as exc:
        return tool_error(f"kanban board read failed: {exc}")

    from plugins.dietcode.lib.tools.kanban_broccolidb_bridge import get_config

    cfg = get_config()
    intel_params = {
        "shard_id": cfg.shard_id,
        "queue_limit": max(lim * 10, 100),
        "hive_limit": max(lim * 10, 100),
    }

    # One RPC round-trip for BroccoliQ metrics + hive drift probe
    task_ids = [t["id"] for t in board_summary.get("tasks", []) if isinstance(t, dict) and t.get("id")]
    batch_calls: list[tuple[str, dict]] = [("hive_board_intel", intel_params)]
    if task_ids:
        batch_calls.append((
            "hive_drift",
            {"shard_id": cfg.shard_id, "task_ids": task_ids},
        ))

    raw_batch = run_db_rpc_batch(batch_calls, timeout=60)
    hive_metrics: dict = {}
    drift_from_batch: Optional[dict] = None
    try:
        batch_data = json.loads(raw_batch)
        if batch_data.get("success") and isinstance(batch_data.get("results"), list):
            for entry in batch_data["results"]:
                if not entry.get("ok"):
                    continue
                m = entry.get("method")
                res = entry.get("result") if isinstance(entry.get("result"), dict) else {}
                if m == "hive_board_intel":
                    hive_metrics = res
                elif m == "hive_drift":
                    drift_from_batch = _drift_report_from_hive_rows(
                        board_summary,
                        res.get("rows") if isinstance(res.get("rows"), list) else [],
                        shard_id=cfg.shard_id,
                        limit=lim,
                    )
        if not hive_metrics:
            hive_metrics = batch_data
    except json.JSONDecodeError:
        hive_metrics = {"parse_error": raw_batch[:500]}

    drift = drift_from_batch if drift_from_batch is not None else compute_drift(board=board, limit=lim)

    return json.dumps({
        "success": True,
        "board": board_summary,
        "broccoliq": hive_metrics,
        "drift": drift,
    })


def kanban_broccolidb_drift(board: str = None, limit: int = 200) -> str:
    guard = _require_orchestrator_tool("kanban_broccolidb_drift")
    if guard:
        return guard
    return json.dumps(compute_drift(board=board, limit=limit))


# ─── Schemas ───

registry.register(
    name="kanban_broccolidb_context",
    toolset="dietcode",
    schema={
        "name": "kanban_broccolidb_context",
        "description": (
            "Load BroccoliDB epistemic context for a kanban task. Call after kanban_show(). "
            "Syncs kanban state to hive_tasks first unless sync_first=false."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "sync_first": {"type": "boolean", "default": True},
            },
        },
    },
    handler=lambda args, **kw: kanban_broccolidb_context(
        task_id=args.get("task_id"),
        sync_first=args.get("sync_first", True),
    ),
    check_fn=_check_kanban_broccolidb_mode,
    emoji="🧠",
)

registry.register(
    name="kanban_broccolidb_sync",
    toolset="dietcode",
    schema={
        "name": "kanban_broccolidb_sync",
        "description": "Force-sync a kanban task into BroccoliQ hive_tasks (bypasses debounce).",
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "event": {
                    "type": "string",
                    "enum": ["sync", "start", "heartbeat", "complete", "block", "create", "context", "record"],
                },
            },
        },
    },
    handler=lambda args, **kw: kanban_broccolidb_sync(
        task_id=args.get("task_id"),
        event=args.get("event", "sync"),
    ),
    check_fn=_check_kanban_broccolidb_mode,
    emoji="🔄",
)

registry.register(
    name="kanban_broccolidb_record",
    toolset="dietcode",
    schema={
        "name": "kanban_broccolidb_record",
        "description": (
            "Record a durable handoff/decision in BroccoliDB before kanban_complete. "
            "Auto-syncs hive state after write."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "task_id": {"type": "string"},
                "tags": {"type": "string"},
                "kb_type": {"type": "string", "default": "kanban_handoff"},
            },
            "required": ["summary"],
        },
    },
    handler=lambda args, **kw: kanban_broccolidb_record(
        summary=args.get("summary", ""),
        task_id=args.get("task_id"),
        tags=args.get("tags"),
        kb_type=args.get("kb_type", "kanban_handoff"),
    ),
    check_fn=_check_kanban_broccolidb_mode,
    emoji="📓",
)

registry.register(
    name="kanban_broccolidb_board_intel",
    toolset="dietcode",
    schema={
        "name": "kanban_broccolidb_board_intel",
        "description": (
            "Orchestrator-only: kanban board snapshot + BroccoliQ metrics + drift report."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "board": {"type": "string"},
                "limit": {"type": "integer", "default": 25},
            },
        },
    },
    handler=lambda args, **kw: kanban_broccolidb_board_intel(
        board=args.get("board"),
        limit=args.get("limit", 25),
    ),
    check_fn=_check_kanban_broccolidb_orchestrator_mode,
    emoji="📊",
)

registry.register(
    name="kanban_broccolidb_drift",
    toolset="dietcode",
    schema={
        "name": "kanban_broccolidb_drift",
        "description": (
            "Orchestrator-only: detect kanban vs hive_tasks mismatches (missing rows, status drift)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "board": {"type": "string"},
                "limit": {"type": "integer", "default": 200},
            },
        },
    },
    handler=lambda args, **kw: kanban_broccolidb_drift(
        board=args.get("board"),
        limit=args.get("limit", 200),
    ),
    check_fn=_check_kanban_broccolidb_orchestrator_mode,
    emoji="🔍",
)
