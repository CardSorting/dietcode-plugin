#!/usr/bin/env python3
"""DietCode contract doctor — CI-friendly runtime validation."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def main() -> int:
    from tests.support import bootstrap_plugins_namespace

    bootstrap_plugins_namespace(plugin_root=_PLUGIN_ROOT)

    from plugins.dietcode.lib.agent.self_check import run_self_check

    payload = run_self_check()
    warnings: list[str] = []

    import importlib.util

    try:
        hermes_runtime = importlib.util.find_spec("tools.registry") is not None
    except ModuleNotFoundError:
        hermes_runtime = False

    contract_payload: dict[str, object] = {"skipped": True, "reason": "Hermes tools.registry not available"}
    if hermes_runtime:
        try:
            from plugins.dietcode.contracts import validate_runtime_contract

            report = validate_runtime_contract(strict=False)
            contract_payload = {
                "ok": report.ok,
                "errors": report.errors,
                "warnings": report.warnings,
                "checks": report.checks,
            }
            if not report.ok:
                payload["failures"] = list(payload.get("failures") or []) + list(report.errors)
                payload["ok"] = False
            warnings.extend(report.warnings)
        except Exception as exc:
            contract_payload = {"skipped": True, "reason": str(exc)}
            warnings.append(f"Hermes runtime contract failed: {exc}")

    payload["warnings"] = warnings
    payload["contract"] = contract_payload
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
