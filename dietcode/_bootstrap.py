# -*- coding: utf-8 -*-
"""Bootstrap ``plugins.dietcode`` imports for drag-and-drop Hermes installs.

Hermes directory plugins load as ``hermes_plugins.<name>``, but DietCode source
uses absolute imports under ``plugins.dietcode.*``. This module aliases the
loaded plugin directory onto ``plugins.dietcode`` before any other plugin code
runs.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

_CANONICAL = "plugins.dietcode"


def ensure_namespace(loaded_name: str) -> None:
    """Map the on-disk plugin tree to ``plugins.dietcode`` (idempotent)."""
    plugin_dir = Path(__file__).resolve().parent
    plugins_dir = plugin_dir.parent

    existing = sys.modules.get(_CANONICAL)
    if existing is not None:
        existing_path = getattr(existing, "__path__", None)
        if existing_path and str(plugin_dir) in [str(p) for p in existing_path]:
            return

    if "plugins" not in sys.modules:
        plugins_pkg = types.ModuleType("plugins")
        plugins_pkg.__path__ = [str(plugins_dir)]  # type: ignore[attr-defined]
        plugins_pkg.__package__ = "plugins"
        sys.modules["plugins"] = plugins_pkg

    loaded = sys.modules.get(loaded_name)
    if loaded is None:
        return

    loaded.__package__ = _CANONICAL
    loaded.__path__ = [str(plugin_dir)]  # type: ignore[attr-defined]
    sys.modules[_CANONICAL] = loaded
