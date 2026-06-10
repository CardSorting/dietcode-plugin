"""Per-project bootstrap fill plan — map template phrases to evidence-backed replacements."""
from __future__ import annotations

import re
from typing import Any, Optional

from plugins.dietcode.lib.agent.roadmap.schema import find_bootstrap_placeholders


def _phrase_from_issue(message: str) -> str:
    match = re.search(r"[“\"](.+?)[”\"]", message or "")
    return match.group(1) if match else (message or "")


def _suggest_replacement(
    phrase: str,
    *,
    fingerprint: dict[str, Any],
    evidence: dict[str, Any],
) -> tuple[str, str]:
    """Return (suggested_replacement, evidence_source)."""
    git = evidence.get("git") or {}
    soup = evidence.get("code_soup_audit") or {}
    commits = git.get("recent_commits") or []
    changed = git.get("changed_files_recent") or []
    centralize = (soup.get("centralization_recommendation") or "").strip()
    signals = soup.get("signals") or []
    signal_text = "; ".join(f"{s.get('code')}: {s.get('detail')}" for s in signals[:3])

    purpose = fingerprint.get("purpose_hint") or fingerprint.get("readme_tagline") or ""
    operators = fingerprint.get("operators_hint") or fingerprint.get("package_description") or ""
    runtime = fingerprint.get("runtime_center_hint") or ""
    stack = fingerprint.get("stack_summary") or fingerprint.get("primary_language") or ""
    brief = fingerprint.get("steering_brief") or fingerprint.get("steering_identity") or ""
    archetype = fingerprint.get("project_archetype") or "project"
    tests = fingerprint.get("test_frameworks") or []
    ci = fingerprint.get("ci_systems") or []
    scripts = fingerprint.get("entry_points") or []
    make_targets = fingerprint.get("makefile_targets") or []
    if make_targets:
        scripts = list(dict.fromkeys([*scripts, *make_targets[:3]]))

    mapping: dict[str, tuple[str, str]] = {
        "Describe from README and project evidence": (
            purpose or brief or "State the project's core purpose in plain language.",
            "README tagline / package description",
        ),
        "Define from README and project evidence": (
            purpose or brief or "State the project's core purpose in plain language.",
            "README tagline / package description",
        ),
        "Derived from README and config evidence during bootstrap.": (
            operators or f"Developers and operators working on {brief or 'this codebase'}.",
            "package.json/pyproject description",
        ),
        "Document from architecture docs and repo layout.": (
            _architecture_hint(fingerprint, evidence, purpose, stack),
            "architecture_docs + project_fingerprint",
        ),
        "Describe the main architectural shape from docs and code layout.": (
            _architecture_hint(fingerprint, evidence, purpose, stack),
            "architecture_docs + project_fingerprint",
        ),
        "List the primary flows agents and humans must preserve.": (
            _workflow_hint(fingerprint, scripts, tests, ci),
            "entry_points + CI/test markers",
        ),
        "Preserve primary agent and operator flows identified in README and recent commits.": (
            _workflow_hint(fingerprint, scripts, tests, ci),
            "README + npm/pyproject scripts + CI/test markers",
        ),
        "Hermes workspace project root — ROADMAP.md lives beside source, not in plugin install trees.": (
            runtime or "Project workspace root — ROADMAP.md beside source at repo root.",
            "project_fingerprint.runtime_center_hint",
        ),
        "A fragmented patch surface without a documented center of gravity.": (
            _anti_goal(archetype),
            "project_fingerprint.project_archetype",
        ),
        "Initial roadmap bootstrap.": (
            f"Bootstrap steering surface for {brief}." if brief else "Initial roadmap bootstrap from evidence.",
            "project_fingerprint.steering_brief",
        ),
        "Insufficient evidence during first pass.": (
            _primary_risk(evidence, fingerprint),
            "evidence.uncertainty + git/readme availability",
        ),
        "Clear center of gravity before feature sprawl.": (
            f"Document {brief} center of gravity before expanding scope." if brief else "Document center of gravity before feature sprawl.",
            "project_fingerprint.steering_brief",
        ),
        "Evidence-backed initial audit — see code_soup_pre_audit in checkpoint payload.": (
            centralize or signal_text or f"Code soup risk: {soup.get('overall_risk', 'Low')} — see code_soup_pre_audit.",
            "code_soup_pre_audit",
        ),
        "Runtime and mutation authority documented in project docs; plugin/kernel trees are not project roots.": (
            runtime or "Runtime authority in repo manifests; ROADMAP.md stays in project workspace only.",
            "project_fingerprint.runtime_center_hint",
        ),
        "Run code_soup_pre_audit and document canonical paths.": (
            centralize or signal_text or "Document canonical paths from code_soup_pre_audit signals.",
            "code_soup_pre_audit.centralization_recommendation",
        ),
        "Document canonical paths from code_soup_pre_audit.": (
            centralize or signal_text or "List canonical modules and entrypoints from code_soup_pre_audit.",
            "code_soup_pre_audit",
        ),
        "No recent git activity in evidence.": (
            commits[0][:160] if commits else "No recent git commits — note limited change signals.",
            "git.recent_commits",
        ),
        "No recent git commits captured in evidence.": (
            commits[0][:160] if commits else "No recent git commits captured.",
            "git.recent_commits",
        ),
        "Populate Now with 1–3 evidence-backed items connected to center of gravity.": (
            "Now populated from git and fingerprint — review, refine, or demote items.",
            "bootstrap_fill.now_suggestions",
        ),
        "Populated from code_soup_pre_audit during bootstrap.": (
            f"Code soup risk {soup.get('overall_risk', 'Low')} from pre-audit."
            + (f" {centralize[:120]}" if centralize else ""),
            "code_soup_pre_audit",
        ),
        "Identify from README and config evidence.": (
            operators or purpose or brief or "Identify primary users from README and package manifests.",
            "project_fingerprint.operators_hint",
        ),
        "State where operational truth lives.": (
            runtime or f"Operational truth at workspace root ({brief})." if brief else "Document where runtime and config authority lives.",
            "project_fingerprint.runtime_center_hint",
        ),
        "List anti-goals that protect coherence.": (
            _anti_goal(archetype),
            "project_fingerprint.project_archetype",
        ),
        "Describe what the project is becoming using README, architecture docs, and recent commits.": (
            _narrative_hint(fingerprint, evidence, commits),
            "README + git.recent_commits",
        ),
        "Initial audit from evidence bundle.": (
            centralize or signal_text or f"Initial code soup audit — risk {soup.get('overall_risk', 'Low')}.",
            "code_soup_pre_audit",
        ),
        "Document runtime, state, mutation, and diagnostic authority.": (
            runtime or _runtime_authority_hint(fingerprint, archetype),
            "project_fingerprint + archetype",
        ),
        "Review recent git changes for isolated patterns.": (
            _git_drift_hint(commits, changed),
            "git.changed_files_recent",
        ),
        "Confirm canonical patch and inspection paths are obvious.": (
            centralize or _canonical_paths_hint(fingerprint, soup),
            "code_soup_pre_audit + entry_points",
        ),
        "One recommendation to strengthen project gravity.": (
            centralize or f"Strengthen {brief} center of gravity via documented Now items and section 9 audit." if brief else "One concrete step to strengthen documented center of gravity.",
            "code_soup_pre_audit.centralization_recommendation",
        ),
        "Initial structure only — audit pending deeper pass.": (
            f"Schema established for {brief}; deepen section 9 and Now from ongoing checkpoints." if brief else "Schema established — deepen audits on next checkpoint.",
            "project_fingerprint.steering_brief",
        ),
        "Created initial ROADMAP.md from evidence.": (
            f"Created ROADMAP.md for {brief} from README, git, and code_soup_pre_audit." if brief else "Created initial ROADMAP.md from gathered evidence.",
            "checkpoint evidence bundle",
        ),
        "Review Now items — refine goals and demote anything not truly in motion.": (
            "Now seeded from git and fingerprint — refine titles and demote stale items.",
            "bootstrap_fill.now_suggestions",
        ),
        "Enable long-horizon coherence under agent-assisted development.": (
            f"Adopt ROADMAP.md as the long-horizon steering surface for {brief}." if brief else "Enable long-horizon coherence under agent-assisted development.",
            "project decision",
        ),
        "Strategic work routes through Now/Next/Later instead of ad-hoc task dumps.": (
            f"Route {brief} strategic work through Now/Next/Later — max 5 Now items." if brief else "Route strategic work through Now/Next/Later instead of ad-hoc task dumps.",
            "roadmap schema contract",
        ),
        "Adopt ROADMAP.md as the project steering surface.": (
            f"Adopt ROADMAP.md at workspace root as the steering surface for {brief}." if brief else "Adopt ROADMAP.md as the project steering surface.",
            "checkpoint bootstrap decision",
        ),
    }

    if phrase in mapping:
        return mapping[phrase]

    if "README" in phrase:
        return purpose or brief or phrase, "README / fingerprint"
    if "git" in phrase.lower():
        return commits[0][:160] if commits else phrase, "git.recent_commits"
    if "code_soup" in phrase.lower():
        return centralize or signal_text or phrase, "code_soup_pre_audit"

    return _fallback_replacement(phrase, fingerprint=fingerprint)


