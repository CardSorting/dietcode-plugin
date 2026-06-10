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

    ok = all(c["ok"] for c in checks if c["name"] not in {"roadmap_present"})
    if not roadmap_path.is_file():
        ok = ok and cfg.enabled and skill_src.is_file()

    return {
        "success": ok,
        "ok": ok,
        "workspace": root,
        "workspace_source": workspace_source,
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
