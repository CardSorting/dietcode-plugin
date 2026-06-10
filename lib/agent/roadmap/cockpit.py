"""One-screen roadmap operator cockpit."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config, resolve_workspace_root
from plugins.dietcode.lib.agent.roadmap.phase_guide import clarity_envelope, determine_phase
from plugins.dietcode.lib.agent.roadmap.freshness import assess_checkpoint_freshness
from plugins.dietcode.lib.agent.roadmap.operator import is_bootstrap_incomplete, recommend_next_action
from plugins.dietcode.lib.agent.roadmap.progress import read_current, read_last_error
from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot
from plugins.dietcode.lib.agent.roadmap.skill_install import _SKILL_REL
from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context


def build_cockpit_payload(*, workspace: Optional[str] = None) -> dict[str, Any]:
    cfg = get_roadmap_config()
    if workspace and str(workspace).strip():
        root = resolve_workspace_root(workspace)
        workspace_source = "explicit"
    else:
        from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace

        root, workspace_source = resolve_workspace()
    steering = build_steering_context(workspace=root)
    snap = get_workspace_snapshot(root, tier="full")
    evidence = snap.evidence
    roadmap = evidence.get("roadmap") or {}
    roadmap_path = Path(snap.roadmap_path)
    validation = snap.validation
    code_soup = evidence.get("code_soup_audit") or {}
    ws_state = snap.gate_inputs.get("workspace_state") or {}
    gate_state = snap.gate_state
    bootstrap_inc = is_bootstrap_incomplete(
        roadmap_exists=bool(roadmap.get("exists")),
        workspace_state=ws_state,
        bootstrap_complete=steering.get("bootstrap_complete") or gate_state.get("bootstrap_complete"),
        bootstrap_placeholder_count=steering.get("bootstrap_placeholder_count")
        or gate_state.get("bootstrap_placeholder_count"),
    )
    phase_info = determine_phase(
        roadmap_exists=bool(roadmap.get("exists")),
        sections_missing=roadmap.get("sections_missing") or [],
        health_status=roadmap.get("health_status"),
        validation_valid=validation.valid if validation else None,
        bootstrap_incomplete=bootstrap_inc,
    )

    git = evidence.get("git") or {}
    freshness = snap.gate_inputs.get("freshness") or assess_checkpoint_freshness(
        recent_checkpoint_date=roadmap.get("recent_checkpoint_date"),
        git_commits=git.get("recent_commits") or [],
        schema_valid=validation.valid if validation else None,
        stale_days=cfg.stale_checkpoint_days,
    )
    current_progress = read_current()
    last_error = read_last_error()
    next_rec = recommend_next_action(
        phase=phase_info.get("phase") or "",
        roadmap_exists=bool(roadmap.get("exists")),
        schema_valid=validation.valid if validation else ws_state.get("schema_valid"),
        stale=bool(freshness.get("stale")),
        validation_pending=bool(ws_state.get("validation_pending")),
        bootstrap_incomplete=bootstrap_inc,
        last_error=last_error or None,
    )

    payload: dict[str, Any] = {
            "cockpit": True,
            "success": True,
            "ok": True,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "workspace": root,
            "workspace_source": workspace_source,
            "workspace_safe": steering.get("workspace_safe", True),
            "bootstrap_complete": steering.get("bootstrap_complete") if steering.get("bootstrap_complete") is not None else ws_state.get("bootstrap_complete"),
            "bootstrap_placeholder_count": steering.get("bootstrap_placeholder_count") if steering.get("bootstrap_placeholder_count") is not None else ws_state.get("bootstrap_placeholder_count"),
            "steering_identity": steering.get("steering_identity"),
            "steering_brief": steering.get("steering_brief"),
            "stack_summary": steering.get("stack_summary"),
            "project_archetype": steering.get("project_archetype"),
            "readme_tagline": steering.get("readme_tagline"),
            "center_of_gravity_excerpt": steering.get("center_of_gravity_excerpt"),
            "enabled": cfg.enabled,
            "skill_path": _SKILL_REL,
            "roadmap_exists": bool(roadmap.get("exists")),
            "roadmap_path": str(roadmap_path),
            "health_status": roadmap.get("health_status"),
            "code_soup_risk": roadmap.get("code_soup_risk") or code_soup.get("overall_risk"),
            "recent_checkpoint_date": roadmap.get("recent_checkpoint_date"),
            "sections_present": len(roadmap.get("sections_present") or []),
            "sections_missing": roadmap.get("sections_missing") or [],
            "now_item_count": validation.now_item_count if validation else 0,
            "schema_valid": validation.valid if validation else False,
            "schema_complete": validation.schema_complete if validation else False,
            "git_recent_commits": len(git.get("recent_commits") or []),
            "todo_marker_count": len(evidence.get("todo_markers") or []),
            "code_soup_signals": code_soup.get("signals") or [],
            "centralization_recommendation": code_soup.get("centralization_recommendation"),
            "uncertainty": evidence.get("uncertainty") or [],
            "operator_summary": phase_info.get("operator_summary"),
            "agent_next_call": next_rec.get("command"),
            "recommended_slash_command": next_rec.get("command") or "/roadmap cockpit",
            "recommended_next_action": next_rec,
            "checkpoint_freshness": freshness,
            "workspace_state": ws_state or None,
            "roadmap_gate": gate_state,
            "kanban_complete_allowed": gate_state.get("kanban_complete_allowed"),
            "closed_gate_count": gate_state.get("closed_gate_count"),
            "progress_phase": current_progress.get("phase"),
            "last_error": last_error or None,
            "evidence_tier": evidence.get("evidence_tier"),
            "project_fingerprint": evidence.get("project_fingerprint"),
    }
    if bootstrap_inc:
        from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import _enrich_with_bootstrap_fill

        roadmap_text = evidence.get("_roadmap_text") or ""
        if not roadmap_text and roadmap_path.is_file():
            try:
                roadmap_text = roadmap_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                roadmap_text = ""
        enriched: dict[str, Any] = {}
        _enrich_with_bootstrap_fill(
            enriched,
            roadmap_text=roadmap_text,
            evidence=evidence,
            bootstrap_inc=True,
        )
        payload.update(enriched)

    return clarity_envelope(payload, phase_info=phase_info)


def format_cockpit_report(*, workspace: Optional[str] = None) -> str:
    data = build_cockpit_payload(workspace=workspace)
    hints = data.get("_roadmap_operator_hints") or {}
    lines = [
        "🗺️ Roadmap cockpit",
        f"Workspace: {data.get('workspace')}",
    ]
    if data.get("steering_brief") or data.get("steering_identity"):
        lines.append(f"Project: {data.get('steering_brief') or data['steering_identity']}")
    if data.get("stack_summary"):
        archetype = data.get("project_archetype")
        stack_line = f"Stack: {data['stack_summary']}"
        if archetype and archetype != "project":
            stack_line += f" ({archetype.replace('-', ' ')})"
        lines.append(stack_line)
    if data.get("readme_tagline"):
        tag = str(data["readme_tagline"])
        if len(tag) > 90:
            tag = tag[:89] + "…"
        lines.append(f"Purpose: {tag}")
    if data.get("center_of_gravity_excerpt"):
        excerpt = str(data["center_of_gravity_excerpt"])
        if len(excerpt) > 100:
            excerpt = excerpt[:99] + "…"
        lines.append(f"Center of gravity: {excerpt}")
    lines.append(f"ROADMAP.md: {data.get('roadmap_path')}")
    if data.get("workspace_source"):
        lines.append(f"Workspace source: {data['workspace_source']}")
    write_guard = hints.get("write_guard") or f"Write guard: ROADMAP.md only at {data.get('roadmap_path')}"
    if not write_guard.startswith("Write guard:"):
        write_guard = f"Write guard: {write_guard}"
    lines.append(write_guard)
    lines.extend([
        f"Phase: {data.get('phase')}",
        f"Enabled: {data.get('enabled')}",
        "",
    ])

    if data.get("roadmap_exists"):
        lines.append(f"ROADMAP.md: present | health={data.get('health_status') or 'unparsed'}")
        lines.append(
            f"Schema: {'valid' if data.get('schema_valid') else 'invalid'}"
            f" | sections={data.get('sections_present')}/12"
            f" | Now items={data.get('now_item_count')}"
        )
        if data.get("recent_checkpoint_date"):
            lines.append(f"Last checkpoint: {data['recent_checkpoint_date']}")
        fresh = data.get("checkpoint_freshness") or {}
        if fresh.get("stale"):
            lines.append(f"⚠️  Stale: {fresh.get('reason')} — {fresh.get('summary')}")
        if data.get("kanban_complete_allowed") is False:
            lines.append("⚠️  kanban_complete blocked — /roadmap explain-gate")
    else:
        lines.append("ROADMAP.md: missing — bootstrap required")

    lines.append(f"Code soup risk: {data.get('code_soup_risk') or 'unknown'}")
    signals = data.get("code_soup_signals") or []
    if signals:
        lines.append(f"Signals: {len(signals)}")
        for sig in signals[:3]:
            lines.append(f"  • {sig.get('code')}: {sig.get('detail')}")

    if data.get("bootstrap_complete") is False and data.get("bootstrap_placeholder_count"):
        lines.append(
            f"⚠️  Bootstrap placeholders: {data['bootstrap_placeholder_count']} — "
            "roadmap(action='apply_bootstrap_fill', context='write') before closing pass"
        )
        fill_plan = data.get("bootstrap_fill_plan") or {}
        if fill_plan.get("remaining_count"):
            lines.append(
                f"Fill plan: {fill_plan['remaining_count']} task(s) — roadmap(action='apply_bootstrap_fill') or checkpoint plan"
            )
        digest = data.get("project_steering_digest") or {}
        agent_rules = digest.get("agent_rules_files") or data.get("project_fingerprint", {}).get("agent_rules_files") or []
        if agent_rules:
            lines.append(f"Agent rules: {', '.join(agent_rules[:3])}")
        make_targets = digest.get("makefile_targets") or data.get("project_fingerprint", {}).get("makefile_targets") or []
        if make_targets:
            lines.append(f"Makefile targets: {', '.join(make_targets[:4])}")
    lines.append("")
    lines.append(data.get("operator_summary") or "")
    if data.get("progress_phase"):
        lines.append(f"Progress: {data['progress_phase']}")
    if data.get("last_error"):
        lines.append(f"Last issue: {data['last_error'].get('phase')}")
    next_rec = data.get("recommended_next_action") or {}
    if next_rec.get("action"):
        lines.append(f"Next action: {next_rec.get('action')} — {next_rec.get('detail')}")
        lines.append(f"→ {next_rec.get('command') or data.get('agent_next_call')}")
    else:
        lines.append(f"Command: {data.get('agent_next_call')}")
    if data.get("centralization_recommendation"):
        lines.append(f"Centralize: {data['centralization_recommendation']}")

    uncertainty = data.get("uncertainty") or []
    if uncertainty:
        lines.append("")
        lines.append("Uncertainty:")
        for note in uncertainty[:4]:
            lines.append(f"  • {note}")

    lines.append("")
    lines.append("Live: /roadmap watch | progress --current | progress --timeline | explain-gate")
    return "\n".join(lines)
