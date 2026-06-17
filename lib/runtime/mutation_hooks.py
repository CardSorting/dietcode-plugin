# -*- coding: utf-8 -*-
"""Mutation runtime hooks — journal dietcode_kernel results into JoyZoning."""
from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def _result_already_journaled(result: Any) -> bool:
    from plugins.dietcode.lib.agent.kernel_receipt_journal import parse_tool_result

    parsed = parse_tool_result(result)
    if not isinstance(parsed, dict):
        return False
    journal_meta = parsed.get("_journal")
    if not isinstance(journal_meta, dict):
        return False
    return bool(journal_meta.get("journaled") or journal_meta.get("deduplicated"))


def _journal_action(args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    return str(args.get("action") or "").strip().lower()


def _post_tool_call(
    *,
    tool_name: str = "",
    args: Any = None,
    result: Any = None,
    **_: Any,
) -> None:
    if tool_name != "dietcode_kernel":
        return
    if _result_already_journaled(result):
        return
    action = _journal_action(args)
    try:
        if action == "patch":
            from plugins.dietcode.lib.agent.kernel_receipt_journal import journal_kernel_patch

            journal_kernel_patch(tool_name=tool_name, args=args, result=result)
        elif action == "verify":
            from plugins.dietcode.lib.agent.kernel_verify_journal import journal_kernel_verify

            journal_kernel_verify(tool_name=tool_name, args=args, result=result)
    except Exception as exc:
        logger.warning("dietcode mutation post_tool_call journal skipped: %s", exc)


def on_mutation_journal_transform(
    tool_name: str = "",
    args: Optional[dict[str, Any]] = None,
    result: Any = None,
    **_: Any,
) -> Optional[str]:
    if tool_name != "dietcode_kernel":
        return None
    action = _journal_action(args)
    if action not in {"patch", "verify"}:
        return None
    try:
        if action == "patch":
            from plugins.dietcode.lib.agent.kernel_receipt_journal import (
                journal_kernel_patch,
                merge_journal_warning_into_result,
            )

            report = journal_kernel_patch(tool_name=tool_name, args=args, result=result)
            return merge_journal_warning_into_result(result, report)
        from plugins.dietcode.lib.agent.kernel_verify_journal import (
            journal_kernel_verify,
            merge_journal_warning_into_result,
        )

        report = journal_kernel_verify(tool_name=tool_name, args=args, result=result)
        return merge_journal_warning_into_result(result, report)
    except Exception as exc:
        logger.warning("dietcode mutation transform journal skipped: %s", exc)
        return None
