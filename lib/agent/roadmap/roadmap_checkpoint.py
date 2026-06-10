"""Auto-rolling roadmap checkpoint orchestration."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config, resolve_workspace_root
from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence, parse_roadmap
from plugins.dietcode.lib.agent.roadmap.phase_guide import clarity_envelope, determine_phase
from plugins.dietcode.lib.agent.roadmap.schema import (
    REQUIRED_SECTIONS,
    algorithm_steps,
    bootstrap_skeleton,
    bootstrap_skeleton_from_evidence,
    bootstrap_skeleton_from_evidence_autofilled,
    bootstrap_completeness_metrics,
    validate_roadmap_content,
)
from plugins.dietcode.lib.agent.roadmap.skill_install import _SKILL_REL, ensure_workspace_skills


def probe_roadmap_available() -> bool:
    """Roadmap tooling is available when the feature is enabled."""
    return bool(get_roadmap_config().enabled)


def _skill_bootstrap(workspace: str) -> dict[str, Any]:
    cfg = get_roadmap_config()
    if not cfg.auto_install_skills:
        return {"skipped": True, "reason": "auto_install_skills disabled"}
    from plugins.dietcode.lib.agent.roadmap.skill_install import ensure_primary_skill

    return ensure_primary_skill(workspace)


def _phase_from_evidence(evidence: dict[str, Any], *, validation_valid: Optional[bool] = None) -> dict[str, Any]:
    roadmap = evidence.get("roadmap") or {}
    bootstrap_inc = False
    if roadmap.get("exists"):
        from plugins.dietcode.lib.agent.roadmap.operator import is_bootstrap_incomplete

        bootstrap_inc = is_bootstrap_incomplete(
            roadmap_exists=True,
            bootstrap_complete=roadmap.get("bootstrap_complete"),
            bootstrap_placeholder_count=roadmap.get("bootstrap_placeholder_count"),
        )
    return determine_phase(
        roadmap_exists=bool(roadmap.get("exists")),
        sections_missing=roadmap.get("sections_missing") or [],
        health_status=roadmap.get("health_status"),
        validation_valid=validation_valid,
        bootstrap_incomplete=bootstrap_inc,
    )


def _enrich_with_bootstrap_fill(
    payload: dict[str, Any],
    *,
    roadmap_text: str,
    evidence: dict[str, Any],
    bootstrap_inc: bool,
) -> None:
    from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import (
        bootstrap_steering_bundle,
        build_project_steering_digest,
    )

    if bootstrap_inc:
        payload.update(
            bootstrap_steering_bundle(
                roadmap_text=roadmap_text,
                evidence=evidence,
                include_preview=True,
            )
        )
        return
    fp = evidence.get("project_fingerprint") or {}
    if fp:
        payload["project_steering_digest"] = build_project_steering_digest(fp)


def operational_status(
    *,
    workspace: Optional[str] = None,
    context_hint: str = "",
    evidence: Optional[dict[str, Any]] = None,
    snapshot: Any = None,
    tier: str = "standard",
) -> dict[str, Any]:
    """Return phase, evidence summary, and next agent call (guide action)."""
    from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace

    if workspace and str(workspace).strip():
        root = resolve_workspace_root(workspace)
        workspace_source = "explicit"
    else:
        root, workspace_source = resolve_workspace()
    bootstrap = _skill_bootstrap(root)

    from plugins.dietcode.lib.agent.roadmap.gate import collect_gate_inputs, gate_state_from_inputs
    from plugins.dietcode.lib.agent.roadmap.operator import recommend_next_action
    from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot
    from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state

    if snapshot is not None:
        bundle = evidence if evidence is not None else snapshot.evidence
        validation_valid = snapshot.validation.valid if snapshot.validation else None
        gate_state = snapshot.gate_state
        freshness = snapshot.gate_inputs.get("freshness") or {}
        ws_state = snapshot.gate_inputs.get("workspace_state") or read_state(root)
    elif evidence is not None:
        text = evidence.get("_roadmap_text") or ""
        from plugins.dietcode.lib.agent.roadmap.roadmap_core import read_roadmap_core

        core = read_roadmap_core(root)
        validation = core.validation if core.text == text else (
            validate_roadmap_content(text) if text.strip() else None
        )
        validation_valid = validation.valid if validation else None
        bundle = evidence
        gate_inputs = collect_gate_inputs(
            workspace=root,
            evidence=bundle,
            roadmap_text=text or None,
            validation=validation,
        )
        gate_state = gate_state_from_inputs(gate_inputs)
        freshness = gate_inputs.get("freshness") or {}
        ws_state = gate_inputs.get("workspace_state") or read_state(root)
    else:
        snap = get_workspace_snapshot(root, tier=tier, force_refresh=bool(context_hint))
        bundle = snap.evidence
        validation_valid = snap.validation.valid if snap.validation else None
        gate_state = snap.gate_state
        freshness = snap.gate_inputs.get("freshness") or {}
        ws_state = snap.gate_inputs.get("workspace_state") or read_state(root)

    roadmap = bundle.get("roadmap") or {}
    from plugins.dietcode.lib.agent.roadmap.operator import is_bootstrap_incomplete

    bootstrap_inc = is_bootstrap_incomplete(
        roadmap_exists=bool(roadmap.get("exists")),
        workspace_state=ws_state,
        bootstrap_complete=gate_state.get("bootstrap_complete"),
        bootstrap_placeholder_count=gate_state.get("bootstrap_placeholder_count"),
    )
    phase_info = _phase_from_evidence(bundle, validation_valid=validation_valid)
    if bootstrap_inc and roadmap.get("exists"):
        phase_info = determine_phase(
            roadmap_exists=True,
            sections_missing=roadmap.get("sections_missing") or [],
            health_status=roadmap.get("health_status"),
            validation_valid=validation_valid,
            bootstrap_incomplete=True,
        )
    next_rec = recommend_next_action(
        phase=phase_info.get("phase") or "",
        roadmap_exists=bool(roadmap.get("exists")),
        schema_valid=validation_valid if validation_valid is not None else ws_state.get("schema_valid"),
        stale=bool(freshness.get("stale")),
        validation_pending=bool(ws_state.get("validation_pending")),
        bootstrap_incomplete=bootstrap_inc,
    )

    payload = {
        "action": "guide",
        "success": True,
        "ok": True,
        "phase": phase_info["phase"],
        "skill": "auto-rolling-roadmap",
        "skill_path": _SKILL_REL,
        "workspace": root,
        "workspace_source": workspace_source,
        "roadmap_exists": bool(roadmap.get("exists")),
        "health_status": roadmap.get("health_status"),
        "code_soup_risk": roadmap.get("code_soup_risk")
        or (bundle.get("code_soup_audit") or {}).get("overall_risk"),
        "sections_missing": roadmap.get("sections_missing") or [],
        "sections_present_count": len(roadmap.get("sections_present") or []),
        "now_item_count": roadmap.get("now_item_count", 0),
        "recent_checkpoint_date": roadmap.get("recent_checkpoint_date"),
        "operator_summary": phase_info["operator_summary"],
        "agent_next_call": next_rec.get("command") or phase_info["agent_next_call"],
        "recommended_next_action": next_rec,
        "schema_valid": validation_valid,
        "prime_directive": "Did the latest work strengthen or weaken the project's center of gravity?",
        "skill_bootstrap": bootstrap,
        "uncertainty": bundle.get("uncertainty") or [],
        "checkpoint_freshness": freshness,
        "roadmap_gate": gate_state,
        "kanban_complete_allowed": gate_state.get("kanban_complete_allowed"),
        "workspace_state": ws_state or None,
    }
    fingerprint = bundle.get("project_fingerprint") or {}
    if fingerprint:
        payload["project_fingerprint"] = fingerprint
        payload["steering_brief"] = fingerprint.get("steering_brief")
        payload["stack_summary"] = fingerprint.get("stack_summary")
        payload["project_archetype"] = fingerprint.get("project_archetype")
    if ws_state.get("validation_pending"):
        payload["validation_pending"] = True
        payload["operator_summary"] = (
            "ROADMAP.md changed since last validate — confirm schema before closing checkpoint."
        )
        payload["agent_next_call"] = next_rec.get("command") or "roadmap(action='validate')"
    if freshness.get("stale"):
        payload["operator_summary"] = freshness.get("summary") or payload.get("operator_summary")
    roadmap_text = bundle.get("_roadmap_text") or ""
    if not roadmap_text and roadmap.get("exists"):
        try:
            roadmap_text = (Path(root) / "ROADMAP.md").read_text(encoding="utf-8", errors="replace")
        except OSError:
            roadmap_text = ""
    _enrich_with_bootstrap_fill(
        payload,
        roadmap_text=roadmap_text,
        evidence=bundle,
        bootstrap_inc=bootstrap_inc,
    )
    return clarity_envelope(payload, phase_info=phase_info)


def checkpoint_brief(
    *,
    workspace: Optional[str] = None,
    context: str = "",
    user_request: str = "",
) -> dict[str, Any]:
    """Return evidence, algorithm, and instructions for a full roadmap pass."""
    from plugins.dietcode.lib.agent.roadmap.evidence import extend_evidence
    from plugins.dietcode.lib.agent.roadmap.operator import is_bootstrap_incomplete
    from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot

    root = resolve_workspace_root(workspace)
    bootstrap = _skill_bootstrap(root)
    snap = get_workspace_snapshot(root, tier="full", force_refresh=bool(context or user_request))
    evidence = extend_evidence(
        snap.evidence,
        tier="full",
        context_hint=context,
        user_request=user_request,
    )
    status = operational_status(workspace=root, snapshot=snap, evidence=evidence)
    roadmap_path = Path(root) / "ROADMAP.md"
    if workspace and str(workspace).strip():
        workspace_source = "explicit"
    else:
        from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace

        _, workspace_source = resolve_workspace()

    payload = {
        "action": "checkpoint",
        "success": True,
        "ok": True,
        "skill": "auto-rolling-roadmap",
        "skill_path": _SKILL_REL,
        "workspace": root,
        "workspace_source": workspace_source,
        "roadmap_path": str(roadmap_path),
        "phase": status["phase"],
        "prime_directive": status["prime_directive"],
        "algorithm_steps": algorithm_steps(),
        "required_sections": list(REQUIRED_SECTIONS),
        "evidence": evidence,
        "project_fingerprint": evidence.get("project_fingerprint"),
        "existing_roadmap_summary": evidence.get("roadmap"),
        "code_soup_pre_audit": evidence.get("code_soup_audit"),
        "agent_instructions": _agent_instructions(status["phase"], evidence),
        "response_format": _response_format_template(),
        "bootstrap_template_available": not evidence.get("roadmap", {}).get("exists"),
        "skill_bootstrap": bootstrap,
        "operator_summary": status["operator_summary"],
        "recommended_next_action": status.get("recommended_next_action"),
        "steering_brief": (evidence.get("project_fingerprint") or {}).get("steering_brief"),
        "agent_next_call": (
            (status.get("recommended_next_action") or {}).get("command")
            or status.get("agent_next_call")
            or (
                "roadmap(action='apply_bootstrap_fill', context='write')"
                if status.get("phase") == "bootstrap_fill"
                else "roadmap(action='checkpoint')"
                if not evidence.get("roadmap", {}).get("exists")
                else "roadmap(action='validate')"
            )
        ),
    }
    if not evidence.get("roadmap", {}).get("exists"):
        payload["suggested_bootstrap"] = bootstrap_skeleton_from_evidence_autofilled(evidence, workspace=root)
        payload["bootstrap_evidence_driven"] = True
    from plugins.dietcode.lib.agent.roadmap.agent_steering import format_agent_steering_line

    payload["steering_line"] = format_agent_steering_line(workspace=root)
    payload["open_todo_marker_count"] = len(evidence.get("todo_markers") or [])
    roadmap_text = evidence.get("_roadmap_text") or ""
    if not roadmap_text:
        try:
            roadmap_text = (Path(root) / "ROADMAP.md").read_text(encoding="utf-8", errors="replace")
        except OSError:
            roadmap_text = ""
    if status.get("phase") == "bootstrap_fill" or is_bootstrap_incomplete(
        roadmap_exists=bool(evidence.get("roadmap", {}).get("exists")),
        bootstrap_complete=(status.get("roadmap_gate") or {}).get("bootstrap_complete"),
        bootstrap_placeholder_count=(status.get("roadmap_gate") or {}).get("bootstrap_placeholder_count"),
    ):
        _enrich_with_bootstrap_fill(
            payload,
            roadmap_text=roadmap_text,
            evidence=evidence,
            bootstrap_inc=True,
        )
    ctx_lower = (context or "").lower()
    autofill_write = (
        any(
            phrase in ctx_lower
            for phrase in (
                "apply autofill write",
                "apply bootstrap write",
                "autofill write",
                "write autofill",
            )
        )
        or ctx_lower.strip() in ("apply autofill", "apply bootstrap", "autofill")
    ) and "preview" not in ctx_lower
    if autofill_write:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import write_bootstrap_autofill

        applied = write_bootstrap_autofill(workspace=root, dry_run=False)
        payload["bootstrap_autofill_applied"] = applied
        if applied.get("written"):
            payload["operator_summary"] = applied.get("operator_summary")
            payload["agent_next_call"] = "roadmap(action='validate')"
            status = operational_status(workspace=root, tier="full")
            payload["phase"] = status.get("phase")
    return clarity_envelope(payload, phase_info={"phase": status["phase"]})


def validate_roadmap(*, workspace: Optional[str] = None) -> dict[str, Any]:
    """Validate ROADMAP.md against schema contract."""
    root = resolve_workspace_root(workspace)
    roadmap_path = Path(root) / "ROADMAP.md"
    text = ""
    if roadmap_path.is_file():
        try:
            text = roadmap_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return clarity_envelope({
                "action": "validate",
                "valid": False,
                "error": str(exc),
                "workspace": root,
                "roadmap_path": str(roadmap_path),
            })

    validation = validate_roadmap_content(text)
    completeness = bootstrap_completeness_metrics(text) if text.strip() else {}
    validation_dict = validation.to_dict()
    validation_dict.update(completeness)
    parsed = parse_roadmap(text, path=str(roadmap_path)) if text else None
    from plugins.dietcode.lib.agent.roadmap.workspace_state import record_validation

    from plugins.dietcode.lib.agent.roadmap.snapshot import invalidate_snapshot

    record_validation(
        root,
        valid=validation.valid,
        health_status=validation.health_status,
        recent_checkpoint_date=parsed.recent_checkpoint_date if parsed else None,
        phase=(
            "validate_pending"
            if not validation.valid
            else ("bootstrap_fill" if not completeness.get("bootstrap_complete", True) else "checkpoint")
        ),
        issue_count=len(validation.issues),
        bootstrap_placeholder_count=int(completeness.get("bootstrap_placeholder_count") or 0),
    )
    invalidate_snapshot(root)
    from plugins.dietcode.lib.agent.roadmap.operator import is_bootstrap_incomplete

    bootstrap_inc = is_bootstrap_incomplete(
        roadmap_exists=bool(text.strip()),
        bootstrap_complete=completeness.get("bootstrap_complete"),
        bootstrap_placeholder_count=completeness.get("bootstrap_placeholder_count"),
    )
    phase_info = determine_phase(
        roadmap_exists=bool(text.strip()),
        sections_missing=[
            s for s in REQUIRED_SECTIONS
            if s not in (parse_roadmap(text).sections_present if text else [])
        ],
        health_status=validation.health_status,
        validation_valid=validation.valid,
        bootstrap_incomplete=bootstrap_inc,
    )
    from plugins.dietcode.lib.agent.roadmap.operator import recommend_next_action

    next_rec = recommend_next_action(
        phase=phase_info.get("phase") or "",
        roadmap_exists=bool(text.strip()),
        schema_valid=validation.valid,
        bootstrap_incomplete=bootstrap_inc,
    )
    payload = {
        "action": "validate",
        "success": validation.valid,
        "ok": validation.valid,
        "workspace": root,
        "roadmap_path": str(roadmap_path),
        "validation": validation_dict,
        "bootstrap_completeness": completeness,
        "recommended_next_action": next_rec,
        "operator_summary": (
            "ROADMAP.md passes schema validation."
            if validation.valid and completeness.get("bootstrap_complete", True)
            else (
                "ROADMAP.md passes schema but unfilled bootstrap template text remains — apply evidence autofill."
                if validation.valid
                else "ROADMAP.md has schema errors — fix before treating checkpoint as complete."
            )
        ),
        "agent_next_call": (
            "Return Required Final Assistant Response summary."
            if validation.valid and completeness.get("bootstrap_complete", True)
            else (
                "roadmap(action='apply_bootstrap_fill', context='write') then roadmap(action='validate')."
                if validation.valid
                else "Fix validation issues and rerun roadmap(action='validate')."
            )
        ),
    }
    if bootstrap_inc and validation.valid:
        evidence = gather_evidence(root, tier="standard", roadmap_text=text)
        _enrich_with_bootstrap_fill(
            payload,
            roadmap_text=text,
            evidence=evidence,
            bootstrap_inc=True,
        )
    elif validation.valid:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_steering_digest_fields
        from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

        payload.update(attach_steering_digest_fields(build_steering_context(workspace=root)))
    return clarity_envelope(payload, phase_info=phase_info)


def template_brief(*, workspace: Optional[str] = None) -> dict[str, Any]:
    """Return bootstrap skeleton for first-pass ROADMAP.md creation."""
    root = resolve_workspace_root(workspace)
    evidence = gather_evidence(root, tier="standard")
    skeleton = bootstrap_skeleton_from_evidence_autofilled(evidence, workspace=root)
    payload = {
        "action": "template",
        "success": True,
        "ok": True,
        "workspace": root,
        "roadmap_path": str(Path(root) / "ROADMAP.md"),
        "skeleton": skeleton,
        "project_fingerprint": evidence.get("project_fingerprint"),
        "evidence_summary": {
            "readmes": len(evidence.get("readmes") or []),
            "git_commits": len((evidence.get("git") or {}).get("recent_commits") or []),
            "code_soup_risk": (evidence.get("code_soup_audit") or {}).get("overall_risk"),
            "steering_brief": (evidence.get("project_fingerprint") or {}).get("steering_brief"),
        },
        "operator_summary": "Evidence-driven skeleton — write to ROADMAP.md, apply remaining autofill if needed, then validate.",
        "agent_next_call": "Write skeleton to ROADMAP.md, then roadmap(action='apply_bootstrap_fill', context='write') if placeholders remain.",
    }
    from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import bootstrap_steering_bundle

    payload.update(
        bootstrap_steering_bundle(
            roadmap_text=skeleton,
            evidence=evidence,
            include_preview=True,
        )
    )
    fill_plan = payload.get("bootstrap_fill_plan") or {}
    if fill_plan.get("tasks"):
        payload["operator_summary"] = fill_plan.get("operator_summary") or payload["operator_summary"]
        payload["agent_next_call"] = fill_plan.get("agent_next_call") or payload["agent_next_call"]
    return clarity_envelope(payload)


def apply_bootstrap_fill_brief(
    *,
    workspace: Optional[str] = None,
    context: str = "",
) -> dict[str, Any]:
    """Apply evidence-backed autofill to ROADMAP.md (preview unless context='write')."""
    from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import write_bootstrap_autofill

    root = resolve_workspace_root(workspace)
    dry_run = (context or "").strip().lower() not in {"write", "apply", "commit"}
    result = write_bootstrap_autofill(workspace=root, dry_run=dry_run)
    payload = {
        "action": "apply_bootstrap_fill",
        **result,
    }
    if result.get("written"):
        validated = validate_roadmap(workspace=root)
        payload.update({
            "validation": validated.get("validation"),
            "phase": validated.get("phase"),
            "recommended_next_action": validated.get("recommended_next_action"),
            "bootstrap_fill_plan": validated.get("bootstrap_fill_plan"),
            "project_steering_digest": validated.get("project_steering_digest") or payload.get("project_steering_digest"),
            "bootstrap_completeness": validated.get("bootstrap_completeness"),
        })
        valid = (validated.get("validation") or {}).get("valid")
        remaining = (validated.get("bootstrap_completeness") or {}).get("bootstrap_placeholder_count")
        payload["operator_summary"] = (
            f"Applied {result.get('applied_count', 0)} evidence replacement(s); schema {'valid' if valid else 'invalid'}."
            + (f" {remaining} bootstrap phrase(s) remain." if remaining else " Bootstrap fill complete.")
        )
        payload["agent_next_call"] = (
            (validated.get("recommended_next_action") or {}).get("command")
            or "roadmap(action='validate')"
        )
    elif dry_run:
        payload["operator_summary"] = result.get("operator_summary") or "Autofill preview — pass context='write' to apply."
        payload["agent_next_call"] = "roadmap(action='apply_bootstrap_fill', context='write') to write preview_text"
    from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

    steering = build_steering_context(workspace=root)
    payload["steering_brief"] = steering.get("steering_brief")
    payload["project_archetype"] = steering.get("project_archetype")
    return clarity_envelope(payload)


def _agent_instructions(phase: str, evidence: dict[str, Any]) -> list[str]:
    fingerprint = evidence.get("project_fingerprint") or {}
    instructions = [
        "Read optional-skills/dietcode/auto-rolling-roadmap/SKILL.md before editing.",
        "Create or evolve ROADMAP.md at the workspace root — never in ~/.hermes/plugins/dietcode or plugin install trees.",
        "Keep Now to 1–5 actionable items; archive stale work instead of appending endlessly.",
        "Section 9 (Centralization & Code Soup Audit) is mandatory on every pass.",
        "Use code_soup_pre_audit signals when writing section 9.",
        "Mark uncertainty explicitly when evidence is missing.",
        "Finish with roadmap(action='validate') before returning the checkpoint summary.",
    ]
    if fingerprint.get("steering_brief"):
        instructions.append(f"Project identity: {fingerprint['steering_brief']}")
    if fingerprint.get("project_archetype"):
        instructions.append(
            f"Archetype: {fingerprint['project_archetype']} — tailor center of gravity and anti-goals to this shape."
        )
    if fingerprint.get("test_frameworks"):
        instructions.append(
            f"Verification surface: {', '.join(fingerprint['test_frameworks'][:3])} — reference in Maintenance Gravity when relevant."
        )
    uncertainty = evidence.get("uncertainty") or []
    if uncertainty:
        instructions.append(f"Uncertainty to surface: {'; '.join(uncertainty[:3])}")

    if phase == "bootstrap":
        instructions.append(
            "First pass: draft all 12 sections from README, architecture docs, configs, git history, and code_soup_pre_audit."
        )
    elif phase == "structure_repair":
        instructions.append(
            "Repair missing sections while preserving Decision Log and Archive strategic memory."
        )
    elif phase == "coherence_recovery":
        instructions.append(
            "Demote overloaded Now items, strengthen Maintenance Gravity, and recommend convergence."
        )
    elif phase == "validate_pending":
        instructions.append("Fix schema validation errors reported by roadmap(action='validate').")
    elif phase == "bootstrap_fill":
        instructions.append(
            "Preview evidence autofill: roadmap(action='apply_bootstrap_fill'); apply with context='write', then validate."
        )
        instructions.append(
            "Use bootstrap_fill_plan.tasks — each template_phrase maps to suggested_replacement from project_fingerprint and evidence."
        )
        if fingerprint.get("agent_rules_files"):
            instructions.append(
                f"Honor project agent rules: {', '.join(fingerprint['agent_rules_files'][:3])}."
            )
    else:
        instructions.append(
            "Update Recent Checkpoint (section 11) — replace the previous checkpoint with today's pass only."
        )
    return instructions


def _response_format_template() -> dict[str, str]:
    return {
        "title": "Roadmap Checkpoint Updated",
        "fields": (
            "Health, Center of Gravity (one sentence), Moved, Added, Updated, Archived, "
            "Code Soup Risk (with brief reason), Recommended Next Move"
        ),
        "note": "Do not include the full ROADMAP.md in the final response unless the user asks.",
    }


def status_snapshot(*, workspace: Optional[str] = None) -> dict[str, Any]:
    """Read-only parse of the current ROADMAP.md."""
    from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot
    from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

    root = resolve_workspace_root(workspace)
    steering = build_steering_context(workspace=root)
    snap = get_workspace_snapshot(root, tier="light")
    roadmap_path = Path(snap.roadmap_path)
    parsed = snap.evidence.get("roadmap") or {}
    validation = snap.validation
    payload = {
        "action": "status",
        "success": True,
        "ok": True,
        "workspace": root,
        "roadmap_path": str(roadmap_path),
        "steering_brief": steering.get("steering_brief"),
        "project_archetype": steering.get("project_archetype"),
        "stack_summary": steering.get("stack_summary"),
        "parsed": parsed,
        "validation": validation.to_dict() if validation else None,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_bootstrap_steering_fields

    payload.update(attach_bootstrap_steering_fields(steering, tier="light"))
    return clarity_envelope(payload)
