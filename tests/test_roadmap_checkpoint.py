# -*- coding: utf-8 -*-
"""Production tests for auto-rolling roadmap checkpoint feature."""
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

from plugins.dietcode.lib.agent.roadmap.code_soup_audit import assess_code_soup
from plugins.dietcode.lib.agent.roadmap.cockpit import build_cockpit_payload, format_cockpit_report
from plugins.dietcode.lib.agent.roadmap.doctor import run_checks
from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence, parse_roadmap
from plugins.dietcode.lib.agent.roadmap.phase_guide import clarity_envelope, determine_phase
from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import (
    checkpoint_brief,
    operational_status,
    status_snapshot,
    template_brief,
    validate_roadmap,
)
from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton, validate_roadmap_content
from plugins.dietcode.lib.agent.roadmap.errors import error_envelope
from plugins.dietcode.lib.agent.roadmap.freshness import assess_checkpoint_freshness
from plugins.dietcode.lib.agent.roadmap.progress import emit_progress, format_watch_report, read_tail
from plugins.dietcode.lib.agent.roadmap.native_bridge import (
    merge_roadmap_hint_into_result,
    targets_roadmap_file,
)
from plugins.dietcode.lib.agent.roadmap.explain_gate import build_explain_gate_payload
from plugins.dietcode.lib.agent.roadmap.gate import build_roadmap_gate_state, require_fresh_checkpoint_before_complete
from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints, recommend_next_action
from plugins.dietcode.lib.agent.roadmap.session import session_brief
from plugins.dietcode.lib.agent.roadmap.skill_install import ensure_workspace_skills
from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state, record_file_mutation, record_validation


_SAMPLE_ROADMAP = """\
# ROADMAP.md

## 1. Project Center of Gravity

**Core Purpose:**  
Test project steering.

**What This Project Must Not Become:**  
A scattered script pile.

## 2. Roadmap Health

**Status:** Coherent

**Summary:**  
Stable.

## 4. Now

### 1. Ship feature

**Goal:**  
Deliver value.

## 9. Centralization & Code Soup Audit

**Overall Code Soup Risk:** Low

## 11. Recent Checkpoint

**Date:** 2026-06-01

**Code Soup Risk:** Low
"""


class RoadmapSchemaTests(unittest.TestCase):
    def test_bootstrap_skeleton_has_all_sections(self) -> None:
        skeleton = bootstrap_skeleton(project_hint="Test")
        for section in (
            "1. Project Center of Gravity",
            "9. Centralization & Code Soup Audit",
            "12. Archive",
        ):
            self.assertIn(section, skeleton)

    def test_validate_detects_missing_anti_goals(self) -> None:
        bad = "## 1. Project Center of Gravity\n\n**Core Purpose:** x\n"
        result = validate_roadmap_content(bad)
        self.assertFalse(result.valid)
        self.assertTrue(any(i.code == "missing_anti_goals" for i in result.issues))

    def test_validate_now_overload(self) -> None:
        now_items = "\n".join(f"### {i}. Item {i}\n" for i in range(1, 7))
        content = _SAMPLE_ROADMAP.replace("## 4. Now\n\n### 1. Ship feature", f"## 4. Now\n\n{now_items}")
        result = validate_roadmap_content(content)
        self.assertEqual(result.now_item_count, 6)
        self.assertTrue(any(i.code == "now_overloaded" for i in result.issues))


class RoadmapParseTests(unittest.TestCase):
    def test_parse_existing_roadmap(self) -> None:
        parsed = parse_roadmap(_SAMPLE_ROADMAP, path="ROADMAP.md")
        self.assertTrue(parsed.exists)
        self.assertEqual(parsed.health_status, "Coherent")
        self.assertEqual(parsed.code_soup_risk, "Low")
        self.assertEqual(parsed.now_item_count, 1)

    def test_phase_determination(self) -> None:
        phase = determine_phase(roadmap_exists=False, sections_missing=[], health_status=None)
        self.assertEqual(phase["phase"], "bootstrap")


class RoadmapEvidenceTests(unittest.TestCase):
    def test_gather_evidence_in_temp_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Test\nA sample project.", encoding="utf-8")
            (root / "ROADMAP.md").write_text(_SAMPLE_ROADMAP, encoding="utf-8")
            (root / "main.py").write_text("# TODO: finish roadmap tests\n", encoding="utf-8")

            evidence = gather_evidence(root, context_hint="unit test")
            self.assertEqual(evidence["workspace"], str(root.resolve()))
            self.assertTrue(evidence["roadmap"]["exists"])
            self.assertGreaterEqual(len(evidence["readmes"]), 1)
            self.assertIn("code_soup_audit", evidence)
            self.assertGreaterEqual(evidence["test_file_count"], 0)


