"""Scope-scoped audit metadata for completion gates."""
from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Any, Optional

_lock = threading.RLock()
_store: dict[str, dict[str, Any]] = {}
_SPIDER_TTL_SEC = 300.0


def _empty_metadata() -> dict[str, Any]:
    return {
        "violations": [],
        "joy_zoning_violations": [],
        "spider_gate": None,
        "recent_verify_passed": False,
        "recent_verify_at": 0.0,
        "block_count": 0,
        "baseline_metadata": None,
        "advisory_metadata": None,
        "intent_classification": "GENERAL",
        "updated_at": 0.0,
    }


def get_session_metadata(scope_id: str) -> dict[str, Any]:
    with _lock:
        meta = _store.get(scope_id)
        if meta is None:
            meta = _empty_metadata()
            _store[scope_id] = meta
        return deepcopy(meta)


def update_session_metadata(scope_id: str, patch: dict[str, Any]) -> dict[str, Any]:
    with _lock:
        meta = _store.setdefault(scope_id, _empty_metadata())
        meta.update(patch)
        meta["updated_at"] = time.time()
        if "violations" in patch and patch["violations"] is not None:
            from plugins.dietcode.lib.agent.audit.hardening import compute_hardening_assessment

            assessment = compute_hardening_assessment(meta)
            meta["hardening_score"] = assessment["score"]
            meta["hardening_grade"] = assessment["grade"]
        return deepcopy(meta)


def append_violations(scope_id: str, violations: list[str]) -> None:
    if not violations:
        return
    with _lock:
        meta = _store.setdefault(scope_id, _empty_metadata())
        existing = set(meta.get("violations") or [])
        for v in violations:
            if v and v not in existing:
                meta.setdefault("violations", []).append(v)
                existing.add(v)
        meta["updated_at"] = time.time()
        assessment_patch = compute_assessment(meta)
        meta.update(assessment_patch)


def record_spider_gate(scope_id: str, result: dict[str, Any]) -> None:
    payload = {
        **result,
        "recorded_at": time.time(),
    }
    update_session_metadata(scope_id, {"spider_gate": payload})
    if result.get("blocked"):
        append_violations(scope_id, ["spider_gate_blocked"])
    elif str(result.get("qualityGate", "")).upper() == "WARNING":
        append_violations(scope_id, ["spider_warning:structural"])


def record_verify_passed(scope_id: str, *, passed: bool) -> None:
    update_session_metadata(
        scope_id,
        {
            "recent_verify_passed": bool(passed),
            "recent_verify_at": time.time(),
        },
    )
    if not passed:
        append_violations(scope_id, ["missing_validation_evidence"])


def increment_block_count(scope_id: str) -> int:
    with _lock:
        meta = _store.setdefault(scope_id, _empty_metadata())
        meta["block_count"] = int(meta.get("block_count") or 0) + 1
        return int(meta["block_count"])


def spider_gate_fresh(scope_id: str, *, ttl_sec: float = _SPIDER_TTL_SEC) -> bool:
    meta = get_session_metadata(scope_id)
    spider = meta.get("spider_gate") or {}
    recorded = float(spider.get("recorded_at") or 0.0)
    return recorded > 0 and (time.time() - recorded) <= ttl_sec


def compute_assessment(meta: dict[str, Any]) -> dict[str, Any]:
    from plugins.dietcode.lib.agent.audit.hardening import compute_hardening_assessment

    assessment = compute_hardening_assessment(meta)
    return {
        "hardening_score": assessment["score"],
        "hardening_grade": assessment["grade"],
    }


def reset_session_metadata(scope_id: Optional[str] = None) -> None:
    with _lock:
        if scope_id is None:
            _store.clear()
        else:
            _store.pop(scope_id, None)
