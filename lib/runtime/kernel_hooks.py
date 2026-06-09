# -*- coding: utf-8 -*-
"""Kernel bridge hooks — receipt/verify journal (2C/4) and raw-write router (3A)."""
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


def _pre_tool_call(
    *,
    tool_name: str = "",
    args: Any = None,
    **_: Any,
) -> dict[str, str] | None:
    """Warn (or Phase 3B block) on raw Hermes writes when kernel patch gate is open."""
    try:
        from plugins.dietcode.lib.agent.kernel_raw_write_router import evaluate_raw_write_pre_tool_call

        return evaluate_raw_write_pre_tool_call(tool_name=tool_name, args=args)
    except Exception as exc:
        logger.warning("dietcode.kernel raw_write pre_tool_call skipped: %s", exc)
        return None


def _emit_journal_progress(action: str) -> None:
    try:
        from plugins.dietcode.lib.agent.kernel_progress import emit_phase
    except ImportError:
        from lib.agent.kernel_progress import emit_phase
    emit_phase("journal.recording", action=action)
    if action == "verify":
        emit_phase("convergence.checking", action=action)


def _post_tool_call(
    *,
    tool_name: str = "",
    args: Any = None,
    result: Any = None,
    **_: Any,
) -> None:
    """Journal dietcode_kernel patch/verify results into JoyZoning (non-blocking)."""
    if tool_name != "dietcode_kernel":
        return
    if _result_already_journaled(result):
        return
    action = _journal_action(args)
    try:
        if action == "patch":
            _emit_journal_progress("patch")
            from plugins.dietcode.lib.agent.kernel_receipt_journal import journal_kernel_patch

            journal_kernel_patch(tool_name=tool_name, args=args, result=result)
        elif action == "verify":
            _emit_journal_progress("verify")
            from plugins.dietcode.lib.agent.kernel_verify_journal import journal_kernel_verify

            journal_kernel_verify(tool_name=tool_name, args=args, result=result)
    except Exception as exc:
        logger.warning("dietcode.kernel post_tool_call journal skipped: %s", exc)


def on_kernel_journal_transform(
    tool_name: str = "",
    args: Optional[dict[str, Any]] = None,
    result: Any = None,
    **_: Any,
) -> Optional[str]:
    """Attach non-fatal journal warnings to dietcode_kernel patch/verify results."""
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
        logger.warning("dietcode.kernel transform journal skipped: %s", exc)
        return None


def on_kernel_raw_write_transform(
    tool_name: str = "",
    args: Optional[dict[str, Any]] = None,
    result: Any = None,
    **_: Any,
) -> Optional[str]:
    """Surface Phase 3A raw-write warnings in agent-visible tool results."""
    try:
        from plugins.dietcode.lib.agent.kernel_raw_write_router import (
            is_raw_write_tool,
            merge_raw_write_warning_into_result,
            take_raw_write_warning,
        )
    except Exception as exc:
        logger.warning("dietcode.kernel raw_write transform import skipped: %s", exc)
        return None

    if not is_raw_write_tool(tool_name):
        return None

    metadata = take_raw_write_warning()
    if not metadata:
        return None

    try:
        return merge_raw_write_warning_into_result(result, metadata)
    except Exception as exc:
        logger.warning("dietcode.kernel raw_write transform skipped: %s", exc)
        return None
