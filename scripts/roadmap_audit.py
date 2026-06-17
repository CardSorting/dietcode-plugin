#!/usr/bin/env python3
"""Production audit for roadmap checkpoint — wiring, workspace boundaries, and ergonomics."""
from __future__ import annotations

import importlib.util
import re
import sys
import tempfile
import time
import types
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

_REQUIRED = (
    "lib/agent/roadmap/config.py",
    "lib/agent/roadmap/steering_context.py",
    "lib/agent/roadmap/agent_steering.py",
    "lib/agent/roadmap/bootstrap_fill.py",
    "lib/agent/roadmap/project_fingerprint.py",
    "lib/agent/roadmap/phase_guide.py",
    "lib/agent/roadmap/native_bridge.py",
    "lib/agent/roadmap/gate.py",
    "lib/agent/roadmap/operator.py",
    "lib/agent/roadmap/snapshot.py",
    "lib/agent/roadmap/roadmap_core.py",
    "lib/agent/roadmap/workspace_scan.py",
    "lib/agent/roadmap/progress.py",
    "lib/agent/roadmap/workspace_state.py",
    "lib/agent/roadmap/explain_gate.py",
    "lib/agent/roadmap/schema.py",
    "lib/agent/roadmap/roadmap_checkpoint.py",
    "lib/tools/roadmap_tools.py",
    "lib/runtime/roadmap_hooks.py",
    "lib/runtime/hook_registry.py",
    "lib/runtime/hook_guards.py",
    "lib/runtime/command_registry.py",
    "lib/agent/gates/kanban_complete.py",
    "lib/agent/features.py",
    "lib/agent/config_hub.py",
    "lib/agent/self_check.py",
    "lib/agent/production_audit.py",
    "lib/agent/ergonomics.py",
    "hooks.py",
    "prompts.py",
    "optional-skills/dietcode/auto-rolling-roadmap/SKILL.md",
)

_FORBIDDEN_IN_PRODUCTION = re.compile(
    r"\b(mock|stub|placeholder|simulated|not implemented|TODO implement)\b",
    re.IGNORECASE,
)

_ROADMAP_PY_GLOB = "lib/agent/roadmap/*.py"


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


