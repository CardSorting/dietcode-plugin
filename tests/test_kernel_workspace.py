# -*- coding: utf-8 -*-
"""Workspace-root boundary tests for kernel bridge prep (Phase 1.5)."""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Standalone import without Hermes bootstrap
_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

from lib import kernel_workspace as kw  # noqa: E402


class KernelWorkspaceResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self._tmpdir.name) / "hermes-project"
        self.project.mkdir()
        self.plugin_root = _PLUGIN_ROOT.resolve()
        self.kernel_root = (self.plugin_root / "kernel").resolve()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_validate_rejects_plugin_root(self) -> None:
        result = kw.validate_workspace_root(
            self.plugin_root,
            plugin_root=self.plugin_root,
            kernel_root=self.kernel_root,
        )
        self.assertFalse(result.ok)
        self.assertFalse(result.safe_for_mutation)
        self.assertFalse(result.checks["not_plugin_root"])
        self.assertIn("plugin_root", result.errors[0])

    def test_validate_rejects_kernel_root(self) -> None:
        result = kw.validate_workspace_root(
            self.kernel_root,
            plugin_root=self.plugin_root,
            kernel_root=self.kernel_root,
        )
        self.assertFalse(result.ok)
        self.assertFalse(result.safe_for_mutation)
        self.assertFalse(result.checks["not_kernel_root"])
        self.assertIn("kernel", result.errors[0].lower())

    def test_validate_accepts_writable_project_dir(self) -> None:
        result = kw.validate_workspace_root(
            self.project,
            plugin_root=self.plugin_root,
            kernel_root=self.kernel_root,
        )
        self.assertTrue(result.ok)
        self.assertTrue(result.safe_for_mutation)

    def test_validate_rejects_missing_path(self) -> None:
        missing = self.project / "does-not-exist"
        result = kw.validate_workspace_root(
            missing,
            plugin_root=self.plugin_root,
            kernel_root=self.kernel_root,
        )
        self.assertFalse(result.ok)
        self.assertFalse(result.checks["exists"])

    def test_is_quarantined_root(self) -> None:
        self.assertTrue(kw.is_quarantined_root(self.plugin_root))
        self.assertTrue(kw.is_quarantined_root(self.kernel_root))
        self.assertFalse(kw.is_quarantined_root(self.project))

    @mock.patch.dict(os.environ, {"DIETCODE_WORKSPACE_ROOT": ""}, clear=False)
    def test_env_source_unset(self) -> None:
        path, detail = kw.resolve_workspace_root_path(source=kw.SOURCE_ENV_DIETCODE)
        self.assertIsNone(path)
        self.assertIn("unset", detail)

    @mock.patch.dict(os.environ, {"DIETCODE_WORKSPACE_ROOT": ""}, clear=False)
    def test_env_source_resolves(self) -> None:
        with mock.patch.dict(os.environ, {"DIETCODE_WORKSPACE_ROOT": str(self.project)}):
            path, detail = kw.resolve_workspace_root_path(source=kw.SOURCE_ENV_DIETCODE)
        self.assertEqual(path, self.project.resolve())
        self.assertEqual(detail, kw.SOURCE_ENV_DIETCODE)

    def test_explicit_source_from_config(self) -> None:
        with mock.patch(
            "lib.kernel_workspace._load_kernel_config",
            return_value={"workspace_root": str(self.project)},
        ):
            path, detail = kw.resolve_workspace_root_path(source=kw.SOURCE_EXPLICIT)
        self.assertEqual(path, self.project.resolve())
        self.assertEqual(detail, kw.SOURCE_EXPLICIT)

    def test_explicit_source_unset(self) -> None:
        with mock.patch("lib.kernel_workspace._load_kernel_config", return_value={}):
            path, detail = kw.resolve_workspace_root_path(source=kw.SOURCE_EXPLICIT)
        self.assertIsNone(path)
        self.assertIn("unset", detail)

    @mock.patch.dict(os.environ, {"HERMES_KANBAN_WORKSPACE": ""}, clear=False)
    def test_hermes_project_uses_cwd_when_unset(self) -> None:
        with tempfile.TemporaryDirectory() as other:
            other_path = Path(other).resolve()
            with mock.patch.object(Path, "cwd", return_value=other_path):
                path, detail = kw.resolve_workspace_root_path(source=kw.SOURCE_HERMES_PROJECT)
            self.assertEqual(path, other_path)
            self.assertEqual(detail, "hermes_project:cwd")

    def test_resolve_workspace_root_rejects_kernel_via_cwd(self) -> None:
        with mock.patch.object(kw, "get_workspace_root_source", return_value=kw.SOURCE_HERMES_PROJECT):
            with mock.patch.object(Path, "cwd", return_value=self.kernel_root):
                path, detail = kw.resolve_workspace_root_path(source=kw.SOURCE_HERMES_PROJECT)
        self.assertIsNone(path)
        self.assertEqual(detail, "hermes_project:quarantined_cwd")

    def test_is_quarantined_root_subdir_of_plugin(self) -> None:
        nested = self.plugin_root / "lib" / "agent"
        self.assertTrue(kw.is_quarantined_root(nested))

    def test_resolve_workspace_root_accepts_external_project(self) -> None:
        with mock.patch.object(kw, "get_workspace_root_source", return_value=kw.SOURCE_EXPLICIT):
            with mock.patch(
                "lib.kernel_workspace.get_explicit_workspace_root_config",
                return_value=str(self.project),
            ):
                report = kw.resolve_workspace_root()
        self.assertTrue(report.safe_for_mutation)
        self.assertEqual(report.resolved_workspace_root, str(self.project.resolve()))


if __name__ == "__main__":
    unittest.main()
