#!/usr/bin/env python3
"""Operator ergonomics smoke — cockpit, explain_gate, workspace state, joyzoning delegation."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import types
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


def main() -> int:
    _bootstrap()
    from plugins.dietcode.lib.agent.roadmap.agent_steering import format_agent_steering_line
    from plugins.dietcode.lib.agent.roadmap.cockpit import build_cockpit_payload, format_cockpit_report
    from plugins.dietcode.lib.agent.roadmap.explain_gate import build_explain_gate_payload
    from plugins.dietcode.lib.agent.roadmap.gate import build_roadmap_gate_state
    from plugins.dietcode.lib.agent.roadmap.phase_guide import clarity_envelope, determine_phase
    from plugins.dietcode.lib.agent.roadmap.progress import build_progress_snapshot
    from plugins.dietcode.lib.agent.roadmap.operator import recommend_next_action
    from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import checkpoint_brief, validate_roadmap
    from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton
    from plugins.dietcode.lib.agent.roadmap.session import session_brief
    from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state
    from plugins.dietcode.prompts import build_dietcode_guidance

    failures: list[str] = []

    rec = recommend_next_action(roadmap_exists=False)
    if rec.get("action") != "bootstrap_roadmap":
        failures.append(f"recommend_next_action bootstrap: {rec}")

    guidance = build_dietcode_guidance({"roadmap"})
    if "ROADMAP live steering" not in guidance:
        failures.append("build_dietcode_guidance missing live steering block")

    fill = determine_phase(
        roadmap_exists=True,
        sections_missing=[],
        health_status="Coherent",
        bootstrap_incomplete=True,
    )
    if fill.get("phase") != "bootstrap_fill":
        failures.append("determine_phase bootstrap_fill mismatch")

    rec_fill = recommend_next_action(
        phase="bootstrap_fill",
        roadmap_exists=True,
        schema_valid=True,
        bootstrap_incomplete=True,
    )
    if rec_fill.get("action") != "apply_bootstrap_fill":
        failures.append(f"recommend_next_action bootstrap_fill: {rec_fill}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# Operator smoke\n", encoding="utf-8")

        cockpit = build_cockpit_payload(workspace=str(root))
        if not cockpit.get("recommended_next_action"):
            failures.append("cockpit missing recommended_next_action")
        if not cockpit.get("steering_line"):
            failures.append("cockpit missing steering_line")

        report = format_cockpit_report(workspace=str(root))
        if "Write guard:" not in report:
            failures.append("cockpit report missing write guard")

        gate = build_explain_gate_payload(workspace=str(root))
        if gate.get("action") != "explain_gate":
            failures.append("explain_gate action mismatch")
        if "gates_closed" not in gate:
            failures.append("explain_gate missing gates_closed")

        gate_state = build_roadmap_gate_state(workspace=str(root))
        if "kanban_complete_allowed" not in gate_state:
            failures.append("gate_state missing kanban_complete_allowed")

        snap = build_progress_snapshot(workspace=str(root))
        if "current_path" not in snap:
            failures.append("progress snapshot missing current_path")
        if not snap.get("roadmap_path"):
            failures.append("progress snapshot missing roadmap_path")

        brief = session_brief(workspace=str(root))
        if not brief or not brief.get("recommended_next_action"):
            failures.append("session_brief missing recommended_next_action")
        if not brief.get("_roadmap_operator_hints"):
            failures.append("session_brief missing _roadmap_operator_hints")
        if not brief.get("steering_line"):
            failures.append("session_brief missing steering_line")

        brief_ckpt = checkpoint_brief(workspace=str(root))
        if not brief_ckpt.get("steering_line"):
            failures.append("checkpoint_brief missing steering_line")
        if "open_todo_marker_count" not in brief_ckpt:
            failures.append("checkpoint_brief missing open_todo_marker_count")

        line = format_agent_steering_line(workspace=str(root))
        if "ROADMAP live steering" not in line:
            failures.append("format_agent_steering_line missing header")

        envelope = clarity_envelope({"action": "guide", "workspace": str(root)})
        if not envelope.get("steering_line"):
            failures.append("clarity_envelope missing steering_line")
        if not envelope.get("project_identity_line"):
            failures.append("clarity_envelope missing project_identity_line")
        if not brief_ckpt.get("project_identity_line"):
            failures.append("checkpoint_brief missing project_identity_line")

        (root / "ROADMAP.md").write_text(bootstrap_skeleton(), encoding="utf-8")
        validated = validate_roadmap(workspace=str(root))
        if not (validated.get("validation") or {}).get("valid"):
            failures.append("validate failed on bootstrap skeleton")

        state = read_state(root)
        if not state.get("schema_valid"):
            failures.append("workspace state not persisted after validate")

        try:
            from plugins.dietcode.lib.agent.joyzoning.workflow import build_operational_context

            ctx = build_operational_context()
            if "roadmap_checkpoint" not in ctx:
                failures.append("joyzoning context missing roadmap_checkpoint")
            if brief and brief.get("steering_line") and not ctx.get("roadmap_steering_line"):
                failures.append("joyzoning context missing roadmap_steering_line")
            if (brief or {}).get("project_steering_digest") and not ctx.get("project_steering_digest"):
                failures.append("joyzoning context missing project_steering_digest")
            if (brief or {}).get("project_steering_digest") and not ctx.get("project_identity_line"):
                failures.append("joyzoning context missing project_identity_line")
        except ImportError:
            pass

        delegated = build_cockpit_payload(workspace=str(root))
        if not delegated.get("cockpit"):
            failures.append("joyzoning roadmap delegation payload missing cockpit flag")

    if failures:
        print("FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("OK — roadmap operator ergonomics smoke passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
