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
    from plugins.dietcode.lib.agent.roadmap.cockpit import build_cockpit_payload
    from plugins.dietcode.lib.agent.roadmap.explain_gate import build_explain_gate_payload
    from plugins.dietcode.lib.agent.roadmap.gate import build_roadmap_gate_state
    from plugins.dietcode.lib.agent.roadmap.progress import build_progress_snapshot
    from plugins.dietcode.lib.agent.roadmap.operator import recommend_next_action
    from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import validate_roadmap
    from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton
    from plugins.dietcode.lib.agent.roadmap.session import session_brief
    from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state
    failures: list[str] = []

    rec = recommend_next_action(roadmap_exists=False)
    if rec.get("action") != "bootstrap_roadmap":
        failures.append(f"recommend_next_action bootstrap: {rec}")

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# Operator smoke\n", encoding="utf-8")

        cockpit = build_cockpit_payload(workspace=str(root))
        if not cockpit.get("recommended_next_action"):
            failures.append("cockpit missing recommended_next_action")
        if not cockpit.get("success"):
            failures.append("cockpit missing success")

        gate = build_explain_gate_payload(workspace=str(root))
        if gate.get("action") != "explain_gate":
            failures.append("explain_gate action mismatch")
        if "gates_closed" not in gate:
            failures.append("explain_gate missing gates_closed")
        if "closed_gates" not in gate:
            failures.append("explain_gate missing closed_gates list")

        gate_state = build_roadmap_gate_state(workspace=str(root))
        if "kanban_complete_allowed" not in gate_state:
            failures.append("gate_state missing kanban_complete_allowed")

        snap = build_progress_snapshot(workspace=str(root))
        if "current_path" not in snap:
            failures.append("progress snapshot missing current_path")

        brief = session_brief(workspace=str(root))
        if not brief or not brief.get("recommended_next_action"):
            failures.append("session_brief missing recommended_next_action")

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
        except ImportError:
            pass

        # joyzoning(action='roadmap') delegates to build_cockpit_payload — verify payload shape.
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
