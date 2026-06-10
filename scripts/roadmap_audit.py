#!/usr/bin/env python3
"""Production audit for roadmap checkpoint feature — modules, gates, and wiring."""
from __future__ import annotations

import importlib.util
import sys
import tempfile
import time
import types
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))

_REQUIRED = (
    "lib/agent/roadmap/gate.py",
    "lib/agent/roadmap/operator.py",
    "lib/agent/roadmap/snapshot.py",
    "lib/agent/roadmap/roadmap_core.py",
    "lib/agent/roadmap/workspace_scan.py",
    "lib/agent/roadmap/progress.py",
    "lib/agent/roadmap/workspace_state.py",
    "lib/agent/roadmap/explain_gate.py",
    "lib/tools/roadmap_tools.py",
    "lib/runtime/roadmap_hooks.py",
    "optional-skills/dietcode/auto-rolling-roadmap/SKILL.md",
)


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
    failures: list[str] = []

    for rel in _REQUIRED:
        if not (_PLUGIN_ROOT / rel).is_file():
            failures.append(f"missing required file: {rel}")

    from plugins.dietcode.lib.agent.roadmap.cockpit import build_cockpit_payload
    from plugins.dietcode.lib.agent.roadmap.gate import build_roadmap_gate_state, require_fresh_checkpoint_before_complete
    from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints
    from plugins.dietcode.lib.agent.roadmap.progress import build_progress_snapshot
    from plugins.dietcode.lib.agent.roadmap.schema import bootstrap_skeleton
    from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot, invalidate_snapshot
    from plugins.dietcode.lib.agent.roadmap import snapshot as snapshot_mod
    from plugins.dietcode.lib.agent.roadmap.workspace_state import record_file_mutation, record_validation

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# Audit\n", encoding="utf-8")
        gate = build_roadmap_gate_state(workspace=str(root))
        if "blocking_gates" not in gate:
            failures.append("gate state missing blocking_gates")
        hints = build_agent_operator_hints(workspace=str(root))
        if "slash_commands" not in hints:
            failures.append("operator hints missing slash_commands")
        snap = build_progress_snapshot(workspace=str(root))
        if snap.get("recommended_next_action") is None:
            failures.append("progress snapshot missing recommended_next_action")

        (root / "ROADMAP.md").write_text(bootstrap_skeleton(), encoding="utf-8")
        record_validation(str(root), valid=True, phase="checkpoint")
        record_file_mutation(str(root), tool="write_file", path="ROADMAP.md")
        gate2 = build_roadmap_gate_state(workspace=str(root))
        if not gate2.get("validation_pending"):
            failures.append("validation_pending not reflected in gate state")
        if gate2.get("kanban_complete_allowed"):
            failures.append("kanban_complete should block when validation_pending")
        msg = require_fresh_checkpoint_before_complete(workspace=str(root))
        if not msg:
            failures.append("require_fresh should block when validation_pending")

        invalidate_snapshot(str(root))
        snapshot_mod._CACHE.clear()
        (root / "ROADMAP.md").write_text(bootstrap_skeleton(), encoding="utf-8")
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

    if failures:
        print("FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("OK — roadmap production audit passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
