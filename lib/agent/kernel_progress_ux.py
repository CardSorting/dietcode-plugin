# -*- coding: utf-8 -*-
"""Phase 7B — perceived performance, responsiveness, and operator confidence."""
from __future__ import annotations

import re
import statistics
import time
from typing import Any, Optional

PHASE_OPERATION_ACCEPTED = "operation.accepted"
PHASE_PATCH_STAGING = "patch.staging"
PHASE_HEARTBEAT = "bridge.heartbeat"

FAST_PHASE_THRESHOLD_MS = 80
SILENT_GAP_THRESHOLD_MS = 3_000
LONG_RUNNING_MS = 30_000
VERY_LONG_RUNNING_MS = 60_000
SUGGEST_DIAGNOSTIC_MS = 120_000

DEFAULT_HEARTBEAT_INTERVAL_MS = 4_000
SLOW_PHASE_HEARTBEAT_INTERVAL_MS = 2_500

SLOW_HEARTBEAT_PHASES = frozenset({
    "verify.running",
    "approval.waiting",
    "coherence.anchor_refresh",
    "patch.apply",
    "journal.recording",
    "convergence.checking",
})

SUPPRESS_JSONL_FAST_PHASES = frozenset({
    "bridge.preflight",
    "socket.ready",
    "workspace.open",
})

ACTION_PHASE_SEQUENCES: dict[str, list[str]] = {
    "status": [
        PHASE_OPERATION_ACCEPTED,
        "bridge.preflight",
        "socket.ready",
        "workspace.open",
        "done",
    ],
    "search": [
        PHASE_OPERATION_ACCEPTED,
        "bridge.preflight",
        "workspace.open",
        "done",
    ],
    "patch": [
        PHASE_OPERATION_ACCEPTED,
        "bridge.preflight",
        "socket.ready",
        "workspace.open",
        "coherence.read",
        "patch.staging",
        "patch.validate",
        "patch.apply",
        "journal.recording",
        "done",
    ],
    "verify": [
        PHASE_OPERATION_ACCEPTED,
        "bridge.preflight",
        "workspace.open",
        "verify.running",
        "journal.recording",
        "done",
    ],
}

_PHASE_LABELS: dict[str, str] = {
    "bridge.preflight": "bridge.preflight",
    "socket.ready": "socket.ready",
    "workspace.open": "workspace.open",
    "coherence.read": "coherence.read",
    "coherence.anchor_refresh": "coherence.recover",
    "patch.staging": "patch.staging",
    "patch.validate": "patch.validate",
    "patch.apply": "patch.apply",
    "approval.waiting": "approval.waiting",
    "verify.running": "verify.run",
    "journal.recording": "journal.recording",
    "convergence.checking": "convergence.checking",
    "done": "done",
    "error": "error",
}

_STALL_WAITING_REASONS: dict[str, str] = {
    "verify.running": "verify subprocess still running — check allowlisted command output",
    "approval.waiting": "kernel approval pending — resolve approval queue before retry",
    "coherence.anchor_refresh": "coherence recovery in progress — anchor refresh or retry",
    "patch.apply": "patch RPC in flight — waiting for kernel mutation receipt",
    "journal.recording": "JoyZoning journal write in progress",
    "workspace.open": "workspace open RPC slow — socket or disk latency",
    "bridge.preflight": "bridge preflight slow — socket/token check",
    "patch.validate": "patch validation RPC in progress",
    "coherence.read": "coherence-aware read in progress",
}

_last_heartbeat_summary: dict[str, str] = {}


def estimated_phase_sequence(action: str) -> list[str]:
    act = str(action or "").strip().lower()
    return list(ACTION_PHASE_SEQUENCES.get(act, ACTION_PHASE_SEQUENCES["status"]))


def next_phase_hint(current_phase: str, action: str) -> str | None:
    seq = estimated_phase_sequence(action)
    phase = str(current_phase or "").strip()
    try:
        idx = seq.index(phase)
    except ValueError:
        return _PHASE_LABELS.get(phase)
    if idx + 1 < len(seq):
        nxt = seq[idx + 1]
        return f"next: {_PHASE_LABELS.get(nxt, nxt)}"
    return None


def stall_waiting_reason(last_phase: str, *, attempt: int = 1) -> str:
    phase = str(last_phase or "unknown")
    base = _STALL_WAITING_REASONS.get(phase, f"no progress update during {phase}")
    if phase == "coherence.anchor_refresh" and attempt > 1:
        return f"coherence recovery retry {attempt} — {base}"
    return base


