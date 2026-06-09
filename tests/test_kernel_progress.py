# -*- coding: utf-8 -*-
"""Phase 6 kernel progress telemetry tests."""
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
import plugins.dietcode.lib.agent.kernel_raw_write_router as router  # noqa: E402
import plugins.dietcode.lib.tools.kernel_bridge_tools as kernel_tools  # noqa: E402
from plugins.dietcode.lib.agent.kernel_bridge_client import (  # noqa: E402
    BRIDGE_PATCH_DISABLED,
    KernelBridgeConfig,
)


class KernelProgressTests(unittest.TestCase):
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

    def _read_events(self) -> list[dict]:
        path = self.session / "kernel-progress.jsonl"
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def test_patch_success_emits_progress(self) -> None:
        receipt = {
            "ok": True,
            "action": "patch",
            "workspace_root": "/tmp/project",
            "path": "src/a.py",
            "kernel": {"mutationReceipt": {"revision": 1}},
        }
        cfg = KernelBridgeConfig(mutations_enabled=True)
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch(
                "plugins.dietcode.lib.tools.kernel_bridge_tools._bridge_client"
            ) as mock_client:
                kbc = mock_client.return_value
                kbc.KernelBridgeConfig.load.return_value = cfg
                kbc.apply_kernel_patch.return_value = receipt
                out = json.loads(
                    kernel_tools.dietcode_kernel(
                        "patch",
                        path="src/a.py",
                        unified_diff="---\n+++",
                    )
                )
        self.assertTrue(out["ok"])
        events = self._read_events()
        phases = [e["phase"] for e in events]
        self.assertIn("bridge.preflight", phases)
        self.assertIn("done", phases)
        self.assertIn("_kernel_operator_hints", out)

    def test_verify_success_emits_progress(self) -> None:
        receipt = {
            "ok": True,
            "action": "verify",
            "verify_ran": True,
            "passed": True,
            "command": "./verify.sh",
        }
        cfg = KernelBridgeConfig(mutations_enabled=True)
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch(
                "plugins.dietcode.lib.tools.kernel_bridge_tools._bridge_client"
            ) as mock_client:
                kbc = mock_client.return_value
                kbc.KernelBridgeConfig.load.return_value = cfg
                kbc.apply_kernel_verify.return_value = receipt
                out = json.loads(
                    kernel_tools.dietcode_kernel("verify", command="./verify.sh")
                )
        self.assertTrue(out["ok"])
        events = self._read_events()
        self.assertTrue(any(e["phase"] == "done" for e in events))
        self.assertEqual(events[-1]["action"], "verify")

    def test_error_phase_recorded_on_failure(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=False)
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch(
                "plugins.dietcode.lib.tools.kernel_bridge_tools._bridge_client"
            ) as mock_client:
                kbc = mock_client.return_value
                kbc.KernelBridgeConfig.load.return_value = cfg
                kbc.apply_kernel_patch.return_value = {
                    "ok": False,
                    "action": "patch",
                    "string_code": BRIDGE_PATCH_DISABLED,
                    "error": {
                        "string_code": BRIDGE_PATCH_DISABLED,
                        "message": "disabled",
                    },
                }
                out = json.loads(
                    kernel_tools.dietcode_kernel("patch", path="x.py", unified_diff="---")
                )
        self.assertFalse(out["ok"])
        events = self._read_events()
        self.assertEqual(events[-1]["phase"], "error")
        self.assertIn("_kernel_error_envelope", out)

    def test_stalled_operation_detected(self) -> None:
        stale = {
            "ts": time.time() - 30,
            "ts_mono": time.monotonic() - 30,
            "operation_id": "op_stale_test",
            "action": "patch",
            "phase": "patch.apply",
            "elapsed_ms": 30000,
            "attempt": 1,
        }
        current_path = self.session / "kernel-progress-current.json"
        current_path.write_text(json.dumps(stale), encoding="utf-8")
        health = progress.build_progress_health()
        self.assertIsNotNone(health.get("stale_progress_ms"))
        self.assertGreaterEqual(health.get("stalled_events_emitted", 0), 1)
        events = self._read_events()
        self.assertTrue(any(e.get("phase") == "bridge.progress_stalled" for e in events))

    def test_progress_handles_missing_log(self) -> None:
        tail = progress.read_progress_tail()
        self.assertTrue(tail["ok"])
        self.assertEqual(tail["count"], 0)
        current = progress.read_progress_current()
        self.assertFalse(current["ok"])
        text = progress.format_progress_report()
        self.assertIn("No kernel progress recorded", text)

    def test_progress_handles_corrupted_jsonl(self) -> None:
        log_path = self.session / "kernel-progress.jsonl"
        log_path.write_text('{"phase":"done"}\nnot-json\n{"phase":"error","string_code":"x"}\n', encoding="utf-8")
        events = progress.read_progress_lines(tolerate_corrupt=True)
        self.assertEqual(len(events), 2)
        last = progress.read_last_error()
        self.assertFalse(last["ok"])

    def test_raw_write_block_includes_actionable_hint(self) -> None:
        gate = {
            "bridge_enabled": True,
            "mutations_enabled": True,
            "workspace_safe_for_mutation": True,
            "resolved_workspace_root": "/tmp/project",
            "socket_ready": True,
            "token_ready": True,
            "patch_allowed": True,
        }
        payload = router.build_raw_write_block_payload(gate=gate)
        self.assertEqual(payload["string_code"], router.KERNEL_RAW_WRITE_BLOCKED)
        self.assertIn("preferred_command", payload)
        self.assertIn("recovery_suggestion", payload)
        self.assertIn("suggested_slash_command", payload)
        self.assertEqual(payload["preferred_tool"], "dietcode_kernel")

    def test_gate_explanation_is_accurate(self) -> None:
        gate = {
            "bridge_enabled": True,
            "mutations_enabled": False,
            "workspace_safe_for_mutation": True,
            "resolved_workspace_root": "/tmp/project",
            "socket_ready": True,
            "token_ready": True,
            "patch_allowed": False,
            "recovery_hint": "enable mutations",
        }
        cfg = KernelBridgeConfig(enabled=True, mutations_enabled=False)
        router_health = {
            "raw_write_policy": "warn",
            "would_warn_on_raw_write": False,
            "would_block_raw_writes": False,
        }
        with mock.patch(
            "plugins.dietcode.lib.agent.kernel_bridge_client.KernelBridgeConfig.load",
            return_value=cfg,
        ):
            with mock.patch(
                "plugins.dietcode.lib.agent.kernel_bridge_client.build_patch_gate_state",
                return_value=gate,
            ):
                with mock.patch(
                    "plugins.dietcode.lib.agent.kernel_raw_write_router.build_raw_write_router_health",
                    return_value=router_health,
                ):
                    payload = progress.build_gate_explanation()
                    text = progress.format_gate_explanation()
        self.assertFalse(payload["ok"])
        self.assertEqual(payload["missing_gate"], "mutations_disabled")
        closed_ids = [g["id"] for g in payload.get("closed_gates") or []]
        self.assertIn("mutations_enabled", closed_ids)
        self.assertIn("raw_write_behavior", payload)
        self.assertIn("mutations_enabled", text)


