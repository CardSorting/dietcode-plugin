# -*- coding: utf-8 -*-
"""dietcode_kernel tool — native mutation surface (codemarie-new strategy)."""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from tools.registry import registry, tool_error

_ACTIONS = frozenset({"status", "search", "patch", "verify", "coherence", "refresh"})


def _manager():
    from plugins.dietcode.lib.agent.native_mutation import NativeMutationManager

    return NativeMutationManager.get_instance()


def _resolve_workspace(override: Optional[str]) -> tuple[Any, Optional[str]]:
    from plugins.dietcode.lib.agent.native_mutation import resolve_workspace

    return resolve_workspace(override)


def _default_task_id(task_id: str) -> str:
    if task_id.strip():
        return task_id.strip()
    for key in ("HERMES_KANBAN_TASK", "DIETCODE_TASK_ID"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return ""


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def dietcode_kernel(
    action: str,
    *,
    workspace: Optional[str] = None,
    path: str = "",
    query: str = "",
    unified_diff: str = "",
    line_search: str = "",
    line_replace: str = "",
    task_id: str = "",
    command: str = "",
    cwd: str = "",
    max_results: int = 20,
    coherence_token_id: str = "",
    expected_workspace_revision: Optional[int] = None,
    paths: Optional[list[str]] = None,
) -> str:
    """Native mutation runtime — status, search, governed patch, verify, coherence, refresh."""
    act = (action or "").strip().lower()
    if act not in _ACTIONS:
        return tool_error(
            f"Unknown action {action!r}. Use: status | search | patch | verify | coherence | refresh."
        )

    ws, err = _resolve_workspace(workspace)
    if ws is None:
        return _json_result({
            "ok": False,
            "error": {"string_code": "workspace_unresolved", "message": err or "workspace not resolved"},
        })

    mgr = _manager()
    tid = _default_task_id(task_id)

    if act == "status":
        return _json_result(mgr.get_status(ws, tid))

    if act == "search":
        if not query.strip():
            return tool_error("query is required for search")
        return _json_result(mgr.search_literal(ws, query, max_results=max_results))

    if act == "coherence":
        if not tid:
            return tool_error("task_id is required for coherence")
        token = mgr.issue_coherence_token(ws, tid, paths or [])
        return _json_result({"ok": True, "result": token})

    if act == "refresh":
        return _json_result(mgr.refresh_anchor(ws, paths))

    if act == "verify":
        if not command.strip():
            return tool_error("command is required for verify")
        return _json_result(mgr.apply_verify(ws, command, cwd=cwd, task_id=tid))

    if not path.strip():
        return tool_error("path is required for patch")
    rev = expected_workspace_revision
    if rev is None and coherence_token_id:
        pass
    return _json_result(
        mgr.apply_patch(
            ws,
            path,
            unified_diff=unified_diff,
            line_search=line_search,
            line_replace=line_replace,
            task_id=tid,
            coherence_token_id=coherence_token_id or None,
            expected_workspace_revision=rev,
        )
    )


registry.register(
    name="dietcode_kernel",
    toolset="dietcode",
    schema={
        "name": "dietcode_kernel",
        "description": (
            "Native mutation runtime — workspace status, literal search, governed patch, "
            "verify, coherence tokens, and context refresh. Mirrors LUMI/codemarie strategy."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "search", "patch", "verify", "coherence", "refresh"],
                },
                "workspace": {"type": "string"},
                "path": {"type": "string"},
                "query": {"type": "string"},
                "unified_diff": {"type": "string"},
                "line_search": {"type": "string"},
                "line_replace": {"type": "string"},
                "task_id": {"type": "string"},
                "command": {"type": "string"},
                "cwd": {"type": "string"},
                "max_results": {"type": "integer", "default": 20},
                "coherence_token_id": {"type": "string"},
                "expected_workspace_revision": {"type": "integer"},
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Paths to anchor (coherence/refresh)",
                },
            },
            "required": ["action"],
        },
    },
    handler=lambda args, **kw: dietcode_kernel(
        action=args.get("action", ""),
        workspace=args.get("workspace"),
        path=args.get("path", ""),
        query=args.get("query", ""),
        unified_diff=args.get("unified_diff", ""),
        line_search=args.get("line_search", ""),
        line_replace=args.get("line_replace", ""),
        task_id=args.get("task_id", ""),
        command=args.get("command", ""),
        cwd=args.get("cwd", ""),
        max_results=int(args.get("max_results") or 20),
        coherence_token_id=str(args.get("coherence_token_id") or ""),
        expected_workspace_revision=args.get("expected_workspace_revision"),
        paths=args.get("paths"),
    ),
    emoji="🥦",
)
