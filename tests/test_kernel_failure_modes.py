# -*- coding: utf-8 -*-
"""Phase 5 failure-mode audit tests — bridge hardening."""
from __future__ import annotations

import importlib.util
import json
import socket
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

from lib.agent import kernel_bridge_client as bridge  # noqa: E402
from lib.agent.kernel_bridge_client import (  # noqa: E402
    BRIDGE_RPC_TIMEOUT,
    BRIDGE_TOKEN_UNAVAILABLE,
    BRIDGE_TRANSPORT_ERROR,
    BRIDGE_WORKSPACE_UNSAFE,
    KernelBridgeConfig,
)
from lib.agent import kernel_receipt_journal as krj  # noqa: E402
import plugins.dietcode.lib.agent.kernel_raw_write_router as router  # noqa: E402


def _open_gate(**overrides: object) -> dict:
    base = {
        "bridge_enabled": True,
        "mutations_enabled": True,
        "workspace_safe_for_mutation": True,
        "resolved_workspace_root": "/tmp/project",
        "socket_ready": True,
        "token_ready": True,
        "patch_allowed": True,
    }
    base.update(overrides)
    return base


class _PatchFakeClient:
    def send_rpc(self, sock, token, method, params=None, request_timeout=None) -> dict:
        if method == "file.read":
            return {"ok": True, "result": {"text": "hello\n"}}
        if method == "patch.validate":
            return {"ok": True, "result": {"valid": True}}
        if method == "patch.apply":
            raise OSError("socket died mid-patch")
        return {"ok": False, "error": {"message": f"unmocked {method}"}}


class KernelFailureModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self._tmpdir.name) / "project"
        self.project.mkdir()
        bridge._PREFLIGHT_CACHE = None
        krj.reset_journal_dedup_cache()
        router.clear_raw_write_warning_stash()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()
        bridge._PREFLIGHT_CACHE = None

    def test_socket_dies_mid_patch_returns_transport_error(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True)
        ws = str(self.project.resolve())
        fake = _PatchFakeClient()

        def fake_open(workspace_root=None, timeout=None):
            return bridge.bridge_ok({"path": ws}, workspace_root=ws)

        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch.object(bridge, "open_workspace", side_effect=fake_open):
                with mock.patch.object(bridge, "ensure_socket_ready", return_value=bridge.bridge_ok()):
                    with mock.patch.object(bridge, "read_kernel_token", return_value=bridge.bridge_ok()):
                        with mock.patch.object(bridge, "_require_safe_workspace", return_value=(ws, None)):
                            with mock.patch.object(bridge, "_kernel_rpc_session") as session:
                                sock = mock.MagicMock()
                                session.return_value.__enter__.return_value = (fake, sock, "tok", cfg)
                                with mock.patch.object(bridge, "_load_coherence_module", return_value=None):
                                    out = bridge.apply_kernel_patch(
                                        ws,
                                        "hello.txt",
                                        unified_diff="--- a/hello.txt\n+++ b/hello.txt\n@@\n-hello\n+hello world\n",
                                    )

        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("string_code"), BRIDGE_TRANSPORT_ERROR)
        self.assertNotIn("mutationReceipt", out.get("kernel") or {})

    def test_token_missing_blocks_patch(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True)
        ws = str(self.project.resolve())
        token_err = bridge.bridge_error(
            BRIDGE_TOKEN_UNAVAILABLE,
            "session.token missing",
        )

        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch.object(bridge, "_require_safe_workspace", return_value=(ws, None)):
                with mock.patch.object(bridge, "ensure_socket_ready", return_value=bridge.bridge_ok()):
                    with mock.patch.object(bridge, "read_kernel_token", return_value=token_err):
                        out = bridge.apply_kernel_patch(ws, "hello.txt", line_search="a", line_replace="b")

        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("string_code"), BRIDGE_TOKEN_UNAVAILABLE)

    def test_workspace_deleted_or_unsafe_blocks_patch(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True)
        ws_err = bridge.bridge_error(BRIDGE_WORKSPACE_UNSAFE, "workspace root missing or deleted")

        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch.object(bridge, "_require_safe_workspace", return_value=(None, ws_err)):
                out = bridge.apply_kernel_patch(None, "hello.txt", line_search="a", line_replace="b")

        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("string_code"), BRIDGE_WORKSPACE_UNSAFE)

    def test_verify_timeout_returns_bridge_rpc_timeout(self) -> None:
        cfg = KernelBridgeConfig()
        ws = str(self.project.resolve())
        fake = mock.MagicMock()
        fake.send_rpc.side_effect = socket.timeout("verify.run timed out")

        def fake_open(workspace_root=None, timeout=None):
            return bridge.bridge_ok({"path": ws}, workspace_root=ws)

        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch.object(bridge, "_require_safe_workspace", return_value=(ws, None)):
                with mock.patch.object(bridge, "ensure_socket_ready", return_value=bridge.bridge_ok()):
                    with mock.patch.object(bridge, "read_kernel_token", return_value=bridge.bridge_ok()):
                        with mock.patch.object(bridge, "open_workspace", side_effect=fake_open):
                            with mock.patch.object(bridge, "_kernel_rpc_session") as session:
                                session.return_value.__enter__.return_value = (fake, mock.MagicMock(), "tok", cfg)
                                out = bridge.apply_kernel_verify(ws, "./verify.sh")

        self.assertFalse(out.get("ok"))
        self.assertEqual(out.get("string_code"), BRIDGE_RPC_TIMEOUT)
        self.assertFalse(out.get("verify_ran"))

    def test_journal_unavailable_emits_warning_not_tool_failure(self) -> None:
        parsed = {
            "ok": True,
            "action": "patch",
            "path": "src/a.py",
            "taskId": "task_1",
            "workspace_root": "/tmp/project",
            "kernel": {
                "mutationReceipt": {
                    "path": "src/a.py",
                    "patchFingerprint": "fp1",
                    "postContentHash": "hash1",
                },
            },
        }
        cfg = mock.MagicMock()
        cfg.enabled = True

        with mock.patch(
            "plugins.dietcode.lib.agent.joyzoning.config.get_joyzoning_config",
            return_value=cfg,
        ):
            with mock.patch(
                "plugins.dietcode.lib.agent.joyzoning.config.resolve_scope_id",
                return_value="scope_1",
            ):
                with mock.patch.object(
                    krj,
                    "_resolve_mutation_id",
                    side_effect=RuntimeError("journal db unavailable"),
                ):
                    report = krj.journal_kernel_patch(
                        tool_name="dietcode_kernel",
                        args={"action": "patch"},
                        result=parsed,
                    )

        self.assertFalse(report.get("journaled"))
        self.assertIn("warning", report)
        merged = krj.merge_journal_warning_into_result(json.dumps(parsed), report)
        assert merged is not None
        body = json.loads(merged)
        self.assertTrue(body["ok"])
        self.assertIn("_journal_warning", body)

    def test_raw_write_block_falls_back_when_gate_closes(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True, raw_write_policy="block")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            with mock.patch.object(router, "raw_write_block_enforcement_enabled", return_value=True):
                out = router.evaluate_raw_write_pre_tool_call(
                    tool_name="write_file",
                    gate=_open_gate(patch_allowed=False, mutations_enabled=False),
                )
        self.assertIsNone(out)

    def test_status_summary_includes_operator_fields(self) -> None:
        from lib.kernel_health import build_kernel_bridge_status_summary

        with mock.patch("lib.kernel_health.platform_supported", return_value=True):
            with mock.patch("lib.kernel_health.socket_reachable", return_value=True):
                with mock.patch("lib.kernel_health.token_readable", return_value=True):
                    with mock.patch.object(KernelBridgeConfig, "load", return_value=KernelBridgeConfig()):
                        summary = build_kernel_bridge_status_summary(probe_runtime=False)

        for key in (
            "bridge_enabled",
            "mutations_enabled",
            "raw_write_policy",
            "env_fuse_present",
            "workspace_safe",
            "patch_allowed",
            "verify_allowlist_count",
        ):
            self.assertIn(key, summary)
        self.assertEqual(summary["raw_write_policy"], "warn")
        self.assertFalse(summary["mutations_enabled"])


if __name__ == "__main__":
    unittest.main()
