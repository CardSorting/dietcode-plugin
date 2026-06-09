# -*- coding: utf-8 -*-
"""Phase 7C — live kernel cockpit, operation states, and release-grade UX."""
from __future__ import annotations

import os
import sys
from typing import Any

# Normalized operator-facing operation states.
STATE_IDLE = "idle"
STATE_ACCEPTED = "accepted"
STATE_PREPARING = "preparing"
STATE_VALIDATING = "validating"
STATE_RECOVERING = "recovering"
STATE_APPLYING = "applying"
STATE_VERIFYING = "verifying"
STATE_JOURNALING = "journaling"
STATE_BLOCKED = "blocked"
STATE_STALLED = "stalled"
STATE_FAILED = "failed"
STATE_COMPLETE = "complete"

OPERATION_STATES = frozenset({
    STATE_IDLE,
    STATE_ACCEPTED,
    STATE_PREPARING,
    STATE_VALIDATING,
    STATE_RECOVERING,
    STATE_APPLYING,
    STATE_VERIFYING,
    STATE_JOURNALING,
    STATE_BLOCKED,
    STATE_STALLED,
    STATE_FAILED,
    STATE_COMPLETE,
})

# Recommended next actions (exactly one per cockpit/progress view).
ACTION_WAIT = "wait"
ACTION_CHECK_LAST_ERROR = "check last-error"
ACTION_RUN_EXPLAIN_GATE = "run explain-gate"
ACTION_RETRY = "retry"
ACTION_ROLLBACK_BLOCK_MODE = "rollback block mode"
ACTION_START_KERNEL_SOCKET = "start kernel socket"
ACTION_ENABLE_MUTATIONS = "enable mutations"
ACTION_SET_WORKSPACE_ROOT = "set workspace root"

UX_BUDGET_ACK_MS = 100
UX_BUDGET_FIRST_PROGRESS_MS = 500
UX_BUDGET_SILENT_WINDOW_MS = 5_000

_PHASE_TO_STATE: dict[str, str] = {
    "operation.accepted": STATE_ACCEPTED,
    "bridge.preflight": STATE_PREPARING,
    "socket.ready": STATE_PREPARING,
    "workspace.open": STATE_PREPARING,
    "coherence.read": STATE_PREPARING,
    "patch.staging": STATE_PREPARING,
    "patch.validate": STATE_VALIDATING,
    "coherence.anchor_refresh": STATE_RECOVERING,
    "patch.apply": STATE_APPLYING,
    "approval.waiting": STATE_BLOCKED,
    "verify.running": STATE_VERIFYING,
    "journal.recording": STATE_JOURNALING,
    "convergence.checking": STATE_JOURNALING,
    "bridge.heartbeat": STATE_PREPARING,  # overridden by parent phase when present
    "bridge.progress_stalled": STATE_STALLED,
    "done": STATE_COMPLETE,
    "error": STATE_FAILED,
}

_UNICODE_SYMBOLS = {
    "complete": "✓",
    "warning": "!",
    "failed": "✕",
    "running": "…",
}
_ASCII_SYMBOLS = {
    "complete": "[OK]",
    "warning": "[!]",
    "failed": "[X]",
    "running": "[..]",
}


def use_unicode_symbols() -> bool:
    if os.environ.get("DIETCODE_ASCII_ONLY", "").strip().lower() in {"1", "true", "yes"}:
        return False
    enc = (getattr(sys.stdout, "encoding", None) or os.environ.get("PYTHONIOENCODING") or "").lower()
    if enc and "utf" not in enc and enc not in {"", "utf-8", "utf8"}:
        return False
    return True


def symbol(kind: str) -> str:
    try:
        from plugins.dietcode.lib.agent.kernel_sonic import visual_symbol
    except ImportError:
        from lib.agent.kernel_sonic import visual_symbol
    mapping = {
        "complete": "success",
        "warning": "warning",
        "failed": "failed",
        "running": "running",
    }
    return visual_symbol(mapping.get(kind, kind))


