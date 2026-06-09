# -*- coding: utf-8 -*-
"""Phase 3A/3B — raw Hermes write router when kernel bridge patch gate is open."""
from __future__ import annotations

import json
import logging
import os
import threading
from typing import Any, Optional

logger = logging.getLogger(__name__)

KERNEL_RAW_WRITE_WARN = "kernel_raw_write_warn"
KERNEL_RAW_WRITE_BLOCKED = "kernel_raw_write_blocked"
RAW_WRITE_REASON_BRIDGE_READY = "bridge_ready"

RAW_WRITE_POLICY_ALLOW = "allow"
RAW_WRITE_POLICY_WARN = "warn"
RAW_WRITE_POLICY_BLOCK = "block"
_VALID_RAW_WRITE_POLICIES = frozenset({
    RAW_WRITE_POLICY_ALLOW,
    RAW_WRITE_POLICY_WARN,
    RAW_WRITE_POLICY_BLOCK,
})

# Hermes file mutation tools (aligned with governance_exemptions).
RAW_WRITE_TOOLS = frozenset({
    "write_file",
    "patch",
    "multi_replace_file_content",
    "replace_file_content",
})

_WARN_MESSAGE = (
    "Kernel bridge is ready; prefer dietcode_kernel(action='patch') for coherent mutation."
)
_BLOCK_MESSAGE = "Use dietcode_kernel(action='patch') for coherent mutation."

# Phase 3B — hard block only when this guard is enabled (config alone is not enough in 3A).
_PHASE_3B_BLOCK_ENV = "DIETCODE_KERNEL_RAW_WRITE_BLOCK"

_local = threading.local()


