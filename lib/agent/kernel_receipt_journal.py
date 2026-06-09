# -*- coding: utf-8 -*-
"""Bridge kernel patch receipts into JoyZoning mutation journal (Phase 2C)."""
from __future__ import annotations

import json
import logging
import time
from typing import Any, Optional

logger = logging.getLogger(__name__)

_JOURNAL_DEDUP_TTL_SEC = 300.0
_JOURNAL_DEDUP_MAX = 500

# Kernel mutationReceipt keys we copy when present (no invented fields).
_RECEIPT_KEYS = frozenset({
    "path",
    "beforeContentHash",
    "postContentHash",
    "patchFingerprint",
    "readSourceBefore",
    "applyChannel",
    "atomic",
})

_KERNEL_RESULT_KEYS = frozenset({
    "operationId",
    "patched",
    "revisionBefore",
    "revisionAfter",
})

_COHERENCE_KEYS = frozenset({
    "coherenceTokenId",
    "expectedWorkspaceRevision",
    "coherence",
    "workspaceRevision",
})

_VERIFY_KEYS = frozenset({
    "verifyStatus",
    "verificationStatus",
    "verified",
    "verify",
})

_JOURNALED_KEYS: dict[str, float] = {}


def _prune_journal_dedup_cache() -> None:
    now = time.monotonic()
    stale = [key for key, seen_at in _JOURNALED_KEYS.items() if (now - seen_at) > _JOURNAL_DEDUP_TTL_SEC]
    for key in stale:
        _JOURNALED_KEYS.pop(key, None)
    if len(_JOURNALED_KEYS) > _JOURNAL_DEDUP_MAX:
        ordered = sorted(_JOURNALED_KEYS.items(), key=lambda item: item[1])
        for key, _seen_at in ordered[: len(_JOURNALED_KEYS) - _JOURNAL_DEDUP_MAX]:
            _JOURNALED_KEYS.pop(key, None)


def reset_journal_dedup_cache() -> None:
    """Test helper — clear in-process dedup keys."""
    _JOURNALED_KEYS.clear()


def parse_tool_result(result: Any) -> Optional[dict[str, Any]]:
    if isinstance(result, dict):
        return result
    if isinstance(result, str) and result.strip():
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def extract_mutation_receipt(parsed: dict[str, Any]) -> Optional[dict[str, Any]]:
    kernel = parsed.get("kernel")
    if not isinstance(kernel, dict):
        return None
    receipt = kernel.get("mutationReceipt")
    if not isinstance(receipt, dict) or not receipt:
        return None
    return receipt


def should_journal_kernel_patch(
    tool_name: str,
    args: Any,
    parsed: Optional[dict[str, Any]],
) -> bool:
    if tool_name != "dietcode_kernel" or not isinstance(parsed, dict):
        return False
    tool_args = args if isinstance(args, dict) else {}
    if str(tool_args.get("action") or "").strip().lower() != "patch":
        return False
    if parsed.get("ok") is not True:
        return False
    return extract_mutation_receipt(parsed) is not None


def _copy_present_keys(source: dict[str, Any], keys: frozenset[str]) -> dict[str, Any]:
    return {key: source[key] for key in keys if key in source}