def normalize_operation_state(
    *,
    phase: str = "",
    stale: bool = False,
    heartbeat_phase: str = "",
) -> str:
    if stale:
        return STATE_STALLED
    phase_name = str(phase or "").strip()
    if phase_name == "bridge.heartbeat" and heartbeat_phase:
        phase_name = str(heartbeat_phase)
    state = _PHASE_TO_STATE.get(phase_name, STATE_PREPARING)
    if phase_name in {"bridge.heartbeat"} and not heartbeat_phase:
        return STATE_PREPARING
    return state


def state_display_label(state: str) -> str:
    return str(state or STATE_IDLE).replace("_", " ")


def state_symbol(state: str) -> str:
    try:
        from plugins.dietcode.lib.agent.kernel_sonic import visual_symbol
    except ImportError:
        from lib.agent.kernel_sonic import visual_symbol
    mapping = {
        STATE_COMPLETE: "success",
        STATE_FAILED: "failed",
        STATE_STALLED: "stalled",
        STATE_BLOCKED: "waiting",
        STATE_IDLE: "running",
    }
    if state in {
        STATE_ACCEPTED,
        STATE_PREPARING,
        STATE_VALIDATING,
        STATE_RECOVERING,
        STATE_APPLYING,
        STATE_VERIFYING,
        STATE_JOURNALING,
    }:
        return visual_symbol("running")
    return visual_symbol(mapping.get(state, "running"))


def _gate_context() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_client import (
            KernelBridgeConfig,
            build_patch_gate_state,
        )
        from plugins.dietcode.lib.agent.kernel_raw_write_router import build_raw_write_router_health
    except ImportError:
        from lib.agent.kernel_bridge_client import KernelBridgeConfig, build_patch_gate_state
        from lib.agent.kernel_raw_write_router import build_raw_write_router_health
    cfg = KernelBridgeConfig.load()
    gate = build_patch_gate_state()
    router = build_raw_write_router_health()
    return {"config": cfg, "gate": gate, "router": router}


def recommend_next_action(
    *,
    operation_state: str,
    gate: dict[str, Any] | None = None,
    router: dict[str, Any] | None = None,
    last_error: dict[str, Any] | None = None,
    stale: bool = False,
) -> dict[str, str]:
    ctx = _gate_context()
    g = gate if gate is not None else ctx["gate"]
    r = router if router is not None else ctx["router"]

    if r.get("would_block_raw_writes"):
        return {
            "action": ACTION_ROLLBACK_BLOCK_MODE,
            "command": "/dietcode kernel explain-gate",
            "detail": "Raw writes are hard-blocked — rollback block mode if intentional bypass is needed.",
        }
    if not g.get("bridge_enabled"):
        return {
            "action": ACTION_RUN_EXPLAIN_GATE,
            "command": "/dietcode kernel explain-gate",
            "detail": "Kernel bridge is disabled in config.",
        }
    if not g.get("mutations_enabled"):
        return {
            "action": ACTION_ENABLE_MUTATIONS,
            "command": "/dietcode kernel explain-gate",
            "detail": "Set dietcode.kernel.bridge.mutations_enabled: true to open patch gate.",
        }
    if not g.get("workspace_safe_for_mutation"):
        return {
            "action": ACTION_SET_WORKSPACE_ROOT,
            "command": "/dietcode kernel explain-gate",
            "detail": "Point HERMES_KANBAN_WORKSPACE at your project root.",
        }
    if not g.get("socket_ready"):
        return {
            "action": ACTION_START_KERNEL_SOCKET,
            "command": "/dietcode kernel status",
            "detail": "make -C kernel restart-agent-server-fast",
        }
    if not g.get("token_ready"):
        return {
            "action": ACTION_START_KERNEL_SOCKET,
            "command": "/dietcode kernel status",
            "detail": "Restart agent server to recreate session.token.",
        }

    if operation_state == STATE_FAILED or (last_error and not last_error.get("ok")):
        envelope = (last_error or {}).get("last_error") or {}
        if envelope.get("safe_to_retry"):
            return {
                "action": ACTION_RETRY,
                "command": envelope.get("retry_command") or "/dietcode kernel status",
                "detail": envelope.get("next_action") or "Safe to retry once after checking gates.",
            }
        return {
            "action": ACTION_CHECK_LAST_ERROR,
            "command": "/dietcode kernel last-error",
            "detail": envelope.get("next_action") or "Review last error envelope before retrying.",
        }

    if operation_state in {STATE_STALLED, STATE_BLOCKED} or stale:
        return {
            "action": ACTION_CHECK_LAST_ERROR,
            "command": "/dietcode kernel progress --timeline",
            "detail": "Inspect timeline; resolve approval or restart socket if dead.",
        }

    if operation_state == STATE_IDLE:
        if not g.get("patch_allowed"):
            return {
                "action": ACTION_RUN_EXPLAIN_GATE,
                "command": "/dietcode kernel explain-gate",
                "detail": "Patch gate closed — review closed gates before mutation.",
            }
        return {
            "action": ACTION_WAIT,
            "command": "/dietcode kernel cockpit",
            "detail": "No active operation — ready for dietcode_kernel.",
        }

    return {
        "action": ACTION_WAIT,
        "command": "/dietcode kernel watch",
        "detail": "Operation in progress — watch live updates.",
    }


