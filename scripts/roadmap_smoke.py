#!/usr/bin/env python3
"""Smoke checks for roadmap checkpoint feature — no live ROADMAP.md mutation required."""
from __future__ import annotations

import importlib.util
import json
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
    from plugins.dietcode.lib.agent.roadmap.cockpit import format_cockpit_report
    from plugins.dietcode.lib.agent.roadmap.doctor import run_checks
    from plugins.dietcode.lib.agent.roadmap.freshness import assess_checkpoint_freshness
    from plugins.dietcode.lib.agent.roadmap.progress import emit_progress, read_tail
    from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import checkpoint_brief, validate_roadmap
    from plugins.dietcode.lib.agent.roadmap.skill_install import ensure_workspace_skills

    failures: list[str] = []
    bundled_skill = _PLUGIN_ROOT / "optional-skills" / "dietcode" / "auto-rolling-roadmap" / "SKILL.md"
    if not bundled_skill.is_file():
        failures.append("bundled SKILL.md missing")

    import os

    with tempfile.TemporaryDirectory() as session_tmp, tempfile.TemporaryDirectory() as tmp:
        os.environ["DIETCODE_SESSION_DIR"] = session_tmp
        (Path(tmp) / "README.md").write_text("# Smoke Project\nTest workspace.", encoding="utf-8")
        install = ensure_workspace_skills(tmp)
        if not install.get("ok"):
            failures.append(f"skill install failed: {install.get('errors')}")

        brief = checkpoint_brief(workspace=tmp, context="smoke")
        if brief.get("action") != "checkpoint":
            failures.append("checkpoint_brief action mismatch")
        if not brief.get("algorithm_steps"):
            failures.append("checkpoint_brief missing algorithm_steps")
        if not brief.get("code_soup_pre_audit"):
            failures.append("checkpoint_brief missing code_soup_pre_audit")

        doctor = run_checks(workspace=tmp)
        if not doctor.get("checks"):
            failures.append("doctor returned no checks")

        cockpit = format_cockpit_report(workspace=tmp)
        if "Roadmap cockpit" not in cockpit:
            failures.append("cockpit report missing header")

        (Path(tmp) / "ROADMAP.md").write_text((brief.get("suggested_bootstrap") or ""), encoding="utf-8")
        validated = validate_roadmap(workspace=tmp)
        if not (validated.get("validation") or {}).get("valid"):
            failures.append(f"bootstrap validation failed: {validated}")

        emit_progress("smoke.test", action="checkpoint", workspace=tmp, success=True)
        if not read_tail(lines=3):
            failures.append("progress telemetry not recorded")

        fresh = assess_checkpoint_freshness(
            recent_checkpoint_date="2020-01-01",
            git_commits=["a", "b", "c"],
            stale_days=7,
        )
        if not fresh.get("stale"):
            failures.append("freshness heuristic did not detect stale checkpoint")

    result = {"ok": not failures, "failures": failures}
    print(json.dumps(result, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
