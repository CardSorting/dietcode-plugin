# -*- coding: utf-8 -*-
"""Phase 7B kernel progress UX tests."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import time
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

import plugins.dietcode.lib.agent.kernel_progress as progress  # noqa: E402
import plugins.dietcode.lib.agent.kernel_progress_ux as ux  # noqa: E402
import plugins.dietcode.lib.tools.kernel_bridge_tools as kernel_tools  # noqa: E402
from plugins.dietcode.lib.agent.kernel_bridge_client import KernelBridgeConfig  # noqa: E402


class KernelProgressUxTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.session = Path(self._tmpdir.name) / "session"
        self.session.mkdir(parents=True)
        progress._stall_emitted_for.clear()
        ux._last_heartbeat_summary.clear()
        self._patch_session = mock.patch.object(progress, "session_dir", return_value=self.session)
        self._patch_session.start()

    def tearDown(self) -> None:
        progress.end_operation()
        self._patch_session.stop()
        self._tmpdir.cleanup()

    def _read_events(self) -> list[dict]:
        path = self.session / "kernel-progress.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_immediate_operation_acknowledgement(self) -> None:
        tracker = progress.start_operation(action="patch", path="src/foo.py", workspace_root="/tmp/p")
        self.assertEqual(tracker.last_phase, progress.PHASE_BRIDGE_PREFLIGHT)
        events = self._read_events()
        self.assertGreaterEqual(len(events), 1)
        self.assertEqual(events[0]["phase"], progress.PHASE_OPERATION_ACCEPTED)
        self.assertEqual(events[0]["status"], "accepted")
        self.assertIn("operation_id", events[0])
        self.assertIn("phase_sequence", events[0])
        self.assertIn("next_phase_hint", events[0])
        self.assertLess(int(events[0].get("elapsed_ms") or 0), 100)

    def test_mutation_preview_builder(self) -> None:
        patch = "--- a/src/foo.py\n+++ b/src/foo.py\n@@\n+x\n"
        preview = ux.build_mutation_preview(
            path="src/foo.py",
            patch_text=patch,
            task_id="task-1",
            verify_command="./verify.sh",
        )
        self.assertEqual(preview["files_affected"], 1)
        self.assertGreater(preview["patch_bytes"], 0)
        self.assertEqual(preview["taskId"], "task-1")
        self.assertIn("verify.sh", preview["human_summary"])

    def test_compact_watch_line(self) -> None:
        line = ux.compact_watch_line({
            "action": "patch",
            "operation_id": "op_abcd1234ef56",
            "phase": "patch.apply",
            "path": "src/foo.py",
            "elapsed_ms": 12000,
            "next_phase_hint": "next: journal.recording",
        })
        self.assertIn("PATCH", line)
        self.assertIn("applying", line)
        self.assertIn("src/foo.py", line)
        self.assertIn("12s", line)

    def test_heartbeat_coalescing(self) -> None:
        self.assertTrue(ux.should_emit_heartbeat("op_test", "still verifying... (5s)"))
        self.assertFalse(ux.should_emit_heartbeat("op_test", "still verifying... (5s)"))
        self.assertTrue(ux.should_emit_heartbeat("op_test", "still verifying... (9s)"))
        ux.clear_heartbeat_coalesce("op_test")

    def test_stall_waiting_reason(self) -> None:
        reason = ux.stall_waiting_reason("verify.running")
        self.assertIn("verify", reason.lower())
        retry = ux.stall_waiting_reason("coherence.anchor_refresh", attempt=2)
        self.assertIn("retry 2", retry)

    def test_run_duration_tiers(self) -> None:
        tier = ux.run_duration_tier(125_000)
        self.assertEqual(tier["run_tier"], "very_long_running")
        self.assertIn("timeline", tier["suggested_diagnostic"])

    def test_ux_perf_metrics_from_events(self) -> None:
        events = [
            {"phase": "operation.accepted", "elapsed_ms": 0, "ts_mono": 1.0},
            {"phase": "bridge.preflight", "elapsed_ms": 5, "ts_mono": 1.01},
            {"phase": "patch.apply", "elapsed_ms": 4000, "ts_mono": 8.0},
        ]
        metrics = ux.compute_operation_ux_metrics(events)
        self.assertEqual(metrics["time_to_first_feedback_ms"], 0)
        self.assertEqual(metrics["time_to_first_progress_ms"], 5)
        self.assertGreater(metrics["total_silent_window_ms"], 0)

    def test_tool_result_includes_acknowledgement(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True)
        receipt = {"ok": True, "action": "status", "workspace_root": "/tmp/p"}
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch(
                "plugins.dietcode.lib.tools.kernel_bridge_tools._bridge_client"
            ) as mock_client:
                kbc = mock_client.return_value
                kbc.KernelBridgeConfig.load.return_value = cfg
                kbc.workspace_status.return_value = receipt
                out = json.loads(kernel_tools.dietcode_kernel(action="status"))
        self.assertIn("_kernel_acknowledgement", out)
        self.assertEqual(out["_kernel_acknowledgement"]["status"], "accepted")
        self.assertIn("operation_id", out["_kernel_acknowledgement"])

    def test_tracker_emits_heartbeat_during_slow_phase(self) -> None:
        tracker = progress.KernelProgressTracker(action="verify")
        tracker.command = "./verify.sh"
        progress._local.tracker = tracker
        tracker.emit(progress.PHASE_VERIFY_RUNNING, command="./verify.sh")
        time.sleep(0.05)
        tracker._stop_heartbeat()
        current_path = self.session / "kernel-progress-current.json"
        self.assertTrue(current_path.is_file())
        snap = json.loads(current_path.read_text())
        self.assertIn(snap.get("phase"), {progress.PHASE_VERIFY_RUNNING, progress.PHASE_HEARTBEAT})


if __name__ == "__main__":
    unittest.main()