def _find_last_operation(*, action: str, status: str) -> dict[str, Any] | None:
    try:
        from plugins.dietcode.lib.agent.kernel_progress import summarize_recent_operations
    except ImportError:
        from lib.agent.kernel_progress import summarize_recent_operations
    payload = summarize_recent_operations(count=50)
    for op in payload.get("operations") or []:
        if str(op.get("action") or "").lower() == action and str(op.get("status") or "") == status:
            return op
    return None


def build_cockpit_report() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.kernel_progress import (
            PHASE_DONE,
            PHASE_ERROR,
            read_last_error,
            read_progress_current,
        )
    except ImportError:
        from lib.agent.kernel_progress import (
            PHASE_DONE,
            PHASE_ERROR,
            read_last_error,
            read_progress_current,
        )

    ctx = _gate_context()
    gate = ctx["gate"]
    router = ctx["router"]
    current_payload = read_progress_current()
    snap = current_payload.get("current") if current_payload.get("ok") else None
    stale = bool(current_payload.get("stale"))
    last_error = read_last_error()

    operation_state = STATE_IDLE
    current_op: dict[str, Any] | None = None
    if isinstance(snap, dict):
        phase = str(snap.get("phase") or "")
        if phase in {PHASE_DONE, PHASE_ERROR}:
            operation_state = normalize_operation_state(phase=phase)
        else:
            operation_state = normalize_operation_state(
                phase=phase,
                stale=stale,
                heartbeat_phase=str(snap.get("heartbeat_phase") or ""),
            )
        current_op = {
            "operation_id": snap.get("operation_id"),
            "action": snap.get("action"),
            "phase": phase,
            "operation_state": operation_state,
            "elapsed_ms": snap.get("elapsed_ms"),
            "elapsed_s": int((snap.get("elapsed_ms") or 0) / 1000),
            "next_phase_hint": snap.get("next_phase_hint"),
            "path": snap.get("path"),
            "command": snap.get("command"),
            "workspace_root": snap.get("workspace_root") or gate.get("resolved_workspace_root"),
            "summary": snap.get("summary"),
            "fast_path": bool(snap.get("fast_path") or snap.get("mode") == "sonic_fast_path"),
            "eta_remaining_s": snap.get("eta_remaining_s"),
        }
        if current_op.get("fast_path"):
            current_op["mode"] = "sonic_fast_path"

    next_action = recommend_next_action(
        operation_state=operation_state,
        gate=gate,
        router=router,
        last_error=last_error,
        stale=stale,
    )
    last_patch = _find_last_operation(action="patch", status="success")
    last_verify = _find_last_operation(action="verify", status="success")
    safe_to_retry = False
    if not last_error.get("ok") and isinstance(last_error.get("last_error"), dict):
        safe_to_retry = bool(last_error["last_error"].get("safe_to_retry"))

    return {
        "ok": True,
        "operation_state": operation_state,
        "current_operation": current_op,
        "workspace_root": gate.get("resolved_workspace_root"),
        "patch_gate": {
            "patch_allowed": bool(gate.get("patch_allowed")),
            "mutations_enabled": bool(gate.get("mutations_enabled")),
            "socket_ready": bool(gate.get("socket_ready")),
            "token_ready": bool(gate.get("token_ready")),
            "workspace_safe": bool(gate.get("workspace_safe_for_mutation")),
        },
        "raw_write_policy": router.get("raw_write_policy"),
        "raw_write_behavior": (
            "block"
            if router.get("would_block_raw_writes")
            else "warn"
            if router.get("would_warn_on_raw_write")
            else str(router.get("raw_write_policy") or "warn")
        ),
        "last_error": None if last_error.get("ok") else last_error,
        "last_successful_patch": last_patch,
        "last_verify_result": last_verify,
        "safe_to_retry": safe_to_retry,
        "stale_progress": stale,
        "recommended_next_action": next_action,
    }


