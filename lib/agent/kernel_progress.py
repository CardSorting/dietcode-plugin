# -*- coding: utf-8 -*-
"""Phase 6 — kernel bridge progress telemetry, storage, and operator ergonomics."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterator, Optional

logger = logging.getLogger(__name__)

PHASE_BRIDGE_PREFLIGHT = "bridge.preflight"
PHASE_SOCKET_READY = "socket.ready"
PHASE_WORKSPACE_OPEN = "workspace.open"
PHASE_COHERENCE_READ = "coherence.read"
PHASE_COHERENCE_ANCHOR_REFRESH = "coherence.anchor_refresh"
PHASE_PATCH_VALIDATE = "patch.validate"
PHASE_PATCH_APPLY = "patch.apply"
PHASE_APPROVAL_WAITING = "approval.waiting"
PHASE_VERIFY_RUNNING = "verify.running"
PHASE_JOURNAL_RECORDING = "journal.recording"
PHASE_CONVERGENCE_CHECKING = "convergence.checking"
PHASE_DONE = "done"
PHASE_ERROR = "error"
PHASE_PROGRESS_STALLED = "bridge.progress_stalled"

PROGRESS_PHASES = frozenset({
    PHASE_BRIDGE_PREFLIGHT,
    PHASE_SOCKET_READY,
    PHASE_WORKSPACE_OPEN,
    PHASE_COHERENCE_READ,
    PHASE_COHERENCE_ANCHOR_REFRESH,
    PHASE_PATCH_VALIDATE,
    PHASE_PATCH_APPLY,
    PHASE_APPROVAL_WAITING,
    PHASE_VERIFY_RUNNING,
    PHASE_JOURNAL_RECORDING,
    PHASE_CONVERGENCE_CHECKING,
    PHASE_DONE,
    PHASE_ERROR,
    PHASE_PROGRESS_STALLED,
})

STALL_THRESHOLD_MS = 15_000
PROGRESS_HEARTBEAT_INTERVAL_MS = 7_500
MAX_LOG_BYTES = 2 * 1024 * 1024
MAX_LOG_LINES = 5000
DEFAULT_TAIL_LINES = 40
DEFAULT_LAST_OPERATIONS = 5

_SECRET_PATTERNS = (
    re.compile(r"(token|secret|password|api[_-]?key|authorization)\s*[:=]\s*\S+", re.I),
    re.compile(r"Bearer\s+\S+", re.I),
    re.compile(r"session\.token", re.I),
)

_local = threading.local()
_write_lock = threading.Lock()
_stall_emitted_for: set[str] = set()
_progress_jsonl_buffer: list[str] = []
_last_jsonl_flush_mono: float = 0.0
_TERMINAL_PHASES = frozenset({PHASE_DONE, PHASE_ERROR, PHASE_PROGRESS_STALLED})


def session_dir() -> Path:
    raw = os.environ.get("DIETCODE_SESSION_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".dietcode" / "session"


def progress_log_path() -> Path:
    return session_dir() / "kernel-progress.jsonl"


def progress_current_path() -> Path:
    return session_dir() / "kernel-progress-current.json"


def new_operation_id() -> str:
    return f"op_{uuid.uuid4().hex[:12]}"


def new_correlation_id() -> str:
    return f"corr_{uuid.uuid4().hex[:12]}"


def redact_secrets(value: Any) -> Any:
    if isinstance(value, str):
        redacted = value
        for pattern in _SECRET_PATTERNS:
            redacted = pattern.sub(lambda m: m.group(0).split("=")[0] + "=***" if "=" in m.group(0) else "***", redacted)
        if len(redacted) > 4000:
            return redacted[:4000] + "…"
        return redacted
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            key_lower = str(key).lower()
            if any(tok in key_lower for tok in ("token", "secret", "password", "authorization")):
                out[key] = "***"
            else:
                out[key] = redact_secrets(item)
        return out
    if isinstance(value, list):
        return [redact_secrets(item) for item in value[:50]]
    return value


def _ensure_session_dir() -> None:
    session_dir().mkdir(parents=True, exist_ok=True)


def rotate_or_truncate_log() -> None:
    path = progress_log_path()
    if not path.is_file():
        return
    try:
        if path.stat().st_size <= MAX_LOG_BYTES:
            return
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        if len(lines) <= MAX_LOG_LINES:
            keep = lines[-(MAX_LOG_LINES // 2) :]
        else:
            keep = lines[-MAX_LOG_LINES :]
        path.write_text("\n".join(keep) + ("\n" if keep else ""), encoding="utf-8")
    except OSError as exc:
        logger.warning("kernel progress log rotation skipped: %s", exc)


def _progress_flush_interval_ms() -> int:
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_client import KernelBridgeConfig
    except ImportError:
        try:
            from lib.agent.kernel_bridge_client import KernelBridgeConfig
        except ImportError:
            return 250
    return max(0, int(KernelBridgeConfig.load().progress_flush_interval_ms))


def _flush_progress_jsonl(*, force: bool = False) -> None:
    global _last_jsonl_flush_mono
    if not _progress_jsonl_buffer:
        return
    interval_ms = _progress_flush_interval_ms()
    now = time.monotonic()
    if not force and interval_ms > 0:
        if _last_jsonl_flush_mono <= 0:
            _last_jsonl_flush_mono = now
            return
        if (now - _last_jsonl_flush_mono) * 1000.0 < interval_ms:
            return
    _ensure_session_dir()
    rotate_or_truncate_log()
    with _write_lock:
        with progress_log_path().open("a", encoding="utf-8") as handle:
            for line in _progress_jsonl_buffer:
                handle.write(line + "\n")
        _progress_jsonl_buffer.clear()
        _last_jsonl_flush_mono = now


def flush_progress_writes(*, force: bool = True) -> None:
    """Flush batched JSONL progress lines (tests / shutdown)."""
    _flush_progress_jsonl(force=force)


def reset_progress_write_buffer() -> None:
    """Test helper."""
    global _last_jsonl_flush_mono
    _progress_jsonl_buffer.clear()
    _last_jsonl_flush_mono = 0.0


def _write_progress_event(event: dict[str, Any]) -> None:
    _ensure_session_dir()
    redacted = redact_secrets(event)
    line = json.dumps(redacted, ensure_ascii=False, separators=(",", ":"))
    phase = str(event.get("phase") or "")
    with _write_lock:
        progress_current_path().write_text(
            json.dumps(redacted, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        _progress_jsonl_buffer.append(line)
    force = phase in _TERMINAL_PHASES
    _flush_progress_jsonl(force=force)


def current_tracker() -> Optional["KernelProgressTracker"]:
    tracker = getattr(_local, "tracker", None)
    return tracker if isinstance(tracker, KernelProgressTracker) else None


def emit_phase(phase: str, *, string_code: str = "", **extra: Any) -> None:
    tracker = current_tracker()
    if tracker is not None:
        tracker.emit(phase, string_code=string_code, **extra)


class KernelProgressTracker:
    """Structured progress emitter for one kernel bridge operation."""

    def __init__(
        self,
        *,
        action: str,
        path: str = "",
        workspace_root: str = "",
        task_id: str = "",
        attempt: int = 1,
        correlation_id: str | None = None,
        operation_id: str | None = None,
    ) -> None:
        self.operation_id = operation_id or new_operation_id()
        self.correlation_id = correlation_id or new_correlation_id()
        self.action = str(action or "").strip().lower()
        self.path = str(path or "")
        self.command = ""
        self.workspace_root = str(workspace_root or "")
        self.task_id = str(task_id or "")
        self.attempt = max(1, int(attempt))
        self.started_mono = time.monotonic()
        self.last_emit_mono = self.started_mono
        self.last_phase = PHASE_BRIDGE_PREFLIGHT
        self.finished = False
        self._phase_count = 0

    def elapsed_ms(self) -> int:
        return int((time.monotonic() - self.started_mono) * 1000)

    def since_last_emit_ms(self) -> int:
        return int((time.monotonic() - self.last_emit_mono) * 1000)

    def emit(self, phase: str, *, string_code: str = "", **extra: Any) -> dict[str, Any]:
        if self.finished and phase not in {PHASE_PROGRESS_STALLED, PHASE_DONE, PHASE_ERROR}:
            return {}
        phase_name = str(phase or "").strip()
        if phase_name not in PROGRESS_PHASES:
            phase_name = PHASE_BRIDGE_PREFLIGHT
        now_mono = time.monotonic()
        phase_duration_ms = int((now_mono - self.last_emit_mono) * 1000) if self._phase_count else 0
        self.last_phase = phase_name
        self.last_emit_mono = now_mono
        self._phase_count += 1
        if phase_name != PHASE_PROGRESS_STALLED:
            _stall_emitted_for.discard(self.operation_id)
        event: dict[str, Any] = {
            "ts": time.time(),
            "ts_mono": time.monotonic(),
            "correlation_id": self.correlation_id,
            "operation_id": self.operation_id,
            "taskId": self.task_id or None,
            "action": self.action,
            "path": self.path or None,
            "workspace_root": self.workspace_root or None,
            "elapsed_ms": self.elapsed_ms(),
            "duration_ms": self.elapsed_ms(),
            "attempt": self.attempt,
            "phase": phase_name,
            "phase_duration_ms": phase_duration_ms,
            "perf_bucket": None,
            "string_code": string_code or None,
        }
        try:
            from plugins.dietcode.lib.agent.kernel_bridge_perf import PHASE_PERF_BUCKETS
        except ImportError:
            from lib.agent.kernel_bridge_perf import PHASE_PERF_BUCKETS
        event["perf_bucket"] = PHASE_PERF_BUCKETS.get(phase_name)
        if extra:
            event.update(extra)
            if extra.get("command"):
                self.command = str(extra["command"])
        event["summary"] = human_progress_summary(event)
        _write_progress_event(event)
        return event

    def finish(
        self,
        *,
        ok: bool = True,
        string_code: str = "",
        error: dict[str, Any] | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        phase = PHASE_DONE if ok else PHASE_ERROR
        payload = dict(extra)
        if error:
            payload["error"] = redact_secrets(error)
        event = self.emit(phase, string_code=string_code, **payload)
        self.finished = True
        flush_progress_writes(force=True)
        return event

    def check_stalled(self) -> dict[str, Any] | None:
        if self.finished:
            return None
        if self.since_last_emit_ms() < STALL_THRESHOLD_MS:
            return None
        if self.operation_id in _stall_emitted_for:
            return None
        _stall_emitted_for.add(self.operation_id)
        return self.emit(
            PHASE_PROGRESS_STALLED,
            string_code="bridge_progress_stalled",
            last_phase=self.last_phase,
            stalled_ms=self.since_last_emit_ms(),
        )


def start_operation(
    *,
    action: str,
    path: str = "",
    command: str = "",
    workspace_root: str = "",
    task_id: str = "",
    attempt: int = 1,
) -> KernelProgressTracker:
    tracker = KernelProgressTracker(
        action=action,
        path=path,
        workspace_root=workspace_root,
        task_id=task_id,
        attempt=attempt,
    )
    tracker.command = str(command or "")
    _local.tracker = tracker
    tracker.emit(PHASE_BRIDGE_PREFLIGHT, command=tracker.command or None)
    return tracker


def end_operation() -> None:
    tracker = current_tracker()
    if tracker is not None and not tracker.finished:
        tracker.finish(ok=False, string_code="operation_interrupted")
    _local.tracker = None
    flush_progress_writes(force=True)


def coherence_emit_callback(event_name: str, task_id: str, **kwargs: Any) -> None:
    """Map dietcode_coherence harness events to kernel progress phases."""
    mapping = {
        "approval.required": (PHASE_APPROVAL_WAITING, "approval_required"),
        "approval.resolved": (PHASE_PATCH_APPLY, "approval_resolved"),
        "context.stale": (PHASE_COHERENCE_READ, "coherence_stale"),
        "context.refreshed": (PHASE_COHERENCE_ANCHOR_REFRESH, "coherence_refreshed"),
        "coherence.retry": (PHASE_COHERENCE_ANCHOR_REFRESH, "coherence_retry"),
        "coherence.operator_required": (PHASE_ERROR, "coherence_operator_required"),
    }
    phase, code = mapping.get(event_name, (PHASE_COHERENCE_READ, event_name))
    emit_phase(phase, string_code=code, taskId=task_id, **kwargs)


def _elapsed_seconds(event: dict[str, Any]) -> float:
    ms = event.get("stalled_ms") or event.get("elapsed_ms") or 0
    try:
        return max(0.0, float(ms) / 1000.0)
    except (TypeError, ValueError):
        return 0.0


def human_progress_summary(event: dict[str, Any]) -> str:
    """Concise operator-facing line for a progress event."""
    phase = str(event.get("phase") or "unknown")
    elapsed = _elapsed_seconds(event)
    elapsed_i = int(elapsed)
    attempt = event.get("attempt") or 1
    path = event.get("path") or ""
    command = event.get("command") or ""
    action = event.get("action") or ""

    if phase == PHASE_PATCH_APPLY:
        target = path or "patch"
        return f"patch applying: {target}, attempt {attempt}, {elapsed_i}s elapsed"
    if phase == PHASE_APPROVAL_WAITING:
        return f"waiting for approval: patch.apply, {elapsed_i}s elapsed"
    if phase == PHASE_VERIFY_RUNNING:
        cmd = command or action or "verify"
        return f"verify running: {cmd}, {elapsed_i}s elapsed"
    if phase == PHASE_PROGRESS_STALLED:
        last_phase = event.get("last_phase") or "unknown"
        stalled_s = int((event.get("stalled_ms") or 0) / 1000)
        return f"stalled: last phase {last_phase}, no update for {stalled_s}s"
    if phase == PHASE_COHERENCE_ANCHOR_REFRESH:
        target = path or "workspace"
        return f"coherence recover: {target}, attempt {attempt}, {elapsed_i}s elapsed"
    if phase == PHASE_COHERENCE_READ:
        target = path or "file"
        return f"coherence read: {target}, {elapsed_i}s elapsed"
    if phase == PHASE_PATCH_VALIDATE:
        return f"patch validating: {path or 'file'}, {elapsed_i}s elapsed"
    if phase == PHASE_JOURNAL_RECORDING:
        return f"journal recording: {action or 'mutation'}, {elapsed_i}s elapsed"
    if phase == PHASE_DONE:
        return f"done: {action or 'operation'}, {elapsed_i}s total"
    if phase == PHASE_ERROR:
        code = event.get("string_code") or "error"
        return f"failed: {code}, {elapsed_i}s elapsed"
    if phase == PHASE_SOCKET_READY:
        return f"socket ready, {elapsed_i}s elapsed"
    if phase == PHASE_WORKSPACE_OPEN:
        return f"workspace open, {elapsed_i}s elapsed"
    return f"{phase}: {action or 'kernel'}, {elapsed_i}s elapsed"


def group_events_by_operation(events: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        op_id = str(event.get("operation_id") or "")
        if not op_id:
            continue
        grouped.setdefault(op_id, []).append(event)
    return grouped


def _operation_status(events: list[dict[str, Any]]) -> str:
    if not events:
        return "unknown"
    terminal = events[-1].get("phase")
    if terminal == PHASE_DONE:
        return "success"
    if terminal == PHASE_ERROR:
        return "failed"
    if terminal == PHASE_PROGRESS_STALLED:
        return "stalled"
    return "in_progress"


def summarize_recent_operations(*, count: int = DEFAULT_LAST_OPERATIONS) -> dict[str, Any]:
    events = read_progress_lines()
    grouped = group_events_by_operation(events)
    summaries: list[dict[str, Any]] = []
    for op_id, op_events in grouped.items():
        first = op_events[0]
        last = op_events[-1]
        status = _operation_status(op_events)
        duration_ms = last.get("elapsed_ms") or last.get("duration_ms") or 0
        entry: dict[str, Any] = {
            "operation_id": op_id,
            "action": first.get("action"),
            "path": first.get("path"),
            "command": first.get("command"),
            "status": status,
            "duration_ms": duration_ms,
            "final_phase": last.get("phase"),
            "summary": last.get("summary") or human_progress_summary(last),
        }
        if status == "failed":
            entry["string_code"] = last.get("string_code")
        summaries.append(entry)
    last_index: dict[str, int] = {}
    for idx, event in enumerate(events):
        op_id = str(event.get("operation_id") or "")
        if op_id:
            last_index[op_id] = idx
    summaries.sort(key=lambda item: last_index.get(str(item.get("operation_id") or ""), 0), reverse=True)
    trimmed = summaries[: max(1, int(count))]
    return {"ok": True, "count": len(trimmed), "operations": trimmed}


def read_operation_events(operation_id: str) -> list[dict[str, Any]]:
    op_id = str(operation_id or "").strip()
    if not op_id:
        return []
    return [
        event
        for event in read_progress_lines()
        if str(event.get("operation_id") or "") == op_id
    ]


def build_operation_timeline(*, operation_id: str | None = None) -> dict[str, Any]:
    events: list[dict[str, Any]]
    if operation_id:
        events = read_operation_events(operation_id)
        if not events:
            return {
                "ok": False,
                "error": "operation_not_found",
                "operation_id": operation_id,
                "message": f"No events for operation_id={operation_id!r}",
            }
    else:
        current = read_progress_current()
        if current.get("ok") and isinstance(current.get("current"), dict):
            op_id = str(current["current"].get("operation_id") or "")
            events = read_operation_events(op_id) if op_id else []
        else:
            events = []
        if not events:
            all_events = read_progress_lines()
            grouped = group_events_by_operation(all_events)
            if not grouped:
                return {"ok": False, "error": "no_operations", "message": "No kernel operations recorded."}
            last_op_id = list(grouped.keys())[-1]
            events = grouped[last_op_id]
            operation_id = last_op_id

    lines: list[str] = []
    for event in events:
        seconds = _elapsed_seconds(event)
        phase = event.get("phase") or "unknown"
        lines.append(f"[{seconds:.1f}s] {phase}")

    op_id = operation_id or (events[0].get("operation_id") if events else None)
    return {
        "ok": True,
        "operation_id": op_id,
        "action": events[0].get("action") if events else None,
        "status": _operation_status(events),
        "timeline": lines,
        "timeline_text": "\n".join(lines),
        "events": events,
    }


def format_operation_timeline(*, operation_id: str | None = None) -> str:
    payload = build_operation_timeline(operation_id=operation_id)
    if not payload.get("ok"):
        return payload.get("message") or json.dumps(payload, indent=2)
    header = f"🥦 Kernel timeline — {payload.get('operation_id')} ({payload.get('action')}, {payload.get('status')})"
    return "\n".join([header, "", payload.get("timeline_text", "")])


def format_recent_operations_report(*, count: int = DEFAULT_LAST_OPERATIONS) -> str:
    payload = summarize_recent_operations(count=count)
    lines = [f"🥦 Kernel progress — last {payload['count']} operations", ""]
    for op in payload.get("operations") or []:
        mark = "✅" if op.get("status") == "success" else "⚠️ " if op.get("status") == "in_progress" else "❌"
        target = op.get("path") or op.get("command") or ""
        duration_s = int((op.get("duration_ms") or 0) / 1000)
        line = (
            f"{mark} {op.get('operation_id')} | {op.get('action')} | "
            f"{target} | {op.get('status')} | {duration_s}s | {op.get('final_phase')}"
        )
        if op.get("string_code"):
            line += f" | {op['string_code']}"
        lines.append(line)
    if payload["count"] == 0:
        lines.append("ℹ️  No operations recorded yet.")
    return "\n".join(lines)


_ERROR_ENVELOPE_HINTS: dict[str, dict[str, Any]] = {
    "bridge_disabled": {
        "operator_action": "Enable dietcode.kernel.bridge.enabled in Hermes config.",
        "suggested_slash_command": "/dietcode kernel status",
        "next_action": "Set dietcode.kernel.bridge.enabled: true and reload Hermes.",
        "retryable": False,
        "safe_to_retry": False,
        "diagnostic_command": "/dietcode kernel status",
    },
    "bridge_platform_unsupported": {
        "operator_action": "Kernel bridge is macOS-only; use BroccoliDB/JoyZoning on Linux.",
        "suggested_slash_command": "/dietcode doctor",
        "next_action": "Continue with raw Hermes writes or BroccoliDB on this host.",
        "retryable": False,
        "safe_to_retry": False,
        "diagnostic_command": "/dietcode doctor",
    },
    "bridge_binary_missing": {
        "operator_action": "Build the kernel binary: make -C kernel kernel",
        "suggested_slash_command": "/dietcode kernel status",
        "next_action": "Run make -C kernel kernel then make -C kernel restart-agent-server-fast.",
        "retryable": False,
        "safe_to_retry": False,
        "diagnostic_command": "/dietcode kernel status",
    },
    "bridge_socket_unavailable": {
        "operator_action": "Restart the kernel agent server.",
        "suggested_slash_command": "/dietcode kernel status",
        "next_action": "make -C kernel restart-agent-server-fast, then retry.",
        "retryable": True,
        "safe_to_retry": True,
        "retry_command": "dietcode_kernel(action='status')",
        "diagnostic_command": "/dietcode kernel status",
    },
    "bridge_token_unavailable": {
        "operator_action": "Restart agent server to refresh session.token.",
        "suggested_slash_command": "/dietcode kernel status",
        "next_action": "make -C kernel restart-agent-server-fast (token is recreated, not leaked in logs).",
        "retryable": True,
        "safe_to_retry": True,
        "retry_command": "dietcode_kernel(action='status')",
        "diagnostic_command": "/dietcode kernel status",
    },
    "bridge_workspace_unsafe": {
        "operator_action": "Point HERMES_KANBAN_WORKSPACE at your project root.",
        "suggested_slash_command": "/dietcode kernel explain-gate",
        "next_action": "export HERMES_KANBAN_WORKSPACE=/path/to/project",
        "retryable": False,
        "safe_to_retry": False,
        "diagnostic_command": "/dietcode kernel explain-gate",
    },
    "bridge_workspace_unresolved": {
        "operator_action": "Set HERMES_KANBAN_WORKSPACE or DIETCODE_WORKSPACE_ROOT.",
        "suggested_slash_command": "/dietcode kernel explain-gate",
        "next_action": "export HERMES_KANBAN_WORKSPACE=/path/to/project",
        "retryable": False,
        "safe_to_retry": False,
        "diagnostic_command": "/dietcode kernel explain-gate",
    },
    "bridge_patch_disabled": {
        "operator_action": "Set dietcode.kernel.bridge.mutations_enabled: true.",
        "suggested_slash_command": "/dietcode kernel explain-gate",
        "next_action": "Set mutations_enabled: true in Hermes config, reload, then retry patch.",
        "retryable": False,
        "safe_to_retry": False,
        "diagnostic_command": "/dietcode kernel explain-gate",
        "rollback_command": "Use raw write_file/patch (patch gate closed — always allowed).",
    },
    "bridge_rpc_timeout": {
        "operator_action": "Retry after checking socket health; increase request_timeout_sec if needed.",
        "suggested_slash_command": "/dietcode kernel progress --current",
        "next_action": "Check progress timeline; restart socket if stalled, then retry once.",
        "retryable": True,
        "safe_to_retry": True,
        "retry_command": "dietcode_kernel(action='status')",
        "diagnostic_command": "/dietcode kernel progress --timeline",
    },
    "bridge_verify_command_rejected": {
        "operator_action": "Use an allowlisted verify command prefix.",
        "suggested_slash_command": "/dietcode kernel status",
        "next_action": "Retry with ./verify.sh, make test, or another allowlisted prefix.",
        "retryable": False,
        "safe_to_retry": True,
        "retry_command": "dietcode_kernel(action='verify', command='./verify.sh')",
        "diagnostic_command": "/dietcode kernel status",
    },
    "kernel_raw_write_blocked": {
        "operator_action": "Use dietcode_kernel(action='patch') instead of raw write_file/patch.",
        "suggested_slash_command": "/dietcode kernel explain-gate",
        "next_action": "Switch to dietcode_kernel(action='patch') for this mutation.",
        "retryable": False,
        "safe_to_retry": False,
        "diagnostic_command": "/dietcode kernel explain-gate",
        "rollback_command": "Set raw_write_policy: allow and unset DIETCODE_KERNEL_RAW_WRITE_BLOCK=1",
    },
    "kernel_raw_write_warn": {
        "operator_action": "Prefer dietcode_kernel(action='patch') for governed mutation.",
        "suggested_slash_command": "/dietcode kernel explain-gate",
        "next_action": "Retry with dietcode_kernel(action='patch') or continue raw write (warn only).",
        "retryable": False,
        "safe_to_retry": True,
        "retry_command": "dietcode_kernel(action='patch', path='...', unified_diff='...')",
        "diagnostic_command": "/dietcode kernel explain-gate",
    },
    "approval_required": {
        "operator_action": "Resolve pending kernel approval before retrying patch.",
        "suggested_slash_command": "/dietcode kernel progress --current",
        "next_action": "Wait for approval resolution or check kernel approval queue.",
        "retryable": True,
        "safe_to_retry": True,
        "retry_command": "dietcode_kernel(action='patch', ...)",
        "diagnostic_command": "/dietcode kernel progress --timeline",
    },
    "bridge_progress_stalled": {
        "operator_action": "Check /dietcode kernel progress --current; restart socket if dead.",
        "suggested_slash_command": "/dietcode kernel progress --current",
        "next_action": "Inspect timeline; restart socket if no phase change, then retry once.",
        "retryable": True,
        "safe_to_retry": True,
        "retry_command": "dietcode_kernel(action='status')",
        "diagnostic_command": "/dietcode kernel progress --timeline",
    },
    "coherence_operator_required": {
        "operator_action": "Re-read changed paths and regenerate patch manually.",
        "suggested_slash_command": "/dietcode kernel progress --timeline",
        "next_action": "dietcode_kernel(action='status') then re-read stale paths before patch.",
        "retryable": False,
        "safe_to_retry": False,
        "diagnostic_command": "/dietcode kernel progress --timeline",
    },
    "mutations_disabled": {
        "operator_action": "Set dietcode.kernel.bridge.mutations_enabled: true.",
        "suggested_slash_command": "/dietcode kernel explain-gate",
        "next_action": "Enable mutations_enabled in config and reload Hermes.",
        "retryable": False,
        "safe_to_retry": False,
        "diagnostic_command": "/dietcode kernel explain-gate",
        "rollback_command": "Raw write_file/patch remain available while gate is closed.",
    },
    "socket_offline": {
        "operator_action": "Restart kernel agent server.",
        "suggested_slash_command": "/dietcode kernel status",
        "next_action": "make -C kernel restart-agent-server-fast",
        "retryable": True,
        "safe_to_retry": True,
        "retry_command": "dietcode_kernel(action='status')",
        "diagnostic_command": "/dietcode kernel status",
    },
    "token_missing": {
        "operator_action": "Restart agent server to recreate session.token.",
        "suggested_slash_command": "/dietcode kernel status",
        "next_action": "make -C kernel restart-agent-server-fast",
        "retryable": True,
        "safe_to_retry": True,
        "diagnostic_command": "/dietcode kernel status",
    },
    "workspace_unsafe": {
        "operator_action": "Point workspace at your project, not plugin/kernel roots.",
        "suggested_slash_command": "/dietcode kernel explain-gate",
        "next_action": "export HERMES_KANBAN_WORKSPACE=/path/to/project",
        "retryable": False,
        "safe_to_retry": False,
        "diagnostic_command": "/dietcode kernel explain-gate",
    },
}


def normalize_bridge_error(
    string_code: str,
    message: str,
    *,
    phase: str = "",
    recovery_hint: str = "",
    retryable: bool = False,
    raw_error: Any = None,
) -> dict[str, Any]:
    code = str(string_code or "bridge_rpc_error").strip()
    hints = _ERROR_ENVELOPE_HINTS.get(code, {})
    operator_action = recovery_hint or hints.get("operator_action") or "Review /dietcode kernel last-error."
    safe_to_retry = bool(hints.get("safe_to_retry", hints.get("retryable", retryable)))
    envelope: dict[str, Any] = {
        "string_code": code,
        "human_message": str(message or code),
        "operator_action": operator_action,
        "next_action": hints.get("next_action") or operator_action,
        "retryable": bool(retryable if retryable is not None else hints.get("retryable", False)),
        "safe_to_retry": safe_to_retry,
        "phase": phase or None,
        "raw_error": redact_secrets(_summarize_raw_error(raw_error)),
        "suggested_slash_command": hints.get("suggested_slash_command", "/dietcode kernel progress --current"),
        "diagnostic_command": hints.get("diagnostic_command", "/dietcode kernel progress --current"),
    }
    if hints.get("retry_command"):
        envelope["retry_command"] = hints["retry_command"]
    if hints.get("rollback_command"):
        envelope["rollback_command"] = hints["rollback_command"]
    return envelope


def _summarize_raw_error(raw_error: Any) -> Any:
    if raw_error is None:
        return None
    if isinstance(raw_error, dict):
        summary = {
            key: raw_error[key]
            for key in ("string_code", "message", "recovery_hint", "retryable")
            if key in raw_error
        }
        if "rpc" in raw_error and isinstance(raw_error["rpc"], dict):
            rpc_err = raw_error["rpc"].get("error")
            if isinstance(rpc_err, dict):
                summary["rpc_error"] = {
                    k: rpc_err[k]
                    for k in ("string_code", "message")
                    if k in rpc_err
                }
        return summary or raw_error
    if isinstance(raw_error, Exception):
        return {"type": raw_error.__class__.__name__, "message": str(raw_error)}
    text = str(raw_error)
    return text[:500] + ("…" if len(text) > 500 else "")


def build_agent_operator_hints(
    *,
    action: str = "",
    gate: dict[str, Any] | None = None,
    string_code: str = "",
    mutation_safe: bool | None = None,
) -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_client import build_patch_gate_state
    except ImportError:
        from lib.agent.kernel_bridge_client import build_patch_gate_state

    snap = gate if gate is not None else build_patch_gate_state()
    ws_root = snap.get("resolved_workspace_root") or ""
    patch_allowed = bool(snap.get("patch_allowed"))
    safe = mutation_safe if mutation_safe is not None else bool(snap.get("workspace_safe_for_mutation"))
    hints: dict[str, Any] = {
        "workspace_root": ws_root,
        "mutation_safe": safe,
        "patch_allowed": patch_allowed,
        "preferred_command": _preferred_command_shape(action),
        "slash_commands": [
            "/dietcode kernel progress --current",
            "/dietcode kernel explain-gate",
        ],
    }
    if string_code:
        envelope = normalize_bridge_error(string_code, "", phase="", raw_error=None)
        hints["error"] = envelope
        hints["recovery_suggestion"] = envelope.get("operator_action")
        hints["suggested_slash_command"] = envelope.get("suggested_slash_command")
        hints["next_action"] = envelope.get("next_action")
        hints["safe_to_retry"] = envelope.get("safe_to_retry")
        hints["retry_command"] = envelope.get("retry_command")
        hints["diagnostic_command"] = envelope.get("diagnostic_command")
        hints["rollback_command"] = envelope.get("rollback_command")
    elif not patch_allowed:
        hints["missing_gate"] = _missing_gate_reason(snap)
        hints["recovery_suggestion"] = snap.get("recovery_hint") or hints["missing_gate"]
    elif action == "patch":
        hints["recovery_suggestion"] = "Patch gate open — use dietcode_kernel(action='patch', path=..., unified_diff=...)."
    return hints


def _preferred_command_shape(action: str) -> str:
    act = str(action or "").strip().lower()
    shapes = {
        "patch": "dietcode_kernel(action='patch', path='src/foo.py', unified_diff='...', task_id='...')",
        "verify": "dietcode_kernel(action='verify', command='./verify.sh', task_id='...')",
        "status": "dietcode_kernel(action='status')",
        "search": "dietcode_kernel(action='search', query='pattern')",
    }
    return shapes.get(act, "dietcode_kernel(action='status')")


def _missing_gate_reason(gate: dict[str, Any]) -> str:
    if not gate.get("bridge_enabled"):
        return "bridge_disabled"
    if not gate.get("mutations_enabled"):
        return "mutations_disabled"
    if not gate.get("workspace_safe_for_mutation"):
        return "workspace_unsafe"
    if not gate.get("socket_ready"):
        return "socket_offline"
    if not gate.get("token_ready"):
        return "token_missing"
    if not gate.get("patch_allowed"):
        return "patch_gate_closed"
    return ""


_GATE_CHECKS: list[dict[str, Any]] = [
    {
        "id": "bridge_enabled",
        "label": "Bridge enabled",
        "is_open": lambda cfg, gate, _router: bool(cfg.enabled),
        "why_closed": "dietcode.kernel.bridge.enabled is false.",
        "fix": "Set dietcode.kernel.bridge.enabled: true in Hermes config.",
        "safe": True,
    },
    {
        "id": "mutations_enabled",
        "label": "Mutations enabled",
        "is_open": lambda cfg, gate, _router: bool(cfg.mutations_enabled),
        "why_closed": "dietcode.kernel.bridge.mutations_enabled is false (patch gate closed by default).",
        "fix": "Set dietcode.kernel.bridge.mutations_enabled: true in Hermes config.",
        "safe": True,
    },
    {
        "id": "workspace_safe",
        "label": "Workspace safe for mutation",
        "is_open": lambda _cfg, gate, _router: bool(gate.get("workspace_safe_for_mutation")),
        "why_closed": "Resolved workspace is plugin/kernel root or unresolved.",
        "fix": "export HERMES_KANBAN_WORKSPACE=/path/to/your/project",
        "safe": True,
    },
    {
        "id": "socket_ready",
        "label": "Control socket live",
        "is_open": lambda _cfg, gate, _router: bool(gate.get("socket_ready")),
        "why_closed": "~/.dietcode/control.sock offline or unreachable.",
        "fix": "make -C kernel restart-agent-server-fast",
        "safe": True,
    },
    {
        "id": "token_ready",
        "label": "Session token present",
        "is_open": lambda _cfg, gate, _router: bool(gate.get("token_ready")),
        "why_closed": "~/.dietcode/session.token missing or empty.",
        "fix": "make -C kernel restart-agent-server-fast",
        "safe": True,
    },
]


def _raw_write_behavior(router: dict[str, Any]) -> str:
    policy = router.get("raw_write_policy") or "warn"
    if router.get("would_block_raw_writes"):
        return f"{policy} + DIETCODE_KERNEL_RAW_WRITE_BLOCK — raw write_file/patch BLOCKED"
    if router.get("would_warn_on_raw_write"):
        return f"{policy} — raw write_file/patch get kernel hint (non-blocking)"
    if policy == "block" and not router.get("env_fuse_present"):
        return f"{policy} — fuse unset; warn-only until DIETCODE_KERNEL_RAW_WRITE_BLOCK=1"
    if policy == "allow":
        return "allow — raw writes allowed without kernel hints"
    return f"{policy} — no warn/block (patch gate closed or policy=allow)"


def build_gate_explanation() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_client import (
            KernelBridgeConfig,
            build_patch_gate_state,
        )
    except ImportError:
        from lib.agent.kernel_bridge_client import KernelBridgeConfig, build_patch_gate_state

    try:
        from plugins.dietcode.lib.agent.kernel_raw_write_router import (
            build_raw_write_router_health,
            raw_write_block_enforcement_enabled,
        )
    except ImportError:
        from lib.agent.kernel_raw_write_router import (
            build_raw_write_router_health,
            raw_write_block_enforcement_enabled,
        )

    cfg = KernelBridgeConfig.load()
    gate = build_patch_gate_state()
    router = build_raw_write_router_health()
    closed_gates: list[dict[str, Any]] = []
    open_gates: list[str] = []
    for check in _GATE_CHECKS:
        if check["is_open"](cfg, gate, router):
            open_gates.append(str(check["id"]))
        else:
            closed_gates.append({
                "id": check["id"],
                "label": check["label"],
                "why": check["why_closed"],
                "fix": check["fix"],
                "safe_to_apply": bool(check["safe"]),
            })

    missing = _missing_gate_reason(gate)
    raw_write_behavior = _raw_write_behavior(router)
    lines = [
        f"patch_allowed={gate.get('patch_allowed')}",
        f"closed_gates={len(closed_gates)}",
        f"raw_write_policy={router.get('raw_write_policy')}",
        f"raw_write_behavior={raw_write_behavior}",
        f"env_fuse_present={raw_write_block_enforcement_enabled()}",
    ]
    for item in closed_gates:
        lines.append(f"  ✗ {item['id']}: {item['why']}")
        lines.append(f"    fix ({'safe' if item['safe_to_apply'] else 'caution'}): {item['fix']}")
    if not closed_gates:
        lines.append("  ✓ all patch gates open")

    return {
        "ok": bool(gate.get("patch_allowed")),
        "gate": gate,
        "raw_write_router": router,
        "missing_gate": missing or None,
        "closed_gates": closed_gates,
        "open_gates": open_gates,
        "raw_write_behavior": raw_write_behavior,
        "summary": "\n".join(lines),
        "preferred_patch_command": _preferred_command_shape("patch"),
        "preferred_verify_command": _preferred_command_shape("verify"),
        "rollback_block_mode": (
            "Set raw_write_policy: allow (or warn) and unset DIETCODE_KERNEL_RAW_WRITE_BLOCK"
            if router.get("would_block_raw_writes")
            else None
        ),
    }


def format_gate_explanation() -> str:
    payload = build_gate_explanation()
    lines = ["🥦 Kernel gate explanation", "", payload["summary"], ""]
    if payload.get("closed_gates"):
        lines.append(f"⚠️  {len(payload['closed_gates'])} gate(s) closed")
        for item in payload["closed_gates"]:
            lines.append(f"   • {item['label']}: {item['fix']}")
    else:
        lines.append("✅ Patch gate open — governed mutation available")
    lines.append(f"   raw writes: {payload.get('raw_write_behavior')}")
    if payload.get("rollback_block_mode"):
        lines.append(f"   rollback block mode: {payload['rollback_block_mode']}")
    lines.append(f"   preferred patch: {payload['preferred_patch_command']}")
    lines.append("")
    lines.append("Slash: /dietcode kernel progress --timeline")
    return "\n".join(lines)


def read_progress_lines(*, tolerate_corrupt: bool = True) -> list[dict[str, Any]]:
    path = progress_log_path()
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            if tolerate_corrupt:
                continue
            raise
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def read_progress_current() -> dict[str, Any]:
    path = progress_current_path()
    if not path.is_file():
        return {"ok": False, "error": "no_progress_snapshot", "message": "No kernel progress recorded yet."}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"ok": False, "error": "corrupt_progress_snapshot", "message": "Current progress file is corrupt."}
    if not isinstance(data, dict):
        return {"ok": False, "error": "invalid_progress_snapshot", "message": "Current progress file is invalid."}
    stale = _stale_snapshot(data)
    payload = {"ok": True, "current": data}
    if stale:
        payload["stale"] = True
        payload["stale_ms"] = stale
    return payload


def read_progress_tail(*, lines: int = DEFAULT_TAIL_LINES) -> dict[str, Any]:
    events = read_progress_lines()
    if not events:
        return {
            "ok": True,
            "count": 0,
            "events": [],
            "message": "No kernel progress log yet — run dietcode_kernel to populate ~/.dietcode/session/kernel-progress.jsonl",
        }
    tail = events[-max(1, int(lines)) :]
    return {"ok": True, "count": len(tail), "events": tail}


def read_last_error() -> dict[str, Any]:
    for event in reversed(read_progress_lines()):
        if event.get("phase") == PHASE_ERROR or event.get("string_code"):
            if event.get("phase") == PHASE_DONE and not event.get("string_code"):
                continue
            code = str(event.get("string_code") or "bridge_rpc_error")
            message = ""
            err = event.get("error")
            if isinstance(err, dict):
                message = str(err.get("message") or err.get("human_message") or "")
            envelope = normalize_bridge_error(
                code,
                message or f"Kernel bridge failed during {event.get('phase')}",
                phase=str(event.get("phase") or ""),
                raw_error=err,
            )
            return {
                "ok": False,
                "last_error": envelope,
                "operation_id": event.get("operation_id"),
                "correlation_id": event.get("correlation_id"),
                "phase": event.get("phase"),
                "elapsed_ms": event.get("elapsed_ms"),
            }
    return {"ok": True, "message": "No kernel bridge errors recorded in progress log."}


def _stale_snapshot(snapshot: dict[str, Any]) -> int | None:
    phase = snapshot.get("phase")
    if phase in {PHASE_DONE, PHASE_ERROR, PHASE_PROGRESS_STALLED}:
        return None
    ts_mono = snapshot.get("ts_mono")
    if not isinstance(ts_mono, (int, float)):
        return None
    stalled_ms = int((time.monotonic() - float(ts_mono)) * 1000)
    if stalled_ms >= STALL_THRESHOLD_MS:
        return stalled_ms
    return None


def check_stalled_operations() -> list[dict[str, Any]]:
    current = read_progress_current()
    if not current.get("ok"):
        return []
    snap = current.get("current")
    if not isinstance(snap, dict):
        return []
    stale_ms = _stale_snapshot(snap)
    if stale_ms is None:
        return []
    op_id = str(snap.get("operation_id") or "")
    if op_id and op_id in _stall_emitted_for:
        return []
    event = {
        "ts": time.time(),
        "ts_mono": time.monotonic(),
        "correlation_id": snap.get("correlation_id"),
        "operation_id": op_id or new_operation_id(),
        "taskId": snap.get("taskId"),
        "action": snap.get("action"),
        "path": snap.get("path"),
        "command": snap.get("command"),
        "workspace_root": snap.get("workspace_root"),
        "elapsed_ms": snap.get("elapsed_ms"),
        "duration_ms": stale_ms,
        "attempt": snap.get("attempt", 1),
        "phase": PHASE_PROGRESS_STALLED,
        "string_code": "bridge_progress_stalled",
        "last_phase": snap.get("phase"),
        "stalled_ms": stale_ms,
    }
    event["summary"] = human_progress_summary(event)
    if op_id:
        _stall_emitted_for.add(op_id)
    _write_progress_event(event)
    return [event]


def build_progress_health() -> dict[str, Any]:
    current = read_progress_current()
    stale_ms = None
    if current.get("ok") and isinstance(current.get("current"), dict):
        stale_ms = _stale_snapshot(current["current"])
    stalled = check_stalled_operations() if stale_ms else []
    return {
        "log_path": str(progress_log_path()),
        "current_path": str(progress_current_path()),
        "log_exists": progress_log_path().is_file(),
        "current_exists": progress_current_path().is_file(),
        "stale_progress_ms": stale_ms,
        "stalled_events_emitted": len(stalled),
        "current": current.get("current") if current.get("ok") else None,
    }


def parse_progress_args(argv: list[str]) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "tail": False,
        "current": False,
        "timeline": False,
        "operation": None,
        "last": None,
    }
    idx = 0
    while idx < len(argv):
        arg = argv[idx].lower()
        if arg == "--current":
            opts["current"] = True
        elif arg == "--tail":
            opts["tail"] = True
        elif arg == "--timeline":
            opts["timeline"] = True
        elif arg == "--operation" and idx + 1 < len(argv):
            opts["operation"] = argv[idx + 1]
            idx += 1
        elif arg == "--last" and idx + 1 < len(argv):
            try:
                opts["last"] = int(argv[idx + 1])
            except ValueError:
                opts["last"] = DEFAULT_LAST_OPERATIONS
            idx += 1
        idx += 1
    return opts


def format_progress_report(
    *,
    tail: bool = False,
    current_only: bool = False,
    timeline: bool = False,
    operation_id: str | None = None,
    last: int | None = None,
) -> str:
    if current_only:
        payload = read_progress_current()
        if payload.get("ok") and isinstance(payload.get("current"), dict):
            snap = payload["current"]
            payload["human_summary"] = snap.get("summary") or human_progress_summary(snap)
        return json.dumps(payload, indent=2, ensure_ascii=False)
    if tail:
        if operation_id:
            events = read_operation_events(operation_id)
            return json.dumps(
                {"ok": bool(events), "operation_id": operation_id, "count": len(events), "events": events},
                indent=2,
                ensure_ascii=False,
            )
        return json.dumps(read_progress_tail(), indent=2, ensure_ascii=False)
    if timeline:
        return format_operation_timeline(operation_id=operation_id)
    if last is not None:
        return format_recent_operations_report(count=last)

    current = read_progress_current()
    lines = ["🥦 Kernel progress", ""]
    if not current.get("ok"):
        lines.append(f"ℹ️  {current.get('message', 'No progress recorded')}")
        lines.append(f"   log: {progress_log_path()}")
        return "\n".join(lines)
    snap = current.get("current") or {}
    summary = snap.get("summary") or human_progress_summary(snap)
    lines.append(summary)
    lines.append(
        f"   phase={snap.get('phase')} | operation_id={snap.get('operation_id')} | "
        f"action={snap.get('action')}"
    )
    if current.get("stale"):
        stalled_summary = human_progress_summary({
            "phase": PHASE_PROGRESS_STALLED,
            "last_phase": snap.get("phase"),
            "stalled_ms": current.get("stale_ms"),
        })
        lines.append(f"⚠️  {stalled_summary}")
    lines.append(f"   current: {progress_current_path()}")
    lines.append(f"   log: {progress_log_path()}")
    lines.append("")
    lines.append("More: --timeline | --last 5 | --operation <id> | --tail | --current")
    return "\n".join(lines)


def attach_operator_hints_to_result(result: dict[str, Any], *, action: str) -> dict[str, Any]:
    if not isinstance(result, dict):
        return result
    code = str(result.get("string_code") or "")
    if not code and isinstance(result.get("error"), dict):
        code = str(result["error"].get("string_code") or "")
    hints = build_agent_operator_hints(action=action, string_code=code if not result.get("ok") else "")
    merged = dict(result)
    merged["_kernel_operator_hints"] = hints
    if not result.get("ok"):
        err = result.get("error") if isinstance(result.get("error"), dict) else {}
        merged["_kernel_error_envelope"] = normalize_bridge_error(
            code or "bridge_rpc_error",
            str(err.get("message") or result.get("message") or "kernel bridge failed"),
            phase=str(current_tracker().last_phase if current_tracker() else ""),
            recovery_hint=str(err.get("recovery_hint") or ""),
            retryable=bool(err.get("retryable", False)),
            raw_error=err or result,
        )
    return merged
