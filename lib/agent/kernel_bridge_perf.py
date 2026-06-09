# -*- coding: utf-8 -*-
"""Phase 7 — kernel bridge performance telemetry aggregation."""
from __future__ import annotations

import statistics
from typing import Any

# Progress phase → perf bucket for operator reports.
PHASE_PERF_BUCKETS: dict[str, str] = {
    "bridge.preflight": "socket/preflight",
    "socket.ready": "socket/preflight",
    "workspace.open": "workspace.open",
    "coherence.read": "coherence.read",
    "coherence.anchor_refresh": "anchor.refresh",
    "patch.validate": "patch.validate",
    "patch.apply": "patch.apply",
    "approval.waiting": "patch.apply",
    "verify.running": "verify.run",
    "journal.recording": "journal.recording",
    "convergence.checking": "convergence.checking",
    "done": "done",
    "error": "error",
    "bridge.progress_stalled": "stalled",
}


def _percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    ordered = sorted(values)
    idx = (len(ordered) - 1) * (pct / 100.0)
    lo = int(idx)
    hi = min(lo + 1, len(ordered) - 1)
    frac = idx - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def aggregate_phase_durations(events: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Aggregate ``phase_duration_ms`` by perf bucket across events."""
    buckets: dict[str, list[float]] = {}
    for event in events:
        phase = str(event.get("phase") or "")
        bucket = PHASE_PERF_BUCKETS.get(phase, phase or "other")
        try:
            duration = float(event.get("phase_duration_ms") or 0)
        except (TypeError, ValueError):
            duration = 0.0
        if duration <= 0 and phase in {"done", "error"}:
            try:
                duration = float(event.get("elapsed_ms") or 0)
            except (TypeError, ValueError):
                duration = 0.0
        if duration <= 0:
            continue
        buckets.setdefault(bucket, []).append(duration)
    summary: dict[str, dict[str, float]] = {}
    for bucket, values in buckets.items():
        summary[bucket] = {
            "count": float(len(values)),
            "avg_ms": statistics.mean(values),
            "p50_ms": _percentile(values, 50),
            "p95_ms": _percentile(values, 95),
            "max_ms": max(values),
        }
    return summary


def build_perf_report(*, last_operations: int = 10) -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.kernel_progress import (
            group_events_by_operation,
            read_progress_lines,
        )
    except ImportError:
        from lib.agent.kernel_progress import group_events_by_operation, read_progress_lines

    events = read_progress_lines()
    grouped = group_events_by_operation(events)
    op_ids = list(grouped.keys())
    if not op_ids:
        return {
            "ok": True,
            "operation_count": 0,
            "message": "No kernel operations recorded for perf analysis.",
            "by_phase": {},
            "slowest_phases": [],
        }

    # Last N operations by log order
    last_index: dict[str, int] = {}
    for idx, event in enumerate(events):
        op_id = str(event.get("operation_id") or "")
        if op_id:
            last_index[op_id] = idx
    op_ids.sort(key=lambda op: last_index.get(op, 0), reverse=True)
    selected = op_ids[: max(1, int(last_operations))]

    selected_events: list[dict[str, Any]] = []
    for op_id in selected:
        selected_events.extend(grouped.get(op_id, []))

    by_phase = aggregate_phase_durations(selected_events)
    slowest = sorted(
        (
            {"bucket": bucket, **stats}
            for bucket, stats in by_phase.items()
        ),
        key=lambda item: item.get("p95_ms", 0),
        reverse=True,
    )

    return {
        "ok": True,
        "operation_count": len(selected),
        "operations_analyzed": selected,
        "by_phase": by_phase,
        "slowest_phases": slowest[:8],
    }


def parse_perf_args(argv: list[str]) -> int:
    idx = 0
    while idx < len(argv):
        if argv[idx].lower() == "--last" and idx + 1 < len(argv):
            try:
                return max(1, int(argv[idx + 1]))
            except ValueError:
                return 10
            idx += 1
        idx += 1
    return 10


def format_perf_report(*, last_operations: int = 10) -> str:
    payload = build_perf_report(last_operations=last_operations)
    lines = [f"🥦 Kernel perf — last {payload.get('operation_count', 0)} operations", ""]
    if not payload.get("by_phase"):
        lines.append(payload.get("message") or "No phase timing data yet.")
        return "\n".join(lines)
    lines.append("Slowest phases (p95):")
    for item in payload.get("slowest_phases") or []:
        lines.append(
            f"  {item.get('bucket')}: p50={int(item.get('p50_ms', 0))}ms "
            f"p95={int(item.get('p95_ms', 0))}ms avg={int(item.get('avg_ms', 0))}ms "
            f"n={int(item.get('count', 0))}"
        )
    lines.append("")
    lines.append("All buckets:")
    for bucket, stats in sorted(
        (payload.get("by_phase") or {}).items(),
        key=lambda pair: pair[1].get("avg_ms", 0),
        reverse=True,
    ):
        lines.append(
            f"  {bucket}: avg={int(stats.get('avg_ms', 0))}ms "
            f"p50={int(stats.get('p50_ms', 0))}ms p95={int(stats.get('p95_ms', 0))}ms"
        )
    return "\n".join(lines)