def format_cockpit_report() -> str:
    payload = build_cockpit_report()
    sym = state_symbol(str(payload.get("operation_state") or STATE_IDLE))
    state = state_display_label(str(payload.get("operation_state") or STATE_IDLE))
    lines = [f"🥦 Kernel cockpit — {sym} {state}", ""]

    op = payload.get("current_operation")
    if op:
        lines.append(
            f"Current: {op.get('action') or 'kernel'} {op.get('operation_id') or ''} "
            f"| phase={op.get('phase')} | {op.get('elapsed_s', 0)}s"
        )
        if op.get("path") or op.get("command"):
            lines.append(f"  target: {op.get('path') or op.get('command')}")
        if op.get("next_phase_hint"):
            lines.append(f"  {op.get('next_phase_hint')}")
        if op.get("fast_path"):
            lines.append(f"  {symbol('complete')} FAST PATH ACTIVE")
        if op.get("eta_remaining_s"):
            lines.append(f"  ~{op.get('eta_remaining_s')}s remaining (estimated)")
    else:
        lines.append("Current: (idle)")

    ws = payload.get("workspace_root") or "(unresolved)"
    lines.append(f"Workspace: {ws}")

    pg = payload.get("patch_gate") or {}
    gate_sym = symbol("complete") if pg.get("patch_allowed") else symbol("warning")
    lines.append(
        f"Patch gate: {gate_sym} {'open' if pg.get('patch_allowed') else 'closed'} "
        f"(mutations={pg.get('mutations_enabled')}, socket={pg.get('socket_ready')}, "
        f"token={pg.get('token_ready')}, workspace_safe={pg.get('workspace_safe')})"
    )
    lines.append(f"Raw write policy: {payload.get('raw_write_policy')} ({payload.get('raw_write_behavior')})")

    if payload.get("last_successful_patch"):
        lp = payload["last_successful_patch"]
        lines.append(
            f"Last patch {symbol('complete')}: {lp.get('operation_id')} "
            f"{lp.get('path') or ''} ({int((lp.get('duration_ms') or 0) / 1000)}s)"
        )
    else:
        lines.append(f"Last patch: (none recorded)")

    if payload.get("last_verify_result"):
        lv = payload["last_verify_result"]
        lines.append(
            f"Last verify {symbol('complete')}: {lv.get('operation_id')} "
            f"{lv.get('command') or ''} ({int((lv.get('duration_ms') or 0) / 1000)}s)"
        )
    else:
        lines.append("Last verify: (none recorded)")

    if payload.get("last_error"):
        lines.append(f"Last error {symbol('failed')}: see /dietcode kernel last-error")
    else:
        lines.append(f"Last error: {symbol('complete')} none")

    retry_sym = symbol("complete") if payload.get("safe_to_retry") else symbol("warning")
    lines.append(f"Safe to retry: {retry_sym} {payload.get('safe_to_retry')}")

    rec = payload.get("recommended_next_action") or {}
    lines.append("")
    lines.append(f"Next action: {rec.get('action')}")
    lines.append(f"  {rec.get('detail')}")
    if rec.get("command"):
        lines.append(f"  → {rec['command']}")
    lines.append("")
    lines.append("Live: /dietcode kernel watch | perf --ux | progress --timeline")
    return "\n".join(lines)


