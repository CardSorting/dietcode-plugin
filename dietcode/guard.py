# -*- coding: utf-8 -*-
"""DietCode plugin presence and hook wiring checks."""
from __future__ import annotations

_DIETCODE_TRANSFORM_HOOK = "dietcode_transform_tool_result"


def is_dietcode_plugin_registered() -> bool:
    """Return True when the unified DietCode plugin registered on PluginManager."""
    try:
        from hermes_cli.plugins import get_plugin_manager

        pm = get_plugin_manager()
        return bool(getattr(pm, "_dietcode_registered", False))
    except Exception:
        return False


def dietcode_tools_in_registry() -> bool:
    """Return True when at least one expected DietCode tool is in the registry."""
    try:
        from plugins.dietcode.tools_loader import EXPECTED_DIETCODE_TOOLS
        from tools.registry import registry

        present = set(registry._tools)
        return bool(EXPECTED_DIETCODE_TOOLS & present)
    except Exception:
        return False


def dietcode_governance_hook_active() -> bool:
    """Return True when DietCode's consolidated transform_tool_result hook is registered."""
    try:
        from hermes_cli.plugins import get_plugin_manager

        pm = get_plugin_manager()
        for cb in pm._hooks.get("transform_tool_result", []):
            if getattr(cb, "__name__", "") == _DIETCODE_TRANSFORM_HOOK:
                return True
    except Exception:
        pass
    return False


def dietcode_startup_expected() -> bool:
    """Return True when config implies DietCode should be loaded at startup."""
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        if not isinstance(cfg, dict):
            return False
        toolsets = cfg.get("toolsets") or []
        plugins = cfg.get("plugins") if isinstance(cfg.get("plugins"), dict) else {}
        disabled = plugins.get("disabled") or []
        if not isinstance(toolsets, list):
            return False
        if "dietcode" not in toolsets:
            return False
        if isinstance(disabled, list) and "dietcode" in disabled:
            return False
        return True
    except Exception:
        return False
