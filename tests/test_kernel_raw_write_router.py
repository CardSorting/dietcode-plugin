# -*- coding: utf-8 -*-
"""Phase 3A raw write router tests."""
from __future__ import annotations

import importlib.util
import json
import sys
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

import plugins.dietcode.lib.agent.kernel_raw_write_router as router  # noqa: E402
from plugins.dietcode.lib.agent.kernel_bridge_client import KernelBridgeConfig  # noqa: E402
from plugins.dietcode.lib.runtime import kernel_hooks  # noqa: E402


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


class KernelRawWriteRouterTests(unittest.TestCase):
    def setUp(self) -> None:
        router.clear_raw_write_warning_stash()

    def test_is_raw_write_tool(self) -> None:
        self.assertTrue(router.is_raw_write_tool("write_file"))
        self.assertTrue(router.is_raw_write_tool("patch"))
        self.assertFalse(router.is_raw_write_tool("dietcode_kernel"))
        self.assertFalse(router.is_raw_write_tool("read_file"))

    def test_warn_when_bridge_ready(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True, raw_write_policy="warn")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            out = router.evaluate_raw_write_pre_tool_call(
                tool_name="patch",
                gate=_open_gate(),
            )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["action"], "warn")
        self.assertEqual(out["string_code"], router.KERNEL_RAW_WRITE_WARN)
        self.assertEqual(out["preferred_tool"], "dietcode_kernel")
        self.assertEqual(out["reason"], router.RAW_WRITE_REASON_BRIDGE_READY)
        self.assertEqual(out["workspace_root"], "/tmp/project")

    def test_no_warn_when_policy_allow(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True, raw_write_policy="allow")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            out = router.evaluate_raw_write_pre_tool_call(
                tool_name="write_file",
                gate=_open_gate(),
            )
        self.assertIsNone(out)

    def test_no_warn_when_bridge_disabled(self) -> None:
        cfg = KernelBridgeConfig(enabled=False, raw_write_policy="warn")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            out = router.evaluate_raw_write_pre_tool_call(
                tool_name="patch",
                gate=_open_gate(bridge_enabled=False, patch_allowed=False),
            )
        self.assertIsNone(out)

    def test_no_warn_when_mutations_disabled(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=False, raw_write_policy="warn")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            out = router.evaluate_raw_write_pre_tool_call(
                tool_name="patch",
                gate=_open_gate(mutations_enabled=False, patch_allowed=False),
            )
        self.assertIsNone(out)

    def test_no_warn_when_workspace_unsafe(self) -> None:
        cfg = KernelBridgeConfig(raw_write_policy="warn")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            out = router.evaluate_raw_write_pre_tool_call(
                tool_name="patch",
                gate=_open_gate(
                    workspace_safe_for_mutation=False,
                    patch_allowed=False,
                ),
            )
        self.assertIsNone(out)

    def test_no_warn_when_socket_unavailable(self) -> None:
        cfg = KernelBridgeConfig(raw_write_policy="warn")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            out = router.evaluate_raw_write_pre_tool_call(
                tool_name="patch",
                gate=_open_gate(socket_ready=False, patch_allowed=False),
            )
        self.assertIsNone(out)

    def test_no_warn_when_token_unavailable(self) -> None:
        cfg = KernelBridgeConfig(raw_write_policy="warn")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            out = router.evaluate_raw_write_pre_tool_call(
                tool_name="patch",
                gate=_open_gate(token_ready=False, patch_allowed=False),
            )
        self.assertIsNone(out)

    def test_no_warn_for_dietcode_kernel(self) -> None:
        cfg = KernelBridgeConfig(raw_write_policy="warn")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            out = router.evaluate_raw_write_pre_tool_call(
                tool_name="dietcode_kernel",
                gate=_open_gate(),
            )
        self.assertIsNone(out)

    def test_block_policy_still_warns_without_phase_3b_guard(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True, raw_write_policy="block")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            with mock.patch.object(router, "raw_write_block_enforcement_enabled", return_value=False):
                out = router.evaluate_raw_write_pre_tool_call(
                    tool_name="write_file",
                    gate=_open_gate(),
                )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["action"], "warn")

    def test_block_config_without_env_fuse_does_not_block(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True, raw_write_policy="block")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            with mock.patch.object(router, "raw_write_block_enforcement_enabled", return_value=False):
                out = router.evaluate_raw_write_pre_tool_call(
                    tool_name="patch",
                    gate=_open_gate(),
                )
        assert out is not None
        self.assertNotEqual(out.get("action"), "block")

    def test_env_fuse_without_block_config_does_not_block(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True, raw_write_policy="warn")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            with mock.patch.object(router, "raw_write_block_enforcement_enabled", return_value=True):
                out = router.evaluate_raw_write_pre_tool_call(
                    tool_name="patch",
                    gate=_open_gate(),
                )
        assert out is not None
        self.assertEqual(out.get("action"), "warn")

    def test_block_policy_blocks_with_phase_3b_guard(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True, raw_write_policy="block")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            with mock.patch.object(router, "raw_write_block_enforcement_enabled", return_value=True):
                out = router.evaluate_raw_write_pre_tool_call(
                    tool_name="write_file",
                    gate=_open_gate(),
                )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertEqual(out["action"], "block")
        payload = json.loads(out["message"])
        self.assertFalse(payload["ok"])
        self.assertTrue(payload["blocked"])
        self.assertEqual(payload["string_code"], router.KERNEL_RAW_WRITE_BLOCKED)
        self.assertEqual(payload["preferred_tool"], "dietcode_kernel")
        self.assertEqual(payload["workspace_root"], "/tmp/project")

    def test_unsafe_workspace_does_not_block(self) -> None:
        cfg = KernelBridgeConfig(mutations_enabled=True, raw_write_policy="block")
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            with mock.patch.object(router, "raw_write_block_enforcement_enabled", return_value=True):
                out = router.evaluate_raw_write_pre_tool_call(
                    tool_name="write_file",
                    gate=_open_gate(
                        workspace_safe_for_mutation=False,
                        patch_allowed=False,
                    ),
                )
        self.assertIsNone(out)

    def test_transform_merges_stashed_warning(self) -> None:
        meta = router.build_raw_write_warning_metadata(gate=_open_gate())
        router.stash_raw_write_warning(meta)
        raw = json.dumps({"ok": True})
        merged = kernel_hooks.on_kernel_raw_write_transform(
            tool_name="patch",
            args={"path": "src/a.py"},
            result=raw,
        )
        assert merged is not None
        parsed = json.loads(merged)
        self.assertTrue(parsed["ok"])
        self.assertEqual(
            parsed["_kernel_raw_write_warning"]["string_code"],
            router.KERNEL_RAW_WRITE_WARN,
        )
        self.assertIsNone(router.take_raw_write_warning())

    def test_build_router_health_would_warn(self) -> None:
        cfg = KernelBridgeConfig(raw_write_policy="warn")
        gate = _open_gate()
        with mock.patch.object(router, "_load_bridge_config", return_value=cfg):
            with mock.patch.object(router, "_load_patch_gate", return_value=gate):
                health = router.build_raw_write_router_health(probe_runtime=False)
        self.assertTrue(health["would_warn_on_raw_write"])
        self.assertFalse(health["raw_write_blocking"])
        self.assertEqual(health["raw_write_policy"], "warn")


if __name__ == "__main__":
    unittest.main()
