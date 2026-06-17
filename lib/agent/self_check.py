"""DietCode plugin self-check — layout, registries, and wiring validation."""
from __future__ import annotations

from typing import Any


def run_self_check() -> dict[str, Any]:
    """Return structured self-check payload; ``ok`` is false when any hard failure exists."""
    from plugins.dietcode.audit import runtime_layout_ok
    from plugins.dietcode.lib.agent.production_audit import run_production_hardening_audit
    from plugins.dietcode.lib.runtime.command_registry import validate_command_registry
    from plugins.dietcode.lib.runtime.hook_registry import validate_hook_registry
    from plugins.dietcode.tools_loader import discover_tool_modules

    failures: list[str] = []
    failures.extend(validate_hook_registry())
    failures.extend(validate_command_registry())

    layout_ok, layout_missing = runtime_layout_ok()
    if not layout_ok:
        failures.append(f"runtime layout incomplete: {layout_missing}")

    hardening = run_production_hardening_audit()
    if not hardening.get("ok"):
        failures.extend(list(hardening.get("failures") or []))

    return {
        "ok": not failures,
        "failures": failures,
        "layout_ok": layout_ok,
        "layout_missing": layout_missing,
        "tool_modules": list(discover_tool_modules()),
        "production_hardening": hardening,
    }
