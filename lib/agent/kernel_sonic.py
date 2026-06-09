# -*- coding: utf-8 -*-
"""Phase 7D — high-tempo kinetic kernel UX (tempo only, no mutation semantics)."""
from __future__ import annotations

import os
import re
import statistics
import subprocess
import sys
import time
from typing import Any

SONIC_ACK_TARGET_MS = 50
SONIC_MICRO_PHASE_MS = 100
SONIC_FAST_PATH_MODE = "sonic_fast_path"

_SPINNER_FRAMES_UNICODE = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
_SPINNER_FRAMES_ASCII = ("|", "/", "-", "\\")

_MEANINGFUL_PHASES = frozenset({
    "operation.accepted",
    "patch.staging",
    "patch.validate",
    "patch.apply",
    "verify.running",
    "coherence.anchor_refresh",
    "approval.waiting",
    "journal.recording",
    "done",
    "error",
    "bridge.progress_stalled",
})

_VISUAL_UNICODE = {
    "running": "…",
    "success": "✓",
    "warning": "!",
    "failed": "✕",
    "waiting": "⏸",
    "stalled": "⚠",
}
_VISUAL_ASCII = {
    "running": "RUN",
    "success": "OK",
    "warning": "WARN",
    "failed": "FAIL",
    "waiting": "WAIT",
    "stalled": "STALL",
}

_ANSI_RESET = "\033[0m"
_ANSI_BY_STATE: dict[str, str] = {
    "accepted": "\033[36m",
    "preparing": "\033[36m",
    "validating": "\033[33m",
    "recovering": "\033[35m",
    "applying": "\033[34m",
    "verifying": "\033[32m",
    "journaling": "\033[90m",
    "blocked": "\033[33m",
    "stalled": "\033[31m",
    "failed": "\033[31m",
    "complete": "\033[32;1m",
    "idle": "\033[90m",
}

_ETA_MIN_SAMPLES = 3
_ETA_MIN_CONFIDENCE = 0.45


def use_unicode() -> bool:
    if os.environ.get("DIETCODE_ASCII_ONLY", "").strip().lower() in {"1", "true", "yes"}:
        return False
    enc = (getattr(sys.stdout, "encoding", None) or os.environ.get("PYTHONIOENCODING") or "").lower()
    if enc and "utf" not in enc and enc not in {"", "utf-8", "utf8"}:
        return False
    return True


def use_ansi() -> bool:
    if os.environ.get("DIETCODE_ASCII_ONLY", "").strip().lower() in {"1", "true", "yes"}:
        return False
    if os.environ.get("NO_COLOR", "").strip():
        return False
    if not (sys.stdout.isatty() or os.environ.get("DIETCODE_FORCE_ANSI", "").strip() in {"1", "true"}):
        return False
    term = (os.environ.get("TERM") or "").lower()
    if term == "dumb":
        return False
    return True


def visual_symbol(kind: str) -> str:
    table = _VISUAL_UNICODE if use_unicode() else _VISUAL_ASCII
    return table.get(kind, table["running"])


def spinner_frame(*, tick: int = 0) -> str:
    frames = _SPINNER_FRAMES_UNICODE if use_unicode() else _SPINNER_FRAMES_ASCII
    return frames[tick % len(frames)]


def build_accept_line(*, action: str, path: str = "", command: str = "") -> str:
    act = str(action or "kernel").strip().upper()
    target = str(path or command or "").strip()
    sym = visual_symbol("running")
    if target:
        return f"{sym} {act} accepted — {target}"
    return f"{sym} {act} accepted"


def should_suppress_operator_transition(
    *,
    phase: str,
    phase_duration_ms: int,
    fast_path: bool = False,
    string_code: str = "",
) -> bool:
    phase_name = str(phase or "")
    if phase_name in _MEANINGFUL_PHASES:
        return False
    if fast_path or phase_name == "patch.apply":
        return False
    if string_code or phase_name in {"error", "bridge.progress_stalled"}:
        return False
    if phase_duration_ms < SONIC_MICRO_PHASE_MS:
        return True
    return False


def _load_bridge_config() -> Any:
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_client import KernelBridgeConfig
    except ImportError:
        from lib.agent.kernel_bridge_client import KernelBridgeConfig
    return KernelBridgeConfig.load()


