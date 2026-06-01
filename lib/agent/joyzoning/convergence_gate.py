"""Convergence gate helpers — shared by plugin hooks and kanban_db.complete_task."""
from __future__ import annotations

from typing import Any, Optional


def block_dict(message: str) -> dict[str, str]:
    """Hermes pre_tool_call contract — only dict blocks are honored."""
    return {"action": "block", "message": message}


def pre_tool_call_block(
    *,
    tool_name: str,
    args: Any = None,
    fail_closed: bool = True,
) -> dict[str, str] | None:
    """Return a block dict when kanban_complete violates convergence policy."""
    if tool_name != "kanban_complete":
        return None
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, resolve_scope_id
        from plugins.dietcode.lib.agent.joyzoning.convergence import require_review_before_complete

        if not get_joyzoning_config().enabled:
            return None
        parsed = args if isinstance(args, dict) else {}
        scope = resolve_scope_id(parsed.get("task_id"))
        msg = require_review_before_complete(scope)
        return block_dict(msg) if msg else None
    except Exception as exc:
        if fail_closed:
            try:
                from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config
                if get_joyzoning_config().enabled:
                    return block_dict(f"Convergence gate unavailable: {exc}")
            except Exception:
                return block_dict("Convergence gate unavailable.")
        return None


def assert_kanban_completion_allowed(task_id: str) -> None:
    """Raise when joyzoning convergence policy blocks kanban completion."""
    from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config
    from plugins.dietcode.lib.agent.joyzoning.convergence import require_review_before_complete

    if not get_joyzoning_config().enabled:
        return
    msg = require_review_before_complete(task_id)
    if msg:
        raise JoyZoningCompletionBlocked(msg)


class JoyZoningCompletionBlocked(Exception):
    """Kanban completion rejected by Hermes-owned convergence gate."""