def raw_write_block_enforcement_enabled() -> bool:
    """Phase 3B gate — ``raw_write_policy: block`` is warn-only until this is true."""
    return os.environ.get(_PHASE_3B_BLOCK_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


def normalize_raw_write_policy(raw: str | None) -> str:
    policy = str(raw or RAW_WRITE_POLICY_WARN).strip().lower()
    if policy not in _VALID_RAW_WRITE_POLICIES:
        return RAW_WRITE_POLICY_WARN
    return policy


def is_raw_write_tool(tool_name: str) -> bool:
    return str(tool_name or "").strip() in RAW_WRITE_TOOLS


def _load_patch_gate(*, probe_runtime: bool = True) -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_client import build_patch_gate_state
    except ImportError:
        from lib.agent.kernel_bridge_client import build_patch_gate_state

    if probe_runtime:
        return build_patch_gate_state()

    cfg = _load_bridge_config()
    ws = _resolve_workspace_report()
    return {
        "bridge_enabled": cfg.enabled,
        "mutations_enabled": cfg.mutations_enabled,
        "workspace_safe_for_mutation": ws.safe_for_mutation,
        "resolved_workspace_root": ws.resolved_workspace_root,
        "socket_ready": False,
        "token_ready": False,
        "patch_allowed": False,
    }


def _load_bridge_config() -> Any:
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_client import KernelBridgeConfig
    except ImportError:
        from lib.agent.kernel_bridge_client import KernelBridgeConfig
    return KernelBridgeConfig.load()


def _resolve_workspace_report() -> Any:
    try:
        from plugins.dietcode.lib import kernel_workspace as kw
    except ImportError:
        from lib import kernel_workspace as kw
    return kw.resolve_workspace_root()


def bridge_ready_for_raw_write_hint(*, gate: dict[str, Any] | None = None) -> tuple[bool, dict[str, Any]]:
    """
    Return (ready, gate_snapshot).

    Ready when patch gate is open: bridge enabled, mutations on, safe workspace,
    socket + token live.
    """
    snap = gate if gate is not None else _load_patch_gate(probe_runtime=True)
    ready = bool(
        snap.get("bridge_enabled")
        and snap.get("mutations_enabled")
        and snap.get("workspace_safe_for_mutation")
        and snap.get("socket_ready")
        and snap.get("token_ready")
        and snap.get("patch_allowed")
    )
    return ready, snap


def should_intercept_raw_write(
    tool_name: str,
    *,
    policy: str | None = None,
    gate: dict[str, Any] | None = None,
) -> bool:
    if not is_raw_write_tool(tool_name):
        return False
    if tool_name == "dietcode_kernel":
        return False
    cfg = _load_bridge_config()
    effective_policy = normalize_raw_write_policy(policy if policy is not None else cfg.raw_write_policy)
    if effective_policy == RAW_WRITE_POLICY_ALLOW:
        return False
    ready, _ = bridge_ready_for_raw_write_hint(gate=gate)
    return ready


def build_raw_write_warning_metadata(*, gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "string_code": KERNEL_RAW_WRITE_WARN,
        "message": _WARN_MESSAGE,
        "preferred_tool": "dietcode_kernel",
        "reason": RAW_WRITE_REASON_BRIDGE_READY,
        "workspace_root": gate.get("resolved_workspace_root") or "",
    }


def build_raw_write_block_payload(*, gate: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "blocked": True,
        "string_code": KERNEL_RAW_WRITE_BLOCKED,
        "message": _BLOCK_MESSAGE,
        "preferred_tool": "dietcode_kernel",
        "workspace_root": gate.get("resolved_workspace_root") or "",
    }


def build_raw_write_block_pre_tool_call(*, gate: dict[str, Any]) -> dict[str, Any]:
    """Hermes pre_tool_call block directive with structured JSON message payload."""
    payload = build_raw_write_block_payload(gate=gate)
    return {
        "action": "block",
        "message": json.dumps(payload, ensure_ascii=False),
    }


def stash_raw_write_warning(metadata: dict[str, Any]) -> None:
    _local.pending_raw_write_warning = metadata


def take_raw_write_warning() -> Optional[dict[str, Any]]:
    meta = getattr(_local, "pending_raw_write_warning", None)
    _local.pending_raw_write_warning = None
    return meta if isinstance(meta, dict) else None


def clear_raw_write_warning_stash() -> None:
    """Test helper."""
    _local.pending_raw_write_warning = None


def evaluate_raw_write_pre_tool_call(
    *,
    tool_name: str = "",
    args: Any = None,
    gate: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Pre-tool router — warn (non-blocking) or block (Phase 3B guard only).

    Returns Hermes pre_tool_call dict (``action: block``) or warn metadata dict
    (``action: warn``) or None.
    """
    if not is_raw_write_tool(tool_name):
        return None

    cfg = _load_bridge_config()
    policy = normalize_raw_write_policy(cfg.raw_write_policy)
    if policy == RAW_WRITE_POLICY_ALLOW:
        return None

    ready, snap = bridge_ready_for_raw_write_hint(gate=gate)
    if not ready:
        return None

    metadata = build_raw_write_warning_metadata(gate=snap)

    if policy == RAW_WRITE_POLICY_BLOCK and raw_write_block_enforcement_enabled():
        logger.info(
            "kernel raw write block (%s): %s workspace=%s",
            tool_name,
            KERNEL_RAW_WRITE_BLOCKED,
            snap.get("resolved_workspace_root"),
        )
        return build_raw_write_block_pre_tool_call(gate=snap)

    stash_raw_write_warning(metadata)
    logger.info(
        "kernel raw write warn (%s): %s workspace=%s",
        tool_name,
        metadata["string_code"],
        metadata.get("workspace_root"),
    )
    return {"action": "warn", **metadata}


def merge_raw_write_warning_into_result(result: Any, metadata: dict[str, Any]) -> Optional[str]:
    """Attach warning metadata to tool JSON without changing success."""
    if not metadata:
        return None
    if isinstance(result, str) and result.strip():
        try:
            parsed = json.loads(result)
        except json.JSONDecodeError:
            return result + "\n\n⚠️ " + metadata.get("message", KERNEL_RAW_WRITE_WARN)
        if not isinstance(parsed, dict):
            return None
        if parsed.get("_kernel_raw_write_warning"):
            return None
        merged = dict(parsed)
        merged["_kernel_raw_write_warning"] = metadata
        return json.dumps(merged, ensure_ascii=False)

    if isinstance(result, dict):
        if result.get("_kernel_raw_write_warning"):
            return None
        merged = dict(result)
        merged["_kernel_raw_write_warning"] = metadata
        return json.dumps(merged, ensure_ascii=False)

    return None


def build_raw_write_router_health(*, probe_runtime: bool = True) -> dict[str, Any]:
    """Doctor payload for Phase 3A raw-write router."""
    cfg = _load_bridge_config()
    policy = normalize_raw_write_policy(cfg.raw_write_policy)
    gate = _load_patch_gate(probe_runtime=probe_runtime)
    ready, _ = bridge_ready_for_raw_write_hint(gate=gate)
    fuse = raw_write_block_enforcement_enabled()
    would_block = policy == RAW_WRITE_POLICY_BLOCK and ready and fuse
    would_warn = policy != RAW_WRITE_POLICY_ALLOW and ready and not would_block
    return {
        "raw_write_policy": policy,
        "patch_gate_open": bool(gate.get("patch_allowed")),
        "bridge_ready_for_hint": ready,
        "would_warn_on_raw_write": would_warn,
        "would_block_raw_writes": would_block,
        "env_fuse_present": fuse,
        "block_enforcement_active": fuse,
        "raw_write_blocking": would_block,
        "target_tools": sorted(RAW_WRITE_TOOLS),
        "workspace_root": gate.get("resolved_workspace_root"),
    }
