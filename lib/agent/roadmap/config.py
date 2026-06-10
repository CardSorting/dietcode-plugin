"""Roadmap checkpoint configuration."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
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
    block_kanban_on_bootstrap_incomplete: bool = False
    block_writes_outside_workspace: bool = True
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
                block_kanban_on_bootstrap_incomplete=bool(
                    roadmap.get("block_kanban_on_bootstrap_incomplete", False)
                ),
                block_writes_outside_workspace=bool(roadmap.get("block_writes_outside_workspace", True)),
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


class RoadmapWorkspaceError(ValueError):
    """Project workspace for ROADMAP.md could not be resolved safely."""


def _reject_quarantined(root: str) -> None:
    try:
        from plugins.dietcode.lib.kernel_workspace import is_quarantined_root
    except ImportError:
        return
    if is_quarantined_root(root):
        raise RoadmapWorkspaceError(
            f"ROADMAP.md belongs in your Hermes project workspace, not the DietCode plugin tree: {root}. "
            "Set kanban.workspace or HERMES_KANBAN_WORKSPACE to your project root."
        )


def _candidate_from_env() -> tuple[Optional[str], str]:
    for key in (
        "HERMES_KANBAN_WORKSPACE",
        "JOYZONING_WORKSPACE_ROOT",
        "DIETCODE_WORKSPACE_ROOT",
    ):
        val = os.environ.get(key, "").strip()
        if not val:
            continue
        root = str(Path(val).expanduser().resolve())
        try:
            from plugins.dietcode.lib.kernel_workspace import is_quarantined_root

            if is_quarantined_root(root):
                continue
        except ImportError:
            pass
        return root, key
    return None, "env:unset"


def _candidate_from_kanban_config() -> tuple[Optional[str], str]:
    try:
        from hermes_cli.config import load_config

        raw = load_config()
        if not isinstance(raw, dict):
            return None, "kanban:unset"
        kanban = raw.get("kanban", {})
        if not isinstance(kanban, dict):
            return None, "kanban:unset"
        ws = str(kanban.get("workspace") or kanban.get("workspace_root") or "").strip()
        if not ws:
            return None, "kanban:unset"
        root = str(Path(ws).expanduser().resolve())
        try:
            from plugins.dietcode.lib.kernel_workspace import is_quarantined_root

            if is_quarantined_root(root):
                return None, "kanban:quarantined"
        except ImportError:
            pass
        return root, "kanban.workspace"
    except Exception:
        return None, "kanban:unset"


def resolve_workspace(*, explicit: Optional[str] = None) -> tuple[str, str]:
    """Resolve the user project workspace for ROADMAP.md (never plugin/kernel trees).

    Returns ``(absolute_path, resolution_source)``.
    """
    if explicit and str(explicit).strip():
        root = str(Path(explicit).expanduser().resolve())
        _reject_quarantined(root)
        return root, "explicit"

    try:
        from plugins.dietcode.lib.kernel_workspace import (
            is_quarantined_root,
            resolve_workspace_root as resolve_kernel_workspace,
        )

        report = resolve_kernel_workspace()
        candidate = report.resolved_workspace_root
        if candidate and not is_quarantined_root(candidate):
            return candidate, report.resolution_detail
    except Exception:
        pass

    try:
        from plugins.dietcode.lib.agent.joyzoning.jsdp_harness_client import (
            resolve_workspace_root as _jz_resolve,
        )

        jz_root = _jz_resolve(explicit=None)
        if jz_root:
            try:
                from plugins.dietcode.lib.kernel_workspace import is_quarantined_root

                if not is_quarantined_root(jz_root):
                    return jz_root, "joyzoning.jsdp"
            except ImportError:
                return jz_root, "joyzoning.jsdp"
    except Exception:
        pass

    env_root, env_source = _candidate_from_env()
    if env_root:
        return env_root, env_source

    kanban_root, kanban_source = _candidate_from_kanban_config()
    if kanban_root:
        return kanban_root, kanban_source

    cwd = str(Path.cwd().resolve())
    try:
        from plugins.dietcode.lib.kernel_workspace import is_quarantined_root

        if not is_quarantined_root(cwd):
            return cwd, "cwd"
    except ImportError:
        return cwd, "cwd"

    raise RoadmapWorkspaceError(
        "Could not resolve a project workspace for ROADMAP.md. "
        "Set kanban.workspace in ~/.hermes/config.yaml or export HERMES_KANBAN_WORKSPACE "
        "to your project root (not ~/.hermes/plugins/dietcode)."
    )


def resolve_workspace_root(explicit: Optional[str] = None) -> str:
    """Resolve the project workspace for ROADMAP.md."""
    return resolve_workspace(explicit=explicit)[0]
