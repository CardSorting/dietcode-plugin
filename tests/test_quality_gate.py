"""Quality audit gate unit tests."""
from __future__ import annotations

import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

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


class QualityGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _bootstrap()

    def setUp(self) -> None:
        from plugins.dietcode.lib.agent.audit.session_store import reset_session_metadata

        reset_session_metadata()

    def test_gate_disabled_passes(self) -> None:
        from plugins.dietcode.lib.agent.audit.completion_gate import evaluate_completion_gate
        from plugins.dietcode.lib.agent.audit.config import CompletionGateConfig

        decision = evaluate_completion_gate(
            {"violations": ["spider_gate_blocked"]},
            config=CompletionGateConfig(enabled=False),
        )
        self.assertFalse(decision.blocked)

    def test_critical_violation_blocks(self) -> None:
        from plugins.dietcode.lib.agent.audit.completion_gate import evaluate_completion_gate
        from plugins.dietcode.lib.agent.audit.config import CompletionGateConfig

        decision = evaluate_completion_gate(
            {"violations": ["spider_gate_blocked"]},
            config=CompletionGateConfig(enabled=True, score_threshold=50, critical_only=True),
        )
        self.assertTrue(decision.blocked)
        self.assertTrue(any(r.code == "critical_violations" for r in decision.reasons))

    def test_spider_blocked_recorded(self) -> None:
        from plugins.dietcode.lib.agent.audit.session_store import (
            get_session_metadata,
            record_spider_gate,
        )

        record_spider_gate("scope-a", {"blocked": True, "exitCode": 1, "qualityGate": "FAILED"})
        meta = get_session_metadata("scope-a")
        self.assertIn("spider_gate_blocked", meta.get("violations") or [])

    def test_kanban_allowed_when_clean(self) -> None:
        from plugins.dietcode.lib.agent.audit.config import CompletionGateConfig
        from plugins.dietcode.lib.agent.audit import quality_gate

        cfg = CompletionGateConfig(enabled=True, spider_gate_required=False)
        with patch.object(quality_gate, "get_completion_gate_config", return_value=cfg):
            allowed, msg, decision = quality_gate.kanban_complete_allowed("test-scope")
        self.assertTrue(allowed)
        self.assertIsNone(msg)
        self.assertIsNotNone(decision)
        self.assertFalse(decision.blocked)

    def test_governance_block_records_violations(self) -> None:
        from plugins.dietcode.lib.agent.audit.session_store import (
            append_violations,
            get_session_metadata,
        )

        append_violations("scope-b", ["joy_zoning:src/a.ts:core:import leak"])
        meta = get_session_metadata("scope-b")
        joined = " ".join(meta.get("violations") or [])
        self.assertIn("joy_zoning", joined)


if __name__ == "__main__":
    unittest.main()
