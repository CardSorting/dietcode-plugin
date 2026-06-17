# -*- coding: utf-8 -*-
"""Journal dietcode_kernel verify results into JoyZoning mutation_verify."""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_JOURNAL_DEDUP_TTL_SEC = 300.0
_JOURNAL_DEDUP_MAX = 500
_JOURNALED_VERIFY_KEYS: dict[str, float] = {}


def _prune_verify_dedup_cache() -> None:
    now = time.monotonic()
    stale = [key for key, seen_at in _JOURNALED_VERIFY_KEYS.items() if (now - seen_at) > _JOURNAL_DEDUP_TTL_SEC]
    for key in stale:
        _JOURNALED_VERIFY_KEYS.pop(key, None)
    if len(_JOURNALED_VERIFY_KEYS) > _JOURNAL_DEDUP_MAX:
        ordered = sorted(_JOURNALED_VERIFY_KEYS.items(), key=lambda item: item[1])
        for key, _seen_at in ordered[: len(_JOURNALED_VERIFY_KEYS) - _JOURNAL_DEDUP_MAX]:
            _JOURNALED_VERIFY_KEYS.pop(key, None)


def reset_verify_journal_dedup_cache() -> None:
    """Test helper — clear in-process verify dedup keys."""
    _JOURNALED_VERIFY_KEYS.clear()


def parse_tool_result(result: Any) -> Optional[dict[str, Any]]:
    from plugins.dietcode.lib.agent.mutation_receipt_journal import parse_tool_result as _parse

    return _parse(result)


def merge_journal_warning_into_result(result: Any, journal_report: dict[str, Any]) -> Optional[str]:
    from plugins.dietcode.lib.agent.mutation_receipt_journal import (
        merge_journal_warning_into_result as _merge,
    )

    return _merge(result, journal_report)


def should_journal_mutation_verify(
    tool_name: str,
    args: Any,
    parsed: Optional[dict[str, Any]],
) -> bool:
    if tool_name != "dietcode_kernel" or not isinstance(parsed, dict):
        return False
    tool_args = args if isinstance(args, dict) else {}
    if str(tool_args.get("action") or "").strip().lower() != "verify":
        return False
    if parsed.get("action") != "verify":
        return False
    if parsed.get("ok") is not True:
        return False
    return parsed.get("verify_ran") is True


def _dedup_key(parsed: dict[str, Any]) -> str:
    parts = [
        str(parsed.get("taskId") or ""),
        str(parsed.get("workspace_root") or ""),
        str(parsed.get("command") or ""),
        str(parsed.get("exit_code") or ""),
        str(parsed.get("passed")),
    ]
    return "|".join(parts)


def _build_verify_report(parsed: dict[str, Any]) -> str:
    cmd = str(parsed.get("command") or "")
    passed = parsed.get("passed")
    exit_code = parsed.get("exit_code")
    stdout = str(parsed.get("stdout_summary") or "")
    stderr = str(parsed.get("stderr_summary") or "")
    lines = [
        f"native verify: {cmd}",
        f"passed={passed} exit_code={exit_code}",
    ]
    if stdout.strip():
        lines.append(f"stdout: {stdout.strip()[:500]}")
    if stderr.strip():
        lines.append(f"stderr: {stderr.strip()[:500]}")
    return "\n".join(lines)[:2000]


def _build_journal_metadata(parsed: dict[str, Any]) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "source": "dietcode_kernel",
        "physical_authority": "native_mutation",
        "lifecycle_authority": "joyzoning",
        "verify_ran": True,
    }
    for key in (
        "taskId",
        "workspace_root",
        "command",
        "cwd",
        "passed",
        "exit_code",
        "stdout_summary",
        "stderr_summary",
    ):
        if parsed.get(key) is not None:
            meta[key] = parsed[key]
    block = parsed.get("mutation") or parsed.get("kernel")
    if isinstance(block, dict) and block:
        meta["mutation"] = block
    return meta


def _resolve_active_mutation_id(scope_id: str) -> tuple[str | None, dict[str, Any]]:
    from plugins.dietcode.lib.agent.joyzoning.journal import get_journal

    journal = get_journal()
    active = journal.get_active_mutation(scope_id)
    if not active:
        row = journal._conn().execute(
            """
            SELECT id, state FROM mutation_scopes
            WHERE scope_id = ?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (scope_id,),
        ).fetchone()
        if row:
            return str(row["id"]), {"reused_latest_mutation": True, "state": row["state"]}
        return None, {"reason": "no_mutation_in_scope"}

    return str(active["id"]), {
        "reused_active_mutation": True,
        "mutation_id": active["id"],
        "state": active.get("state"),
    }


def journal_mutation_verify(
    *,
    tool_name: str,
    args: Any = None,
    result: Any = None,
) -> dict[str, Any]:
    """Record native verify in JoyZoning via mutation_verify semantics."""
    parsed = parse_tool_result(result)
    if not should_journal_mutation_verify(tool_name, args, parsed):
        return {"journaled": False, "skipped": True}

    assert parsed is not None

    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, resolve_scope_id
    except ImportError:
        return {
            "journaled": False,
            "warning": "JoyZoning unavailable — verify not journaled",
        }

    cfg = get_joyzoning_config()
    if not cfg.enabled:
        return {"journaled": False, "skipped": True, "reason": "joyzoning_disabled"}

    scope_id = resolve_scope_id(parsed.get("taskId"))
    dedup = _dedup_key(parsed)
    _prune_verify_dedup_cache()
    if dedup in _JOURNALED_VERIFY_KEYS:
        return {"journaled": True, "deduplicated": True, "scope_id": scope_id}

    passed = bool(parsed.get("passed"))
    metadata = _build_journal_metadata(parsed)
    report = _build_verify_report(parsed)

    try:
        mutation_id, mutation_info = _resolve_active_mutation_id(scope_id)
        if not mutation_id:
            return {
                "journaled": False,
                "skipped": True,
                "reason": mutation_info.get("reason", "no_mutation_in_scope"),
            }

        from plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle import record_verification
        from plugins.dietcode.lib.agent.joyzoning.journal import get_journal
        from plugins.dietcode.lib.agent.joyzoning.runtime_events import emit_runtime_event

        verify_result = record_verification(
            mutation_id,
            report=report,
            passed=passed,
            scope_id=scope_id,
        )
        if not verify_result.get("success"):
            raise RuntimeError(
                verify_result.get("message") or verify_result.get("error") or "record_verification failed"
            )

        get_journal().upsert_mutation_scope(
            mutation_id,
            scope_id,
            state="verified" if passed else "rejected",
            goal=report[:500],
            metadata={**metadata, **mutation_info, "passed": passed},
        )

        emit_runtime_event(
            "mutation.verified" if passed else "mutation.verify_failed",
            scope_id=scope_id,
            payload={
                "mutation_id": mutation_id,
                "command": parsed.get("command"),
                "passed": passed,
                "taskId": parsed.get("taskId"),
            },
        )

        _JOURNALED_VERIFY_KEYS[dedup] = time.monotonic()
        return {
            "journaled": True,
            "scope_id": scope_id,
            "mutation_id": mutation_id,
            "passed": passed,
            "metadata": metadata,
        }
    except Exception as exc:
        logger.warning("mutation verify journal failed (non-fatal): %s", exc)
        return {
            "journaled": False,
            "warning": f"Verify completed but JoyZoning journal failed: {exc}",
        }
