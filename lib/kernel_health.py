# -*- coding: utf-8 -*-
"""Kernel subtree health probes — platform, binary, socket, token (Phase 1)."""
from __future__ import annotations

import os
import platform
import shutil
import socket
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

_DEFAULT_SOCKET = Path.home() / ".dietcode" / "control.sock"
_DEFAULT_TOKEN = Path.home() / ".dietcode" / "session.token"


def _plugin_root() -> Path:
    try:
        from plugins.dietcode.paths import get_plugin_root

        return get_plugin_root()
    except ImportError:
        return Path(__file__).resolve().parents[1]


def kernel_root() -> Path:
    try:
        from plugins.dietcode.paths import kernel_root as _root

        return _root()
    except ImportError:
        return _plugin_root() / "kernel"


def kernel_binary_path() -> Path:
    try:
        from plugins.dietcode.paths import kernel_binary_path as _binary

        return _binary()
    except ImportError:
        env = os.environ.get("DIETCODE_APP_PATH", "").strip()
        if env:
            return Path(env).expanduser()
        return kernel_root() / "build" / "dietcode-kernel"


def kernel_makefile_path() -> Path:
    return kernel_root() / "Makefile"


def socket_path() -> Path:
    raw = os.environ.get("DIETCODE_SOCKET_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_SOCKET


def token_path() -> Path:
    raw = os.environ.get("DIETCODE_TOKEN_PATH", "").strip()
    if raw:
        return Path(raw).expanduser()
    return _DEFAULT_TOKEN


def platform_supported() -> bool:
    return sys.platform == "darwin"


def build_toolchain_available() -> bool:
    return bool(shutil.which("make") and shutil.which("clang++"))


def kernel_subtree_present() -> bool:
    root = kernel_root()
    return (
        (root / "Makefile").is_file()
        and (root / "src" / "kernel" / "main.mm").is_file()
        and (root / "scripts" / "dietcode_agent_client.py").is_file()
    )


def binary_exists() -> bool:
    path = kernel_binary_path()
    return path.is_file() and os.access(path, os.X_OK)


def socket_reachable() -> bool:
    path = socket_path()
    if not path.exists():
        return False
    try:
        mode = path.stat().st_mode
    except OSError:
        return False
    if not stat.S_ISSOCK(mode):
        return False
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(1.0)
            sock.connect(str(path))
        return True
    except OSError:
        return False


def token_readable() -> bool:
    path = token_path()
    if not path.is_file():
        return False
    try:
        text = path.read_text(encoding="utf-8").strip()
        return bool(text)
    except OSError:
        return False


def ensure_kernel_built(*, auto_build: bool = False, timeout: int = 600) -> dict[str, Any]:
    """Check or build ``kernel/build/dietcode-kernel`` (macOS + toolchain only)."""
    root = kernel_root()
    binary = kernel_binary_path()

    if not kernel_subtree_present():
        return {"ok": False, "action": "missing_subtree", "error": f"kernel subtree incomplete at {root}"}

    if not platform_supported():
        return {
            "ok": False,
            "action": "unsupported_platform",
            "platform": sys.platform,
            "hint": "Kernel build requires macOS; Hermes plugin remains usable without it.",
        }

    if binary_exists():
        return {"ok": True, "action": "ready", "binary": str(binary.resolve())}

    if not build_toolchain_available():
        return {
            "ok": False,
            "action": "toolchain_missing",
            "hint": "Install Xcode CLT (clang++, make) then: make -C kernel kernel",
        }

    if not auto_build:
        return {
            "ok": False,
            "action": "build_required",
            "hint": f"make -C {root} kernel",
            "binary": str(binary),
        }

    makefile = kernel_makefile_path()
    if not makefile.is_file():
        return {"ok": False, "action": "missing_makefile", "error": str(makefile)}

    # Build cwd is always the quarantined kernel subtree — never the Hermes user workspace.
    build_env = {**os.environ, "CI": "1"}
    build_env.pop("DIETCODE_REPO_ROOT", None)

    try:
        proc = subprocess.run(
            ["make", "kernel"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=build_env,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:800]
            return {
                "ok": False,
                "action": "build_failed",
                "error": err or f"make kernel exit {proc.returncode}",
            }
        if not binary_exists():
            return {"ok": False, "action": "build_failed", "error": f"binary missing after build: {binary}"}
        return {"ok": True, "action": "built", "binary": str(binary.resolve())}
    except subprocess.TimeoutExpired:
        return {"ok": False, "action": "build_timeout", "error": f"make kernel exceeded {timeout}s"}
    except OSError as exc:
        return {"ok": False, "action": "build_error", "error": str(exc)}


def build_kernel_health() -> dict[str, Any]:
    """Aggregate kernel health for /dietcode doctor."""
    supported = platform_supported()
    subtree = kernel_subtree_present()
    binary = binary_exists()
    sock = socket_reachable() if supported else False
    token = token_readable() if supported else False
    plugin_root_path = _plugin_root()
    kernel_root_path = kernel_root()

    workspace: dict[str, Any]
    try:
        from plugins.dietcode.lib.kernel_workspace import build_workspace_health
    except ImportError:
        from lib.kernel_workspace import build_workspace_health

    workspace = build_workspace_health()

    ok = subtree and (not supported or binary or not build_toolchain_available())
    # On macOS with toolchain, expect binary for full ok; socket/token are optional (runtime).
    if supported and build_toolchain_available() and subtree:
        ok = binary

    payload: dict[str, Any] = {
        "ok": ok,
        "platform_supported": supported,
        "platform": platform.system(),
        "machine": platform.machine(),
        "subtree_present": subtree,
        "plugin_root": str(plugin_root_path),
        "kernel_root": str(kernel_root_path),
        "binary_path": str(kernel_binary_path()),
        "binary_exists": binary,
        "build_toolchain": build_toolchain_available(),
        "socket_path": str(socket_path()),
        "socket_reachable": sock,
        "token_path": str(token_path()),
        "token_readable": token,
        "workspace": workspace,
        "resolved_workspace_root": workspace.get("resolved_workspace_root"),
        "workspace_safe_for_mutation": workspace.get("safe_for_mutation", False),
    }

    bridge_preflight: dict[str, Any] = {"ok": False, "action": "skipped"}
    if supported and subtree and binary:
        try:
            from plugins.dietcode.lib.agent.kernel_bridge_client import build_bridge_preflight_health
        except ImportError:
            from lib.agent.kernel_bridge_client import build_bridge_preflight_health
        try:
            bridge_preflight = build_bridge_preflight_health(warm=False)
        except Exception as exc:
            bridge_preflight = {"ok": False, "action": "preflight_error", "error": str(exc)}

    payload["bridge_preflight"] = bridge_preflight

    joyzoning_enabled = False
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config

        joyzoning_enabled = bool(get_joyzoning_config().enabled)
    except Exception:
        pass

    payload["receipt_journal"] = {
        "phase": "2C",
        "physical_mutation_authority": "kernel",
        "lifecycle_journal_authority": "joyzoning",
        "trigger": "dietcode_kernel(action=patch) success with kernel.mutationReceipt",
        "joyzoning_enabled": joyzoning_enabled,
        "hooks": ["post_tool_call", "transform_tool_result"],
    }

    try:
        from plugins.dietcode.lib.agent.kernel_raw_write_router import build_raw_write_router_health
    except ImportError:
        from lib.agent.kernel_raw_write_router import build_raw_write_router_health

    router_health = build_raw_write_router_health(probe_runtime=supported and subtree and binary)
    payload["raw_write_router"] = router_health
    payload["receipt_journal"]["raw_write_blocking"] = router_health.get("raw_write_blocking", False)

    try:
        from plugins.dietcode.lib.agent.kernel_verify_bridge import build_verify_bridge_health
    except ImportError:
        from lib.agent.kernel_verify_bridge import build_verify_bridge_health

    payload["verify_bridge"] = build_verify_bridge_health(probe_runtime=supported and subtree and binary)

    payload["status_summary"] = build_kernel_bridge_status_summary(
        probe_runtime=supported and subtree and binary,
        workspace=workspace,
        bridge_preflight=bridge_preflight,
        router_health=router_health,
        verify_health=payload["verify_bridge"],
    )

    if supported and subtree and not binary:
        payload["hint"] = f"make -C {kernel_root_path} kernel"
    elif supported and binary and not sock:
        payload["hint"] = f"make -C {kernel_root_path} restart-agent-server-fast"
    elif not supported:
        payload["hint"] = "Kernel is macOS-only; plugin BroccoliDB/JoyZoning work without it."

    return payload


def build_kernel_bridge_status_summary(
    *,
    probe_runtime: bool = True,
    workspace: dict[str, Any] | None = None,
    bridge_preflight: dict[str, Any] | None = None,
    router_health: dict[str, Any] | None = None,
    verify_health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact operator summary for ``/dietcode kernel status``."""
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

    try:
        from plugins.dietcode.lib.agent.kernel_verify_bridge import build_verify_bridge_health
    except ImportError:
        from lib.agent.kernel_verify_bridge import build_verify_bridge_health

    if workspace is None:
        try:
            from plugins.dietcode.lib.kernel_workspace import build_workspace_health
        except ImportError:
            from lib.kernel_workspace import build_workspace_health
        workspace = build_workspace_health()

    cfg = KernelBridgeConfig.load()
    gate = build_patch_gate_state() if probe_runtime and platform_supported() else {}
    router = router_health if router_health is not None else build_raw_write_router_health(
        probe_runtime=probe_runtime and platform_supported()
    )
    verify = verify_health if verify_health is not None else build_verify_bridge_health(
        probe_runtime=probe_runtime and platform_supported()
    )
    fuse = raw_write_block_enforcement_enabled()

    return {
        "platform_supported": platform_supported(),
        "bridge_enabled": cfg.enabled,
        "mutations_enabled": cfg.mutations_enabled,
        "raw_write_policy": cfg.raw_write_policy,
        "env_fuse_present": fuse,
        "workspace_safe": bool(workspace.get("safe_for_mutation")),
        "resolved_workspace_root": workspace.get("resolved_workspace_root"),
        "patch_allowed": bool(gate.get("patch_allowed")),
        "socket_reachable": socket_reachable() if platform_supported() else False,
        "token_readable": token_readable() if platform_supported() else False,
        "would_warn_on_raw_write": bool(router.get("would_warn_on_raw_write")),
        "would_block_raw_writes": bool(router.get("would_block_raw_writes")),
        "verify_allowlist_count": int(verify.get("allowlist_count") or 0),
        "verify_available": bool(verify.get("verify_action_available")),
        "bridge_preflight_ok": bool((bridge_preflight or {}).get("ok")),
    }


def format_kernel_status_report(summary: dict[str, Any] | None = None) -> str:
    """Human-readable kernel bridge status for operators."""
    data = summary if summary is not None else build_kernel_bridge_status_summary()
    lines = ["🥦 Kernel bridge status", ""]

    if not data.get("platform_supported"):
        lines.append("ℹ️  Platform: kernel is macOS-only — plugin degrades gracefully on Linux")
    else:
        sock = "live" if data.get("socket_reachable") else "offline"
        tok = "ok" if data.get("token_readable") else "missing"
        lines.append(f"   socket={sock} | token={tok}")

    lines.append(f"   bridge_enabled={data.get('bridge_enabled')}")
    lines.append(f"   mutations_enabled={data.get('mutations_enabled')}")
    lines.append(f"   raw_write_policy={data.get('raw_write_policy')}")
    lines.append(f"   env_fuse_present={data.get('env_fuse_present')}")

    ws = data.get("resolved_workspace_root") or "(unresolved)"
    safe = data.get("workspace_safe")
    mark = "✅" if safe else "⚠️ "
    lines.append(f"{mark} workspace_safe={safe} ({ws})")

    if data.get("patch_allowed"):
        lines.append("✅ patch_allowed=true — dietcode_kernel(action='patch') available")
    else:
        lines.append("⚠️  patch_allowed=false — patch gate closed")

    if data.get("would_block_raw_writes"):
        lines.append("⚠️  would_block_raw_writes=true — raw write_file/patch BLOCKED")
    elif data.get("would_warn_on_raw_write"):
        lines.append("⚠️  would_warn_on_raw_write=true — raw writes get kernel hint")
    else:
        lines.append("ℹ️  raw writes: no warn/block (gate closed or policy=allow)")

    verify_n = data.get("verify_allowlist_count", 0)
    if data.get("verify_available"):
        lines.append(f"✅ verify available | allowlist={verify_n} prefixes")
    else:
        lines.append(f"ℹ️  verify unavailable | allowlist={verify_n} prefixes (when bridge up)")

    lines.append("")
    lines.append("Docs: docs/kernel-bridge-operations.md")
    return "\n".join(lines)
