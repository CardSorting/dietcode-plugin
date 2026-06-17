"""Roadmap tool boundary parity with codemarie RoadmapToolHandler."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def _bootstrap_plugins_namespace() -> None:
    bootstrap_path = _PLUGIN_ROOT / "_bootstrap.py"
    spec = importlib.util.spec_from_file_location("dietcode_bootstrap", bootstrap_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    loaded_name = "hermes_plugins.dietcode"
    loaded = types.ModuleType(loaded_name)
    loaded.__path__ = [str(_PLUGIN_ROOT)]  # type: ignore[attr-defined]
    sys.modules[loaded_name] = loaded
    mod.ensure_namespace(loaded_name)

    # Hermes tools.registry is only needed at import time for registration side effects.
    registry_stub = types.SimpleNamespace(register=lambda **_: None)
    tools_pkg = types.ModuleType("tools")
    registry_mod = types.ModuleType("tools.registry")
    registry_mod.registry = registry_stub  # type: ignore[attr-defined]
    registry_mod.tool_error = lambda msg: msg  # type: ignore[attr-defined]
    sys.modules["tools"] = tools_pkg
    sys.modules["tools.registry"] = registry_mod


_bootstrap_plugins_namespace()

from plugins.dietcode.lib.tools.roadmap_tools import (
    _normalize_action,
    roadmap,
    roadmap_checkpoint,
)


class TestRoadmapActionNormalization(unittest.TestCase):
    def test_hyphen_aliases(self) -> None:
        self.assertEqual(_normalize_action("explain-gate"), "explain_gate")
        self.assertEqual(_normalize_action("explain-stale"), "explain_stale")

    def test_default_guide(self) -> None:
        with patch("plugins.dietcode.lib.tools.roadmap_tools._dispatch") as dispatch:
            dispatch.return_value = {"action": "guide", "ok": True}
            roadmap()
            dispatch.assert_called_once()
            self.assertEqual(dispatch.call_args.args[0], "guide")

    def test_default_checkpoint_alias(self) -> None:
        with patch("plugins.dietcode.lib.tools.roadmap_tools._dispatch") as dispatch:
            dispatch.return_value = {"action": "checkpoint", "ok": True}
            roadmap_checkpoint()
            dispatch.assert_called_once()
            self.assertEqual(dispatch.call_args.args[0], "checkpoint")

    def test_explain_gate_hyphen_action(self) -> None:
        with patch("plugins.dietcode.lib.tools.roadmap_tools._dispatch") as dispatch:
            dispatch.return_value = {"action": "explain_gate", "ok": True}
            raw = roadmap(action="explain-gate")
            payload = json.loads(raw)
            self.assertTrue(payload.get("ok"))
            self.assertEqual(dispatch.call_args.args[0], "explain_gate")

    def test_task_progress_emitted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with patch("plugins.dietcode.lib.tools.roadmap_tools._dispatch") as dispatch:
                dispatch.return_value = {"action": "guide", "ok": True, "phase": "bootstrap"}
                with patch(
                    "plugins.dietcode.lib.agent.roadmap.config.get_roadmap_config"
                ) as cfg:
                    cfg.return_value.progress_enabled = True
                    with patch(
                        "plugins.dietcode.lib.agent.roadmap.progress.emit_progress"
                    ) as emit:
                        roadmap(action="guide", task_progress="filled section 2", workspace=tmp)
                        emit.assert_called_once()
                        self.assertEqual(emit.call_args.args[0], "roadmap.task_progress")
                        self.assertEqual(
                            emit.call_args.kwargs["payload"]["task_progress"],
                            "filled section 2",
                        )


if __name__ == "__main__":
    unittest.main()
