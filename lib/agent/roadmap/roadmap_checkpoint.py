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
    return determine_phase(
        roadmap_exists=bool(roadmap.get("exists")),
        sections_missing=roadmap.get("sections_missing") or [],
        health_status=roadmap.get("health_status"),
        validation_valid=validation_valid,
    )


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
    phase_info = _phase_from_evidence(bundle, validation_valid=validation_valid)
    next_rec = recommend_next_action(
        phase=phase_info.get("phase") or "",
        roadmap_exists=bool(roadmap.get("exists")),
        schema_valid=validation_valid if validation_valid is not None else ws_state.get("schema_valid"),
        stale=bool(freshness.get("stale")),
        validation_pending=bool(ws_state.get("validation_pending")),
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
    if ws_state.get("validation_pending"):
        payload["validation_pending"] = True
        payload["operator_summary"] = (
            "ROADMAP.md changed since last validate — confirm schema before closing checkpoint."
        )
        payload["agent_next_call"] = next_rec.get("command") or "roadmap(action='validate')"
    if freshness.get("stale"):
        payload["operator_summary"] = freshness.get("summary") or payload.get("operator_summary")
    return clarity_envelope(payload, phase_info=phase_info)


def checkpoint_brief(
    *,
    workspace: Optional[str] = None,
    context: str = "",
    user_request: str = "",
) -> dict[str, Any]:
    """Return evidence, algorithm, and instructions for a full roadmap pass."""
    from plugins.dietcode.lib.agent.roadmap.evidence import extend_evidence
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
        "existing_roadmap_summary": evidence.get("roadmap"),
        "code_soup_pre_audit": evidence.get("code_soup_audit"),
        "agent_instructions": _agent_instructions(status["phase"], evidence),
        "response_format": _response_format_template(),
        "bootstrap_template_available": not evidence.get("roadmap", {}).get("exists"),
        "skill_bootstrap": bootstrap,
        "operator_summary": status["operator_summary"],
        "agent_next_call": "Edit ROADMAP.md per skill, then roadmap(action='validate'), then return checkpoint summary.",
    }
    if not evidence.get("roadmap", {}).get("exists"):
        payload["suggested_bootstrap"] = bootstrap_skeleton_from_evidence(evidence, workspace=root)
        payload["bootstrap_evidence_driven"] = True
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
        phase="validate_pending" if not validation.valid else "checkpoint",
        issue_count=len(validation.issues),
        bootstrap_placeholder_count=int(completeness.get("bootstrap_placeholder_count") or 0),
    )
    invalidate_snapshot(root)
    phase_info = determine_phase(
        roadmap_exists=bool(text.strip()),
        sections_missing=[
            s for s in REQUIRED_SECTIONS
            if s not in (parse_roadmap(text).sections_present if text else [])
        ],
        health_status=validation.health_status,
        validation_valid=validation.valid,
    )
    payload = {
        "action": "validate",
        "success": validation.valid,
        "ok": validation.valid,
        "workspace": root,
        "roadmap_path": str(roadmap_path),
        "validation": validation_dict,
        "bootstrap_completeness": completeness,
        "operator_summary": (
            "ROADMAP.md passes schema validation."
            if validation.valid and completeness.get("bootstrap_complete", True)
            else (
                "ROADMAP.md passes schema but unfilled bootstrap template text remains — replace placeholder guidance."
                if validation.valid
                else "ROADMAP.md has schema errors — fix before treating checkpoint as complete."
            )
        ),
        "agent_next_call": (
            "Return Required Final Assistant Response summary."
            if validation.valid and completeness.get("bootstrap_complete", True)
            else (
                "Replace bootstrap_placeholder guidance with project-specific facts, then roadmap(action='validate')."
                if validation.valid
                else "Fix validation issues and rerun roadmap(action='validate')."
            )
        ),
    }
    return clarity_envelope(payload, phase_info=phase_info)


def template_brief(*, workspace: Optional[str] = None) -> dict[str, Any]:
    """Return bootstrap skeleton for first-pass ROADMAP.md creation."""
    root = resolve_workspace_root(workspace)
    evidence = gather_evidence(root, tier="standard")
    skeleton = bootstrap_skeleton_from_evidence(evidence, workspace=root)
    payload = {
        "action": "template",
        "success": True,
        "ok": True,
        "workspace": root,
        "roadmap_path": str(Path(root) / "ROADMAP.md"),
        "skeleton": skeleton,
        "evidence_summary": {
            "readmes": len(evidence.get("readmes") or []),
            "git_commits": len((evidence.get("git") or {}).get("recent_commits") or []),
            "code_soup_risk": (evidence.get("code_soup_audit") or {}).get("overall_risk"),
        },
        "operator_summary": "Evidence-driven skeleton — replace any remaining guidance with project-specific facts, then validate.",
        "agent_next_call": "Write skeleton to ROADMAP.md, evolve from checkpoint evidence, then validate.",
    }
    return clarity_envelope(payload)


def _agent_instructions(phase: str, evidence: dict[str, Any]) -> list[str]:
    instructions = [
        "Read optional-skills/dietcode/auto-rolling-roadmap/SKILL.md before editing.",
        "Create or evolve ROADMAP.md at the workspace root — never in ~/.hermes/plugins/dietcode or plugin install trees.",
        "Keep Now to 1–5 actionable items; archive stale work instead of appending endlessly.",
        "Section 9 (Centralization & Code Soup Audit) is mandatory on every pass.",
        "Use code_soup_pre_audit signals when writing section 9.",
        "Mark uncertainty explicitly when evidence is missing.",
        "Finish with roadmap(action='validate') before returning the checkpoint summary.",
    ]
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

    root = resolve_workspace_root(workspace)
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
        "parsed": parsed,
        "validation": validation.to_dict() if validation else None,
        "checked_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return clarity_envelope(payload)