def _fallback_replacement(phrase: str, *, fingerprint: dict[str, Any]) -> tuple[str, str]:
    brief = fingerprint.get("steering_brief") or fingerprint.get("steering_identity") or ""
    purpose = fingerprint.get("purpose_hint") or ""
    if purpose:
        return purpose, "project_fingerprint.purpose_hint"
    if brief:
        return f"Document project-specific detail for {brief}.", "project_fingerprint.steering_brief"
    return phrase, "manual — review bootstrap_fill_plan.tasks"


def _architecture_hint(
    fingerprint: dict[str, Any],
    evidence: dict[str, Any],
    purpose: str,
    stack: str,
) -> str:
    arch = evidence.get("architecture_docs") or []
    if arch:
        excerpt = (arch[0].get("excerpt") or "").strip().splitlines()
        for line in excerpt:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                return stripped[:400]
    frameworks = fingerprint.get("frameworks") or []
    if purpose and frameworks:
        return f"{purpose} Built with {', '.join(frameworks[:3])}."
    if stack:
        return f"Primary stack: {stack} — canonical layout from repo root and docs."
    return purpose or "Summarize canonical modules and entrypoints from architecture docs."


def _narrative_hint(
    fingerprint: dict[str, Any],
    evidence: dict[str, Any],
    commits: list[str],
) -> str:
    purpose = fingerprint.get("purpose_hint") or ""
    if commits and purpose:
        return f"{purpose} Recent direction: {commits[0][:100]}."
    if purpose:
        return purpose
    readmes = evidence.get("readmes") or []
    if readmes:
        lines = [ln.strip() for ln in (readmes[0].get("excerpt") or "").splitlines() if ln.strip()]
        if len(lines) > 1:
            return " ".join(lines[1:3])[:400]
    return fingerprint.get("steering_brief") or "Describe strategic direction from README and recent commits."


