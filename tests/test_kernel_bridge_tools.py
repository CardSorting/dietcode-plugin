# -*- coding: utf-8 -*-
"""dietcode_kernel tool tests (Phase 2B)."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from lib.agent.kernel_bridge_client import (  # noqa: E402
    BRIDGE_PATCH_DISABLED,
    BRIDGE_WORKSPACE_UNSAFE,
    KernelBridgeConfig,
)
from lib.tools import kernel_bridge_tools  # noqa: E402


class DietcodeKernelToolTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self._tmpdir.name) / "project"
        self.project.mkdir()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def _mock_kbc(self, **attrs: object) -> mock.MagicMock:
        mock_kbc = mock.MagicMock()
        mock_kbc.KernelBridgeConfig.load.return_value = attrs.get(
            "config", KernelBridgeConfig()
        )
        for key, value in attrs.items():
            if key != "config":
                setattr(mock_kbc, key, value)
        return mock_kbc

    def test_status_calls_workspace_status(self) -> None:
        mock_kbc = self._mock_kbc()
        mock_kbc.workspace_status.return_value = {"ok": True, "result": {"driftDetected": False}}
        with mock.patch.object(kernel_bridge_tools, "_bridge_client", return_value=mock_kbc):
            out = json.loads(kernel_bridge_tools.dietcode_kernel("status"))
        mock_kbc.workspace_status.assert_called_once_with(None)
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "status")

    def test_search_calls_search_literal(self) -> None:
        mock_kbc = self._mock_kbc()
        mock_kbc.search_literal.return_value = {"ok": True, "result": {"matches": []}}
        with mock.patch.object(kernel_bridge_tools, "_bridge_client", return_value=mock_kbc):
            out = json.loads(kernel_bridge_tools.dietcode_kernel("search", query="TODO"))
        mock_kbc.search_literal.assert_called_once()
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "search")

    def test_patch_disabled_returns_bridge_patch_disabled(self) -> None:
        from lib.agent import kernel_bridge_client as kbc

        cfg = KernelBridgeConfig(mutations_enabled=False)
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            out = kbc.apply_kernel_patch(str(self.project), "src/a.py", unified_diff="---\n+++")
        self.assertFalse(out["ok"])
        self.assertEqual(out["string_code"], BRIDGE_PATCH_DISABLED)
        self.assertEqual(out["action"], "patch")

    def test_patch_unsafe_workspace(self) -> None:
        from lib.agent import kernel_bridge_client as kbc

        cfg = KernelBridgeConfig(mutations_enabled=True)
        unsafe = kbc.bridge_error(BRIDGE_WORKSPACE_UNSAFE, "unsafe")
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch.object(kbc, "_require_safe_workspace", return_value=(None, unsafe)):
                out = kbc.apply_kernel_patch(None, "src/a.py", unified_diff="---\n+++")
        self.assertFalse(out["ok"])
        self.assertEqual(out["string_code"], BRIDGE_WORKSPACE_UNSAFE)

    def test_patch_success_mocked(self) -> None:
        from lib.agent import kernel_bridge_client as kbc

        cfg = KernelBridgeConfig(mutations_enabled=True)
        ws = str(self.project.resolve())
        receipt = {
            "ok": True,
            "action": "patch",
            "workspace_root": ws,
            "path": "src/a.py",
            "taskId": "task_1",
            "kernel": {"mutationReceipt": {"revision": 2}},
        }
        with mock.patch.object(KernelBridgeConfig, "load", return_value=cfg):
            with mock.patch.object(kbc, "apply_kernel_patch", return_value=receipt):
                mock_kbc = self._mock_kbc(config=cfg)
                mock_kbc.apply_kernel_patch.return_value = receipt
                with mock.patch.object(kernel_bridge_tools, "_bridge_client", return_value=mock_kbc):
                    out = json.loads(
                        kernel_bridge_tools.dietcode_kernel(
                            "patch",
                            path="src/a.py",
                            unified_diff="--- a\n+++ b\n",
                            task_id="task_1",
                        )
                    )
        self.assertTrue(out["ok"])
        self.assertEqual(out["action"], "patch")
        self.assertEqual(out["kernel"]["mutationReceipt"]["revision"], 2)

    def test_tool_patch_disabled_via_client(self) -> None:
        mock_kbc = self._mock_kbc(config=KernelBridgeConfig(mutations_enabled=True))
        mock_kbc.apply_kernel_patch.return_value = {
            "ok": False,
            "action": "patch",
            "string_code": BRIDGE_PATCH_DISABLED,
            "error": {"string_code": BRIDGE_PATCH_DISABLED, "message": "disabled"},
        }
        with mock.patch.object(kernel_bridge_tools, "_bridge_client", return_value=mock_kbc):
            out = json.loads(
                kernel_bridge_tools.dietcode_kernel("patch", path="x.py", unified_diff="---\n")
            )
        self.assertFalse(out["ok"])
        self.assertEqual(out["string_code"], BRIDGE_PATCH_DISABLED)


if __name__ == "__main__":
    unittest.main()
