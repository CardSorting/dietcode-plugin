"""Unified workspace steering context — one bundle for agents and operators."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def roadmap_file_path(workspace: str | Path) -> Path:
    return Path(workspace).expanduser().resolve() / "ROADMAP.md"


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

    return {
        "ok": workspace_safe,
        "workspace": root,
        "workspace_source": source,
        "roadmap_path": str(path),
        "roadmap_exists": path.is_file(),
        "workspace_safe": workspace_safe,
        "operator_action": (
            None
            if workspace_safe
            else "Point Hermes workspace at your project — ROADMAP.md must not live in the plugin install tree"
        ),
        "agent_next_call": (
            "roadmap(action='guide')"
            if workspace_safe
            else "Configure HERMES_KANBAN_WORKSPACE before editing ROADMAP.md"
        ),
    }