def _runtime_authority_hint(fingerprint: dict[str, Any], archetype: str) -> str:
    runtime = fingerprint.get("runtime_center_hint") or ""
    if runtime:
        return runtime
    if archetype == "hermes-plugin":
        return "Hermes plugin.yaml and hooks define runtime authority; kernel trees are not project roots."
    return "Document runtime, state, mutation, and diagnostic authority in repo manifests and docs."


def _git_drift_hint(commits: list[str], changed: list[str]) -> str:
    if changed:
        sample = ", ".join(changed[:5])
        return f"Recent files: {sample}. Review for isolated duplication or drift."
    if commits:
        return f"Recent commit activity: {commits[0][:120]}. Review for structural drift."
    return "No recent git changes captured — limited drift signals."


def _canonical_paths_hint(fingerprint: dict[str, Any], soup: dict[str, Any]) -> str:
    rec = (soup.get("centralization_recommendation") or "").strip()
    if rec:
        return rec[:240]
    scripts = fingerprint.get("entry_points") or []
    if scripts:
        return f"Canonical dev/test entrypoints: {', '.join(scripts[:4])}."
    return "Document canonical patch and inspection paths from code_soup_pre_audit."


def _workflow_hint(
    fingerprint: dict[str, Any],
    scripts: list[str],
    tests: list[str],
    ci: list[str],
) -> str:
    parts: list[str] = []
    if scripts:
        parts.append(f"dev/build via {', '.join(scripts[:3])}")
    if tests:
        parts.append(f"verify with {tests[0]}")
    if ci:
        parts.append(f"CI: {ci[0]}")
    archetype = fingerprint.get("project_archetype") or ""
    if archetype == "hermes-plugin":
        parts.append("Hermes hook/tool registration and plugin.yaml manifest")
    agent_rules = fingerprint.get("agent_rules_files") or []
    if agent_rules:
        parts.append(f"agent rules at {agent_rules[0]}")
    if parts:
        return f"Preserve flows — {'; '.join(parts)}."
    return "Document primary dev, deploy, and agent-assisted workflows from README and scripts."