def run_duration_tier(elapsed_ms: int) -> dict[str, Any]:
    ms = max(0, int(elapsed_ms))
    out: dict[str, Any] = {}
    if ms >= SUGGEST_DIAGNOSTIC_MS:
        out["run_tier"] = "very_long_running"
        out["suggested_diagnostic"] = "/dietcode kernel progress --timeline"
        out["stress_note"] = "Operation exceeded 120s — inspect timeline and socket health"
    elif ms >= VERY_LONG_RUNNING_MS:
        out["run_tier"] = "very_long_running"
        out["stress_note"] = "Operation exceeded 60s — consider /dietcode kernel progress --current"
    elif ms >= LONG_RUNNING_MS:
        out["run_tier"] = "long_running"
        out["stress_note"] = "Operation exceeded 30s — still in progress"
    return out


def should_suppress_jsonl_emit(*, phase: str, phase_duration_ms: int, heartbeat: bool) -> bool:
    if heartbeat:
        return False
    if phase in SUPPRESS_JSONL_FAST_PHASES and 0 < phase_duration_ms < FAST_PHASE_THRESHOLD_MS:
        return True
    return False


def heartbeat_interval_ms(phase: str) -> int:
    if str(phase or "") in SLOW_HEARTBEAT_PHASES:
        return SLOW_PHASE_HEARTBEAT_INTERVAL_MS
    return DEFAULT_HEARTBEAT_INTERVAL_MS


def build_heartbeat_summary(*, phase: str, elapsed_ms: int, attempt: int = 1, command: str = "") -> str:
    elapsed_s = max(0, int(elapsed_ms / 1000))
    if phase == "verify.running":
        cmd = command or "verify"
        return f"still verifying {cmd}... ({elapsed_s}s)"
    if phase == "approval.waiting":
        return f"still waiting for approval... ({elapsed_s}s)"
    if phase == "coherence.anchor_refresh":
        if attempt > 1:
            return f"coherence recovery retry {attempt}... ({elapsed_s}s)"
        return f"coherence recovery in progress... ({elapsed_s}s)"
    if phase == "patch.apply":
        return f"still applying patch... ({elapsed_s}s)"
    if phase == "journal.recording":
        return f"still recording journal... ({elapsed_s}s)"
    if phase == "patch.validate":
        return f"still validating patch... ({elapsed_s}s)"
    label = _PHASE_LABELS.get(phase, phase)
    return f"still in {label}... ({elapsed_s}s)"


def should_emit_heartbeat(operation_id: str, summary: str) -> bool:
    op = str(operation_id or "")
    if not op:
        return True
    prev = _last_heartbeat_summary.get(op)
    if prev == summary:
        return False
    _last_heartbeat_summary[op] = summary
    return True


def clear_heartbeat_coalesce(operation_id: str) -> None:
    _last_heartbeat_summary.pop(str(operation_id or ""), None)


def count_patch_files(patch_text: str) -> int:
    text = str(patch_text or "")
    if not text.strip():
        return 0
    paths = set(re.findall(r"^\+\+\+ b/(.+)$", text, re.MULTILINE))
    if paths:
        return len(paths)
    if "---" in text:
        return max(1, text.count("\n--- "))
    return 1


def default_verify_hint() -> str:
    try:
        from plugins.dietcode.lib.agent.kernel_verify_bridge import load_verify_allowlist
    except ImportError:
        from lib.agent.kernel_verify_bridge import load_verify_allowlist
    prefixes = load_verify_allowlist()
    return prefixes[-1] if prefixes else "./verify.sh"


def build_mutation_preview(
    *,
    path: str,
    patch_text: str = "",
    task_id: str = "",
    verify_command: str = "",
    workspace_root: str = "",
) -> dict[str, Any]:
    patch_bytes = len(str(patch_text or "").encode("utf-8"))
    files_affected = count_patch_files(patch_text)
    if files_affected == 0 and path:
        files_affected = 1
    verify_hint = str(verify_command or "").strip() or default_verify_hint()
    return {
        "files_affected": files_affected,
        "patch_bytes": patch_bytes,
        "patch_lines": str(patch_text or "").count("\n") + (1 if patch_text else 0),
        "primary_path": str(path or ""),
        "taskId": str(task_id or "") or None,
        "verify_command_hint": verify_hint,
        "workspace_root": str(workspace_root or "") or None,
        "human_summary": (
            f"mutation: {files_affected} file(s), {patch_bytes} bytes"
            + (f", taskId={task_id}" if task_id else "")
            + f", verify hint: {verify_hint}"
        ),
    }


