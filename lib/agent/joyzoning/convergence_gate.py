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
        from plugins.dietcode.lib.agent.gates.kanban_complete import first_block_message

        message = first_block_message(args=args)
        if message:
            return block_dict(message)
        return None
    except Exception as exc:
        if fail_closed:
            from plugins.dietcode.lib.agent.features import is_joyzoning_enabled

            if is_joyzoning_enabled():
                return block_dict(f"Convergence gate unavailable: {exc}")
            return block_dict("Convergence gate unavailable.")
        return None


def assert_kanban_completion_allowed(task_id: str) -> None:
    """Raise when joyzoning convergence policy blocks kanban completion."""
    from plugins.dietcode.lib.agent.gates.kanban_complete import first_block_message

    message = first_block_message(task_id)
    if message:
        raise JoyZoningCompletionBlocked(message)


class JoyZoningCompletionBlocked(Exception):
    """Kanban completion rejected by Hermes-owned convergence gate."""
