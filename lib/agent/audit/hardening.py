"""Hardening score assessment — port of taskAuditUtils.computeHardeningAssessment."""
from __future__ import annotations

from typing import Any

VIOLATION_WEIGHTS: dict[str, int] = {
    "result_empty": 40,
    "reported_blocker": 35,
    "missing_validation_evidence": 30,
    "security_leak": 50,
    "stalled_task_timeout": 25,
    "result_too_short": 15,
    "spider_gate_blocked": 45,
    "governance_layer_violation": 35,
}
DEFAULT_VIOLATION_WEIGHT = 12
JOY_ZONING_WEIGHT = 18


def _violation_weight(violation: str) -> int:
    if violation in VIOLATION_WEIGHTS:
        return VIOLATION_WEIGHTS[violation]
    if violation.startswith("unresolved_work_marker:"):
        return 20
    if violation.startswith(("low_intent_coverage:", "high_entropy_low_coverage:")):
        return 10
    if violation.startswith("joy_zoning:"):
        return JOY_ZONING_WEIGHT
    if violation.startswith("spider_warning:"):
        return 15
    return DEFAULT_VIOLATION_WEIGHT


def score_to_grade(score: int) -> str:
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "D"
    return "F"


def compute_hardening_assessment(metadata: dict[str, Any]) -> dict[str, Any]:
    violations = list(metadata.get("violations") or [])
    joy = list(metadata.get("joy_zoning_violations") or [])
    combined = violations + [f"joy_zoning:{v}" for v in joy if f"joy_zoning:{v}" not in violations]

    penalty = sum(_violation_weight(v) for v in combined)
    score = max(0, min(100, 100 - penalty))
    parts = partition_counts(combined)
    return {
        "score": score,
        "grade": score_to_grade(score),
        "critical_count": parts["critical"],
        "warning_count": parts["warning"],
        "violation_count": len(combined),
    }


def partition_counts(violations: list[str]) -> dict[str, int]:
    from plugins.dietcode.lib.agent.audit.severity import partition_violations

    parts = partition_violations(violations)
    return {
        "critical": len(parts["critical"]),
        "warning": len(parts["warning"]),
        "info": len(parts["info"]),
    }
