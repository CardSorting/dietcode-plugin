"""Unified workspace steering context — one bundle for agents and operators."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def roadmap_file_path(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve() / "ROADMAP.md"


def _roadmap_steering_fields(root: Path, path: Path) -> dict[str, Any]:
    """Live ROADMAP.md parse + bootstrap metrics for steering surfaces."""
    fields: dict[str, Any] = {
        "bootstrap_complete": None,
        "bootstrap_placeholder_count": None,
        "health_status": None,
        "code_soup_risk": None,
        "recent_checkpoint_date": None,
        "center_of_gravity_excerpt": None,
        "now_item_count": None,
    }
    if not path.is_file():
        return fields

    try:
        from plugins.dietcode.lib.agent.roadmap.evidence import parse_roadmap
        from plugins.dietcode.lib.agent.roadmap.schema import (
            bootstrap_completeness_metrics,
            find_bootstrap_placeholders,
        )

        text = path.read_text(encoding="utf-8", errors="replace")
        parsed = parse_roadmap(text, path=str(path))
        fields["bootstrap_placeholder_count"] = len(find_bootstrap_placeholders(text))
        metrics = bootstrap_completeness_metrics(text)
        fields["bootstrap_complete"] = metrics.get("bootstrap_complete")
        fields["health_status"] = parsed.health_status
        fields["code_soup_risk"] = parsed.code_soup_risk
        fields["recent_checkpoint_date"] = parsed.recent_checkpoint_date
        fields["now_item_count"] = parsed.now_item_count
        excerpt = (parsed.center_of_gravity_excerpt or "").strip()
        if excerpt:
            fields["center_of_gravity_excerpt"] = excerpt[:240] + ("…" if len(excerpt) > 240 else "")
    except OSError:
        pass
    return fields


def build_steering_context(*, workspace: Optional[str] = None) -> dict[str, Any]:
    """Resolve project workspace + ROADMAP path with safety signals (kernel cockpit pattern)."""
    from plugins.dietcode.lib.agent.roadmap.config import RoadmapWorkspaceError, resolve_workspace

    if workspace and str(workspace).strip():
        from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace_root

        root = resolve_workspace_root(workspace)
        source = "explicit"
    else:
        try:
            root, source = resolve_workspace()
        except RoadmapWorkspaceError as exc:
            return {
                "ok": False,
                "workspace": None,
                "workspace_source": "unresolved",
                "roadmap_path": None,
                "workspace_safe": False,
                "error": str(exc),
                "operator_action": "Set kanban.workspace or export HERMES_KANBAN_WORKSPACE",
                "agent_next_call": "export HERMES_KANBAN_WORKSPACE=/path/to/project",
            }

    path = roadmap_file_path(root)
    workspace_safe = True
    try:
        from plugins.dietcode.lib.kernel_workspace import is_quarantined_root

        workspace_safe = not is_quarantined_root(root)
    except ImportError:
        pass

    roadmap_fields = _roadmap_steering_fields(root, path)
    fingerprint: dict[str, Any] = {}
    try:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        fingerprint = build_project_fingerprint(root)
    except Exception:
        fingerprint = {"steering_identity": root.name}

    agent_next_call = (
        "roadmap(action='guide')"
        if workspace_safe
        else "Configure HERMES_KANBAN_WORKSPACE before editing ROADMAP.md"
    )
    if workspace_safe and roadmap_fields.get("bootstrap_complete") is False and path.is_file():
        from plugins.dietcode.lib.agent.roadmap.operator import recommend_next_action

        next_rec = recommend_next_action(
            phase="bootstrap_fill",
            roadmap_exists=True,
            bootstrap_incomplete=True,
        )
        agent_next_call = next_rec.get("command") or agent_next_call
    elif workspace_safe and not path.is_file():
        from plugins.dietcode.lib.agent.roadmap.operator import recommend_next_action

        next_rec = recommend_next_action(roadmap_exists=False)
        agent_next_call = next_rec.get("command") or agent_next_call

    return {
        "ok": workspace_safe,
        "workspace": root,
        "workspace_source": source,
        "roadmap_path": str(path),
        "roadmap_exists": path.is_file(),
        "workspace_safe": workspace_safe,
        **roadmap_fields,
        **fingerprint,
        "operator_action": (
            None
            if workspace_safe
            else "Point Hermes workspace at your project — ROADMAP.md must not live in the plugin install tree"
        ),
        "agent_next_call": agent_next_call,
    }


_STEERING_PAYLOAD_KEYS: tuple[str, ...] = (
    "workspace",
    "workspace_source",
    "roadmap_path",
    "roadmap_exists",
    "workspace_safe",
    "bootstrap_complete",
    "bootstrap_placeholder_count",
    "health_status",
    "code_soup_risk",
    "recent_checkpoint_date",
    "center_of_gravity_excerpt",
    "now_item_count",
    "project_name",
    "package_name",
    "readme_tagline",
    "package_description",
    "stack_summary",
    "steering_identity",
    "steering_brief",
    "project_archetype",
    "primary_language",
    "frameworks",
    "ci_systems",
    "test_frameworks",
    "monorepo_tools",
    "package_managers",
    "has_ci",
    "has_tests",
    "has_docker",
    "purpose_hint",
    "runtime_center_hint",
    "operators_hint",
    "entry_points",
    "license",
    "git_remote",
    "docs_roots",
    "agent_rules_files",
    "makefile_targets",
    "verification_commands",
    "runtime_versions",
    "has_codeowners",
    "dependency_automation",
    "has_backstage_catalog",
    "catalog_name",
    "catalog_description",
)


def enrich_payload_with_steering(
    payload: dict[str, Any],
    *,
    workspace: Optional[str] = None,
) -> dict[str, Any]:
    """Merge workspace steering fields into any roadmap tool/slash payload."""
    explicit = str(payload.get("workspace") or workspace or "").strip() or None
    steering = build_steering_context(workspace=explicit)
    out = dict(payload)
    if steering.get("workspace") and not out.get("workspace"):
        out["workspace"] = steering["workspace"]
    for key in _STEERING_PAYLOAD_KEYS:
        if key in steering and steering.get(key) is not None and key not in out:
            out[key] = steering[key]
    if steering.get("roadmap_path") and not out.get("roadmap_path"):
        out["roadmap_path"] = steering["roadmap_path"]
    if steering.get("bootstrap_complete") is False and "bootstrap_fill_plan" not in out:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_bootstrap_steering_fields

        out.update(attach_bootstrap_steering_fields(steering, tier="light"))
    return out
