# -*- coding: utf-8 -*-
"""JoyZoning runtime hooks — session lifecycle, convergence gates, journal events."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _on_session_start(*, session_id: str = "", **_: Any) -> None:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, resolve_scope_id
        from plugins.dietcode.lib.agent.joyzoning.runtime_events import emit_runtime_event
        if not get_joyzoning_config().enabled:
            return
        from plugins.dietcode.lib.agent.joyzoning.config import read_scope_env
        from plugins.dietcode.lib.agent.joyzoning.scope_registry import register_from_scope_env

        register_from_scope_env()
        kanban_task = read_scope_env("HERMES_KANBAN_TASK")

        jsdp_brief = None
        if kanban_task or read_scope_env("HERMES_KANBAN_WORKSPACE"):
            try:
                from plugins.dietcode.lib.agent.joyzoning.jsdp_autonomous import session_brief
                jsdp_brief = session_brief()
            except Exception:
                pass

        emit_runtime_event(
            "session.start",
            scope_id=resolve_scope_id(),
            session_id=session_id or read_scope_env("HERMES_SESSION_ID"),
            payload={
                "jsdp_role": get_joyzoning_config().jsdp_role,
                "kanban_task": kanban_task or None,
                "jsdp_autonomous": jsdp_brief,
            },
        )
    except Exception as exc:
        logger.warning("dietcode.joyzoning on_session_start: %s", exc)


def _on_session_end(*, session_id: str = "", **_: Any) -> None:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, read_scope_env, resolve_scope_id
        from plugins.dietcode.lib.agent.joyzoning.runtime_events import emit_runtime_event
        if not get_joyzoning_config().enabled:
            return
        emit_runtime_event(
            "session.end",
            scope_id=resolve_scope_id(),
            session_id=session_id or read_scope_env("HERMES_SESSION_ID"),
        )
    except Exception as exc:
        logger.warning("dietcode.joyzoning on_session_end: %s", exc)


def _pre_tool_call(*, tool_name: str = "", args: Any = None, **_: Any) -> dict[str, str] | None:
    """Convergence gate — block kanban_complete until review/convergence (runtime authority)."""
    from plugins.dietcode.lib.agent.joyzoning.convergence_gate import pre_tool_call_block
    return pre_tool_call_block(tool_name=tool_name, args=args, fail_closed=True)


def _post_tool_call(
    *,
    tool_name: str = "",
    args: Any = None,
    result: Any = None,
    task_id: str = "",
    duration_ms: int = 0,
    **_: Any,
) -> None:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, resolve_scope_id
        from plugins.dietcode.lib.agent.joyzoning.runtime_events import emit_runtime_event

        cfg = get_joyzoning_config()
        if not cfg.enabled or not cfg.execution_journal:
            return
        parsed = args if isinstance(args, dict) else {}
        scope = resolve_scope_id(parsed.get("task_id"))
        emit_runtime_event(
            "tool.complete",
            scope_id=scope,
            payload={
                "tool": tool_name,
                "task_id": task_id,
                "duration_ms": duration_ms,
                "success": isinstance(result, str) and "error" not in result[:200].lower(),
            },
        )
    except Exception as exc:
        logger.debug("dietcode.joyzoning post_tool_call: %s", exc)
