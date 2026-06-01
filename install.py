# -*- coding: utf-8 -*-
"""Seamless Hermes integration — config defaults and BroccoliDB runtime setup."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PLUGIN_NAME = "dietcode"
_MARKER = ".dietcode-integrated"


def plugin_root() -> Path:
    return Path(__file__).resolve().parent


def broccolidb_root() -> Path:
    return plugin_root() / "broccolidb"


def _integration_marker() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home() / "plugins" / _PLUGIN_NAME / _MARKER
    except Exception:
        return Path.home() / ".hermes" / "plugins" / _PLUGIN_NAME / _MARKER


def broccolidb_runtime_ready() -> bool:
    root = broccolidb_root()
    if not (root / "package.json").is_file():
        return False
    nm = root / "node_modules"
    return nm.is_dir() and any(nm.iterdir())


def ensure_broccolidb_runtime(*, auto_npm: bool = False, timeout: int = 300) -> dict[str, Any]:
    """Ensure node_modules exists; optionally run ``npm ci``."""
    root = broccolidb_root()
    if not (root / "package.json").is_file():
        return {"ok": False, "error": "broccolidb/package.json missing from plugin bundle"}

    if broccolidb_runtime_ready():
        return {"ok": True, "root": str(root), "action": "ready"}

    if not auto_npm or not shutil.which("npm"):
        return {
            "ok": False,
            "root": str(root),
            "action": "npm_ci_required",
            "hint": f"cd {root} && npm ci",
        }

    try:
        proc = subprocess.run(
            ["npm", "ci"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "1"},
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:500]
            return {"ok": False, "action": "npm_ci_failed", "error": err or f"exit {proc.returncode}"}
        return {"ok": True, "root": str(root), "action": "npm_ci"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "action": "npm_ci_timeout", "error": f"npm ci exceeded {timeout}s"}
    except OSError as exc:
        return {"ok": False, "action": "npm_ci_error", "error": str(exc)}


def apply_seamless_defaults(*, save: bool = True) -> dict[str, Any]:
    """Merge DietCode-friendly defaults into the active Hermes config."""
    try:
        from hermes_cli.config import load_config, save_config
    except ImportError:
        return {"ok": False, "error": "hermes_cli not available"}

    config = load_config()
    changed: list[str] = []

    plugins_cfg = config.setdefault("plugins", {})
    if not isinstance(plugins_cfg, dict):
        plugins_cfg = {}
        config["plugins"] = plugins_cfg

    enabled = plugins_cfg.get("enabled")
    if enabled is None:
        enabled = []
    if not isinstance(enabled, list):
        enabled = []
    enabled_set = set(enabled)
    if _PLUGIN_NAME not in enabled_set:
        enabled_set.add(_PLUGIN_NAME)
        plugins_cfg["enabled"] = sorted(enabled_set)
        changed.append("plugins.enabled")

    disabled = plugins_cfg.get("disabled") or []
    if isinstance(disabled, list) and _PLUGIN_NAME in disabled:
        disabled = [x for x in disabled if x != _PLUGIN_NAME]
        plugins_cfg["disabled"] = disabled
        changed.append("plugins.disabled")

    toolsets = config.get("toolsets")
    if toolsets is None:
        toolsets = ["hermes-cli"]
    if not isinstance(toolsets, list):
        toolsets = ["hermes-cli"]
    if _PLUGIN_NAME not in toolsets:
        toolsets = list(toolsets) + [_PLUGIN_NAME]
        config["toolsets"] = toolsets
        changed.append("toolsets")

    jz = config.setdefault("joyzoning", {})
    if isinstance(jz, dict):
        gov = jz.setdefault("governance", {})
        if isinstance(gov, dict) and "enabled" not in gov:
            gov["enabled"] = True
            changed.append("joyzoning.governance.enabled")

    if save and changed:
        save_config(config)
        logger.info("DietCode: applied seamless defaults (%s)", ", ".join(changed))

    try:
        _integration_marker().write_text("ok\n", encoding="utf-8")
    except OSError:
        pass

    return {"ok": True, "changed": changed, "saved": bool(save and changed)}


def run_install_wizard(*, auto_npm: bool = True) -> dict[str, Any]:
    """CLI / drag-and-drop installer — config + optional npm ci."""
    cfg = apply_seamless_defaults(save=True)
    runtime = ensure_broccolidb_runtime(auto_npm=auto_npm)
    return {"config": cfg, "broccolidb": runtime}


if __name__ == "__main__":
    import json

    result = run_install_wizard(auto_npm="--skip-npm" not in __import__("sys").argv)
    print(json.dumps(result, indent=2))