def build_acknowledgement_payload(tracker: Any) -> dict[str, Any]:
    return {
        "status": "accepted",
        "operation_id": getattr(tracker, "operation_id", ""),
        "action": getattr(tracker, "action", ""),
        "workspace_root": getattr(tracker, "workspace_root", "") or None,
        "phase_sequence": estimated_phase_sequence(getattr(tracker, "action", "")),
        "next_phase_hint": next_phase_hint(PHASE_OPERATION_ACCEPTED, getattr(tracker, "action", "")),
    }


def _phase_verb(phase: str) -> str:
    mapping = {
        "operation.accepted": "accepted",
        "bridge.preflight": "preflight",
        "socket.ready": "socket",
        "workspace.open": "opening",
        "coherence.read": "reading",
        "coherence.anchor_refresh": "recovering",
        "patch.staging": "staging",
        "patch.validate": "validating",
        "patch.apply": "applying",
        "approval.waiting": "awaiting approval",
        "verify.running": "running",
        "journal.recording": "journaling",
        "convergence.checking": "converging",
        "bridge.heartbeat": "active",
        "bridge.progress_stalled": "stalled",
        "done": "done",
        "error": "failed",
    }
    return mapping.get(str(phase or ""), str(phase or "active"))


def compact_watch_line(event: dict[str, Any], *, polished: bool = True) -> str:
    base = _compact_watch_line_raw(event)
    if not polished:
        return base
    try:
        from plugins.dietcode.lib.agent.kernel_cockpit import (
            normalize_operation_state,
            recommend_next_action,
            state_symbol,
        )
    except ImportError:
        from lib.agent.kernel_cockpit import normalize_operation_state, recommend_next_action, state_symbol
    state = normalize_operation_state(
        phase=str(event.get("phase") or ""),
        heartbeat_phase=str(event.get("heartbeat_phase") or ""),
    )
    sym = state_symbol(state)
    rec = recommend_next_action(operation_state=state)
    return f"{sym} [{state}] {base} | next: {rec.get('action')}"


def _compact_watch_line_raw(event: dict[str, Any]) -> str:
    action = str(event.get("action") or "kernel").upper()
    op_id = str(event.get("operation_id") or "")
    op_short = op_id.replace("op_", "")[-4:] if op_id else "????"
    phase = str(event.get("phase") or "")
    verb = _phase_verb(phase)
    target = event.get("path") or event.get("command") or event.get("workspace_root") or ""
    if isinstance(target, str) and len(target) > 48:
        target = "…" + target[-45:]
    elapsed_s = int((event.get("elapsed_ms") or 0) / 1000)
    hb = event.get("heartbeat_summary") or event.get("summary")
    if phase == PHASE_HEARTBEAT and hb:
        line = f"{action} {op_short} {hb}"
    else:
        line = f"{action} {op_short} {verb} {target} ({elapsed_s}s)"
    nxt = event.get("next_phase_hint")
    if nxt and phase not in {"done", "error"}:
        line += f" | {nxt}"
    tier = event.get("run_tier")
    if tier:
        line += f" [{tier}]"
    if event.get("suggested_diagnostic"):
        line += f" → {event['suggested_diagnostic']}"
    return line.strip()


def parse_watch_args(argv: list[str]) -> dict[str, Any]:
    opts: dict[str, Any] = {"follow": False, "interval_sec": 1.5, "max_sec": 30.0}
    idx = 0
    while idx < len(argv):
        arg = argv[idx].lower()
        if arg in {"--follow", "-f"}:
            opts["follow"] = True
        elif arg == "--interval" and idx + 1 < len(argv):
            try:
                opts["interval_sec"] = max(0.5, float(argv[idx + 1]))
            except ValueError:
                pass
            idx += 1
        elif arg == "--max" and idx + 1 < len(argv):
            try:
                opts["max_sec"] = max(1.0, float(argv[idx + 1]))
            except ValueError:
                pass
            idx += 1
        idx += 1
    return opts


