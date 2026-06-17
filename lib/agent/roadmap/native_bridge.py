"""Native Hermes bridge — ROADMAP.md write detection and post-edit nudges."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

_ROADMAP_NAMES = frozenset({"ROADMAP.md", "roadmap.md"})


def _normalized_path(raw: Any) -> str:
    return str(raw or "").strip().replace("\\", "/")


def _path_basename(path: str) -> str:
    return Path(path).name


def is_roadmap_filename(path: str) -> bool:
    return _path_basename(_normalized_path(path)) in _ROADMAP_NAMES


def resolve_roadmap_write_path(*, write_path: str, workspace: str) -> tuple[Optional[Path], Optional[str]]:
    """Resolve and validate a ROADMAP write target under the project workspace.

    Returns ``(resolved_path, error_message)``. *error_message* is set when rejected.
    """
    ws = Path(workspace).expanduser().resolve()
    raw = _normalized_path(write_path)
    if not raw:
        return None, "missing write path"

    if not is_roadmap_filename(raw):
        return None, "not a ROADMAP.md write"

    candidate = Path(raw)
    resolved = (ws / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
    expected = (ws / "ROADMAP.md").resolve()

    try:
        from plugins.dietcode.lib.workspace_root import is_quarantined_root

        if is_quarantined_root(resolved.parent) or is_quarantined_root(ws):
            return None, (
                f"ROADMAP.md must be written in the project workspace ({expected}), "
                f"not the DietCode plugin install tree"
            )
    except ImportError:
        pass

    if resolved != expected:
        try:
            resolved.relative_to(ws)
        except ValueError:
            return None, f"ROADMAP.md must live at workspace root: {expected} (got {resolved})"
        if _path_basename(str(resolved)) not in _ROADMAP_NAMES:
            return None, f"ROADMAP.md must be named ROADMAP.md at {expected}"

    return expected, None


def targets_roadmap_file(*, tool_name: str = "", args: Any = None) -> bool:
    """True when a mutation tool is writing ROADMAP.md."""
    if not isinstance(args, dict):
        return False
    name = (tool_name or "").strip().lower()
    if name == "write_file":
        return is_roadmap_filename(_normalized_path(args.get("path")))
    if name == "patch":
        return is_roadmap_filename(_normalized_path(args.get("path")))
    if name == "dietcode_kernel" and str(args.get("action") or "").lower() == "patch":
        return is_roadmap_filename(_normalized_path(args.get("path")))
    return False


def validate_roadmap_write_target(
    *,
    write_path: str,
    workspace: Optional[str] = None,
) -> dict[str, Any]:
    """Pre-flight check before accepting a ROADMAP.md mutation."""
    from plugins.dietcode.lib.agent.roadmap.config import RoadmapWorkspaceError, resolve_workspace_root
    from plugins.dietcode.lib.agent.roadmap.steering_context import roadmap_file_path

    try:
        root = resolve_workspace_root(workspace)
    except RoadmapWorkspaceError as exc:
        return {"ok": False, "allowed": False, "error": str(exc), "code": "workspace_unresolved"}

    from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

    steering = build_steering_context(workspace=root)
    project_brief = steering.get("steering_brief") or steering.get("steering_identity")
    bootstrap_inc = steering.get("bootstrap_complete") is False

    resolved, err = resolve_roadmap_write_path(write_path=write_path, workspace=root)
    if err:
        return {
            "ok": False,
            "allowed": False,
            "error": err,
            "code": "workspace_quarantined" if "plugin" in err.lower() else "roadmap_path_invalid",
            "workspace": root,
            "expected_path": str(roadmap_file_path(root)),
            "attempted_path": _normalized_path(write_path),
        }

    return {
        "ok": True,
        "allowed": True,
        "workspace": root,
        "roadmap_path": str(resolved),
        "expected_path": str(roadmap_file_path(root)),
        "project_steering_brief": project_brief,
        "bootstrap_incomplete": bootstrap_inc,
        "bootstrap_placeholder_count": steering.get("bootstrap_placeholder_count"),
    }


def roadmap_write_hint(*, tool_name: str = "", args: Any = None, workspace: Optional[str] = None) -> dict[str, Any]:
    """Operator hints merged after ROADMAP.md mutations."""
    write_path = _normalized_path((args or {}).get("path"))
    check = validate_roadmap_write_target(write_path=write_path, workspace=workspace)
    project_brief = check.get("project_steering_brief")
    bootstrap_inc = check.get("bootstrap_incomplete") is True
    brief_bit = f" Project: {project_brief}." if project_brief else ""

    if not check.get("allowed"):
        return {
            "string_code": check.get("code") or "roadmap_write_rejected",
            "preferred_tool": "roadmap",
            "preferred_command": "roadmap(action='guide')",
            "recovery_suggestion": (check.get("error") or "Write ROADMAP.md only in the Hermes project workspace root.") + brief_bit,
            "suggested_slash_command": "/roadmap cockpit",
            "next_action": check.get("agent_next_call") or "Set HERMES_KANBAN_WORKSPACE to your project root",
            "source_tool": tool_name,
            "path": write_path,
            "workspace": check.get("workspace"),
            "expected_path": check.get("expected_path"),
            "project_steering_brief": project_brief,
            "write_rejected": True,
        }

    followup = (
        f"ROADMAP.md was mutated — run schema validation before closing the checkpoint pass.{brief_bit}"
    )
    if bootstrap_inc:
        followup += (
            f" Bootstrap incomplete ({check.get('bootstrap_placeholder_count', '?')} phrase(s)) — "
            "preview roadmap(action='apply_bootstrap_fill') or apply with context='write'."
        )
    elif project_brief:
        followup += " If bootstrap template phrases remain, preview roadmap(action='apply_bootstrap_fill') or apply with context='write'."

    digest: dict[str, Any] = {}
    if check.get("allowed") and check.get("workspace"):
        try:
            from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_bootstrap_steering_fields
            from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

            steering = build_steering_context(workspace=check.get("workspace"))
            attached = attach_bootstrap_steering_fields(steering, tier="light")
            digest = attached.get("project_steering_digest") or {}
        except Exception:
            digest = {}

    next_action = (
        "roadmap(action='apply_bootstrap_fill', context='write') then roadmap(action='validate')"
        if bootstrap_inc
        else "roadmap(action='validate') then return checkpoint summary if pass complete"
    )
    preferred = (
        "roadmap(action='apply_bootstrap_fill', context='write')"
        if bootstrap_inc
        else "roadmap(action='validate')"
    )

    return {
        "string_code": "roadmap_write_followup",
        "preferred_tool": "roadmap",
        "preferred_command": preferred,
        "recovery_suggestion": followup,
        "suggested_slash_command": "/roadmap validate",
        "next_action": next_action,
        "source_tool": tool_name,
        "path": write_path,
        "workspace": check.get("workspace"),
        "roadmap_path": check.get("roadmap_path"),
        "expected_path": check.get("expected_path"),
        "project_steering_brief": project_brief,
        "bootstrap_incomplete": bootstrap_inc,
        "project_steering_digest": digest or None,
        "write_rejected": False,
    }


def merge_roadmap_hint_into_result(result: Any, hint: dict[str, Any]) -> str:
    """Attach ``_roadmap_write_hint`` to JSON tool results."""
    parsed: dict[str, Any]
    if isinstance(result, dict):
        parsed = dict(result)
    elif isinstance(result, str):
        try:
            loaded = json.loads(result)
            parsed = loaded if isinstance(loaded, dict) else {"result": result}
        except json.JSONDecodeError:
            parsed = {"result": result}
    else:
        parsed = {"result": result}

    parsed["_roadmap_write_hint"] = hint
    digest = hint.get("project_steering_digest")
    if isinstance(digest, dict):
        parsed["project_steering_digest"] = digest
        if digest.get("identity_line"):
            parsed["project_identity_line"] = digest["identity_line"]
    if hint.get("bootstrap_incomplete") and isinstance(digest, dict) and digest.get("agent_next_call"):
        parsed["agent_next_call"] = digest["agent_next_call"]
    try:
        from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints

        parsed["_roadmap_operator_hints"] = build_agent_operator_hints(
            action="write_file",
            workspace=str(hint.get("workspace") or ""),
            last_error={"operator_action": hint.get("recovery_suggestion")} if hint.get("write_rejected") else None,
        )
    except Exception:
        pass
    if hint.get("write_rejected"):
        parsed["_roadmap_write_rejected"] = True
        parsed["success"] = False
        parsed["ok"] = False
    return json.dumps(parsed, ensure_ascii=False)


def parse_roadmap_tool_action(args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    return str(args.get("action") or "").strip().lower()
