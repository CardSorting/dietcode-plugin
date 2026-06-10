"""Roadmap checkpoint configuration."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional

_config_cache: Optional["RoadmapConfig"] = None
_config_cache_at: float = 0.0
_CONFIG_TTL = 30.0


@dataclass(frozen=True)
class RoadmapConfig:
    enabled: bool = True
    auto_install_skills: bool = True
    nudge_on_roadmap_write: bool = True
    progress_enabled: bool = True
    stale_checkpoint_days: int = 7
    warn_on_stale_before_complete: bool = True
    block_kanban_on_invalid_schema: bool = False
    block_kanban_on_validation_pending: bool = True
    evidence_cache_ttl_seconds: float = 15.0
    git_timeout_seconds: float = 5.0
    heavy_scan_cache_ttl_seconds: float = 60.0

    @classmethod
    def load(cls) -> "RoadmapConfig":
        try:
            from hermes_cli.config import load_config

            raw = load_config().get("dietcode", {})
            if not isinstance(raw, dict):
                raw = {}
            roadmap = raw.get("roadmap", {})
            if not isinstance(roadmap, dict):
                roadmap = {}
            stale_days = roadmap.get("stale_checkpoint_days", 7)
            try:
                stale_days = int(stale_days)
            except (TypeError, ValueError):
                stale_days = 7
            return cls(
                enabled=bool(roadmap.get("enabled", True)),
                auto_install_skills=bool(roadmap.get("auto_install_skills", True)),
                nudge_on_roadmap_write=bool(roadmap.get("nudge_on_roadmap_write", True)),
                progress_enabled=bool(roadmap.get("progress_enabled", True)),
                stale_checkpoint_days=max(1, stale_days),
                warn_on_stale_before_complete=bool(roadmap.get("warn_on_stale_before_complete", True)),
                block_kanban_on_invalid_schema=bool(roadmap.get("block_kanban_on_invalid_schema", False)),
                block_kanban_on_validation_pending=bool(roadmap.get("block_kanban_on_validation_pending", True)),
                evidence_cache_ttl_seconds=max(0.0, float(roadmap.get("evidence_cache_ttl_seconds", 15))),
                git_timeout_seconds=max(1.0, float(roadmap.get("git_timeout_seconds", 5))),
                heavy_scan_cache_ttl_seconds=max(0.0, float(roadmap.get("heavy_scan_cache_ttl_seconds", 60))),
            )
        except Exception:
            return cls()


def get_roadmap_config() -> RoadmapConfig:
    global _config_cache, _config_cache_at
    now = time.monotonic()
    if _config_cache is None or (now - _config_cache_at) > _CONFIG_TTL:
        _config_cache = RoadmapConfig.load()
        _config_cache_at = now
    return _config_cache


def resolve_workspace_root(explicit: Optional[str] = None) -> str:
    """Resolve the project workspace for ROADMAP.md."""
    if explicit and str(explicit).strip():
        from pathlib import Path

        return str(Path(explicit).expanduser().resolve())

    try:
        from plugins.dietcode.lib.agent.joyzoning.jsdp_harness_client import (
            resolve_workspace_root as _jz_resolve,
        )

        return _jz_resolve(explicit=None)
    except Exception:
        from pathlib import Path

        for key in ("HERMES_KANBAN_WORKSPACE", "JOYZONING_WORKSPACE_ROOT"):
            val = os.environ.get(key, "").strip()
            if val:
                return str(Path(val).expanduser().resolve())
        return str(Path.cwd().resolve())
