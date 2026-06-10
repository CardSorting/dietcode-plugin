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


def targets_roadmap_file(*, tool_name: str = "", args: Any = None) -> bool:
    """True when a mutation tool is writing ROADMAP.md."""
    if not isinstance(args, dict):
        return False
    name = (tool_name or "").strip().lower()
    if name == "write_file":
        return _path_basename(_normalized_path(args.get("path"))) in _ROADMAP_NAMES
    if name == "patch":
        return _path_basename(_normalized_path(args.get("path"))) in _ROADMAP_NAMES
    if name == "dietcode_kernel" and str(args.get("action") or "").lower() == "patch":
        return _path_basename(_normalized_path(args.get("path"))) in _ROADMAP_NAMES
    return False


def roadmap_write_hint(*, tool_name: str = "", args: Any = None) -> dict[str, Any]:
    """Operator hints merged after ROADMAP.md mutations."""
    return {
        "string_code": "roadmap_write_followup",
        "preferred_tool": "roadmap",
        "preferred_command": "roadmap(action='validate')",
        "recovery_suggestion": (
            "ROADMAP.md was mutated — run schema validation before closing the checkpoint pass."
        ),
        "suggested_slash_command": "/roadmap validate",
        "next_action": "roadmap(action='validate') then return checkpoint summary if pass complete",
        "source_tool": tool_name,
        "path": _normalized_path((args or {}).get("path")),
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
    return json.dumps(parsed, ensure_ascii=False)


def parse_roadmap_tool_action(args: Any) -> str:
    if not isinstance(args, dict):
        return ""
    return str(args.get("action") or "").strip().lower()
