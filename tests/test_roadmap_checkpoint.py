# -*- coding: utf-8 -*-
"""Production tests for auto-rolling roadmap checkpoint feature."""
from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
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

        with tempfile.TemporaryDirectory() as session_tmp, tempfile.TemporaryDirectory() as tmp:
            os.environ["DIETCODE_SESSION_DIR"] = session_tmp
            try:
                report = format_watch_report(workspace=tmp)
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

    def test_read_state_cache(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.workspace_state import (
            invalidate_state_cache,
            read_state,
            record_validation,
        )

        with tempfile.TemporaryDirectory() as tmp:
            record_validation(tmp, valid=True, phase="checkpoint")
            invalidate_state_cache(tmp)
            first = read_state(tmp)
            second = read_state(tmp)
            self.assertEqual(first, second)
            self.assertTrue(first.get("schema_valid"))

    def test_ensure_primary_skill_fast_path(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.skill_install import ensure_primary_skill

        with tempfile.TemporaryDirectory() as tmp:
            first = ensure_primary_skill(tmp)
            self.assertTrue(first.get("ok"))
            second = ensure_primary_skill(tmp)
            self.assertTrue(any("auto-rolling-roadmap" in s for s in (second.get("skipped") or [])))

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


    def test_validate_includes_bootstrap_completeness(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            text = bootstrap_skeleton(project_hint="Demo")
            (root / "ROADMAP.md").write_text(text, encoding="utf-8")
            result = validate_roadmap(workspace=str(root))
            self.assertIn("bootstrap_completeness", result)
            self.assertIn("bootstrap_placeholder_count", result.get("validation") or {})


class RoadmapNativeBridgeTests(unittest.TestCase):
    def test_validate_roadmap_write_target_allows_workspace_root(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.native_bridge import validate_roadmap_write_target

        with tempfile.TemporaryDirectory() as tmp:
            ok = validate_roadmap_write_target(write_path="ROADMAP.md", workspace=tmp)
            self.assertTrue(ok.get("allowed"))
            self.assertIn("ROADMAP.md", ok.get("roadmap_path") or "")

    def test_validate_roadmap_write_target_rejects_outside_workspace(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.native_bridge import validate_roadmap_write_target

        with tempfile.TemporaryDirectory() as tmp:
            bad = validate_roadmap_write_target(write_path="/etc/ROADMAP.md", workspace=tmp)
            self.assertFalse(bad.get("allowed"))
            self.assertEqual(bad.get("code"), "roadmap_path_invalid")

    def test_roadmap_write_hint_includes_expected_path(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.native_bridge import roadmap_write_hint

        with tempfile.TemporaryDirectory() as tmp:
            hint = roadmap_write_hint(
                tool_name="write_file",
                args={"path": "ROADMAP.md"},
                workspace=tmp,
            )
            self.assertFalse(hint.get("write_rejected"))
            self.assertIn("ROADMAP.md", hint.get("expected_path") or "")


class RoadmapBootstrapEvidenceTests(unittest.TestCase):
    def test_bootstrap_skeleton_from_evidence(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton_from_evidence

        evidence = {
            "readmes": [{"excerpt": "# My App\n\nHandles invoices for SMBs."}],
            "git": {"recent_commits": ["a1b2c3 Add billing module"], "changed_files_recent": ["src/billing.py"]},
            "code_soup_audit": {"overall_risk": "Medium", "centralization_recommendation": "Consolidate billing helpers."},
        }
        with tempfile.TemporaryDirectory() as tmp:
            skeleton = bootstrap_skeleton_from_evidence(evidence, workspace=tmp)
            self.assertIn("My App", skeleton)
            self.assertIn("billing module", skeleton)
            self.assertIn("Medium", skeleton)
            self.assertNotIn("Describe from README and project evidence", skeleton)

    def test_find_bootstrap_placeholders(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.schema import find_bootstrap_placeholders

        sample = "## 1. Project Center of Gravity\n\nDescribe from README and project evidence\n"
        issues = find_bootstrap_placeholders(sample)
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "bootstrap_placeholder")

    def test_expanded_bootstrap_placeholders_detect_skeleton_boilerplate(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton, find_bootstrap_placeholders

        skeleton = bootstrap_skeleton(project_hint="Acme Widgets")
        issues = find_bootstrap_placeholders(skeleton)
        messages = " ".join(i.message for i in issues)
        self.assertGreaterEqual(len(issues), 6)
        self.assertIn("Preserve primary agent", messages)
        self.assertIn("Acme Widgets", skeleton)
        self.assertNotIn("Acme Widgets", messages)


class RoadmapSteeringTests(unittest.TestCase):
    def test_project_fingerprint_from_readme(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Invoice Portal\n\nSMB billing.", encoding="utf-8")
            (root / "pyproject.toml").write_text('[project]\nname = "invoice-portal"\n', encoding="utf-8")
            (root / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
            fp = build_project_fingerprint(root)
            self.assertEqual(fp["readme_title"], "Invoice Portal")
            self.assertEqual(fp["package_name"], "invoice-portal")
            self.assertIn("Invoice Portal", fp["steering_identity"])
            self.assertEqual(fp["readme_tagline"], "SMB billing.")
            self.assertIn("pytest", fp["test_frameworks"])
            self.assertTrue(fp["has_tests"])
            self.assertIn("Invoice Portal", fp["steering_brief"])

    def test_project_fingerprint_hermes_plugin_archetype(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "plugin.yaml").write_text("name: demo\n", encoding="utf-8")
            (root / "README.md").write_text("# Demo Plugin\n\nExtends Hermes.", encoding="utf-8")
            fp = build_project_fingerprint(root)
            self.assertEqual(fp["project_archetype"], "hermes-plugin")
            self.assertIn("Hermes plugin", fp["frameworks"])
            self.assertIn("Hermes plugin workspace", fp["runtime_center_hint"] or "")

    def test_bootstrap_from_evidence_uses_fingerprint(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton_from_evidence

        evidence = {
            "readmes": [{"excerpt": "# Billing API\n\nHandles invoices."}],
            "git": {"recent_commits": ["feat: billing"], "changed_files_recent": ["src/billing.py"]},
            "code_soup_audit": {"overall_risk": "Low", "centralization_recommendation": "Keep billing in src/billing."},
            "project_fingerprint": {
                "purpose_hint": "Handles invoices.",
                "operators_hint": "Finance ops and API integrators.",
                "runtime_center_hint": "FastAPI service root with Docker deploy.",
                "steering_brief": "Billing API — Python",
                "project_archetype": "web-app",
                "frameworks": ["FastAPI"],
                "test_frameworks": ["pytest"],
                "ci_systems": ["GitHub Actions"],
            },
        }
        skeleton = bootstrap_skeleton_from_evidence(evidence, workspace="/tmp/billing")
        self.assertIn("Handles invoices.", skeleton)
        self.assertIn("Finance ops and API integrators.", skeleton)
        self.assertIn("FastAPI service root", skeleton)
        self.assertNotIn("Derived from README and config evidence during bootstrap.", skeleton)


class RoadmapBootstrapFillTests(unittest.TestCase):
    def test_bootstrap_fill_plan_maps_placeholders_to_evidence(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import build_bootstrap_fill_plan
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton_from_evidence

        evidence = {
            "readmes": [{"excerpt": "# Shop\n\nE-commerce API."}],
            "git": {"recent_commits": ["feat: checkout flow"], "changed_files_recent": ["src/checkout.py"]},
            "code_soup_audit": {"overall_risk": "Low", "centralization_recommendation": "Keep checkout in src/checkout."},
            "project_fingerprint": {
                "steering_brief": "Shop — E-commerce API.",
                "purpose_hint": "E-commerce API.",
                "operators_hint": "Store operators and integrators.",
                "runtime_center_hint": "API service root with Docker deploy.",
                "project_archetype": "web-app",
                "test_frameworks": ["pytest"],
                "entry_points": ["dev", "test"],
            },
        }
        skeleton = bootstrap_skeleton_from_evidence(evidence, workspace="/tmp/shop")
        plan = build_bootstrap_fill_plan(roadmap_text=skeleton, evidence=evidence)
        self.assertGreater(plan["remaining_count"], 0)
        self.assertTrue(plan["now_suggestions"])
        tasks = plan["tasks"]
        self.assertTrue(any("Evidence-backed initial audit" in t["template_phrase"] for t in tasks))
        mapped = next(t for t in tasks if "Evidence-backed initial audit" in t["template_phrase"])
        self.assertIn("checkout", mapped["suggested_replacement"].lower())
        self.assertNotEqual(mapped["suggested_replacement"], mapped["template_phrase"])

    def test_autofilled_skeleton_fewer_placeholders(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.schema import (
            bootstrap_skeleton,
            bootstrap_skeleton_from_evidence,
            bootstrap_skeleton_from_evidence_autofilled,
            find_bootstrap_placeholders,
        )

        evidence = {
            "readmes": [{"excerpt": "# App\n\nDoes things."}],
            "git": {"recent_commits": ["abc init"]},
            "project_fingerprint": {
                "steering_brief": "App — Does things.",
                "purpose_hint": "Does things.",
                "project_archetype": "library",
            },
        }
        raw = bootstrap_skeleton_from_evidence(evidence, workspace="/tmp/app")
        filled = bootstrap_skeleton_from_evidence_autofilled(evidence, workspace="/tmp/app")
        self.assertLess(len(find_bootstrap_placeholders(filled)), len(find_bootstrap_placeholders(raw)))

    def test_fingerprint_detects_agents_md(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text("# Agent rules\n", encoding="utf-8")
            fp = build_project_fingerprint(root)
            self.assertIn("AGENTS.md", fp.get("agent_rules_files") or [])

    def test_apply_bootstrap_fill_dry_run(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import write_bootstrap_autofill
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Dry Run\n\nTest project.\n", encoding="utf-8")
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Dry Run"), encoding="utf-8")
            preview = write_bootstrap_autofill(workspace=str(root), dry_run=True)
            self.assertTrue(preview.get("ok"))
            self.assertFalse(preview.get("written"))
            self.assertGreater((preview.get("bootstrap_autofill_preview") or {}).get("applied_count", 0), 0)

    def test_fingerprint_entry_points_from_package_json(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text(
                '{"name":"demo","scripts":{"dev":"vite","test":"vitest run"}}',
                encoding="utf-8",
            )
            fp = build_project_fingerprint(root)
            self.assertIn("dev", fp.get("entry_points") or [])
            self.assertIn("test", fp.get("entry_points") or [])

    def test_apply_bootstrap_fill_draft_reduces_placeholders(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import apply_bootstrap_fill_draft, build_bootstrap_fill_plan
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton, find_bootstrap_placeholders

        skeleton = bootstrap_skeleton(project_hint="Acme App")
        evidence = {
            "project_fingerprint": {
                "steering_brief": "Acme App",
                "purpose_hint": "Acme application platform.",
                "operators_hint": "Platform operators.",
                "runtime_center_hint": "Acme monorepo root.",
                "project_archetype": "web-app",
                "test_frameworks": ["pytest"],
                "entry_points": ["dev", "test"],
            },
            "git": {"recent_commits": ["abc feat: launch"], "changed_files_recent": ["src/app.py"]},
            "code_soup_audit": {"overall_risk": "Low", "centralization_recommendation": "Keep app entry in src/app.py."},
        }
        before = len(find_bootstrap_placeholders(skeleton))
        draft = apply_bootstrap_fill_draft(skeleton, evidence)
        after = draft.get("remaining_count", before)
        self.assertGreater(draft.get("applied_count", 0), 0)
        self.assertLess(after, before)

    def test_bootstrap_fill_maps_all_placeholder_phrases(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import build_bootstrap_fill_plan
        from plugins.dietcode.lib.agent.roadmap.schema import BOOTSTRAP_PLACEHOLDER_PHRASES, bootstrap_skeleton

        skeleton = bootstrap_skeleton(project_hint="Coverage Test")
        evidence = {
            "readmes": [{"excerpt": "# Coverage Test\n\nFull coverage project."}],
            "git": {"recent_commits": ["init"], "changed_files_recent": ["src/main.py"]},
            "code_soup_audit": {"overall_risk": "Low", "centralization_recommendation": "Single src tree."},
            "project_fingerprint": {
                "steering_brief": "Coverage Test — Full coverage project.",
                "purpose_hint": "Full coverage project.",
                "operators_hint": "Engineering team.",
                "runtime_center_hint": "Repo root.",
                "project_archetype": "library",
                "test_frameworks": ["pytest"],
                "entry_points": ["test"],
            },
        }
        plan = build_bootstrap_fill_plan(roadmap_text=skeleton, evidence=evidence)
        mapped_phrases = {t["template_phrase"] for t in plan["tasks"]}
        for phrase in BOOTSTRAP_PLACEHOLDER_PHRASES:
            if phrase in skeleton:
                self.assertIn(phrase, mapped_phrases)
        manual = [t for t in plan["tasks"] if t["evidence_source"].startswith("manual")]
        self.assertEqual(len(manual), 0)
    def test_steering_context_includes_identity_and_live_parse(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton
        from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Steer Test\n", encoding="utf-8")
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Steer Test"), encoding="utf-8")
            ctx = build_steering_context(workspace=str(root))
            self.assertEqual(ctx["steering_identity"], "Steer Test")
            self.assertFalse(ctx["bootstrap_complete"])
            self.assertGreater(ctx["bootstrap_placeholder_count"], 0)
            self.assertEqual(ctx["health_status"], "Coherent")

    def test_agent_steering_line_includes_project_context(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.agent_steering import format_agent_steering_line
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Context App\n", encoding="utf-8")
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Context App"), encoding="utf-8")
            line = format_agent_steering_line(workspace=str(root))
            self.assertIn("ROADMAP live steering", line)
            self.assertIn("Project:", line)
            self.assertIn("Context App", line)
            self.assertIn("health=Coherent", line)

    def test_doctor_recommends_bootstrap_fill_when_placeholders_remain(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.doctor import run_checks
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Doctor Test"), encoding="utf-8")
            with mock.patch(
                "plugins.dietcode.lib.agent.roadmap.doctor.read_last_error",
                return_value={},
            ):
                report = run_checks(workspace=str(root))
            action = (report.get("recommended_next_action") or {}).get("action")
            self.assertEqual(action, "apply_bootstrap_fill")
            self.assertIsNotNone(report.get("bootstrap_fill_plan"))
            digest = report.get("project_steering_digest") or {}
            self.assertTrue(digest.get("steering_brief") or digest.get("bootstrap_remaining") is not None)

    def test_fingerprint_cache_returns_consistent_results(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import (
            build_project_fingerprint,
            invalidate_fingerprint_cache,
        )

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Cache Test\n", encoding="utf-8")
            fp1 = build_project_fingerprint(root)
            fp2 = build_project_fingerprint(root)
            self.assertEqual(fp1.get("readme_title"), fp2.get("readme_title"))
            (root / "README.md").write_text("# Cache Test Updated\n", encoding="utf-8")
            invalidate_fingerprint_cache(root)
            fp3 = build_project_fingerprint(root)
            self.assertEqual(fp3.get("readme_title"), "Cache Test Updated")

    def test_enrich_payload_with_bootstrap_context(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import enrich_payload_with_bootstrap_context
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Enrich Test\n", encoding="utf-8")
            skeleton = bootstrap_skeleton(project_hint="Enrich Test")
            evidence = {"project_fingerprint": {"steering_brief": "Enrich Test — library"}}
            payload = enrich_payload_with_bootstrap_context(
                {"action": "evidence"},
                roadmap_text=skeleton,
                evidence=evidence,
            )
            self.assertIn("bootstrap_fill_plan", payload)
            self.assertIn("project_steering_digest", payload)
            self.assertIn("bootstrap_autofill_preview", payload)

    def test_agent_rules_excerpt_enriches_operators_hint(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "AGENTS.md").write_text(
                "# Agents\n\nAlways run make verify before committing roadmap changes.\n",
                encoding="utf-8",
            )
            fp = build_project_fingerprint(root)
            self.assertIn("AGENTS.md", fp.get("agent_rules_files") or [])
            self.assertIn("make verify", fp.get("operators_hint") or "")

    def test_steering_digest_includes_agent_rules_and_sample_task(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_bootstrap_steering_fields
        from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Digest Test\n", encoding="utf-8")
            (root / "Makefile").write_text(".PHONY: verify test\nverify:\n\ttrue\n", encoding="utf-8")
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Digest Test"), encoding="utf-8")
            steering = build_steering_context(workspace=str(root))
            attached = attach_bootstrap_steering_fields(steering, tier="light")
            digest = attached.get("project_steering_digest") or {}
            self.assertIn("makefile_targets", digest)
            self.assertIn("sample_fill_task", digest)

    def test_explain_gate_includes_bootstrap_digest(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.explain_gate import build_explain_gate_payload
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Gate Test"), encoding="utf-8")
            payload = build_explain_gate_payload(workspace=str(root))
            self.assertIn("bootstrap_fill_plan", payload)
            self.assertIn("project_steering_digest", payload)

    def test_status_includes_bootstrap_digest(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import status_snapshot
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Status Test"), encoding="utf-8")
            payload = status_snapshot(workspace=str(root))
            self.assertIn("bootstrap_fill_plan", payload)
            self.assertIn("project_steering_digest", payload)

    def test_checkpoint_recommends_apply_bootstrap_fill(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import checkpoint_brief
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Checkpoint Test\n", encoding="utf-8")
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Checkpoint Test"), encoding="utf-8")
            brief = checkpoint_brief(workspace=str(root))
            self.assertIn(
                "apply_bootstrap_fill",
                (brief.get("bootstrap_fill_plan") or {}).get("agent_next_call") or "",
            )

    def test_catalog_metadata_in_fingerprint(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "catalog-info.yaml").write_text(
                "apiVersion: backstage.io/v1alpha1\nkind: Component\nmetadata:\n  name: my-service\n  description: Core API service\n",
                encoding="utf-8",
            )
            fp = build_project_fingerprint(root)
            self.assertTrue(fp.get("has_backstage_catalog"))
            self.assertEqual(fp.get("catalog_name"), "my-service")
            self.assertIn("Core API", fp.get("catalog_description") or fp.get("purpose_hint") or "")

    def test_validate_includes_recommended_next_action(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import validate_roadmap
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Validate Rec"), encoding="utf-8")
            payload = validate_roadmap(workspace=str(root))
            rec = payload.get("recommended_next_action") or {}
            self.assertEqual(rec.get("action"), "apply_bootstrap_fill")

    def test_template_fill_plan_recommends_autofill(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import template_brief

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Template Rec\n\nTagline for steering.\n", encoding="utf-8")
            tmpl = template_brief(workspace=str(root))
            fill_plan = tmpl.get("bootstrap_fill_plan") or {}
            self.assertIn("bootstrap_autofill_preview", tmpl)
            next_call = fill_plan.get("agent_next_call") or tmpl.get("agent_next_call") or ""
            if fill_plan.get("tasks"):
                self.assertIn("apply_bootstrap_fill", next_call)
            else:
                self.assertIn("validate", next_call)
                self.assertTrue(fill_plan.get("bootstrap_complete"))

    def test_progress_report_mentions_bootstrap_fill(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.progress import format_progress_report
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Progress Test"), encoding="utf-8")
            report = format_progress_report(workspace=str(root))
            self.assertIn("apply_bootstrap_fill", report)

    def test_native_bridge_write_hint_prioritizes_bootstrap_fill(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.native_bridge import roadmap_write_hint
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Bridge Test"), encoding="utf-8")
            hint = roadmap_write_hint(
                tool_name="write_file",
                args={"path": "ROADMAP.md"},
                workspace=str(root),
            )
            self.assertIn("apply_bootstrap_fill", hint.get("preferred_command") or "")
            self.assertIn("apply_bootstrap_fill", hint.get("next_action") or "")

    def test_fallback_replacement_uses_purpose_hint(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import build_bootstrap_fill_plan
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        skeleton = bootstrap_skeleton(project_hint="Fallback Test")
        evidence = {
            "project_fingerprint": {
                "steering_brief": "Fallback Test",
                "purpose_hint": "Unique purpose for fallback testing.",
            },
        }
        plan = build_bootstrap_fill_plan(roadmap_text=skeleton + "\nUnmapped custom phrase xyz.\n", evidence=evidence)
        unknown = [t for t in plan["tasks"] if "Unmapped custom phrase" in (t.get("template_phrase") or "")]
        if unknown:
            self.assertIn("Unique purpose", unknown[0]["suggested_replacement"])

    def test_explain_gate_report_includes_bootstrap_fill(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.explain_gate import build_explain_gate_payload
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Explain Test"), encoding="utf-8")
            payload = build_explain_gate_payload(workspace=str(root))
            self.assertIn("apply_bootstrap_fill", payload.get("report") or "")

    def test_autofill_write_marks_validation_pending(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import write_bootstrap_autofill
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton
        from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Autofill Pending\n\nPurpose line.\n", encoding="utf-8")
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Autofill Pending"), encoding="utf-8")
            result = write_bootstrap_autofill(workspace=str(root), dry_run=False)
            if result.get("written"):
                state = read_state(root)
                self.assertTrue(state.get("validation_pending"))

    def test_doctor_recommends_bootstrap_autofill(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.doctor import run_checks
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Doctor Fill"), encoding="utf-8")
            with mock.patch(
                "plugins.dietcode.lib.agent.roadmap.doctor.read_last_error",
                return_value={},
            ):
                report = run_checks(workspace=str(root))
            recs = report.get("recommendations") or []
            self.assertTrue(any("apply_bootstrap_fill" in r for r in recs))

    def test_contributing_excerpt_in_fingerprint(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "CONTRIBUTING.md").write_text(
                "# Contributing\n\nRun make verify before opening a pull request.\n",
                encoding="utf-8",
            )
            fp = build_project_fingerprint(root)
            self.assertIn("make verify", fp.get("operators_hint") or "")

    def test_steering_context_agent_next_call_bootstrap_fill(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton
        from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Steering Next"), encoding="utf-8")
            ctx = build_steering_context(workspace=str(root))
            self.assertIn("apply_bootstrap_fill", ctx.get("agent_next_call") or "")

    def test_apply_bootstrap_fill_write_includes_recommended_action(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import apply_bootstrap_fill_brief
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Apply Rec\n\nPurpose.\n", encoding="utf-8")
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Apply Rec"), encoding="utf-8")
            payload = apply_bootstrap_fill_brief(workspace=str(root), context="write")
            if payload.get("written"):
                self.assertIn("recommended_next_action", payload)
                self.assertIn("validation", payload)

    def test_explain_stale_report_includes_project(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.freshness import format_explain_stale_report

        report = format_explain_stale_report(
            {"stale": True, "reason": "test", "summary": "stale test", "recommended_action": "checkpoint"},
            steering_brief="Stale Project — library",
        )
        self.assertIn("Stale Project", report)

    def test_steering_digest_includes_agent_next_call(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_bootstrap_steering_fields
        from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Digest Call"), encoding="utf-8")
            steering = build_steering_context(workspace=str(root))
            attached = attach_bootstrap_steering_fields(steering, tier="light")
            digest = attached.get("project_steering_digest") or {}
            self.assertIn("apply_bootstrap_fill", digest.get("agent_next_call") or "")

    def test_format_doctor_report_bootstrap_hint(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.doctor import format_doctor_report
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Doctor Report"), encoding="utf-8")
            report = format_doctor_report(workspace=str(root))
            self.assertIn("Roadmap doctor", report)
            self.assertIn("apply_bootstrap_fill", report)

    def test_native_bridge_write_hint_includes_digest(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.native_bridge import roadmap_write_hint
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Bridge Digest"), encoding="utf-8")
            hint = roadmap_write_hint(
                tool_name="write_file",
                args={"path": "ROADMAP.md"},
                workspace=str(root),
            )
            digest = hint.get("project_steering_digest") or {}
            self.assertTrue(hint.get("bootstrap_incomplete"))
            self.assertTrue(digest.get("bootstrap_remaining") or digest.get("sample_fill_task"))

    def test_native_bridge_merge_propagates_digest(self) -> None:
        import json

        from plugins.dietcode.lib.agent.roadmap.native_bridge import merge_roadmap_hint_into_result, roadmap_write_hint
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text(".PHONY: verify\nverify:\n\ttrue\n", encoding="utf-8")
            (root / "ROADMAP.md").write_text(bootstrap_skeleton(project_hint="Merge Digest"), encoding="utf-8")
            hint = roadmap_write_hint(
                tool_name="write_file",
                args={"path": "ROADMAP.md"},
                workspace=str(root),
            )
            merged = json.loads(merge_roadmap_hint_into_result({"ok": True}, hint))
            self.assertIn("project_steering_digest", merged)
            self.assertIn("apply_bootstrap_fill", merged.get("agent_next_call") or "")

    def test_fingerprint_verification_commands_from_makefile(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text(".PHONY: verify test\nverify:\n\ttrue\n", encoding="utf-8")
            fp = build_project_fingerprint(root)
            self.assertIn("make verify", fp.get("verification_commands") or [])
            self.assertIn("verify", fp.get("makefile_targets") or [])

    def test_steering_digest_includes_verification_commands(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import build_project_steering_digest
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Makefile").write_text(".PHONY: verify\nverify:\n\ttrue\n", encoding="utf-8")
            fp = build_project_fingerprint(root)
            digest = build_project_steering_digest(fp)
            self.assertIn("make verify", digest.get("verification_commands") or [])

    def test_anti_goal_never_returns_placeholder_phrase(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import build_bootstrap_fill_plan

        phrase = "A fragmented patch surface without a documented center of gravity."
        plan = build_bootstrap_fill_plan(
            roadmap_text=f"# Test\n\n{phrase}\n",
            evidence={
                "project_fingerprint": {
                    "steering_brief": "Sample Project",
                    "project_archetype": "library",
                },
                "git": {},
                "code_soup_audit": {},
            },
        )
        task = (plan.get("tasks") or [{}])[0]
        self.assertNotEqual(task.get("suggested_replacement"), phrase)

    def test_fingerprint_compose_services(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "docker-compose.yml").write_text(
                "services:\n  api:\n    image: node\n  db:\n    image: postgres\n",
                encoding="utf-8",
            )
            fp = build_project_fingerprint(root)
            self.assertIn("api", fp.get("compose_services") or [])
            self.assertIn("db", fp.get("compose_services") or [])

    def test_gate_closed_bootstrap_includes_project_brief(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.gate import evaluate_gate_checks

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            closed, _open = evaluate_gate_checks({
                "workspace": str(root),
                "roadmap_present": True,
                "bootstrap_complete": False,
                "bootstrap_placeholder_count": 4,
                "project_fingerprint": {"steering_brief": "Gate Test — library"},
                "validation": {"valid": True},
                "freshness": {"stale": False},
                "workspace_state": {},
            })
            bootstrap = [g for g in closed if g.get("id") == "bootstrap_complete"]
            self.assertTrue(bootstrap)
            self.assertIn("Gate Test", bootstrap[0].get("why") or "")

    def test_fingerprint_governance_and_workspace_packages(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "SECURITY.md").write_text("# Security\n", encoding="utf-8")
            (root / "pnpm-workspace.yaml").write_text("packages:\n  - apps/web\n  - packages/ui\n", encoding="utf-8")
            fp = build_project_fingerprint(root)
            self.assertIn("SECURITY.md", fp.get("governance_files") or [])
            self.assertIn("apps/web", fp.get("workspace_packages") or [])

    def test_fallback_never_manual_source(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import build_bootstrap_fill_plan

        plan = build_bootstrap_fill_plan(
            roadmap_text="# Test\n\nTotally unknown custom phrase xyz.\n",
            evidence={
                "project_fingerprint": {"project_archetype": "library"},
                "git": {},
                "code_soup_audit": {},
            },
        )
        task = (plan.get("tasks") or [{}])[0]
        self.assertFalse(str(task.get("evidence_source") or "").startswith("manual"))

    def test_operator_hints_include_project_brief(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Hint Project\n\nTagline.\n", encoding="utf-8")
            (root / "Makefile").write_text(".PHONY: verify\nverify:\n\ttrue\n", encoding="utf-8")
            hints = build_agent_operator_hints(workspace=str(root))
            self.assertTrue(hints.get("project_steering_brief"))
            self.assertIn("make verify", hints.get("verification_commands") or [])

    def test_steering_digest_always_attached_when_bootstrap_complete(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_bootstrap_steering_fields
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton_from_evidence_autofilled

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Complete Project\n\nDone.\n", encoding="utf-8")
            from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence

            evidence = gather_evidence(root, tier="standard")
            skeleton = bootstrap_skeleton_from_evidence_autofilled(evidence, workspace=str(root))
            (root / "ROADMAP.md").write_text(skeleton, encoding="utf-8")
            from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

            steering = build_steering_context(workspace=str(root))
            attached = attach_bootstrap_steering_fields(steering, tier="light")
            digest = attached.get("project_steering_digest") or {}
            self.assertTrue(digest.get("steering_brief"))
            self.assertNotIn("bootstrap_fill_plan", attached)

    def test_fingerprint_ci_workflow_names(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            wf = root / ".github" / "workflows"
            wf.mkdir(parents=True)
            (wf / "test.yml").write_text("name: test\n", encoding="utf-8")
            fp = build_project_fingerprint(root)
            self.assertIn("test", fp.get("ci_workflow_names") or [])

    def test_steering_digest_identity_line(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import (
            build_project_steering_digest,
            format_steering_identity_line,
        )

        digest = build_project_steering_digest({
            "steering_brief": "Demo App — Python",
            "stack_summary": "Python, pytest",
            "verification_commands": ["make verify"],
            "project_archetype": "library",
        })
        self.assertIn("make verify", digest.get("identity_line") or "")
        self.assertIn("Demo App", format_steering_identity_line(digest))

    def test_evidence_action_includes_digest_without_placeholders(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import enrich_payload_with_bootstrap_context
        from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence
        from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton_from_evidence_autofilled

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "README.md").write_text("# Evidence Digest\n\nTagline.\n", encoding="utf-8")
            (root / "Makefile").write_text(".PHONY: verify\nverify:\n\ttrue\n", encoding="utf-8")
            evidence = gather_evidence(root, tier="standard")
            skeleton = bootstrap_skeleton_from_evidence_autofilled(evidence, workspace=str(root))
            (root / "ROADMAP.md").write_text(skeleton, encoding="utf-8")
            evidence = gather_evidence(root, tier="standard", roadmap_text=skeleton)
            payload = enrich_payload_with_bootstrap_context(
                {"action": "evidence", **evidence},
                evidence=evidence,
                roadmap_text=skeleton,
            )
            digest = payload.get("project_steering_digest") or {}
            self.assertTrue(digest.get("identity_line"))
            self.assertNotIn("bootstrap_fill_plan", payload)


class RoadmapWorkspaceResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.project = Path(self._tmpdir.name)

    def tearDown(self) -> None:
        self._tmpdir.cleanup()

    def test_resolve_workspace_rejects_plugin_subdir(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.config import RoadmapWorkspaceError, resolve_workspace

        with self.assertRaises(RoadmapWorkspaceError):
            resolve_workspace(explicit=str(_PLUGIN_ROOT.resolve() / "lib"))

    def test_resolve_workspace_uses_kernel_project_root(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace

        project = str(self.project)
        with mock.patch(
            "plugins.dietcode.lib.kernel_workspace.resolve_workspace_root",
            return_value=mock.Mock(resolved_workspace_root=project, resolution_detail="explicit"),
        ):
            with mock.patch(
                "plugins.dietcode.lib.kernel_workspace.is_quarantined_root",
                return_value=False,
            ):
                root, source = resolve_workspace()
        self.assertEqual(Path(root).resolve(), self.project.resolve())
        self.assertEqual(source, "explicit")

    @mock.patch.dict(os.environ, {"HERMES_KANBAN_WORKSPACE": ""}, clear=False)
    def test_resolve_workspace_skips_quarantined_kernel_candidate(self) -> None:
        from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace

        with mock.patch(
            "plugins.dietcode.lib.kernel_workspace.resolve_workspace_root",
            return_value=mock.Mock(
                resolved_workspace_root=str(_PLUGIN_ROOT),
                resolution_detail="hermes_project:quarantined_cwd",
            ),
        ):
            with mock.patch(
                "plugins.dietcode.lib.kernel_workspace.is_quarantined_root",
                return_value=True,
            ):
                with mock.patch(
                    "plugins.dietcode.lib.agent.roadmap.config._candidate_from_kanban_config",
                    return_value=(str(self.project), "kanban.workspace"),
                ):
                    with mock.patch(
                        "plugins.dietcode.lib.agent.roadmap.config._candidate_from_env",
                        return_value=(None, "env:unset"),
                    ):
                        root, source = resolve_workspace()
        self.assertEqual(Path(root).resolve(), self.project.resolve())
        self.assertEqual(source, "kanban.workspace")


class RoadmapSkillInstallTests(unittest.TestCase):
    def test_install_skill_into_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = ensure_workspace_skills(tmp)
            self.assertTrue(result["ok"])
            dest = Path(tmp) / "optional-skills" / "dietcode" / "auto-rolling-roadmap" / "SKILL.md"
            self.assertTrue(dest.is_file())


if __name__ == "__main__":
    unittest.main()