def build_journal_metadata(parsed: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    """Build JoyZoning journal metadata from kernel tool result (present fields only)."""
    meta: dict[str, Any] = {
        "source": "dietcode_kernel",
        "physical_authority": "kernel",
        "lifecycle_authority": "joyzoning",
    }

    if parsed.get("taskId"):
        meta["taskId"] = parsed["taskId"]
    if parsed.get("workspace_root"):
        meta["workspace_root"] = parsed["workspace_root"]
    if parsed.get("path"):
        meta["relative_path"] = parsed["path"]

    receipt_copy = _copy_present_keys(receipt, _RECEIPT_KEYS)
    if receipt_copy:
        meta["mutationReceipt"] = receipt_copy

    kernel = parsed.get("kernel")
    if isinstance(kernel, dict):
        kernel_extra = _copy_present_keys(kernel, _KERNEL_RESULT_KEYS)
        if kernel_extra:
            meta["kernel"] = kernel_extra

    coherence: dict[str, Any] = {}
    rpc = parsed.get("rpc")
    rpc_result = rpc.get("result") if isinstance(rpc, dict) else None
    for src in (parsed, kernel if isinstance(kernel, dict) else {}, rpc_result if isinstance(rpc_result, dict) else {}):
        if not isinstance(src, dict):
            continue
        for key in _COHERENCE_KEYS:
            if key in src and src[key] is not None and key not in coherence:
                coherence[key] = src[key]
    if coherence:
        meta["coherence"] = coherence

    verify: dict[str, Any] = {}
    for src in (parsed, kernel if isinstance(kernel, dict) else {}, rpc_result if isinstance(rpc_result, dict) else {}):
        if not isinstance(src, dict):
            continue
        for key in _VERIFY_KEYS:
            if key in src and src[key] is not None and key not in verify:
                verify[key] = src[key]
    if verify:
        meta["verification"] = verify

    return meta


def _dedup_key(parsed: dict[str, Any], receipt: dict[str, Any]) -> str:
    parts = [
        str(parsed.get("taskId") or ""),
        str(parsed.get("workspace_root") or ""),
        str(parsed.get("path") or ""),
        str(receipt.get("patchFingerprint") or ""),
        str(receipt.get("postContentHash") or ""),
    ]
    return "|".join(parts)


def _resolve_mutation_id(scope_id: str, parsed: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    from plugins.dietcode.lib.agent.joyzoning.journal import get_journal
    from plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle import begin_mutation, record_patch

    journal = get_journal()
    active = journal.get_active_mutation(scope_id)
    if active and str(active.get("state") or "") in {"proposed", "patching"}:
        mutation_id = str(active["id"])
        return mutation_id, {"reused_active_mutation": True, "mutation_id": mutation_id}

    rel_path = str(parsed.get("path") or "unknown")
    begun = begin_mutation(goal=f"kernel patch: {rel_path}", scope_id=scope_id)
    if not begun.get("success"):
        raise RuntimeError(begun.get("message") or begun.get("error") or "begin_mutation failed")
    mutation_id = str(begun["mutation_id"])
    return mutation_id, {"created_mutation": True, "mutation_id": mutation_id, "begin": begun}


def journal_kernel_patch(
    *,
    tool_name: str,
    args: Any = None,
    result: Any = None,
) -> dict[str, Any]:
    """
    Record a successful dietcode_kernel patch in the JoyZoning journal.

    Returns ``{journaled: bool, warning?: str, ...}``. Never flips tool success.
    """
    parsed = parse_tool_result(result)
    if not should_journal_kernel_patch(tool_name, args, parsed):
        return {"journaled": False, "skipped": True}

    assert parsed is not None
    receipt = extract_mutation_receipt(parsed)
    assert receipt is not None

    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, resolve_scope_id
    except ImportError:
        return {
            "journaled": False,
            "warning": "JoyZoning unavailable — kernel patch not journaled",
        }

    cfg = get_joyzoning_config()
    if not cfg.enabled:
        return {"journaled": False, "skipped": True, "reason": "joyzoning_disabled"}

    scope_id = resolve_scope_id(parsed.get("taskId"))
    dedup = _dedup_key(parsed, receipt)
    _prune_journal_dedup_cache()
    if dedup in _JOURNALED_KEYS:
        return {"journaled": True, "deduplicated": True, "scope_id": scope_id}

    metadata = build_journal_metadata(parsed, receipt)
    rel_path = str(parsed.get("path") or "")

    try:
        mutation_id, mutation_info = _resolve_mutation_id(scope_id, parsed)
        from plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle import record_patch
        from plugins.dietcode.lib.agent.joyzoning.journal import get_journal
        from plugins.dietcode.lib.agent.joyzoning.runtime_events import emit_runtime_event

        summary = f"kernel patch {rel_path}"
        patch_result = record_patch(mutation_id, summary=summary, scope_id=scope_id)
        if not patch_result.get("success"):
            raise RuntimeError(patch_result.get("message") or patch_result.get("error") or "record_patch failed")

        get_journal().upsert_mutation_scope(
            mutation_id,
            scope_id,
            state="patching",
            goal=summary,
            metadata={**metadata, **mutation_info},
        )

        emit_runtime_event(
            "mutation.kernel_patched",
            scope_id=scope_id,
            payload={
                "mutation_id": mutation_id,
                "path": rel_path,
                "taskId": parsed.get("taskId"),
                "mutationReceipt": metadata.get("mutationReceipt"),
            },
        )

        _JOURNALED_KEYS[dedup] = time.monotonic()
        return {
            "journaled": True,
            "scope_id": scope_id,
            "mutation_id": mutation_id,
            "metadata": metadata,
        }
    except Exception as exc:
        logger.warning("kernel receipt journal failed (non-fatal): %s", exc)
        return {
            "journaled": False,
            "warning": f"Kernel patch succeeded but JoyZoning journal failed: {exc}",
        }


def merge_journal_warning_into_result(result: Any, journal_report: dict[str, Any]) -> Optional[str]:
    """Append non-fatal journal warning to tool JSON without changing ``ok``."""
    warning = journal_report.get("warning")
    if not warning:
        return None
    parsed = parse_tool_result(result)
    if not isinstance(parsed, dict) or parsed.get("ok") is not True:
        return None
    if parsed.get("_journal_warning"):
        return None
    merged = dict(parsed)
    merged["_journal_warning"] = str(warning)
    merged["_journal"] = {
        "journaled": bool(journal_report.get("journaled")),
        "deduplicated": bool(journal_report.get("deduplicated")),
    }
    return json.dumps(merged, ensure_ascii=False)
