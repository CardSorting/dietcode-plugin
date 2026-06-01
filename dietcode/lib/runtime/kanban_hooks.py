# -*- coding: utf-8 -*-
"""Kanban ↔ BroccoliQ lifecycle hooks."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _on_session_start(*, session_id: str = "", **_: Any) -> None:
    """Hive sync + scope aliases for kanban dispatcher workers."""
    try:
        from plugins.dietcode.lib.tools.kanban_broccolidb_bridge import sync_on_worker_start
        sync_on_worker_start()
    except Exception as exc:
        logger.warning("dietcode.kanban on_session_start: %s", exc)


def _extract_task_id_from_result(result: Any) -> str | None:
    if not isinstance(result, str):
        return None
    try:
        data = json.loads(result)
    except (json.JSONDecodeError, TypeError):
        return None
    from plugins.dietcode.lib.tools.kanban_broccolidb_bridge import validate_task_id
    return validate_task_id(data.get("task_id"))


def _on_post_tool_call(
    *,
    tool_name: str = "",
    args: Any = None,
    result: Any = None,
    **_: Any,
) -> None:
    try:
        from plugins.dietcode.lib.tools.kanban_broccolidb_bridge import (
            maybe_auto_sync_tool,
            resolve_board_slug,
            schedule_sync,
        )

        parsed_args = args if isinstance(args, dict) else {}
        maybe_auto_sync_tool(tool_name, parsed_args)

        if tool_name == "kanban_create":
            new_id = _extract_task_id_from_result(result)
            if new_id:
                schedule_sync(
                    new_id,
                    event="create",
                    board=resolve_board_slug(),
                    force=True,
                )
    except Exception as exc:
        logger.warning("dietcode.kanban post_tool_call (%s): %s", tool_name, exc)
