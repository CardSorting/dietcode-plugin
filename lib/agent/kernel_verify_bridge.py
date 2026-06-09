# -*- coding: utf-8 -*-
"""Kernel verify.run bridge helpers — allowlist + doctor (Phase 4)."""
from __future__ import annotations

from typing import Any, Iterable

BRIDGE_VERIFY_COMMAND_REJECTED = "bridge_verify_command_rejected"

# Default prefixes aligned with kernel AgentVerifyCommands (verify-gate.md).
DEFAULT_VERIFY_COMMAND_PREFIXES: tuple[str, ...] = (
    "make test",
    "make kernel",
    "git diff --check",
    "npm test",
    "./verify.sh",
)

_OUTPUT_SUMMARY_LIMIT = 2000


def _load_kernel_bridge_raw() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.kernel_workspace import _load_kernel_config
    except ImportError:
        from lib.kernel_workspace import _load_kernel_config

    raw = _load_kernel_config()
    bridge = raw.get("bridge", {}) if isinstance(raw.get("bridge"), dict) else {}
    return bridge if isinstance(bridge, dict) else {}


def load_verify_allowlist() -> tuple[str, ...]:
    """Configured allowlist prefixes merged with kernel defaults."""
    bridge = _load_kernel_bridge_raw()
    extra = bridge.get("verify_allowlist")
    prefixes = list(DEFAULT_VERIFY_COMMAND_PREFIXES)
    if isinstance(extra, (list, tuple)):
        for item in extra:
            text = str(item or "").strip()
            if text and text not in prefixes:
                prefixes.append(text)
    return tuple(prefixes)


def is_command_allowlisted(command: str, *, allowlist: Iterable[str] | None = None) -> bool:
    cmd = str(command or "").strip()
    if not cmd:
        return False
    prefixes = tuple(allowlist) if allowlist is not None else load_verify_allowlist()
    return any(cmd.startswith(prefix) for prefix in prefixes)


def summarize_output(text: str, *, limit: int = _OUTPUT_SUMMARY_LIMIT) -> str:
    raw = str(text or "")
    if len(raw) <= limit:
        return raw
    return raw[:limit] + f"... [{len(raw) - limit} chars truncated]"


def extract_verify_fields(kernel_result: dict[str, Any]) -> dict[str, Any]:
    """Copy present verify result fields only (no invented values)."""
    fields: dict[str, Any] = {}
    for key in ("passed", "exitCode", "exit_code", "stdout", "stderr", "command", "cwd"):
        if key in kernel_result and kernel_result[key] is not None:
            fields[key] = kernel_result[key]
    if "exit_code" in fields and "exitCode" not in fields:
        fields["exitCode"] = fields["exit_code"]
    if "stdout" in fields:
        fields["stdout_summary"] = summarize_output(str(fields["stdout"]))
    if "stderr" in fields:
        fields["stderr_summary"] = summarize_output(str(fields["stderr"]))
    return fields


def build_verify_bridge_health(*, probe_runtime: bool = True) -> dict[str, Any]:
    allowlist = load_verify_allowlist()
    available = False
    gate: dict[str, Any] = {}
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_client import (
            KernelBridgeConfig,
            build_patch_gate_state,
        )
    except ImportError:
        from lib.agent.kernel_bridge_client import KernelBridgeConfig, build_patch_gate_state

    cfg = KernelBridgeConfig.load()
    if probe_runtime:
        gate = build_patch_gate_state()
        available = bool(
            cfg.enabled
            and gate.get("workspace_safe_for_mutation")
            and gate.get("socket_ready")
            and gate.get("token_ready")
        )
    else:
        available = bool(cfg.enabled)

    return {
        "phase": "4",
        "verify_action_available": available,
        "allowlist_prefixes": list(allowlist),
        "allowlist_count": len(allowlist),
        "bridge_enabled": cfg.enabled,
        "workspace_root": gate.get("resolved_workspace_root"),
        "patch_gate_open": bool(gate.get("patch_allowed")),
    }
