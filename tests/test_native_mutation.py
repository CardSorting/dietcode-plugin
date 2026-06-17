# -*- coding: utf-8 -*-
"""Tests for native mutation manager (codemarie strategy)."""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _bootstrap() -> None:
    if str(_PLUGIN_ROOT) not in sys.path:
        sys.path.insert(0, str(_PLUGIN_ROOT))
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


class NativeMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bootstrap()

    def test_patch_and_status_roundtrip(self) -> None:
        from plugins.dietcode.lib.agent.native_mutation import NativeMutationManager

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "hello.txt"
            target.write_text("hello world\n", encoding="utf-8")

            mgr = NativeMutationManager.get_instance()
            status = mgr.get_status(root)
            self.assertTrue(status.get("ok"))

            patched = mgr.apply_patch(
                root,
                "hello.txt",
                line_search="hello world",
                line_replace="hello native",
            )
            self.assertTrue(patched.get("ok"))
            self.assertIn("mutation", patched)
            self.assertEqual(target.read_text(encoding="utf-8"), "hello native\n")

            state_path = root / ".dietcode" / "mutation-state.json"
            self.assertTrue(state_path.is_file())
            state = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertGreaterEqual(state.get("workspaceRevision", 0), 2)

    def test_auto_track_file_read_updates_anchors(self) -> None:
        from plugins.dietcode.lib.agent.native_mutation import NativeMutationManager

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "tracked.txt"
            target.write_text("anchor me\n", encoding="utf-8")

            mgr = NativeMutationManager.get_instance()
            token = mgr.issue_coherence_token(root, "task-1", ["tracked.txt"])
            token_id = token["tokenId"]

            mgr.auto_track_file_read(root, "tracked.txt", "task-1")

            state = json.loads((root / ".dietcode" / "mutation-state.json").read_text(encoding="utf-8"))
            self.assertIn("tracked.txt", state.get("trackedFileHashes", {}))
            anchors = state["coherenceTokens"][token_id]["anchors"]
            self.assertIn("tracked.txt", anchors)


if __name__ == "__main__":
    unittest.main()
