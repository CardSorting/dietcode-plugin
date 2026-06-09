# -*- coding: utf-8 -*-
"""Kernel receipt → JoyZoning journal bridge tests (Phase 2C)."""
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

from lib.agent import kernel_receipt_journal as krj  # noqa: E402
from lib.agent.joyzoning.config import JoyZoningConfig  # noqa: E402
from lib.runtime import kernel_hooks  # noqa: E402


def _patch_success(**overrides: object) -> dict:
    payload = {
        "ok": True,
        "action": "patch",
        "workspace_root": "/tmp/project",
        "path": "src/a.py",
        "taskId": "task_1",
        "kernel": {
            "mutationReceipt": {
                "patchFingerprint": "fp-abc",
                "postContentHash": "hash-post",
                "beforeContentHash": "hash-before",
            },
            "operationId": "op-1",
        },
    }
    payload.update(overrides)
    return payload


class KernelReceiptJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        krj.reset_journal_dedup_cache()

    def test_should_journal_requires_receipt(self) -> None:
        args = {"action": "patch"}
        self.assertFalse(
            krj.should_journal_kernel_patch(
                "dietcode_kernel",
                args,
                {"ok": True, "action": "patch", "kernel": {}},
            )
        )
        self.assertTrue(
            krj.should_journal_kernel_patch(
                "dietcode_kernel",
                args,
                _patch_success(),
            )
        )

    def test_build_journal_metadata_copies_present_fields_only(self) -> None:
        parsed = _patch_success(
            coherenceTokenId="tok-1",
            verifyStatus="passed",
        )
        receipt = parsed["kernel"]["mutationReceipt"]
        meta = krj.build_journal_metadata(parsed, receipt)
        self.assertEqual(meta["taskId"], "task_1")
        self.assertEqual(meta["workspace_root"], "/tmp/project")
        self.assertEqual(meta["relative_path"], "src/a.py")
        self.assertEqual(meta["mutationReceipt"]["patchFingerprint"], "fp-abc")
        self.assertEqual(meta["kernel"]["operationId"], "op-1")
        self.assertEqual(meta["coherence"]["coherenceTokenId"], "tok-1")
        self.assertEqual(meta["verification"]["verifyStatus"], "passed")
        self.assertNotIn("inventedField", meta["mutationReceipt"])

    def test_successful_patch_journals_once(self) -> None:
        cfg = JoyZoningConfig(enabled=True)
        result = _patch_success()
        mock_journal = mock.MagicMock()
        mock_journal.get_active_mutation.return_value = None

        with mock.patch.object(JoyZoningConfig, "load", return_value=cfg):
            with mock.patch(
                "plugins.dietcode.lib.agent.joyzoning.config.get_joyzoning_config",
                return_value=cfg,
            ):
                with mock.patch(
                    "plugins.dietcode.lib.agent.joyzoning.config.resolve_scope_id",
                    return_value="scope_task_1",
                ):
                    with mock.patch(
                        "plugins.dietcode.lib.agent.joyzoning.journal.get_journal",
                        return_value=mock_journal,
                    ):
                        with mock.patch(
                            "plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle.begin_mutation",
                            return_value={"success": True, "mutation_id": "mut_abc"},
                        ) as begin:
                            with mock.patch(
                                "plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle.record_patch",
                                return_value={"success": True},
                            ) as record:
                                with mock.patch(
                                    "plugins.dietcode.lib.agent.joyzoning.runtime_events.emit_runtime_event",
                                ) as emit:
                                    first = krj.journal_kernel_patch(
                                        tool_name="dietcode_kernel",
                                        args={"action": "patch"},
                                        result=result,
                                    )
                                    second = krj.journal_kernel_patch(
                                        tool_name="dietcode_kernel",
                                        args={"action": "patch"},
                                        result=result,
                                    )
        self.assertTrue(first["journaled"])
        self.assertTrue(second["deduplicated"])
        begin.assert_called_once()
        record.assert_called_once()
        emit.assert_called_once()
        mock_journal.upsert_mutation_scope.assert_called_once()

    def test_missing_receipt_does_not_journal(self) -> None:
        report = krj.journal_kernel_patch(
            tool_name="dietcode_kernel",
            args={"action": "patch"},
            result={"ok": True, "action": "patch", "kernel": {}},
        )
        self.assertFalse(report["journaled"])
        self.assertTrue(report.get("skipped"))

    def test_failed_patch_does_not_journal(self) -> None:
        report = krj.journal_kernel_patch(
            tool_name="dietcode_kernel",
            args={"action": "patch"},
            result=_patch_success(ok=False),
        )
        self.assertFalse(report["journaled"])
        self.assertTrue(report.get("skipped"))

    def test_journal_failure_returns_warning_not_failure(self) -> None:
        cfg = JoyZoningConfig(enabled=True)
        raw = json.dumps(_patch_success())
        with mock.patch.object(JoyZoningConfig, "load", return_value=cfg):
            with mock.patch(
                "plugins.dietcode.lib.agent.joyzoning.config.get_joyzoning_config",
                return_value=cfg,
            ):
                with mock.patch(
                    "plugins.dietcode.lib.agent.joyzoning.config.resolve_scope_id",
                    return_value="scope_task_1",
                ):
                    with mock.patch(
                        "plugins.dietcode.lib.agent.joyzoning.journal.get_journal",
                        side_effect=RuntimeError("journal offline"),
                    ):
                        report = krj.journal_kernel_patch(
                            tool_name="dietcode_kernel",
                            args={"action": "patch"},
                            result=raw,
                        )

        self.assertFalse(report["journaled"])
        self.assertIn("warning", report)
        merged = krj.merge_journal_warning_into_result(raw, report)
        assert merged is not None
        parsed = json.loads(merged)
        self.assertTrue(parsed["ok"])
        self.assertIn("_journal_warning", parsed)
        self.assertIn("journal offline", parsed["_journal_warning"])

    def test_transform_hook_merges_warning(self) -> None:
        raw = json.dumps(_patch_success())
        warning_report = {
            "journaled": False,
            "warning": "Kernel patch succeeded but JoyZoning journal failed: boom",
        }
        with mock.patch(
            "plugins.dietcode.lib.agent.kernel_receipt_journal.journal_kernel_patch",
            return_value=warning_report,
        ):
            out = kernel_hooks.on_kernel_journal_transform(
                tool_name="dietcode_kernel",
                args={"action": "patch"},
                result=raw,
            )
        assert out is not None
        parsed = json.loads(out)
        self.assertTrue(parsed["ok"])
        self.assertIn("_journal_warning", parsed)


if __name__ == "__main__":
    unittest.main()
