"""Shared test bootstrap for DietCode plugin unit tests."""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def bootstrap_plugins_namespace(*, plugin_root: Path | None = None) -> None:
    root = plugin_root or _PLUGIN_ROOT
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    bootstrap_path = root / "_bootstrap.py"
    spec = importlib.util.spec_from_file_location("dietcode_bootstrap", bootstrap_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    loaded_name = "hermes_plugins.dietcode"
    loaded = types.ModuleType(loaded_name)
    loaded.__path__ = [str(root)]  # type: ignore[attr-defined]
    sys.modules[loaded_name] = loaded
    mod.ensure_namespace(loaded_name)