def enrich_ux_metrics(metrics: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    """Add duration, slowest phase, longest silent gap, and budget pass/fail."""
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_perf import PHASE_PERF_BUCKETS
    except ImportError:
        from lib.agent.kernel_bridge_perf import PHASE_PERF_BUCKETS

    total_duration_ms = 0
    longest_silent_ms = 0
    slowest: dict[str, Any] = {"bucket": None, "ms": 0}
    prev_mono: float | None = None

    for event in events:
        elapsed = int(event.get("elapsed_ms") or 0)
        if elapsed > total_duration_ms:
            total_duration_ms = elapsed
        phase = str(event.get("phase") or "")
        bucket = PHASE_PERF_BUCKETS.get(phase, phase)
        dur = int(event.get("phase_duration_ms") or 0)
        if dur > slowest.get("ms", 0):
            slowest = {"bucket": bucket, "phase": phase, "ms": dur}
        ts_mono = event.get("ts_mono")
        if isinstance(ts_mono, (int, float)) and prev_mono is not None:
            gap = int((float(ts_mono) - prev_mono) * 1000)
            if gap > longest_silent_ms:
                longest_silent_ms = gap
        if isinstance(ts_mono, (int, float)):
            prev_mono = float(ts_mono)

    ack_ms = metrics.get("time_to_first_feedback_ms")
    first_progress_ms = metrics.get("time_to_first_progress_ms")
    silent_ms = int(metrics.get("total_silent_window_ms") or 0)

    budgets = {
        "ack_under_100ms": ack_ms is not None and int(ack_ms) < UX_BUDGET_ACK_MS,
        "first_progress_under_500ms": first_progress_ms is not None and int(first_progress_ms) < UX_BUDGET_FIRST_PROGRESS_MS,
        "silent_window_under_5s": silent_ms < UX_BUDGET_SILENT_WINDOW_MS,
        "longest_gap_under_5s": longest_silent_ms < UX_BUDGET_SILENT_WINDOW_MS,
    }
    budgets["ux_budget_passed"] = all(budgets.values())

    return {
        **metrics,
        "total_operation_duration_ms": total_duration_ms,
        "longest_silent_window_ms": longest_silent_ms,
        "slowest_phase": slowest,
        "ux_budgets": budgets,
        "ux_budget_thresholds": {
            "ack_ms": UX_BUDGET_ACK_MS,
            "first_progress_ms": UX_BUDGET_FIRST_PROGRESS_MS,
            "silent_window_ms": UX_BUDGET_SILENT_WINDOW_MS,
        },
    }


def format_watch_line_polished(event: dict[str, Any]) -> str:
    """Compact watch line with normalized state and symbols."""
    try:
        from plugins.dietcode.lib.agent.kernel_progress_ux import compact_watch_line
    except ImportError:
        from lib.agent.kernel_progress_ux import compact_watch_line
    return compact_watch_line(event, polished=True)
