"""Layer tag alignment tests."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
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


class LayerAlignTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bootstrap()

    def test_aligns_mismatched_layer_tag(self) -> None:
        from plugins.dietcode.lib.agent.layer_align import align_layer_tag

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "src" / "core" / "sample.ts"
            target.parent.mkdir(parents=True)
            target.write_text("export function run() { return 1; }\n", encoding="utf-8")
            result = align_layer_tag(root, "src/core/sample.ts")
            self.assertTrue(result.get("aligned"))
            self.assertEqual(result.get("layer"), "core")
            self.assertIn("[LAYER: CORE]", target.read_text(encoding="utf-8").upper())


if __name__ == "__main__":
    unittest.main()
