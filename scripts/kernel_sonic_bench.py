#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 7D — kernel sonic UX tempo benchmark."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def _bootstrap() -> None:
    import importlib.util
    import types

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


_bootstrap()

from plugins.dietcode.lib.agent.kernel_sonic import (  # noqa: E402
    build_sonic_bench_report,
    contains_token_leak,
    format_sonic_bench_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Kernel sonic UX benchmark")
    parser.add_argument("--compact", action="store_true", help="Single-line summary")
    parser.add_argument("--json", action="store_true", help="JSON output")
    args = parser.parse_args()

    payload = build_sonic_bench_report()
    if args.json:
        print(json.dumps(payload, indent=2))
    elif args.compact:
        print(format_sonic_bench_report(compact=True))
    else:
        print(format_sonic_bench_report())

    sample = str(payload.get("watch_line_sample") or "")
    if sample and contains_token_leak(sample):
        print("token_leak: FAIL", file=sys.stderr)
        return 1
    print("token_leak: OK", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
