# -*- coding: utf-8 -*-
"""Kernel verify → JoyZoning journal tests (Phase 4)."""
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

import plugins.dietcode.lib.agent.kernel_verify_journal as kvj  # noqa: E402
from plugins.dietcode.lib.agent.joyzoning.config import JoyZoningConfig  # noqa: E402
from plugins.dietcode.lib.runtime import kernel_hooks  # noqa: E402


def _verify_result(*, passed: bool = True, task_id: str = "task_1") -> dict:
    return {
        "ok": True,
        "action": "verify",
        "verify_ran": True,
        "passed": passed,
        "taskId": task_id,
        "workspace_root": "/tmp/project",
        "command": "./verify.sh",
        "exit_code": 0 if passed else 1,
        "stdout_summary": "all good" if passed else "",
        "stderr_summary": "" if passed else "failed",
        "kernel": {"passed": passed, "exitCode": 0 if passed else 1},
    }


class KernelVerifyJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        kvj.reset_verify_journal_dedup_cache()

    def test_verify_success_records_mutation_verify(self) -> None:
        cfg = JoyZoningConfig(enabled=True)
        result = _verify_result(passed=True)
        mock_journal = mock.MagicMock()
        mock_journal.get_active_mutation.return_value = {"id": "mut_abc", "state": "patching"}

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
                        "plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle.record_verification",
                        return_value={"success": True},
                    ) as record:
                        report = kvj.journal_kernel_verify(
                            tool_name="dietcode_kernel",
                            args={"action": "verify"},
                            result=result,
                        )

        self.assertTrue(report["journaled"])
        record.assert_called_once()
        self.assertTrue(record.call_args.kwargs.get("passed"))

    def test_verify_failure_records_failed_verification(self) -> None:
        cfg = JoyZoningConfig(enabled=True)
        result = _verify_result(passed=False)
        mock_journal = mock.MagicMock()
        mock_journal.get_active_mutation.return_value = {"id": "mut_abc", "state": "patching"}

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
                        "plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle.record_verification",
                        return_value={"success": True},
                    ) as record:
                        report = kvj.journal_kernel_verify(
                            tool_name="dietcode_kernel",
                            args={"action": "verify"},
                            result=result,
                        )

        self.assertTrue(report["journaled"])
        self.assertFalse(record.call_args.kwargs.get("passed"))

    def test_missing_task_id_handled_safely(self) -> None:
        cfg = JoyZoningConfig(enabled=True)
        result = _verify_result(task_id="")
        result["taskId"] = None
        mock_journal = mock.MagicMock()
        mock_journal.get_active_mutation.return_value = {"id": "mut_abc", "state": "patching"}

        with mock.patch(
            "plugins.dietcode.lib.agent.joyzoning.config.get_joyzoning_config",
            return_value=cfg,
        ):
            with mock.patch(
                "plugins.dietcode.lib.agent.joyzoning.config.resolve_scope_id",
                return_value="default_scope",
            ):
                with mock.patch(
                    "plugins.dietcode.lib.agent.joyzoning.journal.get_journal",
                    return_value=mock_journal,
                ):
                    with mock.patch(
                        "plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle.record_verification",
                        return_value={"success": True},
                    ):
                        report = kvj.journal_kernel_verify(
                            tool_name="dietcode_kernel",
                            args={"action": "verify"},
                            result=result,
                        )
        self.assertTrue(report["journaled"])

    def test_non_allowlisted_command_not_journaled(self) -> None:
        report = kvj.journal_kernel_verify(
            tool_name="dietcode_kernel",
            args={"action": "verify"},
            result={
                "ok": False,
                "action": "verify",
                "verify_ran": False,
                "string_code": "bridge_verify_command_rejected",
            },
        )
        self.assertTrue(report.get("skipped"))

    def test_journal_failure_returns_warning_not_failure(self) -> None:
        cfg = JoyZoningConfig(enabled=True)
        raw = json.dumps(_verify_result())
        mock_journal = mock.MagicMock()
        mock_journal.get_active_mutation.return_value = {"id": "mut_abc", "state": "patching"}

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
                        "plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle.record_verification",
                        side_effect=RuntimeError("journal offline"),
                    ):
                        report = kvj.journal_kernel_verify(
                            tool_name="dietcode_kernel",
                            args={"action": "verify"},
                            result=raw,
                        )

        self.assertIn("warning", report)
        merged = kvj.merge_journal_warning_into_result(raw, report)
        assert merged is not None
        parsed = json.loads(merged)
        self.assertTrue(parsed["ok"])
        self.assertIn("_journal_warning", parsed)

    def test_transform_hook_journals_verify(self) -> None:
        cfg = JoyZoningConfig(enabled=True)
        raw = json.dumps(_verify_result())
        mock_journal = mock.MagicMock()
        mock_journal.get_active_mutation.return_value = {"id": "mut_abc", "state": "patching"}

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
                        "plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle.record_verification",
                        return_value={"success": True},
                    ):
                        kernel_hooks.on_kernel_journal_transform(
                            tool_name="dietcode_kernel",
                            args={"action": "verify"},
                            result=raw,
                        )


if __name__ == "__main__":
    unittest.main()