def format_watch_report(
    *,
    follow: bool = False,
    interval_sec: float = 1.0,
    max_sec: float = 30.0,
) -> str:
    try:
        from plugins.dietcode.lib.agent.kernel_progress import read_progress_current
        from plugins.dietcode.lib.agent.kernel_sonic import format_kinetic_watch_line, run_kinetic_watch
    except ImportError:
        from lib.agent.kernel_progress import read_progress_current
        from lib.agent.kernel_sonic import format_kinetic_watch_line, run_kinetic_watch

    if follow:
        return run_kinetic_watch(interval_sec=interval_sec, max_sec=max_sec)

    payload = read_progress_current()
    if not payload.get("ok") or not isinstance(payload.get("current"), dict):
        return "🥦 Kernel watch — idle (no active operation)"
    return f"🥦 {format_kinetic_watch_line(payload['current'])}"


def compute_operation_ux_metrics(events: list[dict[str, Any]]) -> dict[str, Any]:
    if not events:
        return {
            "time_to_first_feedback_ms": None,
            "time_to_first_progress_ms": None,
            "total_silent_window_ms": 0,
            "silent_gap_count": 0,
            "heartbeat_count": 0,
            "ack_ms": None,
        }

    first_feedback: int | None = None
    first_progress: int | None = None
    ack_ms: int | None = None
    silent_total = 0
    silent_gaps = 0
    heartbeats = 0

    prev_mono: float | None = None
    for event in events:
        phase = str(event.get("phase") or "")
        elapsed = int(event.get("elapsed_ms") or 0)
        if phase == PHASE_OPERATION_ACCEPTED:
            first_feedback = 0 if first_feedback is None else first_feedback
            ack_ms = elapsed
        elif first_progress is None and phase not in {PHASE_HEARTBEAT}:
            first_progress = elapsed

        if event.get("heartbeat") or phase == PHASE_HEARTBEAT:
            heartbeats += 1

        ts_mono = event.get("ts_mono")
        if isinstance(ts_mono, (int, float)) and prev_mono is not None:
            gap_ms = int((float(ts_mono) - prev_mono) * 1000)
            if gap_ms >= SILENT_GAP_THRESHOLD_MS:
                silent_total += gap_ms
                silent_gaps += 1
        if isinstance(ts_mono, (int, float)):
            prev_mono = float(ts_mono)

    if first_feedback is None and events:
        first_feedback = int(events[0].get("elapsed_ms") or 0)
    if first_progress is None and len(events) > 1:
        first_progress = int(events[1].get("elapsed_ms") or 0)

    return {
        "time_to_first_feedback_ms": first_feedback,
        "time_to_first_progress_ms": first_progress,
        "total_silent_window_ms": silent_total,
        "silent_gap_count": silent_gaps,
        "heartbeat_count": heartbeats,
        "ack_ms": ack_ms,
    }