def _anti_goal(archetype: str) -> str:
    goals = {
        "hermes-plugin": "A Hermes plugin that stores ROADMAP.md outside the project workspace or drifts from kernel hook conventions.",
        "monorepo": "A monorepo without documented package boundaries and shared center of gravity.",
        "web-app": "A web app whose UI, API, and deploy surfaces diverge without documented authority boundaries.",
        "cli-tool": "A CLI whose entrypoints multiply without a documented operational center.",
    }
    return goals.get(archetype, "A fragmented patch surface without a documented center of gravity.")


def _primary_risk(evidence: dict[str, Any], fingerprint: dict[str, Any]) -> str:
    uncertainty = evidence.get("uncertainty") or []
    if uncertainty:
        return uncertainty[0][:200]
    if not fingerprint.get("readme_tagline"):
        return "No README tagline — center of gravity may need explicit operator input."
    return "Limited cross-session steering until Now/Next items connect to center of gravity."


def suggest_now_items(evidence: dict[str, Any], *, limit: int = 3) -> list[dict[str, str]]:
    """Evidence-backed Now item drafts for bootstrap fill."""
    fingerprint = evidence.get("project_fingerprint") or {}
    git = evidence.get("git") or {}
    commits = git.get("recent_commits") or []
    brief = fingerprint.get("steering_brief") or fingerprint.get("project_name") or "this project"
    items: list[dict[str, str]] = []

    items.append({
        "title": "Complete ROADMAP bootstrap fill",
        "goal": f"Replace remaining template phrases with project-specific facts for {brief}.",
        "evidence": "bootstrap_fill_plan + project_fingerprint",
        "impact": "Strengthens",
    })

    for commit in commits[: max(0, limit - 1)]:
        subject = commit.split(maxsplit=1)[-1][:100] if commit else "Recent change"
        items.append({
            "title": subject,
            "goal": f"Verify or continue work tied to recent commit: {commit[:120]}.",
            "evidence": "git.recent_commits",
            "impact": "Neutral",
        })

    soup = evidence.get("code_soup_audit") or {}
    rec = (soup.get("centralization_recommendation") or "").strip()
    if rec and len(items) < limit:
        items.append({
            "title": "Address centralization recommendation",
            "goal": rec[:240],
            "evidence": "code_soup_pre_audit",
            "impact": "Strengthens",
        })

    return items[:limit]


def format_now_section(items: list[dict[str, str]]) -> str:
    if not items:
        return ""
    blocks: list[str] = []
    for idx, item in enumerate(items, 1):
        blocks.append(
            f"""### {idx}. {item['title']}

**Goal:**  
{item['goal']}

**Evidence:**  
{item['evidence']}

**Center-of-Gravity Impact:**  
{item['impact']}
"""
        )
    return "\n".join(blocks)


