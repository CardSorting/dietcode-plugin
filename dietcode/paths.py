# -*- coding: utf-8 -*-
"""BroccoliDB root resolution — single source for DietCode plugin + tools."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

_BROCCOLIDB_DIRNAME = "broccolidb"


def is_valid_broccolidb_root(path: Path | str) -> bool:
    """Return True when *path* looks like a BroccoliDB checkout."""
    root = Path(path).expanduser()
    return (root / "package.json").is_file() and (root / "core").is_dir()


def _plugin_broccolidb_candidates() -> list[Path]:
    """Plugin install fallback — canonical tree is repo-root ``broccolidb/``."""
    if os.environ.get("HERMES_BROCCOLIDB_DISABLE_PLUGIN_FALLBACK", "").strip().lower() in {
        "1", "true", "yes", "on",
    }:
        return []
    out: list[Path] = []
    try:
        from hermes_cli.plugins import get_bundled_plugins_dir

        out.append(get_bundled_plugins_dir() / "dietcode" / _BROCCOLIDB_DIRNAME)
    except Exception:
        pass
    try:
        from hermes_constants import get_hermes_home

        out.append(get_hermes_home() / "plugins" / "dietcode" / _BROCCOLIDB_DIRNAME)
    except Exception:
        pass
    return out


def resolve_broccolidb_root() -> Optional[str]:
    """Locate broccolidb/ for the active process (workspace-aware).

    Resolution order:
      1. ``HERMES_BROCCOLIDB_ROOT`` env (set by kanban dispatcher)
      2. Bundled / user DietCode plugin directories
      3. ``kanban.broccolidb.root`` in config.yaml
      4. Walk parents from ``HERMES_KANBAN_WORKSPACE`` then ``cwd``
      5. Relative ``broccolidb/`` when cwd already contains it
    """
    env_root = os.environ.get("HERMES_BROCCOLIDB_ROOT", "").strip()
    if env_root:
        candidate = Path(env_root).expanduser()
        if is_valid_broccolidb_root(candidate):
            return str(candidate.resolve())

    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        kanban_cfg = cfg.get("kanban", {}) if isinstance(cfg, dict) else {}
        bdb = kanban_cfg.get("broccolidb", {})
        if isinstance(bdb, dict):
            cfg_root = str(bdb.get("root") or "").strip()
            if cfg_root:
                candidate = Path(cfg_root).expanduser()
                if not candidate.is_absolute():
                    candidate = Path.cwd() / candidate
                if is_valid_broccolidb_root(candidate):
                    return str(candidate.resolve())
    except Exception:
        pass

    # Pip / standalone package: broccolidb/ ships beside this module.
    package_bdb = Path(__file__).resolve().parent / _BROCCOLIDB_DIRNAME
    if is_valid_broccolidb_root(package_bdb):
        return str(package_bdb.resolve())

    seeds: list[Path] = []
    ws = os.environ.get("HERMES_KANBAN_WORKSPACE", "").strip()
    if ws:
        seeds.append(Path(ws))
    seeds.append(Path.cwd())

    seen: set[str] = set()
    for seed in seeds:
        try:
            resolved_seed = seed.resolve()
        except OSError:
            continue
        for parent in [resolved_seed, *resolved_seed.parents]:
            key = str(parent)
            if key in seen:
                continue
            seen.add(key)
            candidate = parent / _BROCCOLIDB_DIRNAME
            if is_valid_broccolidb_root(candidate):
                return str(candidate.resolve())

    for plugin_bdb in _plugin_broccolidb_candidates():
        if is_valid_broccolidb_root(plugin_bdb):
            return str(plugin_bdb.resolve())

    rel = Path(_BROCCOLIDB_DIRNAME)
    if is_valid_broccolidb_root(rel):
        return str(rel.resolve())
    return None