def build_ux_perf_report(*, last_operations: int = 10) -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.kernel_progress import group_events_by_operation, read_progress_lines
    except ImportError:
        from lib.agent.kernel_progress import group_events_by_operation, read_progress_lines

    events = read_progress_lines()
    grouped = group_events_by_operation(events)
    if not grouped:
        return {
            "ok": True,
            "operation_count": 0,
            "message": "No kernel operations recorded for UX perf analysis.",
            "operations": [],
            "aggregate": {},
        }

    last_index: dict[str, int] = {}
    for idx, event in enumerate(events):
        op_id = str(event.get("operation_id") or "")
        if op_id:
            last_index[op_id] = idx
    op_ids = sorted(grouped.keys(), key=lambda op: last_index.get(op, 0), reverse=True)
    selected = op_ids[: max(1, int(last_operations))]

    op_metrics: list[dict[str, Any]] = []
    feedback_vals: list[float] = []
    progress_vals: list[float] = []
    silent_vals: list[float] = []

    try:
        from plugins.dietcode.lib.agent.kernel_cockpit import enrich_ux_metrics, normalize_operation_state
    except ImportError:
        from lib.agent.kernel_cockpit import enrich_ux_metrics, normalize_operation_state

    for op_id in selected:
        op_events = grouped.get(op_id, [])
        metrics = enrich_ux_metrics(compute_operation_ux_metrics(op_events), op_events)
        terminal_phase = str(op_events[-1].get("phase") or "") if op_events else ""
        entry = {
            "operation_id": op_id,
            "action": op_events[0].get("action") if op_events else None,
            "status": terminal_phase,
            "operation_state": normalize_operation_state(phase=terminal_phase),
            **metrics,
        }
        op_metrics.append(entry)
        if metrics.get("time_to_first_feedback_ms") is not None:
            feedback_vals.append(float(metrics["time_to_first_feedback_ms"]))
        if metrics.get("time_to_first_progress_ms") is not None:
            progress_vals.append(float(metrics["time_to_first_progress_ms"]))
        silent_vals.append(float(metrics.get("total_silent_window_ms") or 0))

    def _agg(values: list[float]) -> dict[str, float]:
        if not values:
            return {}
        ordered = sorted(values)
        return {
            "avg_ms": statistics.mean(values),
            "p50_ms": ordered[len(ordered) // 2],
            "p95_ms": ordered[int((len(ordered) - 1) * 0.95)],
            "max_ms": max(values),
        }

    passed = sum(1 for op in op_metrics if (op.get("ux_budgets") or {}).get("ux_budget_passed"))
    return {
        "ok": True,
        "operation_count": len(selected),
        "operations": op_metrics,
        "ux_budget_pass_rate": (passed / len(op_metrics)) if op_metrics else 0.0,
        "aggregate": {
            "time_to_first_feedback_ms": _agg(feedback_vals),
            "time_to_first_progress_ms": _agg(progress_vals),
            "total_silent_window_ms": _agg(silent_vals),
        },
        "budget_thresholds": {
            "ack_ms": 100,
            "first_progress_ms": 500,
            "silent_window_ms": 5000,
        },
    }


def parse_perf_ux_args(argv: list[str]) -> tuple[int, bool]:
    last_n = 10
    ux = False
    idx = 0
    while idx < len(argv):
        arg = argv[idx].lower()
        if arg == "--ux":
            ux = True
        elif arg == "--last" and idx + 1 < len(argv):
            try:
                last_n = max(1, int(argv[idx + 1]))
            except ValueError:
                last_n = 10
            idx += 1
        idx += 1
    return last_n, ux


def format_ux_perf_report(*, last_operations: int = 10) -> str:
    try:
        from plugins.dietcode.lib.agent.kernel_cockpit import symbol, use_unicode_symbols
    except ImportError:
        from lib.agent.kernel_cockpit import symbol, use_unicode_symbols

    payload = build_ux_perf_report(last_operations=last_operations)
    lines = [f"🥦 Kernel perf UX — last {payload.get('operation_count', 0)} operations", ""]
    if not payload.get("operations"):
        lines.append(payload.get("message") or "No UX timing data yet.")
        return "\n".join(lines)

    thresholds = payload.get("budget_thresholds") or {}
    lines.append(
        f"UX budgets: ack < {thresholds.get('ack_ms', 100)}ms | "
        f"first progress < {thresholds.get('first_progress_ms', 500)}ms | "
        f"silent window < {thresholds.get('silent_window_ms', 5000)}ms"
    )
    pass_rate = payload.get("ux_budget_pass_rate")
    if pass_rate is not None:
        mark = symbol("complete") if pass_rate >= 1.0 else symbol("warning")
        lines.append(f"Budget pass rate: {mark} {int(pass_rate * 100)}% of operations")
    lines.append("")

    agg = payload.get("aggregate") or {}
    for key, label in (
        ("time_to_first_feedback_ms", "Time to acknowledgement"),
        ("time_to_first_progress_ms", "Time to first progress"),
        ("total_silent_window_ms", "Total silent window"),
    ):
        stats = agg.get(key) or {}
        if stats:
            lines.append(
                f"{label}: p50={int(stats.get('p50_ms', 0))}ms "
                f"p95={int(stats.get('p95_ms', 0))}ms avg={int(stats.get('avg_ms', 0))}ms"
            )
    lines.append("")
    lines.append("Per operation:")
    for op in payload.get("operations") or []:
        budgets = op.get("ux_budgets") or {}
        budget_mark = symbol("complete") if budgets.get("ux_budget_passed") else symbol("failed")
        slow = op.get("slowest_phase") or {}
        lines.append(
            f"  {budget_mark} {op.get('operation_id')} | {op.get('action')} | "
            f"state={op.get('operation_state')} | "
            f"ack={op.get('time_to_first_feedback_ms')}ms "
            f"first={op.get('time_to_first_progress_ms')}ms "
            f"longest_silent={op.get('longest_silent_window_ms')}ms "
            f"total={op.get('total_operation_duration_ms')}ms "
            f"slowest={slow.get('bucket')}({slow.get('ms')}ms)"
        )
    if not use_unicode_symbols():
        lines.append("(ASCII symbols — set UTF-8 terminal or unset DIETCODE_ASCII_ONLY)")
    return "\n".join(lines)
