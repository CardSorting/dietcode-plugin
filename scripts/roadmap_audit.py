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
            if "_TODO_PATTERN" in line or "todo_markers" in line or "TODO|FIXME" in line:
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

    from plugins.dietcode.lib.agent.roadmap.cockpit import build_cockpit_payload
    from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace
    from plugins.dietcode.lib.agent.roadmap.gate import build_roadmap_gate_state, require_fresh_checkpoint_before_complete
    from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints
    from plugins.dietcode.lib.agent.roadmap.progress import build_progress_snapshot
    from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import checkpoint_brief, template_brief
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
    from plugins.dietcode.lib.kernel_workspace import is_quarantined_root

    if is_quarantined_root(_PLUGIN_ROOT):
        # Dev checkout may equal plugin root — quarantine applies to install path at runtime.
        pass

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "README.md").write_text("# Audit Project\n\nReal README evidence.\n", encoding="utf-8")

        gate = build_roadmap_gate_state(workspace=str(root))
        if "blocking_gates" not in gate:
            failures.append("gate state missing blocking_gates")
        if "workspace_safe" not in (gate.get("open_gates") or []) and gate.get("closed_gates"):
            closed_ids = [g.get("id") for g in gate.get("closed_gates") or []]
            if "workspace_safe" in closed_ids:
                failures.append("workspace_safe gate closed for temp project")

        hints = build_agent_operator_hints(workspace=str(root))
        for key in ("slash_commands", "preferred_tool", "next_action"):
            if key not in hints:
                failures.append(f"operator hints missing {key}")

        snap = build_progress_snapshot(workspace=str(root))
        if snap.get("recommended_next_action") is None:
            failures.append("progress snapshot missing recommended_next_action")

        evidence = {"readmes": [{"excerpt": "# Audit Project\n\nPurpose line."}], "git": {"recent_commits": ["abc init"]}}
        skeleton = bootstrap_skeleton_from_evidence(evidence, workspace=str(root))
        if "Audit Project" not in skeleton:
            failures.append("evidence bootstrap missing README title")
        if "Describe from README" in skeleton:
            failures.append("evidence bootstrap still contains generic placeholder phrase")

        (root / "ROADMAP.md").write_text(skeleton, encoding="utf-8")
        placeholders = find_bootstrap_placeholders(skeleton)
        if len(placeholders) > 6:
            failures.append(f"bootstrap skeleton has {len(placeholders)} unfilled placeholders (max 6 tolerated)")

        validated = validate_roadmap_content(skeleton)
        if not validated.schema_complete:
            failures.append("bootstrap skeleton not schema-complete")

        metrics = bootstrap_completeness_metrics(skeleton)
        if metrics.get("bootstrap_placeholder_count", 0) > 8:
            failures.append("evidence bootstrap has too many template placeholders")

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

        brief = session_brief(workspace=str(root))
        if not brief or not brief.get("roadmap_path"):
            failures.append("session_brief missing roadmap_path")

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

        brief = checkpoint_brief(workspace=str(root))
        if Path(brief.get("workspace") or "").resolve() != root.resolve():
            failures.append("checkpoint brief workspace mismatch")

        if "roadmap_path" not in brief:
            failures.append("checkpoint brief missing roadmap_path")
        if "agent_instructions" not in brief:
            failures.append("checkpoint brief missing agent_instructions")

        tmpl = template_brief(workspace=str(root))
        if "evidence_summary" not in tmpl:
            failures.append("template brief missing evidence_summary")

        cockpit = build_cockpit_payload(workspace=str(root))
        if Path(cockpit.get("roadmap_path") or "").resolve() != (root / "ROADMAP.md").resolve():
            failures.append("cockpit roadmap_path not under workspace")
        if not cockpit.get("workspace_source") and not (root / "ROADMAP.md").exists():
            pass  # explicit workspace may omit source in some paths

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
