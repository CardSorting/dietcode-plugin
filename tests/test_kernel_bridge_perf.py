# -*- coding: utf-8 -*-
"""Phase 7 kernel bridge performance tests."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import threading
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

import plugins.dietcode.lib.agent.kernel_bridge_cache as cache  # noqa: E402
import plugins.dietcode.lib.agent.kernel_bridge_client as bridge  # noqa: E402
import plugins.dietcode.lib.agent.kernel_mutation_lock as locks  # noqa: E402
import plugins.dietcode.lib.agent.kernel_progress as progress  # noqa: E402
import plugins.dietcode.lib.agent.kernel_receipt_journal as receipt_journal  # noqa: E402
from plugins.dietcode.lib.agent.kernel_bridge_client import KernelBridgeConfig  # noqa: E402


class KernelBridgePerfTests(unittest.TestCase):
    def setUp(self) -> None:
        cache.reset_bridge_caches()
        locks.reset_mutation_locks()
        progress.reset_progress_write_buffer()
        receipt_journal.reset_journal_dedup_cache()
        bridge._PREFLIGHT_CACHE = None
        bridge._PREFLIGHT_CACHE_AT = 0.0

    def test_preflight_cache_hit_miss(self) -> None:
        cfg = KernelBridgeConfig(preflight_cache_ttl_ms=5000)
        cache.cache_readiness(socket_path="/tmp/s.sock", token_path="/tmp/t.token")
        self.assertTrue(
            cache.get_cached_readiness(
                ttl_sec=5.0,
                socket_path="/tmp/s.sock",
                token_path="/tmp/t.token",
            )
        )
        cache.invalidate_readiness(reason="socket")
        self.assertFalse(
            cache.get_cached_readiness(
                ttl_sec=5.0,
                socket_path="/tmp/s.sock",
                token_path="/tmp/t.token",
            )
        )

    def test_workspace_open_cache_hit_miss(self) -> None:
        cache.mark_workspace_open("/tmp/project")
        self.assertTrue(
            cache.workspace_open_cache_hit(
                enabled=True,
                workspace_root="/tmp/project",
                ttl_sec=5.0,
            )
        )
        cache.invalidate_workspace_cache(reason="workspace")
        self.assertFalse(
            cache.workspace_open_cache_hit(
                enabled=True,
                workspace_root="/tmp/project",
                ttl_sec=5.0,
            )
        )

    def test_progress_batching_flushes_on_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            session.mkdir()
            with mock.patch.object(progress, "session_dir", return_value=session):
                with mock.patch.object(progress, "_progress_flush_interval_ms", return_value=60_000):
                    tracker = progress.KernelProgressTracker(
                        action="patch",
                        path="a.py",
                        operation_id="op_batch",
                    )
                    tracker.emit("socket.ready")
                    log_path = session / "kernel-progress.jsonl"
                    self.assertFalse(log_path.exists())
                    tracker.finish(ok=True)
                    self.assertTrue(log_path.is_file())
                    lines = log_path.read_text().strip().splitlines()
                    self.assertGreaterEqual(len(lines), 2)

    def test_mutation_lock_serializes_patch_calls(self) -> None:
        order: list[str] = []
        started = threading.Event()

        def worker(name: str) -> None:
            with locks.mutation_lock("/tmp/ws", max_concurrent=1):
                order.append(f"{name}-start")
                if name == "a":
                    started.set()
                    time.sleep(0.15)
                order.append(f"{name}-end")

        t1 = threading.Thread(target=worker, args=("a",))
        t2 = threading.Thread(target=worker, args=("b",))
        t1.start()
        self.assertTrue(started.wait(timeout=2))
        t2.start()
        t1.join(timeout=3)
        t2.join(timeout=3)
        self.assertEqual(order, ["a-start", "a-end", "b-start", "b-end"])

    def test_read_search_without_mutation_lock(self) -> None:
        entered: list[str] = []

        class _LockSpy:
            @staticmethod
            def mutation_lock(workspace_root: str, *, max_concurrent: int = 1):
                entered.append(workspace_root)
                return locks.mutation_lock(workspace_root, max_concurrent=max_concurrent)

        cfg = KernelBridgeConfig(mutations_enabled=True, workspace_open_cache=False)
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch.object(bridge, "_ensure_bridge_ready", return_value=bridge.bridge_ok()):
                with mock.patch.object(
                    bridge,
                    "open_workspace",
                    return_value=bridge.bridge_ok(workspace_root="/tmp/ws"),
                ):
                    with mock.patch.object(bridge, "_kernel_rpc_session") as session_mock:
                        client = mock.MagicMock()
                        client.send_rpc.return_value = {"ok": True, "result": {"matches": []}}
                        session_mock.return_value.__enter__.return_value = (
                            client,
                            mock.MagicMock(),
                            "tok",
                            cfg,
                        )
                        with mock.patch.object(bridge, "_mutation_lock_module", return_value=_LockSpy()):
                            bridge.search_literal("/tmp/ws", "TODO")
        self.assertEqual(entered, [])

    def test_verify_timeout_envelope(self) -> None:
        cfg = KernelBridgeConfig(verify_timeout_ms=100)
        self.assertEqual(cfg.verify_timeout_ms, 100)
        env = progress.normalize_bridge_error("bridge_rpc_timeout", "verify timed out", phase="verify.running")
        self.assertIn("safe_to_retry", env)
        self.assertTrue(env["safe_to_retry"])

    def test_performance_telemetry_contains_phase_durations(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            session = Path(tmp) / "session"
            session.mkdir()
            with mock.patch.object(progress, "session_dir", return_value=session):
                tracker = progress.KernelProgressTracker(action="status", operation_id="op_perf")
                tracker.emit("bridge.preflight")
                time.sleep(0.01)
                tracker.emit("socket.ready")
                tracker.finish(ok=True)
                progress.flush_progress_writes(force=True)
                events = progress.read_operation_events("op_perf")
                timed = [e for e in events if int(e.get("phase_duration_ms") or 0) >= 0]
                self.assertGreaterEqual(len(timed), 2)
                self.assertIn("perf_bucket", events[-1])

    def test_ensure_bridge_ready_uses_cache(self) -> None:
        cfg = KernelBridgeConfig(preflight_cache_ttl_ms=5000)
        cache.cache_readiness(socket_path=bridge._socket_path(), token_path=bridge._token_path())
        with mock.patch.object(bridge, "ensure_socket_ready") as mock_socket:
            out = bridge._ensure_bridge_ready(cfg)
        mock_socket.assert_not_called()
        self.assertTrue(out.get("ok"))


if __name__ == "__main__":
    unittest.main()