def _hook_commands() -> dict[str, str]:
    cfg = _load_bridge_config()
    hooks = getattr(cfg, "event_hooks", None)
    if isinstance(hooks, dict):
        return {str(k): str(v) for k, v in hooks.items() if v}
    if hooks:
        return {str(k): str(v) for k, v in hooks if v}
    return {}


def event_hooks_enabled() -> bool:
    cfg = _load_bridge_config()
    return bool(getattr(cfg, "event_hooks_enabled", False))


def emit_event_hook(event_name: str, *, payload: dict[str, Any] | None = None) -> None:
    if not event_hooks_enabled():
        return
    commands = _hook_commands()
    cmd = commands.get(event_name) or commands.get(event_name.replace(".", "_"))
    if not cmd:
        return
    env = os.environ.copy()
    env["DIETCODE_KERNEL_EVENT"] = event_name
    for key, value in (payload or {}).items():
        if value is None:
            continue
        env_key = f"DIETCODE_KERNEL_{key.upper()}"
        env[env_key] = str(value)[:500]
    try:
        subprocess.Popen(
            cmd,
            shell=True,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass


def _state_visual_kind(state: str, *, phase: str = "") -> str:
    if state == "complete":
        return "success"
    if state == "failed":
        return "failed"
    if state in {"stalled"} or phase == "bridge.progress_stalled":
        return "stalled"
    if state in {"blocked"} or phase == "approval.waiting":
        return "waiting"
    if state in {"accepted", "preparing", "validating", "recovering", "applying", "verifying", "journaling"}:
        return "running"
    return "running"


def colorize(text: str, *, state: str = "") -> str:
    if not use_ansi():
        return text
    color = _ANSI_BY_STATE.get(state, "")
    if not color:
        return text
    return f"{color}{text}{_ANSI_RESET}"


def format_kinetic_watch_line(
    event: dict[str, Any],
    *,
    spinner_tick: int = 0,
    include_eta: bool = True,
) -> str:
    try:
        from plugins.dietcode.lib.agent.kernel_cockpit import normalize_operation_state
        from plugins.dietcode.lib.agent.kernel_progress_ux import next_phase_hint
    except ImportError:
        from lib.agent.kernel_cockpit import normalize_operation_state
        from lib.agent.kernel_progress_ux import next_phase_hint

    phase = str(event.get("phase") or "")
    state = normalize_operation_state(
        phase=phase,
        heartbeat_phase=str(event.get("heartbeat_phase") or ""),
    )
    kind = _state_visual_kind(state, phase=phase)
    sym = visual_symbol(kind)

    if phase == "done":
        action = str(event.get("action") or "kernel").upper()
        op_short = str(event.get("operation_id") or "").replace("op_", "")[-4:] or "????"
        elapsed = (event.get("elapsed_ms") or 0) / 1000.0
        line = f"{visual_symbol('success')} {action} {op_short} complete ({elapsed:.1f}s)"
        return colorize(line, state="complete")

    if phase == "error":
        action = str(event.get("action") or "kernel").upper()
        op_short = str(event.get("operation_id") or "").replace("op_", "")[-4:] or "????"
        elapsed = (event.get("elapsed_ms") or 0) / 1000.0
        line = f"{visual_symbol('failed')} {action} {op_short} failed ({elapsed:.1f}s)"
        return colorize(line, state="failed")

    spin = spinner_frame(tick=spinner_tick) if kind == "running" else sym
    action = str(event.get("action") or "kernel").upper()
    op_short = str(event.get("operation_id") or "").replace("op_", "")[-4:] or "????"
    target = event.get("path") or event.get("command") or ""
    if isinstance(target, str) and len(target) > 48:
        target = "…" + target[-45:]
    elapsed = (event.get("elapsed_ms") or 0) / 1000.0

    verbs = {
        "operation.accepted": "accepted",
        "patch.apply": "applying",
        "patch.validate": "validating",
        "verify.running": "running",
        "coherence.anchor_refresh": "recovering",
        "approval.waiting": "waiting",
        "journal.recording": "journaling",
    }
    verb = verbs.get(phase, state.replace("_", " "))
    line = f"{spin} {action} {op_short} {verb}"
    if target:
        line += f" {target}"
    line += f" ({elapsed:.1f}s)"

    nxt = event.get("next_phase_hint") or next_phase_hint(phase, str(event.get("action") or ""))
    if nxt:
        line += f" {nxt}"

    if event.get("mode") == SONIC_FAST_PATH_MODE or event.get("fast_path"):
        line += " | FAST PATH ACTIVE"

    if include_eta:
        eta = estimate_remaining_ms(
            action=str(event.get("action") or ""),
            current_phase=phase,
            elapsed_ms=int(event.get("elapsed_ms") or 0),
        )
        if eta.get("show"):
            line += f" | ~{eta['remaining_s']}s remaining"

    return colorize(line, state=state)


def _phase_history_durations(*, action: str) -> dict[str, list[float]]:
    try:
        from plugins.dietcode.lib.agent.kernel_progress import group_events_by_operation, read_progress_lines
        from plugins.dietcode.lib.agent.kernel_progress_ux import estimated_phase_sequence
    except ImportError:
        from lib.agent.kernel_progress import group_events_by_operation, read_progress_lines
        from lib.agent.kernel_progress_ux import estimated_phase_sequence

    act = str(action or "").strip().lower()
    seq = estimated_phase_sequence(act)
    buckets: dict[str, list[float]] = {p: [] for p in seq}
    grouped = group_events_by_operation(read_progress_lines())
    for _op_id, events in grouped.items():
        if not events or str(events[0].get("action") or "").lower() != act:
            continue
        if events[-1].get("phase") != "done":
            continue
        for event in events:
            phase = str(event.get("phase") or "")
            dur = float(event.get("phase_duration_ms") or 0)
            if phase in buckets and dur > 0:
                buckets[phase].append(dur)
    return buckets


def estimate_remaining_ms(
    *,
    action: str,
    current_phase: str,
    elapsed_ms: int,
) -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.kernel_progress_ux import estimated_phase_sequence
    except ImportError:
        from lib.agent.kernel_progress_ux import estimated_phase_sequence

    seq = estimated_phase_sequence(action)
    phase = str(current_phase or "")
    try:
        idx = seq.index(phase)
    except ValueError:
        return {"show": False, "confidence": 0.0}

    history = _phase_history_durations(action=action)
    remaining: list[float] = []
    samples = 0
    for future_phase in seq[idx + 1 :]:
        if future_phase == "done":
            continue
        vals = history.get(future_phase) or []
        if len(vals) >= _ETA_MIN_SAMPLES:
            remaining.append(statistics.median(vals))
            samples += len(vals)

    if not remaining or samples < _ETA_MIN_SAMPLES:
        return {"show": False, "confidence": 0.0}

    total_remaining = sum(remaining)
    confidence = min(1.0, samples / (len(seq) * _ETA_MIN_SAMPLES))
    if confidence < _ETA_MIN_CONFIDENCE:
        return {"show": False, "confidence": confidence}

    remaining_s = max(1, int(round(total_remaining / 1000.0)))
    return {
        "show": True,
        "remaining_ms": int(total_remaining),
        "remaining_s": remaining_s,
        "confidence": round(confidence, 2),
        "elapsed_ms": elapsed_ms,
    }


def run_kinetic_watch(
    *,
    interval_sec: float = 1.0,
    max_sec: float = 30.0,
) -> str:
    try:
        from plugins.dietcode.lib.agent.kernel_progress import PHASE_DONE, PHASE_ERROR, read_progress_current
    except ImportError:
        from lib.agent.kernel_progress import PHASE_DONE, PHASE_ERROR, read_progress_current

    deadline = time.monotonic() + max_sec
    tick = 0
    last_line = ""
    final_line = ""
    kinetic_tty = sys.stdout.isatty() and (sys.stderr.isatty() or os.environ.get("DIETCODE_FORCE_ANSI"))

    while time.monotonic() < deadline:
        payload = read_progress_current()
        if not payload.get("ok") or not isinstance(payload.get("current"), dict):
            final_line = f"{visual_symbol('running')} Kernel watch — idle"
            if kinetic_tty:
                sys.stdout.write("\r\033[K" + final_line + "\n")
                sys.stdout.flush()
            break
        snap = payload["current"]
        line = format_kinetic_watch_line(snap, spinner_tick=tick)
        final_line = line
        if kinetic_tty:
            sys.stdout.write("\r\033[K" + line)
            sys.stdout.flush()
        elif line != last_line:
            print(line)
        last_line = line
        phase = snap.get("phase")
        if phase in {PHASE_DONE, PHASE_ERROR}:
            if kinetic_tty:
                sys.stdout.write("\n")
                sys.stdout.flush()
            break
        tick += 1
        time.sleep(interval_sec)

    return final_line or last_line or f"{visual_symbol('running')} Kernel watch — idle"


def build_sonic_bench_report() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.kernel_progress import group_events_by_operation, read_progress_current, read_progress_lines
        from plugins.dietcode.lib.agent.kernel_progress_ux import compute_operation_ux_metrics
        from plugins.dietcode.lib.agent.kernel_cockpit import enrich_ux_metrics
    except ImportError:
        from lib.agent.kernel_progress import group_events_by_operation, read_progress_current, read_progress_lines
        from lib.agent.kernel_progress_ux import compute_operation_ux_metrics
        from lib.agent.kernel_cockpit import enrich_ux_metrics

    events = read_progress_lines()
    grouped = group_events_by_operation(events)
    ack_vals: list[float] = []
    first_vals: list[float] = []
    silent_max: list[float] = []
    for _op, op_events in grouped.items():
        if not op_events:
            continue
        m = enrich_ux_metrics(compute_operation_ux_metrics(op_events), op_events)
        if m.get("time_to_first_feedback_ms") is not None:
            ack_vals.append(float(m["time_to_first_feedback_ms"]))
        if m.get("time_to_first_progress_ms") is not None:
            first_vals.append(float(m["time_to_first_progress_ms"]))
        silent_max.append(float(m.get("longest_silent_window_ms") or 0))

    current = read_progress_current()
    watch_line = ""
    if current.get("ok") and isinstance(current.get("current"), dict):
        watch_line = format_kinetic_watch_line(current["current"], include_eta=False)

    return {
        "ok": True,
        "ack_latency_ms": {
            "p50": statistics.median(ack_vals) if ack_vals else None,
            "max": max(ack_vals) if ack_vals else None,
            "budget_ms": SONIC_ACK_TARGET_MS,
            "passed": (max(ack_vals) if ack_vals else 0) < SONIC_ACK_TARGET_MS,
        },
        "first_visible_ms": {
            "p50": statistics.median(first_vals) if first_vals else None,
            "max": max(first_vals) if first_vals else None,
        },
        "max_silent_interval_ms": max(silent_max) if silent_max else 0,
        "watch_refresh_cadence_sec": 1.0,
        "watch_line_sample": watch_line,
        "operation_count": len(grouped),
    }


def format_sonic_bench_report(*, compact: bool = False) -> str:
    payload = build_sonic_bench_report()
    if compact:
        ack = payload.get("ack_latency_ms") or {}
        return (
            f"sonic: ack_p50={ack.get('p50')}ms ack_max={ack.get('max')}ms "
            f"silent_max={payload.get('max_silent_interval_ms')}ms "
            f"ops={payload.get('operation_count')}"
        )
    lines = ["🥦 Kernel sonic bench", ""]
    ack = payload.get("ack_latency_ms") or {}
    mark = visual_symbol("success") if ack.get("passed") else visual_symbol("warning")
    lines.append(f"{mark} Ack latency: p50={ack.get('p50')}ms max={ack.get('max')}ms (budget <{ack.get('budget_ms')}ms)")
    first = payload.get("first_visible_ms") or {}
    lines.append(f"First visible update: p50={first.get('p50')}ms max={first.get('max')}ms")
    lines.append(f"Max silent interval: {payload.get('max_silent_interval_ms')}ms")
    lines.append(f"Watch cadence: {payload.get('watch_refresh_cadence_sec')}s")
    if payload.get("watch_line_sample"):
        lines.append(f"Watch sample: {payload['watch_line_sample']}")
    return "\n".join(lines)


def contains_token_leak(text: str) -> bool:
    patterns = (
        re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}", re.I),
        re.compile(r"session\.token['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9._-]{8,}", re.I),
    )
    return any(p.search(text) for p in patterns)
