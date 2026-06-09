#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 7 kernel bridge perf bench — status/search/patch/verify timing report."""
from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
import time
import types
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _bootstrap() -> None:
    if str(PLUGIN_ROOT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_ROOT))
    bootstrap_path = PLUGIN_ROOT / "_bootstrap.py"
    spec = importlib.util.spec_from_file_location("dietcode_bootstrap", bootstrap_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    loaded_name = "hermes_plugins.dietcode"
    loaded = types.ModuleType(loaded_name)
    loaded.__path__ = [str(PLUGIN_ROOT)]  # type: ignore[attr-defined]
    sys.modules[loaded_name] = loaded
    mod.ensure_namespace(loaded_name)


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    idx = (len(ordered) - 1) * (pct / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def _bench(label: str, fn, *, count: int) -> dict:
    durations: list[float] = []
    errors = 0
    for _ in range(count):
        start = time.perf_counter()
        try:
            fn()
        except Exception:
            errors += 1
        durations.append((time.perf_counter() - start) * 1000.0)
    return {
        "label": label,
        "count": count,
        "errors": errors,
        "p50_ms": _percentile(durations, 50),
        "p95_ms": _percentile(durations, 95),
        "avg_ms": statistics.mean(durations) if durations else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Kernel bridge perf bench")
    parser.add_argument("--status", type=int, default=10)
    parser.add_argument("--search", type=int, default=10)
    parser.add_argument("--patch", type=int, default=5)
    parser.add_argument("--verify", type=int, default=3)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()

    _bootstrap()
    from plugins.dietcode.lib.tools import kernel_bridge_tools as tools
    from plugins.dietcode.lib.agent.kernel_bridge_perf import build_perf_report

    results = []
    if args.status:
        results.append(_bench(
            "status",
            lambda: tools.dietcode_kernel("status"),
            count=args.status,
        ))
    if args.search:
        results.append(_bench(
            "search",
            lambda: tools.dietcode_kernel("search", query="TODO"),
            count=args.search,
        ))
    if args.patch:
        results.append(_bench(
            "patch",
            lambda: tools.dietcode_kernel(
                "patch",
                path="README.md",
                line_search="# DietCode",
                line_replace="# DietCode",
            ),
            count=args.patch,
        ))
    if args.verify:
        results.append(_bench(
            "verify",
            lambda: tools.dietcode_kernel("verify", command="echo dietcode-perf"),
            count=args.verify,
        ))

    phase_report = build_perf_report(last_operations=max(10, args.status + args.patch))

    payload = {"bench": results, "progress_phases": phase_report}
    if args.compact:
        for row in results:
            print(
                f"{row['label']}: p50={row['p50_ms']:.1f}ms "
                f"p95={row['p95_ms']:.1f}ms errors={row['errors']}"
            )
        for item in phase_report.get("slowest_phases") or []:
            print(
                f"phase {item.get('bucket')}: p50={item.get('p50_ms', 0):.0f}ms "
                f"p95={item.get('p95_ms', 0):.0f}ms"
            )
    else:
        print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
