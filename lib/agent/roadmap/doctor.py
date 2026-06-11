"""Roadmap feature production health checks."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config, resolve_workspace_root
from plugins.dietcode.lib.agent.roadmap.progress import progress_jsonl_path, read_last_error
from plugins.dietcode.lib.agent.roadmap.skill_install import bundled_skills_root
from plugins.dietcode.lib.agent.roadmap.operator import recommend_next_action
from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot
from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state, state_path


def run_checks(*, workspace: Optional[str] = None) -> dict[str, Any]:
    cfg = get_roadmap_config()
    from plugins.dietcode.lib.agent.roadmap.config import RoadmapWorkspaceError, resolve_workspace

    workspace_source = "explicit"
    try:
        if workspace and str(workspace).strip():
            root = resolve_workspace_root(workspace)
        else:
            root, workspace_source = resolve_workspace()
    except RoadmapWorkspaceError as exc:
        return {
            "success": False,
            "ok": False,
            "workspace": None,
            "workspace_source": "unresolved",
            "enabled": cfg.enabled,
            "checks": [{"name": "workspace_resolved", "ok": False, "detail": str(exc)}],
            "recommendations": [
                "Set kanban.workspace in ~/.hermes/config.yaml",
                "export HERMES_KANBAN_WORKSPACE=/path/to/your/project",
            ],
            "recommended_next_action": {
                "action": "configure_workspace",
                "command": "export HERMES_KANBAN_WORKSPACE=/path/to/project",
                "detail": str(exc),
            },
        }

    checks: list[dict[str, Any]] = []
    recommendations: list[str] = []

    def _check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    _check("roadmap.enabled", cfg.enabled, "enabled" if cfg.enabled else "disabled in config")
    try:
        from plugins.dietcode.lib.kernel_workspace import is_quarantined_root

        _check(
            "workspace_not_plugin_tree",
            not is_quarantined_root(root),
            f"{root} ({workspace_source})",
        )
    except ImportError:
        pass

    _check(
        "auto_install_skills",
        True,
        "enabled" if cfg.auto_install_skills else "disabled — skill must be copied manually",
    )

    bundled = bundled_skills_root()
    skill_src = bundled / "dietcode" / "auto-rolling-roadmap" / "SKILL.md"
    _check("bundled_skill_present", skill_src.is_file(), str(skill_src) if skill_src.is_file() else "missing")

    ws_skill = Path(root) / "optional-skills" / "dietcode" / "auto-rolling-roadmap" / "SKILL.md"
    _check(
        "workspace_skill_installed",
        ws_skill.is_file(),
        str(ws_skill) if ws_skill.is_file() else "not installed — session start or roadmap(action='doctor')",
    )

    from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

    steering = build_steering_context(workspace=root)
    snap = get_workspace_snapshot(root, tier="light")
    roadmap_path = Path(snap.roadmap_path)
    validation = snap.validation
    freshness = snap.gate_inputs.get("freshness")
    gate_state = snap.gate_state
    ws_state = snap.gate_inputs.get("workspace_state") or read_state(root)

    if roadmap_path.is_file():
        _check("roadmap_readable", True, str(roadmap_path))
        _check(
            "checkpoint_fresh",
            not (freshness or {}).get("stale"),
            (freshness or {}).get("summary") or "ok",
        )
        if (freshness or {}).get("stale"):
            recommendations.append((freshness or {}).get("recommended_action") or "roadmap(action='checkpoint')")
    else:
        _check("roadmap_present", False, "ROADMAP.md not found — bootstrap required")

    _check(
        "progress_log_available",
        progress_jsonl_path().parent.is_dir(),
        str(progress_jsonl_path()) if progress_jsonl_path().parent.is_dir() else "session dir missing",
    )

    _check(
        "workspace_state_available",
        state_path(root).parent.is_dir() or not roadmap_path.is_file(),
        (
            f"last_validated={ws_state.get('last_validated_at') or 'never'}"
            if ws_state
            else ".dietcode/roadmap-state.json not written yet — run validate"
        ),
    )
    if ws_state.get("schema_valid") is False:
        recommendations.append("Schema invalid at last validate — /roadmap explain-gate")

    last_error = read_last_error()
    if last_error:
        recommendations.append(
            f"Last roadmap issue: {last_error.get('phase')} — {last_error.get('operator_action')}"
        )

    if validation:
        _check("schema_complete", validation.schema_complete, f"{len(validation.issues)} issue(s)")
        _check("schema_valid", validation.valid, f"now_items={validation.now_item_count}")
        if validation.now_item_count > 5:
            recommendations.append("Demote Now items — roadmap overloaded (max 5)")
        for issue in validation.issues:
            if issue.severity == "error":
                recommendations.append(f"Fix {issue.code}: {issue.message}")

    if not cfg.enabled:
        recommendations.append("Set dietcode.roadmap.enabled: true in Hermes config")
    if cfg.enabled and not ws_skill.is_file():
        recommendations.append("Run roadmap(action='doctor') or reload session to install workspace skill")
    if not roadmap_path.is_file():
        recommendations.append("Run roadmap(action='checkpoint') to create ROADMAP.md")

    _check(
        "kanban_complete_allowed",
        bool(gate_state.get("kanban_complete_allowed")),
        (
            "ok"
            if gate_state.get("kanban_complete_allowed")
            else f"{gate_state.get('closed_gate_count', 0)} closed gate(s) — /roadmap explain-gate"
        ),
    )
    if not gate_state.get("kanban_complete_allowed"):
        recommendations.append("/roadmap explain-gate — review closed steering gates")
    if ws_state.get("validation_pending"):
        recommendations.append("ROADMAP.md mutated since last validate — roadmap(action='validate')")

    bootstrap_inc = False
    if roadmap_path.is_file():
        from plugins.dietcode.lib.agent.roadmap.operator import is_bootstrap_incomplete

        bootstrap_inc = is_bootstrap_incomplete(
            roadmap_exists=True,
            workspace_state=ws_state,
            bootstrap_complete=gate_state.get("bootstrap_complete"),
            bootstrap_placeholder_count=gate_state.get("bootstrap_placeholder_count"),
        )

    next_rec = recommend_next_action(
        phase=str(ws_state.get("phase") or ""),
        roadmap_exists=roadmap_path.is_file(),
        schema_valid=(validation.valid if validation else ws_state.get("schema_valid")),
        stale=bool((freshness or {}).get("stale")),
        validation_pending=bool(ws_state.get("validation_pending")),
        bootstrap_incomplete=bootstrap_inc,
        last_error=last_error or None,
    )

    fill_plan = None
    steering_digest = None
    if roadmap_path.is_file():
        try:
            from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import (
                build_bootstrap_fill_plan,
                build_project_steering_digest,
            )
            from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence
            from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

            text = roadmap_path.read_text(encoding="utf-8", errors="replace")
            evidence = gather_evidence(root, tier="light", roadmap_text=text)
            fp = evidence.get("project_fingerprint") or build_project_fingerprint(root)
            if bootstrap_inc:
                fill_plan = build_bootstrap_fill_plan(roadmap_text=text, evidence=evidence)
            steering_digest = build_project_steering_digest(fp, fill_plan=fill_plan)
        except OSError:
            fill_plan = None
            steering_digest = None

    if bootstrap_inc:
        count = gate_state.get("bootstrap_placeholder_count") or steering.get("bootstrap_placeholder_count")
        recommendations.append(
            f"Bootstrap fill: {count or '?'} template phrase(s) — "
            "roadmap(action='apply_bootstrap_fill', context='write') then validate"
        )

    ok = all(c["ok"] for c in checks if c["name"] not in {"roadmap_present"})
    if not roadmap_path.is_file():
        ok = ok and cfg.enabled and skill_src.is_file()

    return {
        "success": ok,
        "ok": ok,
        "workspace": root,
        "workspace_source": workspace_source,
        "steering_brief": steering.get("steering_brief"),
        "project_archetype": steering.get("project_archetype"),
        "stack_summary": steering.get("stack_summary"),
        "bootstrap_fill_plan": fill_plan,
        "project_steering_digest": steering_digest,
        "project_identity_line": (steering_digest or {}).get("identity_line") if steering_digest else None,
        "enabled": cfg.enabled,
        "checks": checks,
        "validation": validation.to_dict() if validation else None,
        "checkpoint_freshness": freshness,
        "workspace_state": ws_state or None,
        "roadmap_gate": gate_state,
        "recommended_next_action": next_rec,
        "last_error": last_error or None,
        "recommendations": recommendations,
    }


def format_doctor_report(*, workspace: Optional[str] = None) -> str:
    """Human-readable roadmap doctor summary."""
    data = run_checks(workspace=workspace)
    lines = [
        "🗺️ Roadmap doctor",
        f"Workspace: {data.get('workspace') or '(unresolved)'}",
    ]
    if data.get("steering_brief"):
        lines.append(f"Project: {data['steering_brief']}")
    if data.get("project_identity_line"):
        lines.append(f"Identity: {data['project_identity_line']}")
    elif (data.get("project_steering_digest") or {}).get("identity_line"):
        lines.append(f"Identity: {data['project_steering_digest']['identity_line']}")
    if data.get("stack_summary"):
        lines.append(f"Stack: {data['stack_summary']}")
    digest = data.get("project_steering_digest") or {}
    verify_cmds = digest.get("verification_commands") or []
    if verify_cmds:
        lines.append(f"Verify: {', '.join(verify_cmds[:3])}")
    lines.append(f"Enabled: {data.get('enabled')}")
    lines.append("")

    for check in data.get("checks") or []:
        mark = "✓" if check.get("ok") else "✕"
        detail = check.get("detail") or ""
        suffix = f" — {detail}" if detail and detail not in ("ok", "enabled", "disabled in config") else ""
        lines.append(f"{mark} {check.get('name')}{suffix}")

    digest = data.get("project_steering_digest") or {}
    remaining = digest.get("bootstrap_remaining")
    if remaining and int(remaining) > 0:
        lines.append("")
        lines.append(
            f"Bootstrap fill: {remaining} phrase(s) — roadmap(action='apply_bootstrap_fill', context='write')"
        )
        sample = digest.get("sample_fill_task") or {}
        if sample.get("template_phrase"):
            lines.append(f"  sample: “{sample['template_phrase'][:50]}…”")

    recs = data.get("recommendations") or []
    if recs:
        lines.append("")
        lines.append("Recommendations:")
        for rec in recs[:6]:
            lines.append(f"  • {rec}")

    next_rec = data.get("recommended_next_action") or {}
    if next_rec.get("command"):
        lines.append("")
        lines.append(f"→ {next_rec['command']}")

    return "\n".join(lines)