class KernelProgressPolishTests(unittest.TestCase):
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

    def _write_event(self, **fields: object) -> None:
        event = {
            "ts": time.time(),
            "ts_mono": time.monotonic(),
            "operation_id": fields.get("operation_id", "op_test"),
            "action": fields.get("action", "patch"),
            "phase": fields.get("phase", "bridge.preflight"),
            "elapsed_ms": fields.get("elapsed_ms", 0),
            "attempt": fields.get("attempt", 1),
            "path": fields.get("path"),
            "command": fields.get("command"),
        }
        event.update({k: v for k, v in fields.items() if k not in event})
        event["summary"] = progress.human_progress_summary(event)
        line = json.dumps(event)
        log = self.session / "kernel-progress.jsonl"
        with log.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
        (self.session / "kernel-progress-current.json").write_text(
            json.dumps(event, indent=2),
            encoding="utf-8",
        )

    def test_human_summary_patch_apply(self) -> None:
        summary = progress.human_progress_summary({
            "phase": "patch.apply",
            "path": "src/foo.py",
            "attempt": 2,
            "elapsed_ms": 38000,
        })
        self.assertIn("patch applying: src/foo.py", summary)
        self.assertIn("attempt 2", summary)
        self.assertIn("38s elapsed", summary)

    def test_human_summary_stalled(self) -> None:
        summary = progress.human_progress_summary({
            "phase": "bridge.progress_stalled",
            "last_phase": "coherence.anchor_refresh",
            "stalled_ms": 19000,
        })
        self.assertIn("stalled:", summary)
        self.assertIn("coherence.anchor_refresh", summary)
        self.assertIn("19s", summary)

    def test_timeline_view(self) -> None:
        op = "op_timeline_1"
        for phase, elapsed in [
            ("bridge.preflight", 0),
            ("workspace.open", 400),
            ("coherence.read", 1200),
            ("patch.validate", 3800),
            ("patch.apply", 5100),
            ("journal.recording", 7400),
            ("done", 8000),
        ]:
            self._write_event(operation_id=op, phase=phase, elapsed_ms=elapsed)
        payload = progress.build_operation_timeline(operation_id=op)
        self.assertTrue(payload["ok"])
        text = payload["timeline_text"]
        self.assertIn("[0.0s] bridge.preflight", text)
        self.assertIn("[3.8s] patch.validate", text)
        self.assertIn("[8.0s] done", text)
        report = progress.format_progress_report(timeline=True, operation_id=op)
        self.assertIn("Kernel timeline", report)

    def test_last_operations_summary(self) -> None:
        self._write_event(operation_id="op_a", action="patch", path="a.py", phase="done", elapsed_ms=5000)
        self._write_event(operation_id="op_b", action="verify", command="./verify.sh", phase="error", elapsed_ms=3000, string_code="bridge_rpc_timeout")
        payload = progress.summarize_recent_operations(count=5)
        self.assertEqual(payload["count"], 2)
        ids = [op["operation_id"] for op in payload["operations"]]
        self.assertEqual(ids[0], "op_b")
        self.assertEqual(payload["operations"][1]["status"], "success")
        report = progress.format_progress_report(last=5)
        self.assertIn("op_b", report)
        self.assertIn("bridge_rpc_timeout", report)

    def test_operation_filter_tail(self) -> None:
        self._write_event(operation_id="op_x", phase="patch.apply", path="x.py")
        self._write_event(operation_id="op_y", phase="verify.running", command="./verify.sh")
        out = progress.format_progress_report(tail=True, operation_id="op_x")
        data = json.loads(out)
        self.assertEqual(data["operation_id"], "op_x")
        self.assertEqual(len(data["events"]), 1)

    def test_error_envelope_next_action_fields(self) -> None:
        env = progress.normalize_bridge_error("bridge_socket_unavailable", "socket down")
        self.assertIn("next_action", env)
        self.assertIn("safe_to_retry", env)
        self.assertIn("retry_command", env)
        self.assertIn("diagnostic_command", env)
        self.assertTrue(env["safe_to_retry"])

    def test_silence_regression_periodic_updates(self) -> None:
        tracker = progress.KernelProgressTracker(action="patch", path="src/foo.py", operation_id="op_silence")
        interval = progress.PROGRESS_HEARTBEAT_INTERVAL_MS
        phases = ["bridge.preflight", "socket.ready", "workspace.open", "patch.validate", "patch.apply"]
        for phase in phases:
            tracker.emit(phase)
            self.assertLess(tracker.since_last_emit_ms(), interval * 2)
        progress.flush_progress_writes(force=True)
        events = progress.read_operation_events("op_silence")
        self.assertGreaterEqual(len(events), len(phases))

    def test_silence_regression_stall_without_update(self) -> None:
        tracker = progress.KernelProgressTracker(action="patch", path="src/foo.py", operation_id="op_stall")
        tracker.emit("patch.apply")
        tracker.last_emit_mono = time.monotonic() - (progress.PROGRESS_HEARTBEAT_INTERVAL_MS * 2 + 1000) / 1000
        stalled = tracker.check_stalled()
        self.assertIsNotNone(stalled)
        self.assertEqual(stalled.get("phase"), "bridge.progress_stalled")

    def test_multi_operation_robustness(self) -> None:
        t1 = progress.KernelProgressTracker(action="patch", path="a.py", operation_id="op_multi_a")
        t2 = progress.KernelProgressTracker(action="verify", operation_id="op_multi_b")
        t1.emit("bridge.preflight")
        t2.emit("bridge.preflight")
        t1.emit("patch.apply")
        t2.emit("verify.running", command="./verify.sh")
        t1.finish(ok=True)
        t2.finish(ok=True)

        current = progress.read_progress_current()
        self.assertTrue(current["ok"])
        self.assertEqual(current["current"]["operation_id"], "op_multi_b")

        tl_a = progress.build_operation_timeline(operation_id="op_multi_a")
        tl_b = progress.build_operation_timeline(operation_id="op_multi_b")
        self.assertIn("patch.apply", tl_a["timeline_text"])
        self.assertIn("verify.running", tl_b["timeline_text"])
        self.assertNotEqual(tl_a["timeline_text"], tl_b["timeline_text"])

    def test_format_progress_uses_human_summary(self) -> None:
        self._write_event(
            operation_id="op_live",
            phase="patch.apply",
            path="src/foo.py",
            attempt=2,
            elapsed_ms=38000,
        )
        report = progress.format_progress_report()
        self.assertIn("patch applying: src/foo.py", report)


if __name__ == "__main__":
    unittest.main()