def _scan_production_sources() -> list[str]:
    """Flag mock/stub/placeholder language in roadmap production modules."""
    issues: list[str] = []
    for path in sorted(_PLUGIN_ROOT.glob(_ROADMAP_PY_GLOB)):
        text = path.read_text(encoding="utf-8", errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if "bootstrap_placeholder" in line or "find_bootstrap_placeholders" in line:
                continue
            if "unfilled bootstrap" in line.lower():
                continue
            if "bootstrap_complete" in line or "placeholder guidance" in line:
                continue
            if "_TODO_PATTERN" in line or "todo_markers" in line or "TODO|FIXME" in line:
                continue
            if "manual — review bootstrap_fill_plan" in line:
                continue
            if _FORBIDDEN_IN_PRODUCTION.search(line):
                issues.append(f"{path.relative_to(_PLUGIN_ROOT)}:{i}: {stripped[:100]}")
    return issues


def main() -> int:
    _bootstrap()
    failures: list[str] = []

    for rel in _REQUIRED:
        if not (_PLUGIN_ROOT / rel).is_file():
            failures.append(f"missing required file: {rel}")

    for hit in _scan_production_sources():
        failures.append(f"production language audit: {hit}")

    from plugins.dietcode.lib.agent.production_audit import run_production_hardening_audit

    hardening = run_production_hardening_audit(root=_PLUGIN_ROOT)
    if not hardening.get("ok"):
        for item in hardening.get("failures") or []:
            failures.append(f"production hardening: {item}")

    from plugins.dietcode.lib.agent.roadmap.cockpit import build_cockpit_payload, format_cockpit_report
    from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace
    from plugins.dietcode.lib.agent.roadmap.explain_gate import build_explain_gate_payload
    from plugins.dietcode.lib.agent.roadmap.gate import build_roadmap_gate_state, require_fresh_checkpoint_before_complete
    from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints
    from plugins.dietcode.lib.agent.roadmap.phase_guide import clarity_envelope
    from plugins.dietcode.lib.agent.roadmap.progress import build_progress_snapshot
    from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import (
        apply_bootstrap_fill_brief,
        checkpoint_brief,
        template_brief,
        validate_roadmap,
        operational_status,
        status_snapshot,
    )
    from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import apply_bootstrap_fill_draft
    from plugins.dietcode.lib.agent.roadmap.native_bridge import (
        validate_roadmap_write_target,
    )
    from plugins.dietcode.lib.agent.roadmap.schema import (
        bootstrap_completeness_metrics,
        bootstrap_skeleton_from_evidence,
        find_bootstrap_placeholders,
        validate_roadmap_content,
    )
    from plugins.dietcode.lib.agent.roadmap.session import session_brief
    from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context
    from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot, invalidate_snapshot
    from plugins.dietcode.lib.agent.roadmap import snapshot as snapshot_mod
    from plugins.dietcode.lib.agent.roadmap.workspace_state import record_file_mutation, record_validation
    from plugins.dietcode.lib.workspace_root import is_quarantined_root

    if is_quarantined_root(_PLUGIN_ROOT):
        # Dev checkout may equal plugin root — quarantine applies to install path at runtime.
        pass

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# Audit Project\n\nPurpose line.\n", encoding="utf-8")
        (root / "AGENTS.md").write_text("# Agents\n\nRun make verify before roadmap checkpoint closes.\n", encoding="utf-8")
        (root / "Makefile").write_text(".PHONY: verify test\nverify:\n\ttrue\n", encoding="utf-8")

        gate = build_roadmap_gate_state(workspace=str(root))
        if "blocking_gates" not in gate:
            failures.append("gate state missing blocking_gates")
        if "workspace_safe" not in (gate.get("open_gates") or []) and gate.get("closed_gates"):
            closed_ids = [g.get("id") for g in gate.get("closed_gates") or []]
            if "workspace_safe" in closed_ids:
                failures.append("workspace_safe gate closed for temp project")

        hints = build_agent_operator_hints(workspace=str(root))
        for key in ("slash_commands", "preferred_tool", "next_action", "write_guard", "roadmap_path"):
            if key not in hints:
                failures.append(f"operator hints missing {key}")

        snap = build_progress_snapshot(workspace=str(root))
        if snap.get("recommended_next_action") is None:
            failures.append("progress snapshot missing recommended_next_action")
        if not snap.get("roadmap_path"):
            failures.append("progress snapshot missing roadmap_path")

        evidence = {"readmes": [{"excerpt": "# Audit Project\n\nPurpose line."}], "git": {"recent_commits": ["abc init"]}}
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        evidence["project_fingerprint"] = build_project_fingerprint(root)
        skeleton = bootstrap_skeleton_from_evidence(evidence, workspace=str(root))
        if "Audit Project" not in skeleton:
            failures.append("evidence bootstrap missing README title")
        if "Describe from README" in skeleton:
            failures.append("evidence bootstrap still contains generic placeholder phrase")
        if "Purpose line" not in skeleton:
            failures.append("evidence bootstrap should include README tagline in purpose")

        validated = validate_roadmap_content(skeleton)
        if not validated.schema_complete:
            failures.append("bootstrap skeleton not schema-complete")

        (root / "ROADMAP.md").write_text(
            skeleton + "\n\nDescribe from README and project evidence\n",
            encoding="utf-8",
        )
        placeholders = find_bootstrap_placeholders(skeleton)
        if len(placeholders) < 3:
            failures.append("bootstrap skeleton should retain some template guidance or autofill reduces all phrases")
        autofill = apply_bootstrap_fill_draft(skeleton, evidence)
        if autofill.get("applied_count", 0) < 3:
            failures.append("bootstrap autofill should apply multiple evidence replacements")
        if metrics := bootstrap_completeness_metrics(skeleton):
            if metrics.get("bootstrap_complete"):
                failures.append("evidence bootstrap skeleton must not report bootstrap_complete before agent fill pass")

        reject = validate_roadmap_write_target(
            write_path="/Users/bozoegg/.hermes/plugins/dietcode/ROADMAP.md",
            workspace=str(root),
        )
        if reject.get("allowed"):
            failures.append("should reject ROADMAP write to plugin-style absolute path outside workspace")

        ok_write = validate_roadmap_write_target(write_path="ROADMAP.md", workspace=str(root))
        if not ok_write.get("allowed"):
            failures.append(f"should allow ROADMAP.md at workspace root: {ok_write.get('error')}")

        steering = build_steering_context(workspace=str(root))
        if Path(steering.get("roadmap_path") or "").resolve() != (root / "ROADMAP.md").resolve():
            failures.append("steering context roadmap_path mismatch")
        if not steering.get("steering_identity"):
            failures.append("steering context missing steering_identity")
        if not steering.get("steering_brief"):
            failures.append("steering context missing steering_brief")

        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint, invalidate_fingerprint_cache

        fp = build_project_fingerprint(root)
        if fp.get("readme_title") != "Audit Project":
            failures.append("fingerprint should read README title")
        if not fp.get("steering_brief"):
            failures.append("fingerprint missing steering_brief")
        if "AGENTS.md" not in (fp.get("agent_rules_files") or []):
            failures.append("fingerprint should detect AGENTS.md")
        if not fp.get("makefile_targets"):
            failures.append("fingerprint should detect Makefile targets")
        if "make verify" not in (fp.get("verification_commands") or []):
            failures.append("fingerprint missing make verify from Makefile targets")
        (root / "biome.json").write_text("{}", encoding="utf-8")
        invalidate_fingerprint_cache(root)
        fp_lint = build_project_fingerprint(root)
        if "Biome" not in (fp_lint.get("quality_tools") or []):
            failures.append("fingerprint should detect Biome from biome.json")
        (root / "SECURITY.md").write_text("# Security\n", encoding="utf-8")
        fp_sec = build_project_fingerprint(root)
        if "SECURITY.md" not in (fp_sec.get("governance_files") or []):
            failures.append("fingerprint should detect SECURITY.md governance file")
        wf_dir = root / ".github" / "workflows"
        wf_dir.mkdir(parents=True, exist_ok=True)
        (wf_dir / "ci.yml").write_text("name: ci\n", encoding="utf-8")
        invalidate_fingerprint_cache(root)
        fp_ci = build_project_fingerprint(root)
        if "ci" not in (fp_ci.get("ci_workflow_names") or []):
            failures.append("fingerprint should detect GitHub workflow names")
        if fp.get("project_archetype") not in {"project", "library", "application", "web-app", "cli-tool", "hermes-plugin", "monorepo"}:
            failures.append(f"unexpected project_archetype: {fp.get('project_archetype')}")
        roadmap_text = (root / "ROADMAP.md").read_text(encoding="utf-8")
        ph_issues = find_bootstrap_placeholders(roadmap_text)
        if len(ph_issues) < 5:
            failures.append("expanded bootstrap placeholder detection too weak for skeleton boilerplate")
        boilerplate_markers = (
            "Preserve primary agent",
            "Evidence-backed initial audit",
            "Insufficient evidence during first pass",
            "Review Now items",
        )
        if not any(any(m in (i.message or "") for m in boilerplate_markers) for i in ph_issues):
            failures.append("bootstrap detection missing skeleton boilerplate phrases")

        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import build_bootstrap_fill_plan

        fill_plan = build_bootstrap_fill_plan(roadmap_text=roadmap_text, evidence=evidence)
        if not fill_plan.get("tasks"):
            failures.append("bootstrap_fill_plan should produce tasks for skeleton placeholders")
        if not fill_plan.get("now_suggestions"):
            failures.append("bootstrap_fill_plan missing now_suggestions")
        if not fill_plan.get("project_brief"):
            failures.append("bootstrap_fill_plan missing project_brief")
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import build_project_steering_digest

        digest = build_project_steering_digest(fp, fill_plan=fill_plan)
        if fill_plan.get("tasks") and not digest.get("agent_next_call"):
            failures.append("steering digest missing agent_next_call")

        from plugins.dietcode.lib.agent.roadmap.doctor import format_doctor_report, run_checks

        dr = run_checks(workspace=str(root))
        if not dr.get("recommended_next_action"):
            failures.append("doctor missing recommended_next_action")
        if not dr.get("project_identity_line"):
            failures.append("doctor missing project_identity_line")
        if "apply_bootstrap_fill" not in format_doctor_report(workspace=str(root)):
            failures.append("doctor report missing bootstrap fill hint")

        from plugins.dietcode.lib.agent.roadmap.evidence import extend_evidence

        extended = extend_evidence(
            {"workspace": str(root), "evidence_tier": "light", "git": evidence.get("git") or {}, "roadmap": evidence.get("roadmap") or {}},
            tier="standard",
        )
        if not extended.get("project_fingerprint"):
            failures.append("extend_evidence missing project_fingerprint")
        if not extended.get("project_steering_digest"):
            failures.append("extend_evidence missing project_steering_digest")
        if not extended.get("project_identity_line"):
            failures.append("extend_evidence missing project_identity_line")

        from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence

        gathered = gather_evidence(root, tier="standard")
        if not gathered.get("project_steering_digest"):
            failures.append("gather_evidence missing project_steering_digest")
        if not gathered.get("project_identity_line"):
            failures.append("gather_evidence missing project_identity_line")

        brief = session_brief(workspace=str(root))
        if not brief or not brief.get("roadmap_path"):
            failures.append("session_brief missing roadmap_path")
        if not (brief or {}).get("_roadmap_operator_hints"):
            failures.append("session_brief missing _roadmap_operator_hints")
        if not (brief or {}).get("steering_line"):
            failures.append("session_brief missing steering_line")
        if not (brief or {}).get("project_steering_digest"):
            failures.append("session_brief missing project_steering_digest")
        if not brief.get("project_identity_line"):
            failures.append("session_brief missing project_identity_line")
        if not ((brief or {}).get("project_steering_digest") or {}).get("identity_line"):
            failures.append("session_brief digest missing identity_line")

        from plugins.dietcode.lib.agent.roadmap.schema import BOOTSTRAP_PLACEHOLDER_PHRASES

        minimal_evidence = {
            "project_fingerprint": {
                "steering_brief": "Audit Project — test stack",
                "purpose_hint": "Purpose line.",
                "project_archetype": "library",
            },
            "git": {"recent_commits": [], "changed_files_recent": []},
            "code_soup_audit": {"overall_risk": "Low", "signals": []},
        }
        for phrase in BOOTSTRAP_PLACEHOLDER_PHRASES:
            plan = build_bootstrap_fill_plan(
                roadmap_text=f"# Test\n\n{phrase}\n",
                evidence=minimal_evidence,
            )
            tasks = plan.get("tasks") or []
            if not tasks:
                failures.append(f"bootstrap fill plan missing task for phrase: {phrase[:60]}")
                continue
            task = tasks[0]
            if (task.get("suggested_replacement") or "") == phrase:
                failures.append(f"bootstrap phrase unmapped (same text): {phrase[:60]}")
            if str(task.get("evidence_source") or "").startswith("manual"):
                failures.append(f"bootstrap phrase manual-only: {phrase[:60]}")

        hints = build_agent_operator_hints(workspace=str(root))
        if not hints.get("project_steering_brief"):
            failures.append("operator hints missing project_steering_brief")
        if not hints.get("project_identity_line"):
            failures.append("operator hints missing project_identity_line")
        if "make verify" not in (hints.get("verification_commands") or []):
            failures.append("operator hints missing verification_commands")

        import json as _json
        from plugins.dietcode.lib.agent.roadmap.native_bridge import merge_roadmap_hint_into_result, roadmap_write_hint

        write_hint = roadmap_write_hint(
            tool_name="write_file",
            args={"path": "ROADMAP.md"},
            workspace=str(root),
        )
        merged = _json.loads(merge_roadmap_hint_into_result({"ok": True}, write_hint))
        if not merged.get("project_steering_digest"):
            failures.append("merge_roadmap_hint missing top-level project_steering_digest")
        if write_hint.get("bootstrap_incomplete") and not merged.get("agent_next_call"):
            failures.append("merge_roadmap_hint missing agent_next_call when bootstrap incomplete")

        from plugins.dietcode.lib.agent.roadmap.agent_steering import format_agent_steering_line

        steering_line = format_agent_steering_line(workspace=str(root))
        if "ROADMAP live steering" not in steering_line:
            failures.append("agent_steering line missing live steering header")
        if "Project:" not in steering_line:
            failures.append("agent_steering line missing project identity")
        if "apply_bootstrap_fill" not in steering_line:
            failures.append("agent_steering line missing apply_bootstrap_fill hint when bootstrap incomplete")

        validated = validate_roadmap(workspace=str(root))
        from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state

        state = read_state(root)
        if validated.get("validation", {}).get("bootstrap_complete") is False and state.get("phase") != "bootstrap_fill":
            failures.append("validate should persist bootstrap_fill phase when placeholders remain")

        fill_ckpt = checkpoint_brief(workspace=str(root), context="apply autofill preview")
        if "bootstrap_fill_plan" not in fill_ckpt:
            failures.append("checkpoint bootstrap_fill missing bootstrap_fill_plan")
        if "bootstrap_autofill_preview" not in fill_ckpt:
            failures.append("checkpoint bootstrap_fill missing bootstrap_autofill_preview")
        if "project_steering_digest" not in fill_ckpt:
            failures.append("checkpoint bootstrap_fill missing project_steering_digest")
        if "apply_bootstrap_fill" not in str((fill_ckpt.get("bootstrap_fill_plan") or {}).get("agent_next_call") or ""):
            failures.append("checkpoint bootstrap_fill plan should recommend apply_bootstrap_fill")

        status = status_snapshot(workspace=str(root))
        if not status.get("project_steering_digest"):
            failures.append("status missing project_steering_digest")
        if not (status.get("project_steering_digest") or {}).get("identity_line"):
            failures.append("status digest missing identity_line")

        validated2 = validate_roadmap(workspace=str(root))
        if "bootstrap_fill_plan" not in validated2:
            failures.append("validate should include bootstrap_fill_plan when placeholders remain")
        if not validated2.get("project_steering_digest"):
            failures.append("validate missing project_steering_digest")
        if not validated2.get("project_identity_line"):
            failures.append("validate missing project_identity_line")
        if not (validated2.get("project_steering_digest") or {}).get("identity_line"):
            failures.append("validate digest missing identity_line")
        if "recommended_next_action" not in validated2:
            failures.append("validate missing recommended_next_action")
        rec = validated2.get("recommended_next_action") or {}
        if rec.get("action") != "apply_bootstrap_fill":
            failures.append(f"validate bootstrap_fill recommended action: {rec}")

        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import enrich_payload_with_bootstrap_context

        ev_payload = enrich_payload_with_bootstrap_context(
            {"action": "evidence", **evidence},
            evidence=evidence,
            roadmap_text=roadmap_text,
        )
        if ev_payload.get("action") != "evidence":
            failures.append("evidence action mismatch")
        if "bootstrap_fill_plan" not in ev_payload:
            failures.append("evidence action missing bootstrap_fill_plan when placeholders remain")
        if not ev_payload.get("project_steering_digest"):
            failures.append("evidence action missing project_steering_digest when placeholders remain")

        fp2 = build_project_fingerprint(root)
        if fp2.get("readme_title") != fp.get("readme_title"):
            failures.append("fingerprint cache returned inconsistent readme_title")

        tmpl = template_brief(workspace=str(root))
        if "bootstrap_autofill_preview" not in tmpl:
            failures.append("template brief missing bootstrap_autofill_preview")
        if not (tmpl.get("project_steering_digest") or {}).get("steering_brief"):
            failures.append("template brief missing steering digest")
        fill_plan = tmpl.get("bootstrap_fill_plan") or {}
        if fill_plan.get("tasks"):
            if "apply_bootstrap_fill" not in str(fill_plan.get("agent_next_call") or ""):
                failures.append("template brief fill plan should recommend apply_bootstrap_fill")
        elif not fill_plan.get("bootstrap_complete"):
            failures.append("template brief should report bootstrap_complete when skeleton has no remaining phrases")

        record_validation(str(root), valid=True, phase="checkpoint")
        record_file_mutation(str(root), tool="write_file", path="ROADMAP.md")
        gate2 = build_roadmap_gate_state(workspace=str(root))
        if not gate2.get("validation_pending"):
            failures.append("validation_pending not reflected in gate state")
        if gate2.get("kanban_complete_allowed"):
            failures.append("kanban_complete should block when validation_pending")
        if gate2.get("bootstrap_complete") is not False:
            failures.append("live bootstrap scan should detect placeholders before validate")
        msg = require_fresh_checkpoint_before_complete(workspace=str(root))
        if not msg:
            failures.append("require_fresh should block when validation_pending")

        brief = checkpoint_brief(workspace=str(root))
        if Path(brief.get("workspace") or "").resolve() != root.resolve():
            failures.append("checkpoint brief workspace mismatch")

        for key in ("roadmap_path", "agent_instructions", "steering_line", "open_todo_marker_count", "project_fingerprint"):
            if key not in brief:
                failures.append(f"checkpoint brief missing {key}")
        if not brief.get("project_identity_line"):
            failures.append("checkpoint brief missing project_identity_line")

        tmpl2 = template_brief(workspace=str(root))
        if "evidence_summary" not in tmpl2:
            failures.append("template brief missing evidence_summary")

        guide = clarity_envelope({"action": "guide", "workspace": str(root)})
        if not guide.get("steering_line"):
            failures.append("clarity_envelope missing steering_line")
        if not guide.get("project_identity_line"):
            failures.append("clarity_envelope missing project_identity_line")
        if not (guide.get("_roadmap_operator_hints") or {}).get("write_guard"):
            failures.append("clarity_envelope missing write_guard hint")
        op_status = operational_status(workspace=str(root))
        if not op_status.get("project_steering_digest"):
            failures.append("guide/operational_status missing project_steering_digest")
        if not (op_status.get("project_steering_digest") or {}).get("identity_line"):
            failures.append("guide missing identity_line in digest")

        preview_fill = apply_bootstrap_fill_brief(workspace=str(root), context="preview")
        if preview_fill.get("action") != "apply_bootstrap_fill":
            failures.append("apply_bootstrap_fill action mismatch")
        if "bootstrap_autofill_preview" not in preview_fill:
            failures.append("apply_bootstrap_fill preview missing autofill preview")

        explain = build_explain_gate_payload(workspace=str(root))
        if not explain.get("roadmap_path"):
            failures.append("explain_gate missing roadmap_path")
        if "bootstrap_incomplete" not in (explain.get("gates_closed") or {}):
            failures.append("explain_gate gates_closed missing bootstrap_incomplete")
        if "bootstrap_fill_plan" not in explain:
            failures.append("explain_gate missing bootstrap_fill_plan when placeholders remain")
        if not (explain.get("project_steering_digest") or {}).get("sample_fill_task"):
            failures.append("explain_gate digest missing sample_fill_task")

        prog = build_progress_snapshot(workspace=str(root))
        if not prog.get("project_steering_digest"):
            failures.append("progress missing project_steering_digest")
        if not prog.get("project_identity_line"):
            failures.append("progress missing project_identity_line")

        if not (explain.get("project_steering_digest") or {}).get("steering_brief"):
            failures.append("explain_gate missing project_steering_digest steering_brief")

        auto_ckpt = checkpoint_brief(workspace=str(root), context="apply autofill write")
        if "bootstrap_autofill_applied" not in auto_ckpt:
            failures.append("checkpoint context auto-apply missing bootstrap_autofill_applied")
        from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state

        ws_after_autofill = read_state(root)
        if auto_ckpt.get("bootstrap_autofill_applied", {}).get("written") and not ws_after_autofill.get("validation_pending"):
            failures.append("autofill write should mark validation_pending via record_file_mutation")

        cockpit = build_cockpit_payload(workspace=str(root))
        if Path(cockpit.get("roadmap_path") or "").resolve() != (root / "ROADMAP.md").resolve():
            failures.append("cockpit roadmap_path not under workspace")
        if not (cockpit.get("project_steering_digest") or {}).get("identity_line"):
            failures.append("cockpit missing identity_line in digest")
        if not cockpit.get("steering_line"):
            failures.append("cockpit payload missing steering_line")
        report = format_cockpit_report(workspace=str(root))
        if "Write guard:" not in report:
            failures.append("cockpit report missing write guard line")
        if "→" not in report:
            failures.append("cockpit report missing operator next action arrow")

        import os

        from plugins.dietcode.lib.runtime.roadmap_hooks import _pre_tool_call

        prev_ws = os.environ.get("HERMES_KANBAN_WORKSPACE")
        os.environ["HERMES_KANBAN_WORKSPACE"] = str(root)
        try:
            block = _pre_tool_call(
                tool_name="write_file",
                args={"path": "/Users/bozoegg/.hermes/plugins/dietcode/ROADMAP.md"},
            )
            if not block or block.get("action") != "block":
                failures.append("pre_tool_call should block ROADMAP write outside workspace")
            allow = _pre_tool_call(tool_name="write_file", args={"path": "ROADMAP.md"})
            if allow is not None:
                failures.append("pre_tool_call should allow ROADMAP.md at workspace root")
        finally:
            if prev_ws is None:
                os.environ.pop("HERMES_KANBAN_WORKSPACE", None)
            else:
                os.environ["HERMES_KANBAN_WORKSPACE"] = prev_ws

        from plugins.dietcode.lib.runtime.hook_registry import HOOK_CHAINS

        pre_specs = HOOK_CHAINS.get("pre_tool_call", ())
        if not any("roadmap_hooks" in module for module, _ in pre_specs):
            failures.append("hook_registry missing roadmap pre_tool_call registration")

        from importlib.util import module_from_spec, spec_from_file_location

        wf_path = _PLUGIN_ROOT / "lib/agent/joyzoning/workflow.py"
        wf_spec = spec_from_file_location("roadmap_audit_jz_workflow", wf_path)
        assert wf_spec is not None and wf_spec.loader is not None
        wf_mod = module_from_spec(wf_spec)
        wf_spec.loader.exec_module(wf_mod)
        merged = wf_mod._merge_steering_next_actions(
            ["joyzoning(action='begin')"],
            roadmap_brief={
                "enabled": True,
                "roadmap_path": str(root / "ROADMAP.md"),
                "roadmap_exists": True,
                "bootstrap_complete": False,
                "steering_line": steering_line,
                "phase": "bootstrap_fill",
                "first_call": "roadmap(action='checkpoint')",
                "project_steering_digest": {"bootstrap_remaining": fill_plan.get("remaining_count", 1)},
            },
        )
        if not any("ROADMAP.md lives at" in h for h in merged):
            failures.append("joyzoning merge missing roadmap_path hint")
        if not any("apply_bootstrap_fill" in h for h in merged):
            failures.append("joyzoning merge missing bootstrap fill hint")

        merged2 = wf_mod._merge_steering_next_actions(
            ["joyzoning(action='begin')"],
            roadmap_brief={
                "enabled": True,
                "roadmap_path": str(root / "ROADMAP.md"),
                "roadmap_exists": True,
                "recommended_next_action": {
                    "action": "apply_bootstrap_fill",
                    "command": "roadmap(action='apply_bootstrap_fill', context='write')",
                },
                "first_call": "roadmap(action='apply_bootstrap_fill', context='write')",
            },
        )
        if not any("apply_bootstrap_fill" in h for h in merged2):
            failures.append("joyzoning merge missing apply_bootstrap_fill from recommended_next_action")

        merged3 = wf_mod._merge_steering_next_actions(
            ["joyzoning(action='begin')"],
            roadmap_brief={
                "enabled": True,
                "project_steering_digest": {"verification_commands": ["make verify"], "bootstrap_remaining": 2},
            },
        )
        if not any("Project verify:" in h for h in merged3):
            failures.append("joyzoning merge missing project verify hint from digest")

        from plugins.dietcode.lib.agent.roadmap.gate import evaluate_gate_checks

        gate_inputs = {
            "workspace": str(root),
            "roadmap_present": True,
            "bootstrap_complete": False,
            "bootstrap_placeholder_count": fill_plan.get("remaining_count", 3),
            "project_fingerprint": fp,
            "validation": {"valid": False},
            "freshness": {"stale": False},
            "workspace_state": {},
        }
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config

        gate_inputs["config"] = get_roadmap_config()
        closed_gates, _open = evaluate_gate_checks(gate_inputs)
        bootstrap_closed = [g for g in closed_gates if g.get("id") == "bootstrap_complete"]
        if not bootstrap_closed:
            failures.append("gate audit expected closed bootstrap_complete gate")
        elif "Audit Project" not in str(bootstrap_closed[0].get("why") or ""):
            failures.append("bootstrap gate why should include project steering brief")
        schema_closed = [g for g in closed_gates if g.get("id") == "schema_valid"]
        if schema_closed and "apply_bootstrap_fill" not in str(schema_closed[0].get("fix") or ""):
            failures.append("schema gate fix should prioritize bootstrap fill when placeholders remain")

        invalidate_snapshot(str(root))
        snapshot_mod._CACHE.clear()
        t0 = time.perf_counter()
        build_cockpit_payload(workspace=str(root))
        cold_ms = (time.perf_counter() - t0) * 1000
        t1 = time.perf_counter()
        build_cockpit_payload(workspace=str(root))
        warm_ms = (time.perf_counter() - t1) * 1000
        cached = get_workspace_snapshot(str(root), tier="full")
        if not cached.gate_state:
            failures.append("cached snapshot missing gate_state")
        if warm_ms >= cold_ms and cold_ms > 1.0:
            failures.append(f"snapshot cache not faster (cold={cold_ms:.1f}ms warm={warm_ms:.1f}ms)")

        _, source = resolve_workspace(explicit=str(root))
        if source != "explicit":
            failures.append(f"resolve_workspace explicit source mismatch: {source}")

    if failures:
        print("FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("OK — roadmap production audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