class RoadmapCodeSoupTests(unittest.TestCase):
    def test_assess_plugin_workspace(self) -> None:
        audit = assess_code_soup(_PLUGIN_ROOT)
        self.assertIn(audit["overall_risk"], {"Low", "Medium", "High"})
        self.assertIn("centralization_recommendation", audit)


class RoadmapCheckpointTests(unittest.TestCase):
    def test_operational_status_bootstrap(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = operational_status(workspace=tmp)
            self.assertEqual(status["phase"], "bootstrap")
            self.assertIn("_roadmap_operator_hints", status)
            self.assertIn("agent_playbook", status)

    def test_checkpoint_brief_includes_pre_audit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Demo", encoding="utf-8")
            brief = checkpoint_brief(workspace=str(root), context="initial pass")
            self.assertEqual(brief["action"], "checkpoint")
            self.assertGreaterEqual(len(brief["algorithm_steps"]), 16)
            self.assertIn("code_soup_pre_audit", brief)
            self.assertIn("suggested_bootstrap", brief)

    def test_validate_and_template(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skeleton = bootstrap_skeleton()
            (root / "ROADMAP.md").write_text(skeleton, encoding="utf-8")
            validated = validate_roadmap(workspace=str(root))
            self.assertTrue((validated.get("validation") or {}).get("valid"))
            template = template_brief(workspace=str(root))
            self.assertIn("skeleton", template)


class RoadmapOperatorUxTests(unittest.TestCase):
    def test_cockpit_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = format_cockpit_report(workspace=tmp)
            self.assertIn("Roadmap cockpit", report)
            payload = build_cockpit_payload(workspace=tmp)
            self.assertIn("agent_next_call", payload)

    def test_doctor_installs_skill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            ensure_workspace_skills(tmp)
            doctor = run_checks(workspace=tmp)
            self.assertTrue(any(c["name"] == "workspace_skill_installed" for c in doctor["checks"]))

    def test_clarity_envelope(self) -> None:
        wrapped = clarity_envelope({"skill_path": "optional-skills/dietcode/auto-rolling-roadmap/SKILL.md"})
        self.assertIn("_roadmap_operator_hints", wrapped)


class RoadmapProgressTests(unittest.TestCase):
    def test_emit_and_read_progress(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DIETCODE_SESSION_DIR"] = tmp
            try:
                emit_progress("roadmap.test", action="guide", success=True)
                events = read_tail(lines=5)
                self.assertGreaterEqual(len(events), 1)
                self.assertEqual(events[-1].get("phase"), "roadmap.test")
            finally:
                os.environ.pop("DIETCODE_SESSION_DIR", None)

    def test_watch_report_idle(self) -> None:
        import os
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DIETCODE_SESSION_DIR"] = tmp
            try:
                report = format_watch_report()
                self.assertIn("idle", report.lower())
            finally:
                os.environ.pop("DIETCODE_SESSION_DIR", None)


class RoadmapFreshnessTests(unittest.TestCase):
    def test_stale_with_old_checkpoint_and_git(self) -> None:
        fresh = assess_checkpoint_freshness(
            recent_checkpoint_date="2020-01-01",
            git_commits=["a", "b", "c", "d"],
            stale_days=7,
        )
        self.assertTrue(fresh["stale"])
        self.assertEqual(fresh["reason"], "checkpoint_older_than_git_activity")

    def test_fresh_recent_checkpoint(self) -> None:
        from datetime import datetime, timezone

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        fresh = assess_checkpoint_freshness(
            recent_checkpoint_date=today,
            git_commits=["a"],
            stale_days=7,
        )
        self.assertFalse(fresh["stale"])


class RoadmapErrorTests(unittest.TestCase):
    def test_error_envelope_shape(self) -> None:
        env = error_envelope(code="unknown_action", message="bad", action="nope")
        self.assertFalse(env["success"])
        self.assertIn("_roadmap_operator_hints", env)
        self.assertIn("retry_command", env)


class RoadmapNativeIntegrationTests(unittest.TestCase):
    def test_targets_roadmap_file(self) -> None:
        self.assertTrue(targets_roadmap_file(tool_name="write_file", args={"path": "ROADMAP.md"}))
        self.assertFalse(targets_roadmap_file(tool_name="write_file", args={"path": "README.md"}))

    def test_merge_write_hint(self) -> None:
        raw = merge_roadmap_hint_into_result('{"success": true}', {"next_action": "validate"})
        self.assertIn("_roadmap_write_hint", raw)

    def test_session_brief_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brief = session_brief(workspace=tmp)
            self.assertIsNotNone(brief)
            assert brief is not None
            self.assertIn("phase", brief)
            self.assertIn("first_call", brief)

    def test_write_transform_hook(self) -> None:
        from plugins.dietcode.lib.runtime.roadmap_hooks import on_roadmap_write_transform

        out = on_roadmap_write_transform(
            tool_name="write_file",
            args={"path": "ROADMAP.md"},
            result='{"success": true}',
        )
        self.assertIsNotNone(out)
        assert out is not None
        self.assertIn("_roadmap_write_hint", out)


class RoadmapOperatorModuleTests(unittest.TestCase):
    def test_recommend_bootstrap_when_missing(self) -> None:
        rec = recommend_next_action(roadmap_exists=False)
        self.assertEqual(rec["action"], "bootstrap_roadmap")

    def test_recommend_stale_when_outdated(self) -> None:
        rec = recommend_next_action(
            roadmap_exists=True,
            schema_valid=True,
            stale=True,
            phase="checkpoint",
        )
        self.assertEqual(rec["action"], "run explain-gate")
        self.assertIn("explain-gate", rec["command"])

    def test_workspace_state_persists_validation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record_validation(tmp, valid=True, health_status="Coherent", phase="checkpoint")
            state = read_state(tmp)
            self.assertTrue(state.get("schema_valid"))
            self.assertIn("last_validated_at", state)

    def test_explain_gate_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Demo", encoding="utf-8")
            payload = build_explain_gate_payload(workspace=str(root))
            self.assertEqual(payload["action"], "explain_gate")
            self.assertIn("gates_closed", payload)
            self.assertIn("closed_gates", payload)
            self.assertIn("open_gates", payload)
            self.assertIn("report", payload)

    def test_file_mutation_marks_validation_pending(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            record_validation(tmp, valid=True, phase="checkpoint")
            record_file_mutation(tmp, tool="write_file", path="ROADMAP.md")
            state = read_state(tmp)
            self.assertTrue(state.get("validation_pending"))
            self.assertIsNone(state.get("schema_valid"))

    def test_operational_status_includes_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            status = operational_status(workspace=tmp)
            self.assertIn("roadmap_gate", status)
            self.assertIn("recommended_next_action", status)

    def test_last_error_enriched(self) -> None:
        import os

        with tempfile.TemporaryDirectory() as tmp:
            os.environ["DIETCODE_SESSION_DIR"] = tmp
            try:
                from plugins.dietcode.lib.agent.roadmap.progress import emit_progress, read_last_error

                emit_progress(
                    "roadmap.validated",
                    action="validate",
                    success=False,
                    payload={"validation": {"valid": False}},
                )
                err = read_last_error()
                self.assertEqual(err.get("string_code"), "validate.failed")
                self.assertIn("retry_command", err)
            finally:
                os.environ.pop("DIETCODE_SESSION_DIR", None)

    def test_validation_pending_blocks_kanban(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(), encoding="utf-8")
            record_validation(str(root), valid=True, phase="checkpoint")
            record_file_mutation(str(root), tool="write_file", path="ROADMAP.md")
            state = build_roadmap_gate_state(workspace=str(root))
            self.assertTrue(state.get("validation_pending"))
            self.assertFalse(state.get("kanban_complete_allowed"))
            msg = require_fresh_checkpoint_before_complete(workspace=str(root))
            self.assertIsNotNone(msg)

    def test_agent_operator_hints(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints

        with tempfile.TemporaryDirectory() as tmp:
            hints = build_agent_operator_hints(workspace=tmp)
            self.assertIn("slash_commands", hints)
            self.assertIn("kanban_complete_allowed", hints)

    def test_progress_snapshot_includes_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            from plugins.dietcode.lib.agent.roadmap.progress import build_progress_snapshot

            snap = build_progress_snapshot(workspace=tmp)
            self.assertIn("roadmap_gate", snap)
            self.assertIn("recommended_next_action", snap)
            self.assertIn("kanban_complete_allowed", snap)

    def test_require_fresh_blocks_invalid_schema_when_configured(self) -> None:
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text("## incomplete\n", encoding="utf-8")
            with patch(
                "plugins.dietcode.lib.agent.roadmap.config.RoadmapConfig.load",
                return_value=type("C", (), {
                    "enabled": True,
                    "warn_on_stale_before_complete": False,
                    "block_kanban_on_invalid_schema": True,
                    "stale_checkpoint_days": 7,
                })(),
            ):
                msg = require_fresh_checkpoint_before_complete(workspace=str(root))
                self.assertIsNotNone(msg)
                self.assertIn("explain-gate", msg or "")

    def test_gate_state_stale_blocks_kanban(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_roadmap = _SAMPLE_ROADMAP.replace("**Date:** 2026-06-01", "**Date:** 2020-01-01")
            (root / "ROADMAP.md").write_text(old_roadmap, encoding="utf-8")
            for i in range(5):
                (root / f"file{i}.py").write_text(f"# module {i}\n", encoding="utf-8")
            state = build_roadmap_gate_state(workspace=str(root))
            self.assertTrue(state.get("checkpoint_stale"))
            self.assertFalse(state.get("kanban_complete_allowed"))
            msg = require_fresh_checkpoint_before_complete(workspace=str(root))
            self.assertIsNotNone(msg)
            self.assertIn("explain-gate", msg or "")

    def test_validate_records_workspace_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(), encoding="utf-8")
            validate_roadmap(workspace=str(root))
            state = read_state(root)
            self.assertTrue(state.get("schema_valid"))

    def test_gather_evidence_light_tier_skips_heavy_scans(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(), encoding="utf-8")
            evidence = gather_evidence(root, tier="light")
            self.assertEqual(evidence.get("evidence_tier"), "light")
            self.assertEqual(evidence.get("todo_markers"), [])
            self.assertNotIn("code_soup_audit", evidence)

    def test_snapshot_cache_reuses_gate_state(self) -> None:
        from plugins.dietcode.lib.agent.roadmap import snapshot as snapshot_mod
        from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot, invalidate_snapshot

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(), encoding="utf-8")
            invalidate_snapshot(root)
            snapshot_mod._CACHE.clear()
            first = get_workspace_snapshot(root, tier="light")
            second = get_workspace_snapshot(root, tier="light")
            self.assertIs(first, second)
            invalidate_snapshot(root)
            third = get_workspace_snapshot(root, tier="light", force_refresh=True)
            self.assertIsNot(third, first)

    def test_roadmap_core_cache_reuses_validation(self) -> None:
        from plugins.dietcode.lib.agent.roadmap import roadmap_core as core_mod
        from plugins.dietcode.lib.agent.roadmap.roadmap_core import invalidate_roadmap_core, read_roadmap_core

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(), encoding="utf-8")
            invalidate_roadmap_core(root)
            core_mod._CACHE.clear()
            first = read_roadmap_core(root)
            second = read_roadmap_core(root)
            self.assertIs(first, second)
            self.assertTrue(first.validation.valid)

    def test_extend_evidence_skips_reparse(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.evidence import extend_evidence, gather_evidence

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(), encoding="utf-8")
            light = gather_evidence(root, tier="light")
            full = extend_evidence(light, tier="full")
            self.assertEqual(full.get("roadmap"), light.get("roadmap"))
            self.assertEqual(full.get("git"), light.get("git"))
            self.assertIn("code_soup_audit", full)

    def test_heavy_scan_cache_reuses_walk(self) -> None:
        from plugins.dietcode.lib.agent.roadmap import workspace_scan as scan_mod
        from plugins.dietcode.lib.agent.roadmap.workspace_scan import get_heavy_scan, invalidate_heavy_scan

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "sample.py").write_text("# TODO: optimize\n", encoding="utf-8")
            invalidate_heavy_scan(root)
            scan_mod._HEAVY_CACHE.clear()
            first = get_heavy_scan(root)
            second = get_heavy_scan(root)
            self.assertIs(first, second)
            self.assertGreaterEqual(len(first.todo_markers), 1)

    def test_snapshot_tier_promotion_from_light(self) -> None:
        from plugins.dietcode.lib.agent.roadmap import snapshot as snapshot_mod
        from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot, invalidate_snapshot

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(), encoding="utf-8")
            invalidate_snapshot(root)
            snapshot_mod._CACHE.clear()
            light = get_workspace_snapshot(root, tier="light")
            full = get_workspace_snapshot(root, tier="full")
            self.assertIs(light.gate_state, full.gate_state)
            self.assertEqual(light.roadmap_text, full.roadmap_text)
            self.assertIn("code_soup_audit", full.evidence)

    def test_cockpit_recommended_next_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            payload = build_cockpit_payload(workspace=tmp)
            self.assertIn("recommended_next_action", payload)
            self.assertTrue(payload.get("success"))

    def test_clarity_envelope_success_defaults(self) -> None:
        wrapped = clarity_envelope({})
        self.assertTrue(wrapped.get("success"))
        self.assertTrue(wrapped.get("ok"))

    def test_session_brief_recommended_action(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            brief = session_brief(workspace=tmp)
            assert brief is not None
            self.assertIn("recommended_next_action", brief)


class RoadmapSkillInstallTests(unittest.TestCase):
    def test_install_skill_into_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = ensure_workspace_skills(tmp)
            self.assertTrue(result["ok"])
            dest = Path(tmp) / "optional-skills" / "dietcode" / "auto-rolling-roadmap" / "SKILL.md"
            self.assertTrue(dest.is_file())


if __name__ == "__main__":
    unittest.main()
