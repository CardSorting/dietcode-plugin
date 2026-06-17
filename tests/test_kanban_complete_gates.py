"""Kanban complete gate pipeline unit tests."""
from __future__ import annotations

import importlib.util
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


class KanbanCompleteGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bootstrap()

    def test_pipeline_stops_at_first_joyzoning_block(self) -> None:
        from plugins.dietcode.lib.agent.gates import kanban_complete as gates

        with patch.object(gates, "_eval_joyzoning", return_value=gates.GateLayer("joyzoning", False, message="jz block")):
            with patch.object(gates, "_eval_roadmap") as roadmap_mock:
                with patch.object(gates, "_eval_quality") as quality_mock:
                    result = gates.evaluate_kanban_complete_gates("scope-a")
        self.assertFalse(result.allowed)
        self.assertEqual(result.block_message, "jz block")
        roadmap_mock.assert_not_called()
        quality_mock.assert_not_called()

    def test_pipeline_aggregates_all_layers_when_open(self) -> None:
        from plugins.dietcode.lib.agent.gates import kanban_complete as gates

        with patch.object(gates, "_eval_joyzoning", return_value=gates.GateLayer("joyzoning", True)):
            with patch.object(gates, "_eval_roadmap", return_value=gates.GateLayer("roadmap", True)):
                with patch.object(gates, "_eval_quality", return_value=gates.GateLayer("quality", True)):
                    result = gates.evaluate_kanban_complete_gates("scope-a")
        self.assertTrue(result.allowed)
        self.assertIsNone(result.block_message)
        self.assertEqual(len(result.layers), 3)

    def test_pre_tool_call_block_delegates_to_pipeline(self) -> None:
        cg_path = _PLUGIN_ROOT / "lib/agent/joyzoning/convergence_gate.py"
        spec = importlib.util.spec_from_file_location("convergence_gate_test", cg_path)
        assert spec is not None and spec.loader is not None
        cg_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cg_mod)

        with patch(
            "plugins.dietcode.lib.agent.gates.kanban_complete.first_block_message",
            return_value="blocked",
        ):
            block = cg_mod.pre_tool_call_block(tool_name="kanban_complete", args={"task_id": "t1"})
        self.assertIsNotNone(block)
        self.assertEqual(block.get("action"), "block")
        self.assertEqual(block.get("message"), "blocked")

    def test_hook_registry_declares_all_chains(self) -> None:
        from plugins.dietcode.lib.runtime.hook_registry import HOOK_CHAINS

        self.assertIn("on_session_start", HOOK_CHAINS)
        self.assertIn("post_tool_call", HOOK_CHAINS)
        self.assertIn("audit_hooks", HOOK_CHAINS["post_tool_call"][-1][0])


if __name__ == "__main__":
    unittest.main()
