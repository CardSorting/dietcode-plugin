"""LUMI mem_* alias boundary tests."""
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


class MemToolsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bootstrap()

    def test_mem_context_requires_path_or_task(self) -> None:
        from plugins.dietcode.lib.tools.mem_tools import mem_context

        out = mem_context()
        self.assertIn("error", out)

    def test_mem_context_uses_context_graph_for_path(self) -> None:
        from plugins.dietcode.lib.tools import mem_tools

        payload = json.dumps(
            {
                "success": True,
                "connections": [{"path": "src/a.ts", "weight": 3}],
            }
        )
        with patch.object(mem_tools, "_rpc", return_value=payload) as rpc:
            raw = mem_tools.mem_context(path="src/foo.ts")
            rpc.assert_called_once_with(
                "get_context_graph",
                {"path": "src/foo.ts", "limit": 50},
                flush=False,
            )
            body = json.loads(raw)
            self.assertIn("src/a.ts", body["message"])

    def test_mem_centrality_requires_id(self) -> None:
        from plugins.dietcode.lib.tools.mem_tools import mem_centrality

        self.assertIn("error", mem_centrality())

    def test_mem_hubs_formats_output(self) -> None:
        from plugins.dietcode.lib.tools import mem_tools

        payload = json.dumps(
            {
                "success": True,
                "hubs": [{"kbId": "k1", "score": 5, "content": "hello"}],
            }
        )
        with patch.object(mem_tools, "_rpc", return_value=payload):
            raw = mem_tools.mem_hubs(limit=3)
            body = json.loads(raw)
            self.assertIn("k1", body["message"])
            self.assertIn("hello", body["message"])

    def test_mem_forecast_requires_source(self) -> None:
        from plugins.dietcode.lib.tools.mem_tools import mem_forecast

        self.assertIn("error", mem_forecast())

    def test_mem_claim_requires_resource(self) -> None:
        from plugins.dietcode.lib.tools.mem_tools import mem_claim

        self.assertIn("error", mem_claim())

    def test_mem_changelog_requires_refs(self) -> None:
        from plugins.dietcode.lib.tools.mem_tools import mem_changelog

        self.assertIn("error", mem_changelog(baseId="abc"))


if __name__ == "__main__":
    unittest.main()
