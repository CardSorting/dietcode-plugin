# -*- coding: utf-8 -*-
"""Phase 7D kernel sonic UX tests."""
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

import plugins.dietcode.lib.agent.kernel_progress as progress  # noqa: E402
import plugins.dietcode.lib.agent.kernel_sonic as sonic  # noqa: E402


class KernelSonicTests(unittest.TestCase):
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

    def test_accept_line_format(self) -> None:
        line = sonic.build_accept_line(action="patch", path="src/foo.py")
        self.assertIn("PATCH", line)
        self.assertIn("accepted", line)
        self.assertIn("src/foo.py", line)

    def test_visual_ascii_fallback(self) -> None:
        with mock.patch.dict(os.environ, {"DIETCODE_ASCII_ONLY": "1"}):
            self.assertEqual(sonic.visual_symbol("success"), "OK")
            self.assertEqual(sonic.visual_symbol("stalled"), "STALL")

    def test_suppress_micro_phase(self) -> None:
        self.assertTrue(
            sonic.should_suppress_operator_transition(
                phase="socket.ready",
                phase_duration_ms=20,
            )
        )
        self.assertFalse(
            sonic.should_suppress_operator_transition(
                phase="patch.apply",
                phase_duration_ms=20,
            )
        )
        self.assertFalse(
            sonic.should_suppress_operator_transition(
                phase="coherence.anchor_refresh",
                phase_duration_ms=20,
            )
        )

    def test_ultra_fast_ack_emitted(self) -> None:
        tracker = progress.start_operation(action="verify", command="./verify.sh")
        current = progress.read_progress_current()
        snap = current.get("current") or {}
        self.assertEqual(snap.get("phase"), progress.PHASE_OPERATION_ACCEPTED)
        self.assertIn("accepted", str(snap.get("summary") or "").lower())
        self.assertIn("./verify.sh", str(snap.get("summary") or ""))
        self.assertLess(int(snap.get("elapsed_ms") or 0), 50)
        tracker.finish(ok=True)

    def test_sonic_fast_path_mode_on_emit(self) -> None:
        tracker = progress.KernelProgressTracker(action="patch", path="a.py")
        event = tracker.emit(progress.PHASE_PATCH_APPLY, fast_path=True, mode="sonic_fast_path")
        self.assertEqual(event.get("mode"), "sonic_fast_path")
        self.assertTrue(event.get("fast_path"))

    def test_kinetic_watch_line_complete(self) -> None:
        line = sonic.format_kinetic_watch_line({
            "action": "patch",
            "operation_id": "op_abcd1234",
            "phase": "done",
            "elapsed_ms": 7800,
        })
        self.assertIn("complete", line.lower())
        self.assertIn("7.8s", line)

    def test_eta_hidden_without_samples(self) -> None:
        eta = sonic.estimate_remaining_ms(action="patch", current_phase="patch.validate", elapsed_ms=1000)
        self.assertFalse(eta.get("show"))

    def test_event_hooks_disabled_by_default(self) -> None:
        with mock.patch("plugins.dietcode.lib.agent.kernel_sonic.subprocess.Popen") as popen:
            sonic.emit_event_hook("operation_accepted", payload={"operation_id": "op_x"})
            popen.assert_not_called()

    def test_token_leak_detector(self) -> None:
        self.assertTrue(sonic.contains_token_leak("Bearer abcdefghijklmnop"))
        self.assertFalse(sonic.contains_token_leak("PATCH accepted — src/foo.py"))


if __name__ == "__main__":
    unittest.main()
