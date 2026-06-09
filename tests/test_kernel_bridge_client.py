# -*- coding: utf-8 -*-
"""Kernel bridge client preflight tests (Phase 2A — mocked RPC)."""
from __future__ import annotations

import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from lib.agent import kernel_bridge_client as bridge  # noqa: E402
from lib.agent.kernel_bridge_client import (  # noqa: E402
    BRIDGE_DISABLED,
    BRIDGE_PATCH_DISABLED,
    BRIDGE_WORKSPACE_UNSAFE,
    BRIDGE_WORKSPACE_UNRESOLVED,
    KernelBridgeConfig,
)


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def ensure_socket(self, **kwargs: object) -> bool:
        return True

    def load_token(self, token_path: str) -> str:
        return "tok_test"

    def connect(self, **kwargs: object) -> socket.socket:
        return mock.MagicMock(spec=socket.socket)

    def send_rpc(self, sock, token, method, params=None, request_timeout=None) -> dict:
        self.calls.append((method, dict(params or {})))
        if method == "rpc.ping":
            return {"ok": True, "result": {"pong": True}}
        if method == "workspace.getRoot":
            return {"ok": True, "result": {"path": "/tmp/project"}}
        if method == "workspace.openFolder":
            return {"ok": True, "result": {"path": params.get("path")}}
        if method == "workspace.status":
            return {"ok": True, "result": {"driftDetected": False}}
        if method == "search.literal":
            return {"ok": True, "result": {"matches": [], "query": params.get("query")}}
        return {"ok": False, "error": {"string_code": "unknown", "message": f"unmocked {method}"}}


class KernelBridgeClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self._tmpdir.name) / "project"
        self.project.mkdir()
        bridge._PREFLIGHT_CACHE = None
        bridge._PREFLIGHT_CACHE_AT = 0.0
        bridge._CLIENT_MODULE = None

    def tearDown(self) -> None:
        self._tmpdir.cleanup()
        bridge._PREFLIGHT_CACHE = None
        bridge._CLIENT_MODULE = None


    def test_mutations_disabled_by_default(self) -> None:
        with mock.patch.object(KernelBridgeConfig, "load", return_value=KernelBridgeConfig()):
            self.assertFalse(bridge.mutations_enabled())

    def test_connect_preflight_disabled(self) -> None:
        cfg = KernelBridgeConfig(enabled=False)
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            report = bridge.connect_preflight()
        self.assertTrue(report.get("ok"))
        self.assertEqual(report.get("action"), "disabled")

    def test_read_kernel_token_disabled(self) -> None:
        cfg = KernelBridgeConfig(enabled=False)
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            out = bridge.read_kernel_token()
        self.assertFalse(out.get("ok"))
        self.assertEqual(out["error"]["string_code"], BRIDGE_DISABLED)

    def test_search_literal_refuses_unsafe_workspace(self) -> None:
        plugin_root = _PLUGIN_ROOT.resolve()
        with mock.patch.object(
            bridge,
            "_require_safe_workspace",
            return_value=(None, bridge.bridge_error(BRIDGE_WORKSPACE_UNSAFE, "bad")),
        ):
            out = bridge.search_literal(None, "hello")
        self.assertFalse(out.get("ok"))
        self.assertEqual(out["error"]["string_code"], BRIDGE_WORKSPACE_UNSAFE)

    def test_open_workspace_refuses_kernel_root(self) -> None:
        kernel_root = (_PLUGIN_ROOT / "kernel").resolve()
        from lib.kernel_workspace import WorkspaceValidation

        mock_kw = mock.MagicMock()
        mock_kw.validate_workspace_root.return_value = WorkspaceValidation(
            ok=False,
            safe_for_mutation=False,
            errors=["workspace_root must not be kernel_root"],
            checks={"not_kernel_root": False},
        )
        with mock.patch.object(bridge, "_resolve_workspace_module", return_value=mock_kw):
            out = bridge.open_workspace(str(kernel_root))
        self.assertFalse(out.get("ok"))
        self.assertEqual(out["error"]["string_code"], BRIDGE_WORKSPACE_UNSAFE)

    def test_send_kernel_rpc_ping_mocked(self) -> None:
        fake = _FakeClient()
        cfg = KernelBridgeConfig()
        ws = str(self.project.resolve())
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch.object(bridge, "_load_client_module", return_value=fake):
                with mock.patch.object(bridge, "ensure_socket_ready", return_value=bridge.bridge_ok()):
                    with mock.patch.object(bridge, "read_kernel_token", return_value=bridge.bridge_ok()):
                        out = bridge.send_kernel_rpc("rpc.ping", {})
        self.assertTrue(out.get("ok"))
        self.assertEqual(fake.calls[0][0], "rpc.ping")

    def test_search_literal_mocked(self) -> None:
        fake = _FakeClient()
        cfg = KernelBridgeConfig()
        ws = str(self.project.resolve())

        def fake_open(workspace_root=None, timeout=None):
            return bridge.bridge_ok({"path": ws}, workspace_root=ws)

        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch.object(bridge, "open_workspace", side_effect=fake_open):
                with mock.patch.object(bridge, "_kernel_rpc_session") as session:
                    sock = mock.MagicMock()
                    session.return_value.__enter__.return_value = (fake, sock, "tok", cfg)
                    out = bridge.search_literal(ws, "CONTRACT")
        self.assertTrue(out.get("ok"))
        self.assertEqual(fake.calls[-1][0], "search.literal")
        self.assertEqual(fake.calls[-1][1]["query"], "CONTRACT")

    def test_connect_preflight_warm_skips_workspace_when_unsafe(self) -> None:
        cfg = KernelBridgeConfig()
        fake = _FakeClient()
        ws_mod = mock.MagicMock()
        ws_mod.resolve_workspace_root.return_value = mock.MagicMock(
            safe_for_mutation=False,
            resolved_workspace_root=str(_PLUGIN_ROOT),
            to_dict=lambda: {"safe_for_mutation": False},
        )
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch("lib.kernel_health.platform_supported", return_value=True):
                with mock.patch.object(bridge, "_kernel_binary_path") as bin_path:
                    bin_path.return_value = mock.MagicMock(is_file=lambda: True)
                    with mock.patch.object(bridge, "_resolve_workspace_module", return_value=ws_mod):
                        with mock.patch.object(bridge, "ensure_socket_ready", return_value=bridge.bridge_ok()):
                            with mock.patch.object(bridge, "read_kernel_token", return_value=bridge.bridge_ok()):
                                with mock.patch.object(
                                    bridge,
                                    "send_kernel_rpc",
                                    return_value=bridge.bridge_ok({"pong": True}),
                                ):
                                    report = bridge.connect_preflight(warm=True, force=True)
        self.assertTrue(report.get("ok"))
        self.assertFalse(report.get("workspace_safe_for_mutation"))
        self.assertEqual(
            report["steps"]["workspace_status"]["error"]["string_code"],
            BRIDGE_WORKSPACE_UNSAFE,
        )

    def test_patch_disabled_constant_exists_for_phase_2b(self) -> None:
        self.assertEqual(BRIDGE_PATCH_DISABLED, "bridge_patch_disabled")

    def test_require_safe_workspace_unresolved(self) -> None:
        mock_kw = mock.MagicMock()
        mock_kw.resolve_workspace_root.return_value = mock.MagicMock(
            resolved_workspace_root=None,
            safe_for_mutation=False,
            validation=mock.MagicMock(errors=["unresolved"]),
            to_dict=lambda: {},
        )
        with mock.patch.object(bridge, "_resolve_workspace_module", return_value=mock_kw):
            path, err = bridge._require_safe_workspace(None)
        self.assertIsNone(path)
        self.assertIsNotNone(err)
        self.assertEqual(err["error"]["string_code"], BRIDGE_WORKSPACE_UNRESOLVED)


if __name__ == "__main__":
    unittest.main()
