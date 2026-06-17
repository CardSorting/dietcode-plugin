"""Unified completion gate evaluator — port of auditGateReport.ts."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from plugins.dietcode.lib.agent.audit.config import CompletionGateConfig, get_completion_gate_config
from plugins.dietcode.lib.agent.audit.gate_policy import resolve_effective_gate_threshold
from plugins.dietcode.lib.agent.audit.hardening import compute_hardening_assessment
from plugins.dietcode.lib.agent.audit.severity import has_critical_violations, partition_violations


@dataclass(frozen=True)
class GateReason:
    code: str
    message: str


@dataclass(frozen=True)
class CompletionGateDecision:
    blocked: bool
    score: int
    effective_threshold: int
    grade: str
    reasons: tuple[GateReason, ...]


def evaluate_completion_gate(
    metadata: dict[str, Any],
    *,
    config: Optional[CompletionGateConfig] = None,
    baseline_metadata: Optional[dict[str, Any]] = None,
    advisory_metadata: Optional[dict[str, Any]] = None,
) -> CompletionGateDecision:
    cfg = config or get_completion_gate_config()
    assessment = compute_hardening_assessment(metadata)
    score = int(metadata.get("hardening_score") or assessment["score"])
    grade = str(metadata.get("hardening_grade") or assessment["grade"])
    intent = str(metadata.get("intent_classification") or "GENERAL")
    effective_threshold = resolve_effective_gate_threshold(
        cfg.score_threshold,
        intent,
        intent_adjustments_enabled=cfg.intent_adjusted_threshold,
    )

    violations = list(metadata.get("violations") or [])
    if cfg.new_violations_only and baseline_metadata:
        baseline_set = set(baseline_metadata.get("violations") or [])
        violations = [v for v in violations if v not in baseline_set]

    reasons: list[GateReason] = []

    if not cfg.enabled:
        return CompletionGateDecision(
            blocked=False,
            score=score,
            effective_threshold=effective_threshold,
            grade=grade,
            reasons=(GateReason("gate_disabled", "Completion gate disabled"),),
        )

    if cfg.advisory_escalation_enabled and advisory_metadata:
        adv_critical = has_critical_violations(advisory_metadata.get("violations"))
        if adv_critical and has_critical_violations(metadata.get("violations")):
            reasons.append(
                GateReason(
                    "advisory_escalation",
                    "Critical act-mode advisory findings remain unresolved",
                )
            )

    if cfg.plan_regression_gate_enabled and baseline_metadata:
        base_score = int(
            baseline_metadata.get("hardening_score")
            or compute_hardening_assessment(baseline_metadata)["score"]
        )
        if score < base_score:
            reasons.append(
                GateReason(
                    "plan_regression",
                    "Hardening score regressed from plan audit baseline",
                )
            )

    spider = metadata.get("spider_gate") or {}
    if cfg.spider_gate_required:
        if spider.get("blocked"):
            reasons.append(
                GateReason(
                    "spider_gate_blocked",
                    f"Spider structural gate blocked (exit {spider.get('exitCode', 1)})",
                )
            )
        elif cfg.fail_on_spider_warning and str(spider.get("qualityGate", "")).upper() == "WARNING":
            reasons.append(
                GateReason("spider_warning", "Spider gate reported WARNING-level structural findings")
            )

    if cfg.require_recent_verify and not metadata.get("recent_verify_passed"):
        reasons.append(
            GateReason(
                "missing_validation_evidence",
                "No passing joyzoning verify recorded for active mutation scope",
            )
        )

    if cfg.new_violations_only:
        if cfg.critical_only:
            if has_critical_violations(violations):
                reasons.append(
                    GateReason(
                        "critical_violations",
                        f"{len(violations)} new critical violation(s) since baseline",
                    )
                )
        elif violations:
            reasons.append(
                GateReason(
                    "policy_violations",
                    f"{len(violations)} new violation(s) since baseline",
                )
            )
    elif cfg.critical_only and has_critical_violations(metadata.get("violations")):
        reasons.append(
            GateReason(
                "critical_violations",
                f"{len(metadata.get('violations') or [])} critical violation(s) present",
            )
        )
    elif score < effective_threshold:
        if assessment["critical_count"] > 0 or violations:
            reasons.append(
                GateReason(
                    "score_below_threshold",
                    f"Score {score} below threshold {effective_threshold}",
                )
            )

    blocked = any(r.code != "gate_disabled" for r in reasons)
    return CompletionGateDecision(
        blocked=blocked,
        score=score,
        effective_threshold=effective_threshold,
        grade=grade,
        reasons=tuple(reasons),
    )


def build_gate_block_message(decision: CompletionGateDecision, metadata: dict[str, Any]) -> str:
    if not decision.blocked:
        return (
            f"Gate ready: Grade {decision.grade} "
            f"({decision.score}/100, threshold {decision.effective_threshold})"
        )
    parts = partition_violations(metadata.get("violations"))
    lines = [
        "COMPLETION BLOCKED — quality audit gate failed.",
        f"Grade: {decision.grade} ({decision.score}/100, threshold {decision.effective_threshold}).",
        "",
        "Resolve before kanban_complete:",
    ]
    for reason in decision.reasons:
        if reason.code != "gate_disabled":
            lines.append(f"- {reason.message}")
    critical = parts["critical"][:5]
    warning = parts["warning"][:3]
    if critical:
        lines.append(f"Critical: {', '.join(critical)}")
    if warning:
        lines.append(f"Warnings: {', '.join(warning)}")
    lines.append("")
    lines.append(
        "Next: broccolidb_violations() then joyzoning(action='verify', report='tests and structural gate cleared', passed=true)."
    )
    return "\n".join(lines)
