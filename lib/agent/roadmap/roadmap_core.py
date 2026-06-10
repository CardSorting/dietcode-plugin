"""Cached ROADMAP.md read, parse, and validation — shared across tiers."""
from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_CACHE: dict[str, tuple[float, float, "RoadmapCore"]] = {}


@dataclass
class RoadmapCore:
    workspace: str
    roadmap_path: str
    mtime: float
    text: str
    parsed: dict[str, Any]
    validation: Any = None


def _core_ttl() -> float:
    try:
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config

        return float(get_roadmap_config().evidence_cache_ttl_seconds)
    except Exception:
        return 15.0


def invalidate_roadmap_core(workspace: str | Path) -> None:
    key = str(Path(workspace).expanduser().resolve())
    _CACHE.pop(key, None)


def read_roadmap_core(workspace: str | Path) -> RoadmapCore:
    """Return cached or fresh ROADMAP text, parse dict, and schema validation."""
    from plugins.dietcode.lib.agent.roadmap.evidence import parse_roadmap
    from plugins.dietcode.lib.agent.roadmap.schema import validate_roadmap_content

    root = Path(workspace).expanduser().resolve()
    roadmap_path = root / "ROADMAP.md"
    key = str(root)
    mtime = 0.0
    if roadmap_path.is_file():
        try:
            mtime = roadmap_path.stat().st_mtime
        except OSError:
            mtime = 0.0

    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached is not None and cached[1] == mtime and (now - cached[0]) <= _core_ttl():
        return cached[2]

    text = ""
    if roadmap_path.is_file():
        try:
            text = roadmap_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""

    parsed_obj = parse_roadmap(text, path=str(roadmap_path))
    parsed = parsed_obj.to_dict()
    validation = validate_roadmap_content(
        text,
        sections_present=parsed_obj.sections_present,
        sections_missing=parsed_obj.sections_missing,
        health_status=parsed_obj.health_status,
        code_soup_risk=parsed_obj.code_soup_risk,
    ) if text.strip() else None
    core = RoadmapCore(
        workspace=str(root),
        roadmap_path=str(roadmap_path),
        mtime=mtime,
        text=text,
        parsed=parsed,
        validation=validation,
    )
    _CACHE[key] = (now, mtime, core)
    return core
