"""ROADMAP.md schema constants, validation, and bootstrap skeleton."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REQUIRED_SECTIONS: tuple[str, ...] = (
    "1. Project Center of Gravity",
    "2. Roadmap Health",
    "3. Strategic Narrative",
    "4. Now",
    "5. Next",
    "6. Later",
    "7. Discovery",
    "8. Maintenance Gravity",
    "9. Centralization & Code Soup Audit",
    "10. Decision Log",
    "11. Recent Checkpoint",
    "12. Archive",
)

HEALTH_STATUSES = frozenset({
    "Coherent",
    "Accelerating",
    "Drifting",
    "Fragmenting",
    "Blocked",
    "Overloaded",
    "Recovering",
})

SOUP_RISK_LEVELS = frozenset({"Low", "Medium", "High"})
GRAVITY_IMPACTS = frozenset({"Strengthens", "Neutral", "Weakens", "Unknown"})
CENTRALIZATION_EFFECTS = frozenset({"Centralizes", "No Change", "Decentralizes"})
ENTROPY_RISKS = frozenset({"Low", "Medium", "High"})

# Template guidance lines agents must replace before treating bootstrap as complete.
BOOTSTRAP_PLACEHOLDER_PHRASES: tuple[str, ...] = (
    "Describe from README and project evidence",
    "Define from README and project evidence",
    "Identify from README and config evidence.",
    "Derived from README and config evidence during bootstrap.",
    "Describe the main architectural shape from docs and code layout.",
    "Document from architecture docs and repo layout.",
    "List the primary flows agents and humans must preserve.",
    "Preserve primary agent and operator flows identified in README and recent commits.",
    "State where operational truth lives.",
    "List anti-goals that protect coherence.",
    "Describe what the project is becoming using README, architecture docs, and recent commits.",
    "Initial audit from evidence bundle.",
    "Evidence-backed initial audit — see code_soup_pre_audit in checkpoint payload.",
    "Document runtime, state, mutation, and diagnostic authority.",
    "Runtime and mutation authority documented in project docs; plugin install trees are not project roots.",
    "Review recent git changes for isolated patterns.",
    "Confirm canonical patch and inspection paths are obvious.",
    "One recommendation to strengthen project gravity.",
    "Initial structure only — audit pending deeper pass.",
    "Initial roadmap bootstrap.",
    "Insufficient evidence during first pass.",
    "Clear center of gravity before feature sprawl.",
    "A fragmented patch surface without a documented center of gravity.",
    "Hermes workspace project root — ROADMAP.md lives beside source, not in plugin install trees.",
    "Run code_soup_pre_audit and document canonical paths.",
    "Document canonical paths from code_soup_pre_audit.",
    "No recent git activity in evidence.",
    "No recent git commits captured in evidence.",
    "Created initial ROADMAP.md from evidence.",
    "Populate Now with 1–3 evidence-backed items connected to center of gravity.",
    "Populated from code_soup_pre_audit during bootstrap.",
    "Enable long-horizon coherence under agent-assisted development.",
    "Strategic work routes through Now/Next/Later instead of ad-hoc task dumps.",
    "Adopt ROADMAP.md as the project steering surface.",
)

_ALGORITHM_STEPS: tuple[str, ...] = (
    "Read the existing ROADMAP.md, if present.",
    "Identify the current stated center of gravity.",
    "Inspect recent project changes and available evidence.",
    "Determine whether the project is coherent, accelerating, drifting, fragmenting, blocked, or overloaded.",
    "Compare current work against the existing roadmap.",
    "Preserve valid strategic intent.",
    "Remove duplicate or stale roadmap entries.",
    "Archive items that no longer deserve active attention.",
    "Promote items only when evidence supports promotion.",
    "Demote items when uncertainty, risk, or entropy increases.",
    "Add new items only when they connect to the center of gravity.",
    "Rewrite technical implementation details into clear product and architecture language.",
    "Run a centralization and code soup audit.",
    "Update the recent checkpoint.",
    "Add decision log entries for meaningful direction changes.",
    "Return a concise summary of what changed.",
)


@dataclass
class ValidationIssue:
    severity: str  # error | warning
    code: str
    message: str
    section: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "section": self.section or "",
        }


@dataclass
class RoadmapValidation:
    valid: bool = True
    schema_complete: bool = False
    health_status: str | None = None
    code_soup_risk: str | None = None
    now_item_count: int = 0
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "schema_complete": self.schema_complete,
            "health_status": self.health_status,
            "code_soup_risk": self.code_soup_risk,
            "now_item_count": self.now_item_count,
            "issues": [
                {"severity": i.severity, "code": i.code, "message": i.message, "section": i.section}
                for i in self.issues
            ],
        }


def bootstrap_completeness_metrics(content: str) -> dict[str, Any]:
    """Measure how much bootstrap template guidance remains unfilled."""
    placeholders = find_bootstrap_placeholders(content)
    count = len(placeholders)
    return {
        "bootstrap_placeholder_count": count,
        "bootstrap_complete": count == 0,
        "bootstrap_completeness_pct": max(0, min(100, 100 - count * 10)),
        "bootstrap_placeholder_issues": [p.to_dict() for p in placeholders[:12]],
    }


def algorithm_steps() -> list[str]:
    return list(_ALGORITHM_STEPS)


def _section_body(content: str, section_title: str) -> str:
    match = re.search(
        rf"^##\s+{re.escape(section_title)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        content,
        re.MULTILINE,
    )
    return match.group(1) if match else ""


def _count_subsections(section_body: str) -> int:
    return len(re.findall(r"^###\s+\d+\.\s+", section_body, re.MULTILINE))


def validate_roadmap_content(
    content: str,
    *,
    sections_present: Optional[list[str]] = None,
    sections_missing: Optional[list[str]] = None,
    health_status: Optional[str] = None,
    code_soup_risk: Optional[str] = None,
) -> RoadmapValidation:
    """Validate ROADMAP.md against the skill schema contract."""
    result = RoadmapValidation()
    if not content.strip():
        result.valid = False
        result.issues.append(ValidationIssue("error", "missing_file", "ROADMAP.md is empty or missing"))
        return result

    if sections_present is not None and sections_missing is not None:
        present = list(sections_present)
        missing = list(sections_missing)
    else:
        present = []
        missing = []
        for section in REQUIRED_SECTIONS:
            if re.search(rf"^##\s+{re.escape(section)}\s*$", content, re.MULTILINE):
                present.append(section)
            else:
                missing.append(section)

    result.schema_complete = not missing
    for section in missing:
        result.issues.append(
            ValidationIssue("error", "missing_section", f"Missing required section: {section}", section)
        )

    health_body = _section_body(content, "2. Roadmap Health")
    if health_status:
        result.health_status = health_status
    else:
        status_match = re.search(r"\*\*Status:\*\*\s*([A-Za-z]+)", health_body)
        if status_match:
            candidate = status_match.group(1).strip()
            for status in HEALTH_STATUSES:
                if status.lower() == candidate.lower():
                    result.health_status = status
                    break
            if not result.health_status:
                result.issues.append(
                    ValidationIssue(
                        "error",
                        "invalid_health_status",
                        f"Invalid health status: {candidate}",
                        "2. Roadmap Health",
                    )
                )
        else:
            result.issues.append(
                ValidationIssue(
                    "warning",
                    "unparsed_health_status",
                    "Could not parse **Status:** in section 2",
                    "2. Roadmap Health",
                )
            )

    soup_body = _section_body(content, "9. Centralization & Code Soup Audit")
    if code_soup_risk and code_soup_risk in SOUP_RISK_LEVELS:
        result.code_soup_risk = code_soup_risk
    else:
        soup_match = re.search(r"\*\*Overall Code Soup Risk:\*\*\s*(Low|Medium|High)", soup_body, re.IGNORECASE)
        if soup_match:
            label = soup_match.group(1).strip().title()
            if label in SOUP_RISK_LEVELS:
                result.code_soup_risk = label
    if not soup_body.strip():
        result.issues.append(
            ValidationIssue(
                "error",
                "missing_code_soup_audit",
                "Section 9 (Centralization & Code Soup Audit) is mandatory",
                "9. Centralization & Code Soup Audit",
            )
        )
    elif not result.code_soup_risk:
        result.issues.append(
            ValidationIssue(
                "warning",
                "unparsed_code_soup_risk",
                "Could not parse **Overall Code Soup Risk:** in section 9",
                "9. Centralization & Code Soup Audit",
            )
        )

    cog_body = _section_body(content, "1. Project Center of Gravity")
    if "must not become" not in cog_body.lower():
        result.issues.append(
            ValidationIssue(
                "error",
                "missing_anti_goals",
                "Section 1 must include **What This Project Must Not Become:**",
                "1. Project Center of Gravity",
            )
        )

    now_body = _section_body(content, "4. Now")
    result.now_item_count = _count_subsections(now_body)
    if result.now_item_count > 5:
        result.issues.append(
            ValidationIssue(
                "warning",
                "now_overloaded",
                f"Now has {result.now_item_count} items — roadmap is overloaded (max 5)",
                "4. Now",
            )
        )

    errors = [i for i in result.issues if i.severity == "error"]
    for unresolved in find_bootstrap_placeholders(content):
        result.issues.append(unresolved)
    result.valid = not errors
    return result


def find_bootstrap_placeholders(content: str) -> list[ValidationIssue]:
    """Detect unfilled bootstrap template guidance still present in ROADMAP.md."""
    issues: list[ValidationIssue] = []
    for phrase in BOOTSTRAP_PLACEHOLDER_PHRASES:
        if phrase in content:
            issues.append(
                ValidationIssue(
                    "warning",
                    "bootstrap_placeholder",
                    f"Replace template guidance still present: “{phrase}”",
                    "",
                )
            )
    return issues


def _first_meaningful_readme_line(excerpt: str) -> str:
    for line in excerpt.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            if title:
                return title[:400]
            continue
        return stripped[:400]
    return ""


def bootstrap_skeleton_from_evidence(evidence: dict[str, Any], *, workspace: str = "") -> str:
    """Build a schema-complete starter ROADMAP.md populated from real project evidence."""
    readmes = evidence.get("readmes") or []
    arch = evidence.get("architecture_docs") or []
    git = evidence.get("git") or {}
    soup = evidence.get("code_soup_audit") or {}
    fingerprint = evidence.get("project_fingerprint") or {}

    purpose = (
        fingerprint.get("purpose_hint")
        or fingerprint.get("readme_tagline")
        or fingerprint.get("package_description")
        or ""
    )
    if not purpose and readmes:
        purpose = _first_meaningful_readme_line(readmes[0].get("excerpt") or "")
    if not purpose and workspace:
        purpose = f"{Path(workspace).name} — center of gravity from first checkpoint pass"

    narrative = ""
    if arch:
        narrative = _first_meaningful_readme_line(arch[0].get("excerpt") or "")
    if not narrative:
        narrative = purpose or fingerprint.get("steering_brief") or ""
    if not narrative and readmes:
        lines = [ln.strip() for ln in (readmes[0].get("excerpt") or "").splitlines() if ln.strip()]
        narrative = " ".join(lines[1:4])[:500] if len(lines) > 1 else purpose

    operators = fingerprint.get("operators_hint") or ""
    if operators and operators.strip() == (purpose or "").strip():
        operators = ""
    if not operators and fingerprint.get("project_archetype") == "hermes-plugin":
        operators = "Hermes operators and agent-assisted developers extending the plugin surface."

    runtime_center = fingerprint.get("runtime_center_hint") or ""
    if not runtime_center:
        stack = fingerprint.get("stack_summary") or fingerprint.get("primary_language") or ""
        if stack:
            runtime_center = f"Project workspace root — primary stack: {stack}"
        else:
            runtime_center = "Hermes workspace project root — ROADMAP.md lives beside source, not in plugin install trees."

    canonical_arch = narrative
    if fingerprint.get("frameworks"):
        fw = ", ".join(fingerprint["frameworks"][:3])
        canonical_arch = f"{narrative} Primary frameworks: {fw}." if narrative else f"Primary frameworks: {fw}."

    workflows = ""
    tests = fingerprint.get("test_frameworks") or []
    ci = fingerprint.get("ci_systems") or []
    if tests or ci:
        parts = []
        if tests:
            parts.append(f"verification via {tests[0]}")
        if ci:
            parts.append(f"CI: {ci[0]}")
        workflows = f"Preserve primary flows — {', '.join(parts)}; align roadmap checkpoints with README and recent commits."
    make_targets = fingerprint.get("makefile_targets") or []
    if make_targets and (not tests and not ci):
        workflows = f"Preserve primary flows — make {', '.join(make_targets[:3])}."
    if not workflows:
        workflows = "Preserve primary agent and operator flows identified in README and recent commits."

    commits = git.get("recent_commits") or []
    git_line = commits[0][:120] if commits else "No recent git commits captured in evidence."

    soup_risk = soup.get("overall_risk") or "Low"
    if soup_risk not in SOUP_RISK_LEVELS:
        soup_risk = "Low"
    centralize = (soup.get("centralization_recommendation") or "").strip()
    signals = soup.get("signals") or []
    signal_summary = ""
    if signals:
        signal_summary = "; ".join(
            f"{s.get('code')}: {s.get('detail')}" for s in signals[:3]
        )

    anti_goals = "A fragmented patch surface without a documented center of gravity."
    archetype = fingerprint.get("project_archetype") or ""
    if archetype == "monorepo":
        anti_goals = "A monorepo without documented package boundaries and shared center of gravity."
    elif archetype == "hermes-plugin":
        anti_goals = "A Hermes plugin that drifts from native mutation conventions or stores ROADMAP.md outside the project workspace."

    health_summary = "Initial roadmap bootstrap."
    if fingerprint.get("steering_brief"):
        health_summary = f"Bootstrap for {fingerprint['steering_brief'][:160]}."

    from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import format_now_section, suggest_now_items

    now_items = suggest_now_items(evidence)
    now_section = format_now_section(now_items)
    checkpoint_next = (
        "Review Now items — refine goals and demote anything not truly in motion."
        if now_section
        else "Populate Now with 1–3 evidence-backed items connected to center of gravity."
    )

    return bootstrap_skeleton(
        project_hint=purpose or "Define from README and project evidence",
        strategic_narrative=narrative or purpose,
        operators_hint=operators,
        canonical_architecture=canonical_arch,
        canonical_workflows=workflows,
        runtime_center=runtime_center,
        anti_goals=anti_goals,
        health_summary=health_summary,
        now_section=now_section,
        checkpoint_next_move=checkpoint_next,
        code_soup_risk=soup_risk,
        centralization_recommendation=centralize or signal_summary or "Run code_soup_pre_audit and document canonical paths.",
        recent_git_summary=git_line,
        changed_files=git.get("changed_files_recent") or [],
    )


def bootstrap_skeleton_from_evidence_autofilled(evidence: dict[str, Any], *, workspace: str = "") -> str:
    """Evidence skeleton with autofill draft applied — fewer template phrases on first write."""
    from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import apply_bootstrap_fill_draft

    skeleton = bootstrap_skeleton_from_evidence(evidence, workspace=workspace)
    draft = apply_bootstrap_fill_draft(skeleton, evidence)
    return draft.get("preview_text") or skeleton


def bootstrap_skeleton(
    *,
    project_hint: str = "",
    strategic_narrative: str = "",
    operators_hint: str = "",
    canonical_architecture: str = "",
    canonical_workflows: str = "",
    runtime_center: str = "",
    anti_goals: str = "",
    health_summary: str = "",
    now_section: str = "",
    checkpoint_next_move: str = "",
    code_soup_risk: str = "Low",
    centralization_recommendation: str = "",
    recent_git_summary: str = "",
    changed_files: Optional[list[str]] = None,
) -> str:
    """Return a schema-complete starter ROADMAP.md for first-pass agents."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    hint = project_hint.strip() or "Define from README and project evidence"
    narrative = (strategic_narrative or hint).strip()
    operators = operators_hint.strip() or "Derived from README and config evidence during bootstrap."
    architecture = canonical_architecture.strip() or (
        " ".join(narrative.split()[:40]) if narrative else "Document from architecture docs and repo layout."
    )
    workflows = canonical_workflows.strip() or "Preserve primary agent and operator flows identified in README and recent commits."
    runtime = runtime_center.strip() or "Hermes workspace project root — ROADMAP.md lives beside source, not in plugin install trees."
    must_not = anti_goals.strip() or "A fragmented patch surface without a documented center of gravity."
    health = health_summary.strip() or "Initial roadmap bootstrap."
    risk = code_soup_risk if code_soup_risk in SOUP_RISK_LEVELS else "Low"
    centralize = centralization_recommendation.strip() or "Document canonical paths from code_soup_pre_audit."
    git_summary = recent_git_summary.strip() or "No recent git activity in evidence."
    drift_lines = "\n".join(f"- {f}" for f in (changed_files or [])[:8]) or "- None captured"
    now_block = now_section.strip()
    next_move = checkpoint_next_move.strip() or "Populate Now with 1–3 evidence-backed items connected to center of gravity."
    return f"""# ROADMAP.md

## 1. Project Center of Gravity

**Core Purpose:**  
{hint}

**Primary Users / Operators:**  
{operators}

**Canonical Architecture:**  
{architecture}

**Canonical Workflows:**  
{workflows}

**Primary Runtime / Operational Center:**  
{runtime}

**What This Project Must Not Become:**  
{must_not}

## 2. Roadmap Health

**Status:** Coherent

**Summary:**  
{health}

**Why This Status:**  
- ROADMAP.md created from gathered evidence
- Schema established for long-horizon steering

**Primary Risk:**  
Insufficient evidence during first pass.

**Primary Opportunity:**  
Clear center of gravity before feature sprawl.

## 3. Strategic Narrative

{narrative}

## 4. Now

{now_block}

## 5. Next

## 6. Later

## 7. Discovery

## 8. Maintenance Gravity

### Hotspots

| Area | Symptom | Risk | Recommended Action |
|---|---|---|---|
| | | Low | |

### Repeated Friction

### Documentation Gaps

### Agent Confusion Points

## 9. Centralization & Code Soup Audit

**Overall Code Soup Risk:** {risk}

### Canonical Path Integrity

**Assessment:**  
Evidence-backed initial audit — see code_soup_pre_audit in checkpoint payload.

### Authority Boundaries

**Assessment:**  
Runtime and mutation authority documented in project docs; plugin install trees are not project roots.

### Structural Drift

**Assessment:**  
Recent changes from git evidence:
{drift_lines}

### Agent Coherence

**Assessment:**  
{git_summary}

### Centralization Recommendation

{centralize}

## 10. Decision Log

### {today} — Initial roadmap bootstrap

**Decision:**  
Adopt ROADMAP.md as the project steering surface.

**Reason:**  
Enable long-horizon coherence under agent-assisted development.

**Impact:**  
Strategic work routes through Now/Next/Later instead of ad-hoc task dumps.

**Follow-up:**  
Run roadmap checkpoints after meaningful direction changes.

## 11. Recent Checkpoint

**Date:** {today}

**Checkpoint Summary:**  
Created initial ROADMAP.md from evidence.

**Moved:**  
- None

**Added:**  
- Full 12-section schema

**Updated:**  
- None

**Archived:**  
- None

**Code Soup Risk:** {risk}  
Populated from code_soup_pre_audit during bootstrap.

**Recommended Next Move:**  
{next_move}

## 12. Archive
"""
