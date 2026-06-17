"""Project map tool boundary tests."""
from __future__ import annotations

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def _bootstrap() -> None:
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
    registry_stub = types.SimpleNamespace(register=lambda **_: None)
    tools_pkg = types.ModuleType("tools")
    registry_mod = types.ModuleType("tools.registry")
    registry_mod.registry = registry_stub  # type: ignore[attr-defined]
    registry_mod.tool_error = lambda msg: json.dumps({"error": msg})  # type: ignore[attr-defined]
    sys.modules["tools"] = tools_pkg
    sys.modules["tools.registry"] = registry_mod


class ProjectMapToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bootstrap()

    def test_requires_at_least_one_target(self) -> None:
        from plugins.dietcode.lib.tools.project_map_tools import project_map

        out = project_map()
        self.assertIn("error", out)

    def test_delegates_to_standalone_script(self) -> None:
        from plugins.dietcode.lib.tools import project_map_tools

        payload = {
            "success": True,
            "title": "Project Map",
            "startingPoint": [{"path": "src/foo.ts", "reason": "main", "weight": 1}],
        }
        with patch.object(project_map_tools, "run_standalone_script", return_value=json.dumps(payload)) as run:
            raw = project_map_tools.project_map(path="src/foo.ts")
            self.assertEqual(json.loads(raw)["title"], "Project Map")
            run.assert_called_once()
            self.assertIn("buildProjectMap", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
