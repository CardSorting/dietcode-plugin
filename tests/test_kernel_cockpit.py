# -*- coding: utf-8 -*-
"""Phase 7C kernel cockpit tests."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

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


_bootstrap_plugins_namespace()

import plugins.dietcode.lib.agent.kernel_cockpit as cockpit  # noqa: E402
import plugins.dietcode.lib.agent.kernel_progress as progress  # noqa: E402
import plugins.dietcode.lib.agent.kernel_progress_ux as ux  # noqa: E402
from plugins.dietcode.lib.agent.kernel_bridge_client import KernelBridgeConfig  # noqa: E402


class KernelCockpitTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.session = Path(self._tmpdir.name) / "session"
        self.session.mkdir(parents=True)
        progress._stall_emitted_for.clear()
        self._patch_session = mock.patch.object(progress, "session_dir", return_value=self.session)
        self._patch_session.start()

    def tearDown(self) -> None:
        progress.end_operation()
        self._patch_session.stop()
        self._tmpdir.cleanup()

    def test_normalize_operation_states(self) -> None:
        self.assertEqual(
            cockpit.normalize_operation_state(phase="patch.validate"),
            cockpit.STATE_VALIDATING,
        )
        self.assertEqual(
            cockpit.normalize_operation_state(phase="verify.running"),
            cockpit.STATE_VERIFYING,
        )
        self.assertEqual(
            cockpit.normalize_operation_state(phase="done"),
            cockpit.STATE_COMPLETE,
        )
        self.assertEqual(cockpit.normalize_operation_state(phase="error"), cockpit.STATE_FAILED)
        self.assertEqual(cockpit.normalize_operation_state(phase="x", stale=True), cockpit.STATE_STALLED)

    def test_ascii_symbol_fallback(self) -> None:
        with mock.patch.dict(os.environ, {"DIETCODE_ASCII_ONLY": "1"}):
            self.assertEqual(cockpit.symbol("complete"), "OK")
            self.assertEqual(cockpit.symbol("failed"), "FAIL")

    def test_recommend_next_action_single(self) -> None:
        rec = cockpit.recommend_next_action(operation_state=cockpit.STATE_VERIFYING)
        self.assertEqual(rec["action"], cockpit.ACTION_WAIT)
        rec_fail = cockpit.recommend_next_action(
            operation_state=cockpit.STATE_FAILED,
            last_error={"ok": False, "last_error": {"safe_to_retry": True, "retry_command": "retry"}},
        )
        self.assertEqual(rec_fail["action"], cockpit.ACTION_RETRY)

    def test_cockpit_report_structure(self) -> None:
        gate = {
            "bridge_enabled": True,
            "patch_allowed": False,
            "mutations_enabled": False,
            "socket_ready": True,
            "token_ready": True,
            "workspace_safe_for_mutation": True,
            "resolved_workspace_root": "/tmp/project",
        }
        router = {"raw_write_policy": "warn", "would_block_raw_writes": False, "would_warn_on_raw_write": True}
        with mock.patch.object(cockpit, "_gate_context", return_value={"config": KernelBridgeConfig(), "gate": gate, "router": router}):
            payload = cockpit.build_cockpit_report()
        self.assertIn("recommended_next_action", payload)
        self.assertEqual(payload["recommended_next_action"]["action"], cockpit.ACTION_ENABLE_MUTATIONS)
        text = cockpit.format_cockpit_report()
        self.assertIn("Kernel cockpit", text)
        self.assertIn("Next action:", text)

    def test_ux_budget_enrichment(self) -> None:
        events = [
            {"phase": "operation.accepted", "elapsed_ms": 0, "ts_mono": 1.0, "phase_duration_ms": 0},
            {"phase": "patch.validate", "elapsed_ms": 40, "ts_mono": 1.04, "phase_duration_ms": 40},
            {"phase": "done", "elapsed_ms": 100, "ts_mono": 1.1, "phase_duration_ms": 60},
        ]
        base = ux.compute_operation_ux_metrics(events)
        enriched = cockpit.enrich_ux_metrics(base, events)
        self.assertTrue(enriched["ux_budgets"]["ack_under_100ms"])
        self.assertTrue(enriched["ux_budgets"]["ux_budget_passed"])
        self.assertEqual(enriched["total_operation_duration_ms"], 100)

    def test_progress_report_includes_next_action(self) -> None:
        tracker = progress.start_operation(action="status")
        tracker.finish(ok=True)
        text = progress.format_progress_report()
        self.assertIn("next action:", text)

    def test_emit_includes_operation_state(self) -> None:
        tracker = progress.KernelProgressTracker(action="patch", path="a.py")
        event = tracker.emit(progress.PHASE_PATCH_VALIDATE)
        self.assertEqual(event.get("operation_state"), cockpit.STATE_VALIDATING)
        self.assertIn("recommended_next_action", event)


if __name__ == "__main__":
    unittest.main()
