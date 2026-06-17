"""Violation severity tiers — port of auditSeverity.ts."""
from __future__ import annotations

CRITICAL_VIOLATIONS = frozenset({
    "result_empty",
    "reported_blocker",
    "missing_validation_evidence",
    "security_leak",
    "stalled_task_timeout",
    "spider_gate_blocked",
    "governance_layer_violation",
})

WARNING_PREFIXES = (
    "unresolved_work_marker:",
    "low_intent_coverage:",
    "high_entropy_low_coverage:",
    "joy_zoning:",
    "spider_warning:",
)


def violation_severity(violation: str) -> str:
    if violation in CRITICAL_VIOLATIONS:
        return "critical"
    if violation.startswith(WARNING_PREFIXES):
        return "warning"
    if violation == "result_too_short":
        return "warning"
    return "info"


def partition_violations(violations: list[str] | None = None) -> dict[str, list[str]]:
    critical: list[str] = []
    warning: list[str] = []
    info: list[str] = []
    for violation in violations or []:
        tier = violation_severity(violation)
        if tier == "critical":
            critical.append(violation)
        elif tier == "warning":
            warning.append(violation)
        else:
            info.append(violation)
    return {"critical": critical, "warning": warning, "info": info}


def has_critical_violations(violations: list[str] | None = None) -> bool:
    return any(violation_severity(v) == "critical" for v in (violations or []))
