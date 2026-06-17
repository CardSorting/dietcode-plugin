#!/usr/bin/env python3
"""Production hardening audit — CI entrypoint for DietCode plugin sources."""
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
    from plugins.dietcode.lib.agent.production_audit import run_production_hardening_audit

    payload = run_production_hardening_audit(root=_PLUGIN_ROOT)
    print(json.dumps(payload, indent=2))
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
