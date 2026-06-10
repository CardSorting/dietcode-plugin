"""Install bundled DietCode optional-skills into the active workspace."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

_SKILL_REL = "optional-skills/dietcode/auto-rolling-roadmap/SKILL.md"


def bundled_skills_root() -> Path:
    try:
        from plugins.dietcode.paths import get_plugin_root

        return get_plugin_root() / "optional-skills"
    except ImportError:
        return Path(__file__).resolve().parents[3] / "optional-skills"


def ensure_primary_skill(workspace: str | Path) -> dict[str, Any]:
    """Fast path — install only the auto-rolling-roadmap skill when missing."""
    root = Path(workspace).expanduser().resolve()
    dest = root / _SKILL_REL
    if dest.is_file():
        return {
            "ok": True,
            "workspace": str(root),
            "installed": [],
            "skipped": [_SKILL_REL],
            "errors": [],
            "primary_skill": _SKILL_REL,
        }

    src_root = bundled_skills_root()
    src = src_root / "dietcode" / "auto-rolling-roadmap" / "SKILL.md"
    if not src.is_file():
        return ensure_workspace_skills(workspace)

    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(src, dest)
        return {
            "ok": True,
            "workspace": str(root),
            "installed": [_SKILL_REL],
            "skipped": [],
            "errors": [],
            "primary_skill": _SKILL_REL,
        }
    except OSError as exc:
        return {
            "ok": False,
            "workspace": str(root),
            "installed": [],
            "skipped": [],
            "errors": [str(exc)],
            "primary_skill": _SKILL_REL,
        }


def ensure_workspace_skills(workspace: str | Path) -> dict[str, Any]:
    """Copy bundled optional-skills into *workspace* when missing or stale."""
    root = Path(workspace).expanduser().resolve()
    src_root = bundled_skills_root()
    if not src_root.is_dir():
        return {"ok": False, "error": "bundled optional-skills missing from plugin"}

    installed: list[str] = []
    skipped: list[str] = []
    errors: list[str] = []

    for skill_file in src_root.rglob("SKILL.md"):
        rel = skill_file.relative_to(src_root)
        dest = root / "optional-skills" / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            if dest.is_file():
                if dest.read_bytes() == skill_file.read_bytes():
                    skipped.append(str(rel))
                    continue
            shutil.copy2(skill_file, dest)
            installed.append(str(rel))
        except OSError as exc:
            errors.append(f"{rel}: {exc}")

    return {
        "ok": not errors,
        "workspace": str(root),
        "installed": installed,
        "skipped": skipped,
        "errors": errors,
        "primary_skill": _SKILL_REL,
    }
