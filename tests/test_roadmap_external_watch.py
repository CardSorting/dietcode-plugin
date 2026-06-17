"""External ROADMAP.md change detection (no VS Code watcher)."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def _bootstrap() -> None:
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


class ExternalRoadmapWatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bootstrap()

    def test_external_edit_detected_at_session_end(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.external_watch import (
            begin_session_roadmap_watch,
            end_session_roadmap_watch,
        )
        from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            roadmap = root / "ROADMAP.md"
            roadmap.write_text("# ROADMAP\n", encoding="utf-8")
            begin_session_roadmap_watch(root)
            time.sleep(0.05)
            roadmap.write_text("# ROADMAP\n\nedited externally\n", encoding="utf-8")
            changed = end_session_roadmap_watch(root, emit_events=False)
            self.assertTrue(changed)
            state = read_state(root)
            self.assertTrue(state.get("validation_pending"))
            self.assertEqual(state.get("last_mutation_tool"), "external")

    def test_tool_mutation_not_double_counted(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.external_watch import (
            begin_session_roadmap_watch,
            end_session_roadmap_watch,
            note_tool_roadmap_mutation,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            roadmap = root / "ROADMAP.md"
            roadmap.write_text("v1\n", encoding="utf-8")
            begin_session_roadmap_watch(root)
            roadmap.write_text("v2\n", encoding="utf-8")
            note_tool_roadmap_mutation(root)
            changed = end_session_roadmap_watch(root, emit_events=False)
            self.assertFalse(changed)


if __name__ == "__main__":
    unittest.main()