def build_bootstrap_fill_plan(
    *,
    roadmap_text: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Per-project checklist: each remaining template phrase → evidence-backed replacement."""
    fingerprint = evidence.get("project_fingerprint") or {}
    placeholders = find_bootstrap_placeholders(roadmap_text or "")
    tasks: list[dict[str, str]] = []
    for issue in placeholders:
        phrase = _phrase_from_issue(issue.message)
        replacement, source = _suggest_replacement(phrase, fingerprint=fingerprint, evidence=evidence)
        tasks.append({
            "template_phrase": phrase,
            "suggested_replacement": replacement,
            "evidence_source": source,
            "severity": issue.severity,
        })

    now_items = suggest_now_items(evidence)
    return {
        "remaining_count": len(tasks),
        "bootstrap_complete": len(tasks) == 0,
        "tasks": tasks,
        "now_suggestions": now_items,
        "project_brief": fingerprint.get("steering_brief") or fingerprint.get("steering_identity"),
        "operator_summary": (
            f"{len(tasks)} template phrase(s) remain — use tasks[].suggested_replacement from project evidence."
            if tasks
            else "Bootstrap fill complete — no template phrases detected."
        ),
        "agent_next_call": (
            "roadmap(action='apply_bootstrap_fill', context='write') then roadmap(action='validate')."
            if tasks
            else "roadmap(action='validate')"
        ),
    }


def format_bootstrap_fill_hint(plan: dict[str, Any], *, limit: int = 3) -> Optional[str]:
    """One-line steering hint for agents when bootstrap is incomplete."""
    tasks = plan.get("tasks") or []
    if not tasks:
        return None
    brief = plan.get("project_brief") or "project"
    sample = tasks[0]
    phrase = sample.get("template_phrase", "")[:50]
    repl = sample.get("suggested_replacement", "")[:60]
    extra = len(tasks) - 1
    suffix = f" (+{extra} more)" if extra > 0 else ""
    return (
        f"Bootstrap fill ({brief}): replace “{phrase}…” → “{repl}…”{suffix} "
        f"— roadmap(action='apply_bootstrap_fill', context='write')"
    )


def apply_bootstrap_fill_draft(
    roadmap_text: str,
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """Apply evidence-backed replacements to remaining template phrases (preview — does not write disk)."""
    plan = build_bootstrap_fill_plan(roadmap_text=roadmap_text, evidence=evidence)
    text = roadmap_text or ""
    applied: list[dict[str, str]] = []
    for task in plan.get("tasks") or []:
        phrase = task.get("template_phrase") or ""
        repl = (task.get("suggested_replacement") or "").strip()
        source = task.get("evidence_source") or ""
        if (
            phrase
            and phrase in text
            and repl
            and repl != phrase
            and not source.startswith("manual")
        ):
            text = text.replace(phrase, repl, 1)
            applied.append(task)

    remaining = find_bootstrap_placeholders(text)
    return {
        "applied_count": len(applied),
        "applied_tasks": applied,
        "remaining_count": len(remaining),
        "bootstrap_complete": len(remaining) == 0,
        "preview_text": text,
        "operator_summary": (
            f"Applied {len(applied)} evidence-backed replacement(s); {len(remaining)} template phrase(s) remain."
            if applied
            else f"No autofill applied — {len(remaining)} template phrase(s) remain — roadmap(action='apply_bootstrap_fill') or manual edits from bootstrap_fill_plan.tasks."
        ),
    }


def build_project_steering_digest(
    fingerprint: dict[str, Any],
    *,
    fill_plan: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Compact per-project steering digest for session, validate, and write hints."""
    digest: dict[str, Any] = {
        "steering_brief": fingerprint.get("steering_brief") or fingerprint.get("steering_identity"),
        "project_archetype": fingerprint.get("project_archetype"),
        "stack_summary": fingerprint.get("stack_summary"),
        "purpose_hint": fingerprint.get("purpose_hint"),
        "has_ci": fingerprint.get("has_ci"),
        "has_tests": fingerprint.get("has_tests"),
        "entry_points": fingerprint.get("entry_points") or [],
        "git_remote": fingerprint.get("git_remote"),
        "agent_rules_files": fingerprint.get("agent_rules_files") or [],
        "makefile_targets": fingerprint.get("makefile_targets") or [],
        "has_backstage_catalog": fingerprint.get("has_backstage_catalog"),
    }
    if fill_plan:
        digest["bootstrap_remaining"] = fill_plan.get("remaining_count")
        digest["bootstrap_complete"] = fill_plan.get("bootstrap_complete")
        tasks = fill_plan.get("tasks") or []
        if tasks:
            first = tasks[0]
            digest["sample_fill_task"] = {
                "template_phrase": first.get("template_phrase"),
                "suggested_replacement": first.get("suggested_replacement"),
                "evidence_source": first.get("evidence_source"),
            }
        digest["agent_next_call"] = fill_plan.get("agent_next_call")
    return digest


def bootstrap_steering_bundle(
    *,
    roadmap_text: str,
    evidence: dict[str, Any],
    fingerprint: Optional[dict[str, Any]] = None,
    include_preview: bool = False,
) -> dict[str, Any]:
    """Build fill plan + digest (+ optional preview) from an evidence bundle."""
    fill_plan = build_bootstrap_fill_plan(roadmap_text=roadmap_text, evidence=evidence)
    fp = fingerprint or evidence.get("project_fingerprint") or {}
    out: dict[str, Any] = {
        "bootstrap_fill_plan": fill_plan,
        "project_steering_digest": build_project_steering_digest(fp, fill_plan=fill_plan),
    }
    if include_preview and fill_plan.get("tasks"):
        out["bootstrap_autofill_preview"] = apply_bootstrap_fill_draft(roadmap_text, evidence)
    if fill_plan.get("tasks"):
        out["operator_summary"] = fill_plan.get("operator_summary")
        out["agent_next_call"] = fill_plan.get("agent_next_call")
    return out


def attach_bootstrap_steering_fields(
    steering: dict[str, Any],
    *,
    tier: str = "light",
    include_preview: bool = False,
) -> dict[str, Any]:
    """Attach fill plan + digest when bootstrap placeholders remain (shared by session/progress/gate)."""
    if steering.get("bootstrap_complete") is not False:
        return {}

    from pathlib import Path as PathCls

    from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence

    root = steering.get("workspace")
    if not root:
        return {}

    roadmap_text = ""
    roadmap_path = steering.get("roadmap_path")
    if roadmap_path:
        try:
            roadmap_text = PathCls(str(roadmap_path)).read_text(encoding="utf-8", errors="replace")
        except OSError:
            roadmap_text = ""

    evidence = gather_evidence(root, tier=tier, roadmap_text=roadmap_text)
    return bootstrap_steering_bundle(
        roadmap_text=roadmap_text,
        evidence=evidence,
        fingerprint=evidence.get("project_fingerprint") or steering,
        include_preview=include_preview,
    )


def write_bootstrap_autofill(
    *,
    workspace: str | Path,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Apply evidence-backed replacements to ROADMAP.md (or preview when dry_run=True)."""
    from pathlib import Path as PathCls

    from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace_root
    from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence

    root = PathCls(resolve_workspace_root(workspace))
    roadmap_path = root / "ROADMAP.md"
    if not roadmap_path.is_file():
        return {
            "ok": False,
            "success": False,
            "error": "ROADMAP.md not found — run roadmap(action='template') or checkpoint first.",
            "workspace": str(root),
        }

    text = roadmap_path.read_text(encoding="utf-8", errors="replace")
    evidence = gather_evidence(root, tier="standard", roadmap_text=text)
    draft = apply_bootstrap_fill_draft(text, evidence)
    fill_plan = build_bootstrap_fill_plan(roadmap_text=text, evidence=evidence)

    result: dict[str, Any] = {
        "ok": True,
        "success": True,
        "workspace": str(root),
        "roadmap_path": str(roadmap_path),
        "dry_run": dry_run,
        "bootstrap_fill_plan": fill_plan,
        "project_steering_digest": build_project_steering_digest(
            evidence.get("project_fingerprint") or {},
            fill_plan=fill_plan,
        ),
        "bootstrap_autofill_preview": draft,
        "operator_summary": draft.get("operator_summary"),
        "agent_next_call": "roadmap(action='validate') after reviewing autofill changes.",
    }

    if dry_run or not draft.get("applied_count"):
        return result

    roadmap_path.write_text(draft["preview_text"], encoding="utf-8")
    try:
        from plugins.dietcode.lib.agent.roadmap.roadmap_core import invalidate_roadmap_core
        from plugins.dietcode.lib.agent.roadmap.snapshot import invalidate_snapshot
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import invalidate_fingerprint_cache
        from plugins.dietcode.lib.agent.roadmap.workspace_state import record_file_mutation

        record_file_mutation(root, tool="roadmap", path="ROADMAP.md")
        invalidate_roadmap_core(root)
        invalidate_snapshot(root)
        invalidate_fingerprint_cache(root)
    except Exception:
        pass

    result["written"] = True
    result["applied_count"] = draft.get("applied_count")
    result["validation_pending"] = True
    return result


def enrich_payload_with_bootstrap_context(
    payload: dict[str, Any],
    *,
    roadmap_text: str = "",
    evidence: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Attach fill plan + steering digest when bootstrap placeholders remain."""
    bundle = evidence if evidence is not None else payload
    text = roadmap_text or bundle.get("_roadmap_text") or ""
    roadmap = bundle.get("roadmap") or {}
    bootstrap_inc = roadmap.get("bootstrap_complete") is False
    if not bootstrap_inc and text:
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_completeness_metrics

        metrics = bootstrap_completeness_metrics(text)
        bootstrap_inc = not metrics.get("bootstrap_complete", True)
    if not bootstrap_inc or not text.strip():
        return payload

    out = dict(payload)
    out.update(
        bootstrap_steering_bundle(
            roadmap_text=text,
            evidence=bundle,
            include_preview=True,
        )
    )
    return out
