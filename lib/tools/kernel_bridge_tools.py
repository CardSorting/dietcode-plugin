# -*- coding: utf-8 -*-
"""Kernel bridge Hermes tool — opt-in governed patch via dietcode-kernel (Phase 2B)."""
from __future__ import annotations

import json
from typing import Any, Optional

from tools.registry import registry, tool_error

_ACTIONS = frozenset({"status", "search", "patch", "verify"})


def _bridge_client():
    from plugins.dietcode.lib.agent import kernel_bridge_client as kbc

    return kbc


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _progress_module():
    try:
        from plugins.dietcode.lib.agent import kernel_progress as kp
    except ImportError:
        from lib.agent import kernel_progress as kp
    return kp


def _run_with_progress(
    *,
    action: str,
    workspace: Optional[str],
    path: str,
    task_id: str,
    command: str = "",
    runner,
) -> dict[str, Any]:
    kp = _progress_module()
    tracker = kp.start_operation(
        action=action,
        path=path,
        command=command,
        workspace_root=str(workspace or ""),
        task_id=task_id,
    )
    try:
        from plugins.dietcode.lib.agent.kernel_progress_ux import build_acknowledgement_payload
    except ImportError:
        from lib.agent.kernel_progress_ux import build_acknowledgement_payload
    ack = build_acknowledgement_payload(tracker)
    try:
        result = runner()
        if isinstance(result, dict):
            result["_kernel_acknowledgement"] = ack
            code = str(result.get("string_code") or "")
            if not code and isinstance(result.get("error"), dict):
                code = str(result["error"].get("string_code") or "")
            if result.get("ok"):
                tracker.finish(ok=True, string_code=code or None)
            else:
                tracker.finish(
                    ok=False,
                    string_code=code or "bridge_rpc_error",
                    error=result.get("error") if isinstance(result.get("error"), dict) else result,
                )
            return kp.attach_operator_hints_to_result(result, action=action)
        tracker.finish(ok=True)
        return {"ok": True, "result": result}
    except Exception as exc:
        tracker.finish(
            ok=False,
            string_code="bridge_transport_error",
            error={"message": str(exc)},
        )
        raise
    finally:
        kp.end_operation()


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
) -> str:
    """Kernel bridge — status, search, governed patch, and verify.run."""
    kbc = _bridge_client()
    act = (action or "").strip().lower()
    if act not in _ACTIONS:
        return tool_error(
            f"Unknown action {action!r}. Use: status | search | patch | verify. "
            "Patch requires dietcode.kernel.bridge.mutations_enabled: true."
        )

    cfg = kbc.KernelBridgeConfig.load()
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_warm import ensure_keep_warm_started
    except ImportError:
        from lib.agent.kernel_bridge_warm import ensure_keep_warm_started
    ensure_keep_warm_started()
    if not cfg.enabled:
        disabled = kbc.bridge_error(kbc.BRIDGE_DISABLED, "Kernel bridge is disabled in config")
        kp = _progress_module()
        payload = kp.attach_operator_hints_to_result(
            {**disabled, "action": act},
            action=act,
        )
        return _json_result(payload)

    if act == "status":
        result = _run_with_progress(
            action=act,
            workspace=workspace,
            path="",
            task_id=task_id,
            runner=lambda: {**kbc.workspace_status(workspace), "action": "status"},
        )
        return _json_result(result)

    if act == "search":
        if not query.strip():
            return tool_error("query is required for search")
        result = _run_with_progress(
            action=act,
            workspace=workspace,
            path="",
            task_id=task_id,
            runner=lambda: {**kbc.search_literal(workspace, query, max_results=max_results), "action": "search"},
        )
        return _json_result(result)

    if act == "verify":
        if not command.strip():
            return tool_error("command is required for verify")
        result = _run_with_progress(
            action=act,
            workspace=workspace,
            path="",
            task_id=task_id,
            command=command,
            runner=lambda: kbc.apply_kernel_verify(
                workspace,
                command,
                cwd=cwd,
                task_id=task_id,
            ),
        )
        return _json_result(result)

    result = _run_with_progress(
        action=act,
        workspace=workspace,
        path=path,
        task_id=task_id,
        runner=lambda: kbc.apply_kernel_patch(
            workspace,
            path,
            unified_diff=unified_diff,
            line_search=line_search,
            line_replace=line_replace,
            task_id=task_id,
        ),
    )
    return _json_result(result)


registry.register(
    name="dietcode_kernel",
    toolset="dietcode",
    schema={
        "name": "dietcode_kernel",
        "description": (
            "DietCode kernel bridge — workspace status, literal search, governed patch, "
            "and allowlisted verify.run. Patch requires "
            "dietcode.kernel.bridge.mutations_enabled: true."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["status", "search", "patch", "verify"],
                    "description": (
                        "status=workspace.status; search=search.literal; "
                        "patch=kernel patch.apply; verify=kernel verify.run (allowlisted commands)"
                    ),
                },
                "workspace": {
                    "type": "string",
                    "description": "Optional workspace root override (must pass safe_for_mutation validation)",
                },
                "path": {
                    "type": "string",
                    "description": "Repo-relative path (required for patch)",
                },
                "query": {
                    "type": "string",
                    "description": "Literal search query (required for search)",
                },
                "unified_diff": {
                    "type": "string",
                    "description": "Unified diff body (patch)",
                },
                "line_search": {
                    "type": "string",
                    "description": "Single-line search text (patch alternative to unified_diff)",
                },
                "line_replace": {
                    "type": "string",
                    "description": "Replacement line when using line_search",
                },
                "task_id": {
                    "type": "string",
                    "description": "Governed task id (defaults to HERMES_KANBAN_TASK / DIETCODE_TASK_ID)",
                },
                "command": {
                    "type": "string",
                    "description": "Allowlisted verify command (required for verify)",
                },
                "cwd": {
                    "type": "string",
                    "description": "Optional workspace-relative cwd for verify.run",
                },
                "max_results": {
                    "type": "integer",
                    "description": "Max search.literal results",
                    "default": 20,
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
    ),
    emoji="🥦",
)
