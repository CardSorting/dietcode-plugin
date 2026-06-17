"""Runtime features and tool discovery unit tests."""
from __future__ import annotations

import unittest
from unittest.mock import patch

from tests.support import bootstrap_plugins_namespace


class RuntimeFeaturesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bootstrap_plugins_namespace()

    def test_features_snapshot_keys(self) -> None:
        from plugins.dietcode.lib.agent.features import features_snapshot

        snap = features_snapshot()
        self.assertEqual(
            set(snap.keys()),
            {
                "joyzoning",
                "roadmap",
                "governance",
                "completion_gate",
                "jsdp",
                "joyzoning_journal",
            },
        )

    def test_config_hub_snapshot(self) -> None:
        from plugins.dietcode.lib.agent.config_hub import runtime_config_snapshot

        snap = runtime_config_snapshot()
        self.assertIn("joyzoning", snap)
        self.assertIn("roadmap", snap)
        self.assertIn("completion_gate", snap)

    def test_self_check_passes(self) -> None:
        from plugins.dietcode.lib.agent.self_check import run_self_check

        result = run_self_check()
        self.assertTrue(result["ok"])
        self.assertEqual(result["failures"], [])

    def test_command_registry_validates(self) -> None:
        from plugins.dietcode.lib.runtime.command_registry import validate_command_registry

        self.assertEqual(validate_command_registry(), [])

    def test_hook_guard_skips_disabled_feature(self) -> None:
        from plugins.dietcode.lib.runtime.hook_guards import when_enabled

        calls: list[str] = []

        @when_enabled("joyzoning")
        def _handler() -> str:
            calls.append("ran")
            return "ok"

        with patch("plugins.dietcode.lib.runtime.hook_guards._feature_active", return_value=False):
            self.assertIsNone(_handler())
        self.assertEqual(calls, [])

    def test_quality_signal_registry(self) -> None:
        from plugins.dietcode.lib.agent.audit.quality_signals import (
            QUALITY_CAPTURE_TOOLS,
            is_quality_capture_tool,
        )

        self.assertIn("joyzoning", QUALITY_CAPTURE_TOOLS)
        self.assertTrue(is_quality_capture_tool("mutation_verify"))
        self.assertFalse(is_quality_capture_tool("read_file"))

    def test_discover_tool_modules_skips_bridge(self) -> None:
        from plugins.dietcode.tools_loader import discover_tool_modules

        modules = discover_tool_modules()
        self.assertIn("plugins.dietcode.lib.tools.broccolidb", modules)
        self.assertNotIn("plugins.dietcode.lib.tools.kanban_broccolidb_bridge", modules)
        self.assertNotIn("plugins.dietcode.lib.tools.mem_tools", modules)
        self.assertEqual(modules[0], "plugins.dietcode.lib.tools.broccolidb")

    def test_hook_registry_validates(self) -> None:
        from plugins.dietcode.lib.runtime.hook_registry import validate_hook_registry

        self.assertEqual(validate_hook_registry(), [])

    def test_runtime_snapshot_includes_gates(self) -> None:
        from plugins.dietcode.lib.agent.features import build_runtime_snapshot

        with patch(
            "plugins.dietcode.lib.agent.gates.kanban_complete.evaluate_kanban_complete_gates"
        ) as evaluate:
            from plugins.dietcode.lib.agent.gates.kanban_complete import (
                GateLayer,
                KanbanCompleteGateResult,
            )

            evaluate.return_value = KanbanCompleteGateResult(
                allowed=True,
                block_message=None,
                layers=(GateLayer("joyzoning", True),),
            )
            snap = build_runtime_snapshot()
        self.assertIn("features", snap)
        self.assertIn("config", snap)
        self.assertIn("gates", snap)
        self.assertTrue(snap["gates"]["kanban_complete_allowed"])


if __name__ == "__main__":
    unittest.main()
