# -*- coding: utf-8 -*-
"""Hermes ↔ kernel JSON-RPC bridge (Python client) — Phase 2A preflight/read-only."""
from __future__ import annotations

import os
import socket
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Optional

# Stable bridge error codes (grep: rg 'bridge_' lib/agent/kernel_bridge_client.py)
BRIDGE_DISABLED = "bridge_disabled"
BRIDGE_PLATFORM_UNSUPPORTED = "bridge_platform_unsupported"
BRIDGE_BINARY_MISSING = "bridge_binary_missing"
BRIDGE_SOCKET_UNAVAILABLE = "bridge_socket_unavailable"
BRIDGE_TOKEN_UNAVAILABLE = "bridge_token_unavailable"
BRIDGE_WORKSPACE_UNSAFE = "bridge_workspace_unsafe"
BRIDGE_WORKSPACE_UNRESOLVED = "bridge_workspace_unresolved"
BRIDGE_RPC_ERROR = "bridge_rpc_error"
BRIDGE_RPC_TIMEOUT = "bridge_rpc_timeout"
BRIDGE_TRANSPORT_ERROR = "bridge_transport_error"
BRIDGE_PATCH_DISABLED = "bridge_patch_disabled"
BRIDGE_VERIFY_COMMAND_REJECTED = "bridge_verify_command_rejected"

_PREFLIGHT_CACHE: dict[str, Any] | None = None
_PREFLIGHT_CACHE_AT: float = 0.0
_PREFLIGHT_TTL_SEC = 30.0
_CLIENT_MODULE: Any = None


def bridge_error(
    string_code: str,
    message: str,
    *,
    recovery_hint: str = "",
    retryable: bool = False,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error": {
            "string_code": string_code,
            "message": message,
            "recovery_hint": recovery_hint,
            "retryable": retryable,
        },
    }
    if details:
        payload.update(details)
    return payload


def bridge_ok(result: Any = None, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": True}
    if result is not None:
        payload["result"] = result
    payload.update(extra)
    return payload


@dataclass(frozen=True)
class KernelBridgeConfig:
    enabled: bool = True
    auto_connect: bool = True
    mutations_enabled: bool = False
    raw_write_policy: str = "warn"
    connect_timeout_sec: float = 15.0
    request_timeout_sec: float = 60.0
    preflight_cache_ttl_ms: int = 5000
    workspace_open_cache: bool = True
    progress_flush_interval_ms: int = 250
    verify_timeout_ms: int = 0
    max_concurrent_mutations_per_workspace: int = 1
    keep_warm: bool = False
    keep_warm_idle_timeout_ms: int = 120_000
    keep_warm_ping_interval_ms: int = 30_000

    @classmethod
    def load(cls) -> KernelBridgeConfig:
        try:
            from plugins.dietcode.lib.kernel_workspace import _load_kernel_config

            raw = _load_kernel_config()
        except ImportError:
            from lib.kernel_workspace import _load_kernel_config

            raw = _load_kernel_config()
        bridge = raw.get("bridge", {}) if isinstance(raw.get("bridge"), dict) else {}
        try:
            from plugins.dietcode.lib.agent.kernel_raw_write_router import normalize_raw_write_policy
        except ImportError:
            from lib.agent.kernel_raw_write_router import normalize_raw_write_policy

        policy_raw = raw.get("raw_write_policy", bridge.get("raw_write_policy", "warn"))
        return cls(
            enabled=bool(raw.get("bridge_enabled", bridge.get("enabled", True))),
            auto_connect=bool(raw.get("auto_connect", bridge.get("auto_connect", True))),
            mutations_enabled=bool(
                raw.get("mutations_enabled", bridge.get("mutations_enabled", False))
            ),
            raw_write_policy=normalize_raw_write_policy(str(policy_raw)),
            connect_timeout_sec=float(
                raw.get("connect_timeout_sec", bridge.get("connect_timeout_sec", 15.0))
            ),
            request_timeout_sec=float(
                raw.get("request_timeout_sec", bridge.get("request_timeout_sec", 60.0))
            ),
            preflight_cache_ttl_ms=int(
                raw.get("preflight_cache_ttl_ms", bridge.get("preflight_cache_ttl_ms", 5000))
            ),
            workspace_open_cache=bool(
                raw.get("workspace_open_cache", bridge.get("workspace_open_cache", True))
            ),
            progress_flush_interval_ms=int(
                raw.get("progress_flush_interval_ms", bridge.get("progress_flush_interval_ms", 250))
            ),
            verify_timeout_ms=int(
                raw.get("verify_timeout_ms", bridge.get("verify_timeout_ms", 0))
            ),
            max_concurrent_mutations_per_workspace=int(
                raw.get(
                    "max_concurrent_mutations_per_workspace",
                    bridge.get("max_concurrent_mutations_per_workspace", 1),
                )
            ),
            keep_warm=bool(raw.get("keep_warm", bridge.get("keep_warm", False))),
            keep_warm_idle_timeout_ms=int(
                raw.get("keep_warm_idle_timeout_ms", bridge.get("keep_warm_idle_timeout_ms", 120_000))
            ),
            keep_warm_ping_interval_ms=int(
                raw.get("keep_warm_ping_interval_ms", bridge.get("keep_warm_ping_interval_ms", 30_000))
            ),
        )


def _kernel_scripts_dir() -> Path:
    try:
        from plugins.dietcode.paths import kernel_root

        return kernel_root() / "scripts"
    except ImportError:
        return Path(__file__).resolve().parents[2] / "kernel" / "scripts"


def _kernel_binary_path() -> Path:
    try:
        from plugins.dietcode.paths import kernel_binary_path

        return kernel_binary_path()
    except ImportError:
        from lib.kernel_health import kernel_binary_path

        return kernel_binary_path()


def _socket_path() -> str:
    try:
        from plugins.dietcode.lib.kernel_health import socket_path

        return str(socket_path())
    except ImportError:
        from lib.kernel_health import socket_path

        return str(socket_path())


def _token_path() -> str:
    try:
        from plugins.dietcode.lib.kernel_health import token_path

        return str(token_path())
    except ImportError:
        from lib.kernel_health import token_path

        return str(token_path())


def _load_client_module() -> Any:
    global _CLIENT_MODULE
    if _CLIENT_MODULE is not None:
        return _CLIENT_MODULE
    scripts = _kernel_scripts_dir()
    scripts_str = str(scripts)
    if scripts_str not in sys.path:
        sys.path.insert(0, scripts_str)
    import dietcode_agent_client as client  # noqa: WPS433

    _CLIENT_MODULE = client
    return client


def _resolve_workspace_module() -> Any:
    try:
        from plugins.dietcode.lib import kernel_workspace as kw
    except ImportError:
        from lib import kernel_workspace as kw
    return kw


def _require_safe_workspace(workspace_root: str | None = None) -> tuple[Optional[str], Optional[dict[str, Any]]]:
    kw = _resolve_workspace_module()
    if workspace_root and str(workspace_root).strip():
        path = Path(workspace_root).expanduser()
        validation = kw.validate_workspace_root(path)
        resolved = str(path.resolve()) if validation.checks.get("resolved") else str(path)
        if not validation.safe_for_mutation:
            return None, bridge_error(
                BRIDGE_WORKSPACE_UNSAFE,
                "; ".join(validation.errors) or f"workspace_root is not safe: {resolved}",
                recovery_hint=(
                    "Set HERMES_KANBAN_WORKSPACE, DIETCODE_WORKSPACE_ROOT, or "
                    "dietcode.kernel.workspace_root — never plugin/ or kernel/."
                ),
                details={"workspace_root": resolved, "checks": validation.checks},
            )
        return resolved, None

    report = kw.resolve_workspace_root()
    if not report.resolved_workspace_root:
        return None, bridge_error(
            BRIDGE_WORKSPACE_UNRESOLVED,
            "; ".join(report.validation.errors)
            or f"workspace_root_source={report.source!r} did not resolve",
            recovery_hint=report.to_dict().get("hint", ""),
            details={"workspace": report.to_dict()},
        )
    if not report.safe_for_mutation:
        return None, bridge_error(
            BRIDGE_WORKSPACE_UNSAFE,
            "; ".join(report.validation.errors) or "workspace_root is not safe for kernel bridge",
            recovery_hint=(
                "Point workspace at the Hermes project directory; "
                "plugin_root and kernel_root are quarantined."
            ),
            details={"workspace": report.to_dict()},
        )
    return report.resolved_workspace_root, None


def read_kernel_token() -> dict[str, Any]:
    """Load the kernel session token from disk."""
    cfg = KernelBridgeConfig.load()
    if not cfg.enabled:
        return bridge_error(BRIDGE_DISABLED, "Kernel bridge is disabled in config")

    try:
        from plugins.dietcode.lib.kernel_health import platform_supported
    except ImportError:
        from lib.kernel_health import platform_supported

    if not platform_supported():
        return bridge_error(
            BRIDGE_PLATFORM_UNSUPPORTED,
            "Kernel bridge requires macOS",
            recovery_hint="Use BroccoliDB/JoyZoning on non-macOS hosts.",
        )

    try:
        client = _load_client_module()
        token = client.load_token(_token_path())
        if not token:
            return bridge_error(
                BRIDGE_TOKEN_UNAVAILABLE,
                f"session token empty: {_token_path()}",
                recovery_hint="make -C kernel restart-agent-server-fast",
            )
        return bridge_ok({"token_path": _token_path(), "token_present": True})
    except OSError as exc:
        return bridge_error(
            BRIDGE_TOKEN_UNAVAILABLE,
            str(exc),
            recovery_hint="make -C kernel restart-agent-server-fast",
        )
    except Exception as exc:
        return bridge_error(BRIDGE_TRANSPORT_ERROR, str(exc), retryable=True)


def ensure_socket_ready(*, timeout: float | None = None, start: bool = True) -> dict[str, Any]:
    """Ensure the kernel control socket accepts connections."""
    cfg = KernelBridgeConfig.load()
    if not cfg.enabled:
        return bridge_error(BRIDGE_DISABLED, "Kernel bridge is disabled in config")

    try:
        from plugins.dietcode.lib.kernel_health import platform_supported
    except ImportError:
        from lib.kernel_health import platform_supported

    if not platform_supported():
        return bridge_error(BRIDGE_PLATFORM_UNSUPPORTED, "Kernel bridge requires macOS")

    binary = _kernel_binary_path()
    if not binary.is_file():
        return bridge_error(
            BRIDGE_BINARY_MISSING,
            f"kernel binary missing: {binary}",
            recovery_hint=f"make -C {binary.parent.parent} kernel",
        )

    client = _load_client_module()
    timeout_sec = timeout if timeout is not None else cfg.connect_timeout_sec
    probe_errors: list[str] = []
    try:
        ready = client.ensure_socket(
            app_path=str(binary),
            timeout=timeout_sec,
            socket_path=_socket_path(),
            start=start,
            quiet=True,
            probe_errors=probe_errors,
        )
    except Exception as exc:
        return bridge_error(
            BRIDGE_TRANSPORT_ERROR,
            str(exc),
            retryable=True,
            details={"probe_errors": probe_errors},
        )

    if not ready:
        return bridge_error(
            BRIDGE_SOCKET_UNAVAILABLE,
            f"control socket not ready at {_socket_path()}",
            recovery_hint="make -C kernel restart-agent-server-fast",
            retryable=True,
            details={"probe_errors": probe_errors},
        )
    return bridge_ok(
        {"socket_path": _socket_path(), "binary_path": str(binary)},
        action="socket_ready",
    )


def send_kernel_rpc(
    method: str,
    params: dict[str, Any] | None = None,
    *,
    request_timeout: float | None = None,
    start_socket: bool = True,
) -> dict[str, Any]:
    """Send one JSON-RPC call and return the full kernel envelope."""
    cfg = KernelBridgeConfig.load()
    if not cfg.enabled:
        return bridge_error(BRIDGE_DISABLED, "Kernel bridge is disabled in config")

    socket_step = ensure_socket_ready(timeout=cfg.connect_timeout_sec, start=start_socket)
    if not socket_step.get("ok"):
        return socket_step

    token_step = read_kernel_token()
    if not token_step.get("ok"):
        return token_step

    client = _load_client_module()
    timeout_sec = request_timeout if request_timeout is not None else cfg.request_timeout_sec
    sock: socket.socket | None = None
    try:
        sock = client.connect(
            timeout=cfg.connect_timeout_sec,
            app_path=str(_kernel_binary_path()),
            socket_path=_socket_path(),
            start=False,
        )
        token = client.load_token(_token_path())
        response = client.send_rpc(
            sock,
            token,
            method,
            params or {},
            request_timeout=timeout_sec,
        )
        if response.get("ok"):
            return bridge_ok(response.get("result"), rpc=response)
        err = response.get("error") if isinstance(response.get("error"), dict) else {}
        return bridge_error(
            str(err.get("string_code") or BRIDGE_RPC_ERROR),
            str(err.get("message") or f"{method} failed"),
            recovery_hint=str(err.get("recovery_hint") or ""),
            retryable=bool(err.get("retryable", False)),
            details={"rpc": response},
        )
    except TimeoutError as exc:
        return bridge_error(
            BRIDGE_RPC_TIMEOUT,
            str(exc),
            recovery_hint="Retry after make -C kernel restart-agent-server-fast",
            retryable=True,
        )
    except socket.timeout as exc:
        return bridge_error(
            BRIDGE_RPC_TIMEOUT,
            str(exc),
            recovery_hint="Increase dietcode.kernel.request_timeout_sec or retry",
            retryable=True,
        )
    except OSError as exc:
        return bridge_error(BRIDGE_TRANSPORT_ERROR, str(exc), retryable=True)
    except Exception as exc:
        client = _load_client_module()
        if exc.__class__.__name__ == "DietCodeRpcError":
            response = getattr(exc, "response", {})
            err = response.get("error", {}) if isinstance(response, dict) else {}
            return bridge_error(
                str(err.get("string_code") or BRIDGE_RPC_ERROR),
                str(exc),
                recovery_hint=str(err.get("recovery_hint") or ""),
                details={"rpc": response},
            )
        if exc.__class__.__name__ == "DietCodeTransportError":
            return bridge_error(BRIDGE_TRANSPORT_ERROR, str(exc), retryable=True)
        return bridge_error(BRIDGE_TRANSPORT_ERROR, str(exc), retryable=True)
    finally:
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass


@contextmanager
def _kernel_rpc_session(
    *,
    start_socket: bool = True,
) -> Iterator[tuple[Any, socket.socket, str, KernelBridgeConfig]]:
    cfg = KernelBridgeConfig.load()
    socket_step = ensure_socket_ready(timeout=cfg.connect_timeout_sec, start=start_socket)
    if not socket_step.get("ok"):
        raise RuntimeError(socket_step["error"]["message"])
    token_step = read_kernel_token()
    if not token_step.get("ok"):
        raise RuntimeError(token_step["error"]["message"])
    client = _load_client_module()
    sock = client.connect(
        timeout=cfg.connect_timeout_sec,
        app_path=str(_kernel_binary_path()),
        socket_path=_socket_path(),
        start=False,
    )
    try:
        yield client, sock, client.load_token(_token_path()), cfg
    finally:
        try:
            sock.close()
        except OSError:
            pass


def _emit_progress(phase: str, *, string_code: str = "", **extra: Any) -> None:
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_warm import touch_bridge_activity
        from plugins.dietcode.lib.agent.kernel_progress import emit_phase
    except ImportError:
        from lib.agent.kernel_bridge_warm import touch_bridge_activity
        from lib.agent.kernel_progress import emit_phase
    touch_bridge_activity()
    emit_phase(phase, string_code=string_code, **extra)


def _emit_patch_staging(
    *,
    path: str,
    patch_text: str,
    task_id: str,
    workspace_root: str,
) -> None:
    try:
        from plugins.dietcode.lib.agent.kernel_progress_ux import build_mutation_preview
    except ImportError:
        from lib.agent.kernel_progress_ux import build_mutation_preview
    preview = build_mutation_preview(
        path=path,
        patch_text=patch_text,
        task_id=task_id,
        workspace_root=workspace_root,
    )
    _emit_progress("patch.staging", path=path, taskId=task_id or None, mutation_preview=preview)


def _bridge_cache_module() -> Any:
    try:
        from plugins.dietcode.lib.agent import kernel_bridge_cache as cache
    except ImportError:
        from lib.agent import kernel_bridge_cache as cache
    return cache


def _mutation_lock_module() -> Any:
    try:
        from plugins.dietcode.lib.agent import kernel_mutation_lock as locks
    except ImportError:
        from lib.agent import kernel_mutation_lock as locks
    return locks


def _ensure_bridge_ready(
    cfg: KernelBridgeConfig,
    *,
    start: bool = True,
) -> dict[str, Any]:
    """Socket + token readiness with short-TTL positive cache (Phase 7)."""
    cache = _bridge_cache_module()
    sock_path = _socket_path()
    tok_path = _token_path()
    ttl_sec = max(0.0, cfg.preflight_cache_ttl_ms / 1000.0)
    if cache.get_cached_readiness(ttl_sec=ttl_sec, socket_path=sock_path, token_path=tok_path):
        _emit_progress("socket.ready", cached=True)
        return bridge_ok({"socket_path": sock_path, "token_path": tok_path, "cached": True})

    socket_step = ensure_socket_ready(timeout=cfg.connect_timeout_sec, start=start)
    if not socket_step.get("ok"):
        err = socket_step.get("error") if isinstance(socket_step.get("error"), dict) else {}
        cache.invalidate_on_error(str(err.get("string_code") or BRIDGE_SOCKET_UNAVAILABLE))
        return socket_step

    token_step = read_kernel_token()
    if not token_step.get("ok"):
        err = token_step.get("error") if isinstance(token_step.get("error"), dict) else {}
        cache.invalidate_on_error(str(err.get("string_code") or BRIDGE_TOKEN_UNAVAILABLE))
        return token_step

    cache.cache_readiness(socket_path=sock_path, token_path=tok_path)
    _emit_progress("socket.ready")
    return bridge_ok({"socket_path": sock_path, "token_path": tok_path})


def open_workspace(workspace_root: str | None = None, *, timeout: float | None = None) -> dict[str, Any]:
    """Open a validated Hermes workspace on the kernel (no patch authority)."""
    ws, err = _require_safe_workspace(workspace_root)
    if err:
        _bridge_cache_module().invalidate_on_error(BRIDGE_WORKSPACE_UNSAFE)
        return err

    cfg = KernelBridgeConfig.load()
    cache = _bridge_cache_module()
    ttl_sec = max(0.0, cfg.preflight_cache_ttl_ms / 1000.0)
    if cache.workspace_open_cache_hit(enabled=cfg.workspace_open_cache, workspace_root=ws, ttl_sec=ttl_sec):
        _emit_progress("workspace.open", workspace_root=ws, cached=True)
        return bridge_ok(
            {"path": ws, "action": "already_open", "cached": True},
            workspace_root=ws,
        )

    timeout_sec = timeout if timeout is not None else cfg.request_timeout_sec
    try:
        with _kernel_rpc_session() as (client, sock, token, _cfg):
            current = client.send_rpc(
                sock, token, "workspace.getRoot", {}, request_timeout=timeout_sec
            )
            if current.get("ok"):
                open_path = (current.get("result") or {}).get("path")
                if open_path and Path(open_path).resolve() == Path(ws).resolve():
                    cache.mark_workspace_open(ws)
                    _emit_progress("workspace.open", workspace_root=ws)
                    return bridge_ok(
                        {"path": open_path, "action": "already_open"},
                        workspace_root=ws,
                    )

            opened = client.send_rpc(
                sock,
                token,
                "workspace.openFolder",
                {"path": ws},
                request_timeout=timeout_sec,
            )
            if not opened.get("ok"):
                err_body = opened.get("error") if isinstance(opened.get("error"), dict) else {}
                return bridge_error(
                    str(err_body.get("string_code") or BRIDGE_RPC_ERROR),
                    str(err_body.get("message") or "workspace.openFolder failed"),
                    recovery_hint=str(err_body.get("recovery_hint") or ""),
                    details={"rpc": opened, "workspace_root": ws},
                )

            verify = client.send_rpc(
                sock, token, "workspace.getRoot", {}, request_timeout=timeout_sec
            )
            path = (verify.get("result") or {}).get("path") if verify.get("ok") else ws
            cache.mark_workspace_open(ws)
            _emit_progress("workspace.open", workspace_root=ws)
            return bridge_ok(
                {"path": path, "action": "opened"},
                workspace_root=ws,
                rpc=opened,
            )
    except (TimeoutError, socket.timeout) as exc:
        return bridge_error(BRIDGE_RPC_TIMEOUT, str(exc), retryable=True)
    except OSError as exc:
        return bridge_error(BRIDGE_TRANSPORT_ERROR, str(exc), retryable=True)
    except RuntimeError as exc:
        return bridge_error(BRIDGE_TRANSPORT_ERROR, str(exc), retryable=True)
    except Exception as exc:
        return bridge_error(BRIDGE_TRANSPORT_ERROR, str(exc), retryable=True)


def workspace_status(workspace_root: str | None = None, *, timeout: float | None = None) -> dict[str, Any]:
    """Return kernel workspace.status for a validated workspace."""
    opened = open_workspace(workspace_root, timeout=timeout)
    if not opened.get("ok"):
        return opened

    cfg = KernelBridgeConfig.load()
    timeout_sec = timeout if timeout is not None else cfg.request_timeout_sec
    try:
        with _kernel_rpc_session() as (client, sock, token, _cfg):
            response = client.send_rpc(
                sock,
                token,
                "workspace.status",
                {},
                request_timeout=timeout_sec,
            )
            if not response.get("ok"):
                err_body = response.get("error") if isinstance(response.get("error"), dict) else {}
                return bridge_error(
                    str(err_body.get("string_code") or BRIDGE_RPC_ERROR),
                    str(err_body.get("message") or "workspace.status failed"),
                    details={"rpc": response},
                )
            return bridge_ok(
                response.get("result"),
                workspace_root=opened.get("workspace_root"),
                rpc=response,
            )
    except (TimeoutError, socket.timeout) as exc:
        return bridge_error(BRIDGE_RPC_TIMEOUT, str(exc), retryable=True)
    except Exception as exc:
        return bridge_error(BRIDGE_TRANSPORT_ERROR, str(exc), retryable=True)


def search_literal(
    workspace_root: str | None,
    query: str,
    *,
    max_results: int = 20,
    timeout: float | None = None,
) -> dict[str, Any]:
    """Deterministic substring search via kernel search.literal."""
    if not query or not str(query).strip():
        return bridge_error(
            BRIDGE_RPC_ERROR,
            "query is required for search_literal",
            recovery_hint="Pass a non-empty query string.",
        )

    opened = open_workspace(workspace_root, timeout=timeout)
    if not opened.get("ok"):
        return opened

    cfg = KernelBridgeConfig.load()
    timeout_sec = timeout if timeout is not None else cfg.request_timeout_sec
    params = {"query": str(query).strip(), "maxResults": max(1, int(max_results))}
    try:
        with _kernel_rpc_session() as (client, sock, token, _cfg):
            response = client.send_rpc(
                sock,
                token,
                "search.literal",
                params,
                request_timeout=timeout_sec,
            )
            if not response.get("ok"):
                err_body = response.get("error") if isinstance(response.get("error"), dict) else {}
                return bridge_error(
                    str(err_body.get("string_code") or BRIDGE_RPC_ERROR),
                    str(err_body.get("message") or "search.literal failed"),
                    details={"rpc": response, "query": params["query"]},
                )
            return bridge_ok(
                response.get("result"),
                workspace_root=opened.get("workspace_root"),
                query=params["query"],
                rpc=response,
            )
    except (TimeoutError, socket.timeout) as exc:
        return bridge_error(BRIDGE_RPC_TIMEOUT, str(exc), retryable=True)
    except Exception as exc:
        return bridge_error(BRIDGE_TRANSPORT_ERROR, str(exc), retryable=True)


def connect_preflight(*, warm: bool = False, force: bool = False) -> dict[str, Any]:
    """Resolve paths, ensure socket/token, optionally ping RPC and validate workspace."""
    global _PREFLIGHT_CACHE, _PREFLIGHT_CACHE_AT

    cfg = KernelBridgeConfig.load()
    if not cfg.enabled:
        return bridge_ok(action="disabled", enabled=False)

    ttl_sec = max(0.0, cfg.preflight_cache_ttl_ms / 1000.0)
    now = time.monotonic()
    if (
        not force
        and _PREFLIGHT_CACHE is not None
        and _PREFLIGHT_CACHE.get("ok")
        and ttl_sec > 0
        and (now - _PREFLIGHT_CACHE_AT) < ttl_sec
    ):
        return dict(_PREFLIGHT_CACHE)

    report: dict[str, Any] = {
        "ok": False,
        "enabled": True,
        "mutations_enabled": cfg.mutations_enabled,
        "steps": {},
    }

    try:
        from plugins.dietcode.lib.kernel_health import platform_supported
    except ImportError:
        from lib.kernel_health import platform_supported

    if not platform_supported():
        report.update(
            bridge_error(
                BRIDGE_PLATFORM_UNSUPPORTED,
                "Kernel bridge requires macOS",
            )
        )
        return report

    binary = _kernel_binary_path()
    report["binary_path"] = str(binary)
    report["socket_path"] = _socket_path()
    report["token_path"] = _token_path()
    if not binary.is_file():
        report.update(
            bridge_error(
                BRIDGE_BINARY_MISSING,
                f"kernel binary missing: {binary}",
                recovery_hint=f"make -C {binary.parent.parent} kernel",
            )
        )
        return report

    ws_report = _resolve_workspace_module().resolve_workspace_root()
    report["workspace"] = ws_report.to_dict()

    if cfg.auto_connect:
        socket_step = ensure_socket_ready(timeout=cfg.connect_timeout_sec, start=True)
        report["steps"]["socket"] = socket_step
        if not socket_step.get("ok"):
            report.update(socket_step)
            _bridge_cache_module().invalidate_readiness(reason="socket")
            return report

        token_step = read_kernel_token()
        report["steps"]["token"] = token_step
        if not token_step.get("ok"):
            report.update(token_step)
            _bridge_cache_module().invalidate_readiness(reason="token")
            return report
        _bridge_cache_module().cache_readiness(
            socket_path=_socket_path(),
            token_path=_token_path(),
        )

    if warm:
        ping = send_kernel_rpc("rpc.ping", {}, start_socket=False)
        report["steps"]["rpc_ping"] = ping
        if not ping.get("ok"):
            report.update(ping)
            report["action"] = "ping_failed"
            _bridge_cache_module().invalidate_readiness(reason="ping_failed")
            return report

        if ws_report.safe_for_mutation:
            status = workspace_status(ws_report.resolved_workspace_root)
            report["steps"]["workspace_status"] = status
            if not status.get("ok"):
                report.update(status)
                report["action"] = "workspace_status_failed"
                _bridge_cache_module().invalidate_workspace_cache(reason="workspace_status")
                return report
        else:
            report["steps"]["workspace_status"] = bridge_error(
                BRIDGE_WORKSPACE_UNSAFE,
                "workspace not safe — skipping warm workspace.status",
                details={"workspace": ws_report.to_dict()},
            )

    report["ok"] = True
    report["action"] = "preflight_ok"
    report["workspace_safe_for_mutation"] = ws_report.safe_for_mutation
    _PREFLIGHT_CACHE = report
    _PREFLIGHT_CACHE_AT = now
    return report


def build_bridge_preflight_health(*, warm: bool = False) -> dict[str, Any]:
    """Doctor payload for kernel bridge preflight."""
    report = connect_preflight(warm=warm, force=False)
    report["patch_gate"] = build_patch_gate_state()
    return report


def mutations_enabled() -> bool:
    """Phase 2B gate — patch routing remains off until explicitly enabled."""
    return KernelBridgeConfig.load().mutations_enabled


def _load_coherence_module() -> Any:
    _load_client_module()
    import dietcode_coherence as coherence  # noqa: WPS433

    return coherence


def _resolve_task_id(explicit: str | None = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import read_scope_env
    except ImportError:
        read_scope_env = lambda key: os.environ.get(key, "").strip()  # noqa: E731
    for key in ("HERMES_KANBAN_TASK", "DIETCODE_TASK_ID"):
        val = read_scope_env(key) or os.environ.get(key, "").strip()
        if val:
            return val
    return ""


def _normalize_rel_path(path: str) -> tuple[str | None, dict[str, Any] | None]:
    raw = (path or "").strip()
    if not raw:
        return None, bridge_error(
            BRIDGE_RPC_ERROR,
            "path is required and must be a relative workspace path",
            recovery_hint="Pass a repo-relative path such as src/foo.py",
        )
    candidate = Path(raw)
    if candidate.is_absolute():
        return None, bridge_error(
            BRIDGE_RPC_ERROR,
            f"path must be relative, not absolute: {raw}",
        )
    if ".." in candidate.parts:
        return None, bridge_error(
            BRIDGE_RPC_ERROR,
            f"path must not contain '..': {raw}",
        )
    return raw.replace("\\", "/"), None


def _build_patch_text(
    rel_path: str,
    *,
    unified_diff: str,
    line_search: str,
    line_replace: str,
    file_content: str,
    coherence_mod: Any,
) -> str:
    if unified_diff.strip():
        return unified_diff.strip()
    if line_search.strip():
        return coherence_mod.build_line_replacement_patch_for_content(
            rel_path,
            file_content,
            search=line_search.strip(),
            replace=line_replace if line_replace is not None else "",
        )
    raise ValueError("unified_diff or line_search+line_replace is required for patch")


def _patch_receipt(
    *,
    ok: bool,
    action: str,
    workspace_root: str | None,
    path: str,
    task_id: str,
    kernel_result: Any = None,
    rpc: Any = None,
    error: dict[str, Any] | None = None,
    string_code: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "action": action,
        "workspace_root": workspace_root,
        "path": path,
        "taskId": task_id or None,
    }
    if kernel_result is not None:
        payload["kernel"] = kernel_result
    if rpc is not None:
        payload["rpc"] = rpc
    if error is not None:
        payload["error"] = error
        payload["string_code"] = string_code or error.get("string_code")
    elif not ok:
        payload["string_code"] = string_code
    return payload


def build_patch_gate_state() -> dict[str, Any]:
    """Doctor-facing patch gate summary (Phase 2B)."""
    cfg = KernelBridgeConfig.load()
    ws = _resolve_workspace_module().resolve_workspace_root()
    socket_step = ensure_socket_ready(start=False) if cfg.enabled else bridge_error(BRIDGE_DISABLED, "")
    token_step = read_kernel_token() if cfg.enabled and socket_step.get("ok") else {"ok": False}
    patch_allowed = bool(
        cfg.enabled
        and cfg.mutations_enabled
        and ws.safe_for_mutation
        and socket_step.get("ok")
        and token_step.get("ok")
    )
    return {
        "bridge_enabled": cfg.enabled,
        "mutations_enabled": cfg.mutations_enabled,
        "workspace_safe_for_mutation": ws.safe_for_mutation,
        "resolved_workspace_root": ws.resolved_workspace_root,
        "socket_ready": bool(socket_step.get("ok")),
        "token_ready": bool(token_step.get("ok")),
        "patch_allowed": patch_allowed,
        "recovery_hint": (
            "Set dietcode.kernel.bridge.mutations_enabled: true to enable dietcode_kernel(action='patch')."
            if cfg.enabled and not cfg.mutations_enabled
            else ""
        ),
    }


def apply_kernel_patch(
    workspace_root: str | None,
    rel_path: str,
    *,
    unified_diff: str = "",
    line_search: str = "",
    line_replace: str = "",
    task_id: str = "",
) -> dict[str, Any]:
    """Apply a governed patch via kernel RPC/coherence (opt-in; Phase 2B)."""
    cfg = KernelBridgeConfig.load()
    if not cfg.enabled:
        err = bridge_error(BRIDGE_DISABLED, "Kernel bridge is disabled in config")
        return _patch_receipt(
            ok=False,
            action="patch",
            workspace_root=workspace_root,
            path=rel_path,
            task_id=task_id,
            error=err["error"],
            string_code=BRIDGE_DISABLED,
        )

    if not cfg.mutations_enabled:
        err = bridge_error(
            BRIDGE_PATCH_DISABLED,
            "Kernel patch routing is disabled (dietcode.kernel.bridge.mutations_enabled=false)",
            recovery_hint="Set dietcode.kernel.bridge.mutations_enabled: true in Hermes config.",
        )
        return _patch_receipt(
            ok=False,
            action="patch",
            workspace_root=workspace_root,
            path=rel_path,
            task_id=task_id,
            error=err["error"],
            string_code=BRIDGE_PATCH_DISABLED,
        )

    ws, ws_err = _require_safe_workspace(workspace_root)
    if ws_err:
        err_body = ws_err.get("error", {})
        return _patch_receipt(
            ok=False,
            action="patch",
            workspace_root=workspace_root,
            path=rel_path,
            task_id=task_id,
            error=err_body if isinstance(err_body, dict) else {"message": str(ws_err)},
            string_code=str((err_body or {}).get("string_code") or BRIDGE_WORKSPACE_UNSAFE),
        )

    ready_step = _ensure_bridge_ready(cfg, start=True)
    if not ready_step.get("ok"):
        err_body = ready_step.get("error", {})
        code = str((err_body or {}).get("string_code") or BRIDGE_SOCKET_UNAVAILABLE)
        return _patch_receipt(
            ok=False,
            action="patch",
            workspace_root=ws,
            path=rel_path,
            task_id=task_id,
            error=err_body if isinstance(err_body, dict) else {},
            string_code=code,
        )

    norm_path, path_err = _normalize_rel_path(rel_path)
    if path_err:
        err_body = path_err.get("error", {})
        return _patch_receipt(
            ok=False,
            action="patch",
            workspace_root=ws,
            path=rel_path,
            task_id=task_id,
            error=err_body if isinstance(err_body, dict) else {},
            string_code=str((err_body or {}).get("string_code") or BRIDGE_RPC_ERROR),
        )

    resolved_task = _resolve_task_id(task_id)
    opened = open_workspace(ws)
    if not opened.get("ok"):
        err_body = opened.get("error", {})
        return _patch_receipt(
            ok=False,
            action="patch",
            workspace_root=ws,
            path=norm_path or rel_path,
            task_id=resolved_task,
            error=err_body if isinstance(err_body, dict) else {},
            string_code=str((err_body or {}).get("string_code") or BRIDGE_RPC_ERROR),
        )

    timeout_sec = cfg.request_timeout_sec
    locks = _mutation_lock_module()
    try:
        with locks.mutation_lock(
            ws,
            max_concurrent=cfg.max_concurrent_mutations_per_workspace,
        ):
            return _apply_kernel_patch_rpc(
                ws=ws,
                norm_path=norm_path or rel_path,
                rel_path=rel_path,
                resolved_task=resolved_task,
                unified_diff=unified_diff,
                line_search=line_search,
                line_replace=line_replace,
                timeout_sec=timeout_sec,
            )
    except (TimeoutError, socket.timeout) as exc:
        _bridge_cache_module().invalidate_on_error(BRIDGE_RPC_TIMEOUT)
        return _patch_receipt(
            ok=False,
            action="patch",
            workspace_root=ws,
            path=norm_path or rel_path,
            task_id=resolved_task,
            error={"string_code": BRIDGE_RPC_TIMEOUT, "message": str(exc)},
            string_code=BRIDGE_RPC_TIMEOUT,
        )
    except Exception as exc:
        _bridge_cache_module().invalidate_on_error(BRIDGE_TRANSPORT_ERROR)
        return _patch_receipt(
            ok=False,
            action="patch",
            workspace_root=ws,
            path=norm_path or rel_path,
            task_id=resolved_task,
            error={"string_code": BRIDGE_TRANSPORT_ERROR, "message": str(exc)},
            string_code=BRIDGE_TRANSPORT_ERROR,
        )


def _workspace_has_drift(client: Any, sock: socket.socket, token: str, timeout_sec: float) -> bool:
    response = client.send_rpc(sock, token, "workspace.status", {}, request_timeout=timeout_sec)
    if not response.get("ok"):
        return True
    result = response.get("result") if isinstance(response.get("result"), dict) else {}
    return bool(result.get("driftDetected"))


def _apply_kernel_patch_rpc(
    *,
    ws: str,
    norm_path: str,
    rel_path: str,
    resolved_task: str,
    unified_diff: str,
    line_search: str,
    line_replace: str,
    timeout_sec: float,
) -> dict[str, Any]:
    try:
        with _kernel_rpc_session() as (client, sock, token, _cfg):
            try:
                coherence_mod = _load_coherence_module()
            except ImportError:
                coherence_mod = None

            try:
                from plugins.dietcode.lib.agent.kernel_progress import coherence_emit_callback
            except ImportError:
                from lib.agent.kernel_progress import coherence_emit_callback

            if coherence_mod is not None and resolved_task:
                drift = _workspace_has_drift(client, sock, token, timeout_sec)
                _emit_progress("coherence.read", path=norm_path, taskId=resolved_task)
                read_result = coherence_mod.read_with_coherence(sock, token, norm_path, resolved_task)
                patch_text = _build_patch_text(
                    norm_path,
                    unified_diff=unified_diff,
                    line_search=line_search,
                    line_replace=line_replace,
                    file_content=read_result.get("text") or "",
                    coherence_mod=coherence_mod,
                )

                def _rebuild_from_content(content: str) -> str:
                    return _build_patch_text(
                        norm_path,
                        unified_diff=unified_diff,
                        line_search=line_search,
                        line_replace=line_replace,
                        file_content=content,
                        coherence_mod=coherence_mod,
                    )

                _emit_patch_staging(
                    path=norm_path,
                    patch_text=patch_text,
                    task_id=resolved_task,
                    workspace_root=ws,
                )
                if not drift:
                    _emit_progress("patch.validate", path=norm_path)
                    validated = client.send_rpc(
                        sock,
                        token,
                        "patch.validate",
                        {"path": norm_path, "patch": patch_text},
                        request_timeout=timeout_sec,
                    )
                    if not validated.get("ok"):
                        err_body = validated.get("error") if isinstance(validated.get("error"), dict) else {}
                        return _patch_receipt(
                            ok=False,
                            action="patch",
                            workspace_root=ws,
                            path=norm_path,
                            task_id=resolved_task,
                            error=err_body,
                            string_code=str(err_body.get("string_code") or BRIDGE_RPC_ERROR),
                            rpc=validated,
                        )
                    _emit_progress("patch.apply", path=norm_path, taskId=resolved_task, fast_path=True)
                    applied = coherence_mod.apply_patch_with_coherence(
                        sock,
                        token,
                        task_id=resolved_task,
                        path=norm_path,
                        patch=patch_text,
                        coherence=read_result["coherence"],
                        expect_before_hash=validated["result"]["validation"]["beforeContentHash"],
                        emit=coherence_emit_callback,
                        resolved_by="dietcode_kernel",
                    )
                else:
                    applied = coherence_mod.recover_and_apply_patch(
                        sock,
                        token,
                        task_id=resolved_task,
                        path=norm_path,
                        stale_patch=patch_text,
                        stale_coherence=read_result["coherence"],
                        build_patch_from_content=_rebuild_from_content,
                        resolved_by="dietcode_kernel",
                        emit=coherence_emit_callback,
                    )
            else:
                # TODO: coherence-aware recovery requires taskId + dietcode_coherence module.
                read_resp = client.send_rpc(
                    sock,
                    token,
                    "file.read",
                    {"path": norm_path, **({"taskId": resolved_task} if resolved_task else {})},
                    request_timeout=timeout_sec,
                )
                if not read_resp.get("ok"):
                    err_body = read_resp.get("error") if isinstance(read_resp.get("error"), dict) else {}
                    return _patch_receipt(
                        ok=False,
                        action="patch",
                        workspace_root=ws,
                        path=norm_path,
                        task_id=resolved_task,
                        error=err_body,
                        string_code=str(err_body.get("string_code") or BRIDGE_RPC_ERROR),
                        rpc=read_resp,
                    )
                file_text = (read_resp.get("result") or {}).get("text") or ""
                if coherence_mod is not None:
                    patch_text = _build_patch_text(
                        norm_path,
                        unified_diff=unified_diff,
                        line_search=line_search,
                        line_replace=line_replace,
                        file_content=file_text,
                        coherence_mod=coherence_mod,
                    )
                else:
                    patch_text = unified_diff.strip()
                    if not patch_text:
                        return _patch_receipt(
                            ok=False,
                            action="patch",
                            workspace_root=ws,
                            path=norm_path,
                            task_id=resolved_task,
                            error={"message": "unified_diff required when coherence module unavailable"},
                            string_code=BRIDGE_RPC_ERROR,
                        )

                _emit_patch_staging(
                    path=norm_path,
                    patch_text=patch_text,
                    task_id=resolved_task,
                    workspace_root=ws,
                )
                _emit_progress("patch.validate", path=norm_path)
                validated = client.send_rpc(
                    sock,
                    token,
                    "patch.validate",
                    {"path": norm_path, "patch": patch_text},
                    request_timeout=timeout_sec,
                )
                if not validated.get("ok"):
                    err_body = validated.get("error") if isinstance(validated.get("error"), dict) else {}
                    return _patch_receipt(
                        ok=False,
                        action="patch",
                        workspace_root=ws,
                        path=norm_path,
                        task_id=resolved_task,
                        error=err_body,
                        string_code=str(err_body.get("string_code") or BRIDGE_RPC_ERROR),
                        rpc=validated,
                    )

                params: dict[str, Any] = {
                    "path": norm_path,
                    "patch": patch_text,
                    "confirm": True,
                    "expectBeforeHash": validated["result"]["validation"]["beforeContentHash"],
                }
                if resolved_task:
                    params["taskId"] = resolved_task
                _emit_progress("patch.apply", path=norm_path, taskId=resolved_task or None)
                applied = client.send_rpc(
                    sock,
                    token,
                    "patch.apply",
                    params,
                    request_timeout=timeout_sec,
                )

            if not applied.get("ok"):
                err_body = applied.get("error") if isinstance(applied.get("error"), dict) else {}
                return _patch_receipt(
                    ok=False,
                    action="patch",
                    workspace_root=ws,
                    path=norm_path,
                    task_id=resolved_task,
                    error=err_body,
                    string_code=str(err_body.get("string_code") or BRIDGE_RPC_ERROR),
                    rpc=applied,
                )

            kernel_result = applied.get("result")
            return _patch_receipt(
                ok=True,
                action="patch",
                workspace_root=ws,
                path=norm_path,
                task_id=resolved_task,
                kernel_result=kernel_result,
                rpc=applied,
            )
    except (TimeoutError, socket.timeout) as exc:
        _bridge_cache_module().invalidate_on_error(BRIDGE_RPC_TIMEOUT)
        return _patch_receipt(
            ok=False,
            action="patch",
            workspace_root=ws,
            path=norm_path or rel_path,
            task_id=resolved_task,
            error={"string_code": BRIDGE_RPC_TIMEOUT, "message": str(exc)},
            string_code=BRIDGE_RPC_TIMEOUT,
        )
    except Exception as exc:
        _bridge_cache_module().invalidate_on_error(BRIDGE_TRANSPORT_ERROR)
        return _patch_receipt(
            ok=False,
            action="patch",
            workspace_root=ws,
            path=norm_path or rel_path,
            task_id=resolved_task,
            error={"string_code": BRIDGE_TRANSPORT_ERROR, "message": str(exc)},
            string_code=BRIDGE_TRANSPORT_ERROR,
        )


def _verify_receipt(
    *,
    ok: bool,
    workspace_root: str | None,
    task_id: str,
    command: str,
    cwd: str = "",
    passed: bool | None = None,
    exit_code: Any = None,
    stdout_summary: str = "",
    stderr_summary: str = "",
    verify_ran: bool = False,
    kernel_result: Any = None,
    rpc: Any = None,
    error: dict[str, Any] | None = None,
    string_code: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": ok,
        "action": "verify",
        "workspace_root": workspace_root,
        "taskId": task_id or None,
        "command": command,
        "verify_ran": verify_ran,
    }
    if cwd:
        payload["cwd"] = cwd
    if passed is not None:
        payload["passed"] = passed
    if exit_code is not None:
        payload["exit_code"] = exit_code
    if stdout_summary:
        payload["stdout_summary"] = stdout_summary
    if stderr_summary:
        payload["stderr_summary"] = stderr_summary
    if kernel_result is not None:
        payload["kernel"] = kernel_result
    if rpc is not None:
        payload["rpc"] = rpc
    if error is not None:
        payload["error"] = error
        payload["string_code"] = string_code or error.get("string_code")
    elif not ok and string_code:
        payload["string_code"] = string_code
    return payload


def apply_kernel_verify(
    workspace_root: str | None,
    command: str,
    *,
    cwd: str = "",
    task_id: str = "",
) -> dict[str, Any]:
    """Run kernel verify.run with client-side allowlist enforcement (Phase 4)."""
    try:
        from plugins.dietcode.lib.agent.kernel_verify_bridge import (
            BRIDGE_VERIFY_COMMAND_REJECTED,
            extract_verify_fields,
            is_command_allowlisted,
            summarize_output,
        )
    except ImportError:
        from lib.agent.kernel_verify_bridge import (
            BRIDGE_VERIFY_COMMAND_REJECTED,
            extract_verify_fields,
            is_command_allowlisted,
            summarize_output,
        )

    cfg = KernelBridgeConfig.load()
    if not cfg.enabled:
        err = bridge_error(BRIDGE_DISABLED, "Kernel bridge is disabled in config")
        return _verify_receipt(
            ok=False,
            workspace_root=workspace_root,
            task_id=task_id,
            command=command,
            cwd=cwd,
            error=err["error"],
            string_code=BRIDGE_DISABLED,
        )

    cmd = str(command or "").strip()
    if not cmd:
        err = bridge_error(
            BRIDGE_RPC_ERROR,
            "command is required for verify.run",
            recovery_hint="Pass an allowlisted verify command such as ./verify.sh",
        )
        return _verify_receipt(
            ok=False,
            workspace_root=workspace_root,
            task_id=task_id,
            command=command,
            cwd=cwd,
            error=err["error"],
            string_code=BRIDGE_RPC_ERROR,
        )

    if not is_command_allowlisted(cmd):
        err = bridge_error(
            BRIDGE_VERIFY_COMMAND_REJECTED,
            f"verify command not allowlisted: {cmd!r}",
            recovery_hint=(
                "Use a prefix from dietcode.kernel.bridge.verify_allowlist "
                f"or defaults: make test, make kernel, git diff --check, npm test, ./verify.sh"
            ),
        )
        return _verify_receipt(
            ok=False,
            workspace_root=workspace_root,
            task_id=task_id,
            command=cmd,
            cwd=cwd,
            error=err["error"],
            string_code=BRIDGE_VERIFY_COMMAND_REJECTED,
        )

    ws, ws_err = _require_safe_workspace(workspace_root)
    if ws_err:
        err_body = ws_err.get("error", {})
        return _verify_receipt(
            ok=False,
            workspace_root=workspace_root,
            task_id=task_id,
            command=cmd,
            cwd=cwd,
            error=err_body if isinstance(err_body, dict) else {"message": str(ws_err)},
            string_code=str((err_body or {}).get("string_code") or BRIDGE_WORKSPACE_UNSAFE),
        )

    ready_step = _ensure_bridge_ready(cfg, start=True)
    if not ready_step.get("ok"):
        err_body = ready_step.get("error", {})
        return _verify_receipt(
            ok=False,
            workspace_root=ws,
            task_id=task_id,
            command=cmd,
            cwd=cwd,
            error=err_body if isinstance(err_body, dict) else {},
            string_code=str((err_body or {}).get("string_code") or BRIDGE_SOCKET_UNAVAILABLE),
        )

    resolved_task = _resolve_task_id(task_id)
    opened = open_workspace(ws)
    if not opened.get("ok"):
        err_body = opened.get("error", {})
        return _verify_receipt(
            ok=False,
            workspace_root=ws,
            task_id=resolved_task,
            command=cmd,
            cwd=cwd,
            error=err_body if isinstance(err_body, dict) else {},
            string_code=str((err_body or {}).get("string_code") or BRIDGE_RPC_ERROR),
        )

    params: dict[str, Any] = {"command": cmd}
    if cwd.strip():
        params["cwd"] = cwd.strip()
    if resolved_task:
        params["taskId"] = resolved_task

    if cfg.verify_timeout_ms > 0:
        timeout_sec = cfg.verify_timeout_ms / 1000.0
    else:
        timeout_sec = cfg.request_timeout_sec

    locks = _mutation_lock_module()
    try:
        with locks.mutation_lock(ws, max_concurrent=cfg.max_concurrent_mutations_per_workspace):
            with _kernel_rpc_session() as (client, sock, token, _cfg):
                _emit_progress("verify.running", command=cmd, taskId=resolved_task or None)
                rpc = client.send_rpc(
                    sock,
                    token,
                    "verify.run",
                    params,
                    request_timeout=timeout_sec,
                )
    except (TimeoutError, socket.timeout) as exc:
        _bridge_cache_module().invalidate_on_error(BRIDGE_RPC_TIMEOUT)
        return _verify_receipt(
            ok=False,
            workspace_root=ws,
            task_id=resolved_task,
            command=cmd,
            cwd=cwd,
            error={"string_code": BRIDGE_RPC_TIMEOUT, "message": str(exc)},
            string_code=BRIDGE_RPC_TIMEOUT,
        )
    except Exception as exc:
        _bridge_cache_module().invalidate_on_error(BRIDGE_TRANSPORT_ERROR)
        return _verify_receipt(
            ok=False,
            workspace_root=ws,
            task_id=resolved_task,
            command=cmd,
            cwd=cwd,
            error={"string_code": BRIDGE_TRANSPORT_ERROR, "message": str(exc)},
            string_code=BRIDGE_TRANSPORT_ERROR,
        )

    if not rpc.get("ok"):
        err_body = rpc.get("error") if isinstance(rpc.get("error"), dict) else {}
        return _verify_receipt(
            ok=False,
            workspace_root=ws,
            task_id=resolved_task,
            command=cmd,
            cwd=cwd,
            verify_ran=False,
            rpc=rpc,
            error=err_body,
            string_code=str(err_body.get("string_code") or BRIDGE_RPC_ERROR),
        )

    kernel_result = rpc.get("result") if isinstance(rpc.get("result"), dict) else {}
    fields = extract_verify_fields(kernel_result)
    passed = bool(fields.get("passed"))
    exit_code = fields.get("exitCode")
    stdout_summary = fields.get("stdout_summary") or summarize_output(
        str(fields.get("stdout") or kernel_result.get("output") or "")
    )
    stderr_summary = fields.get("stderr_summary") or summarize_output(
        str(fields.get("stderr") or "")
    )

    return _verify_receipt(
        ok=True,
        workspace_root=ws,
        task_id=resolved_task or None,
        command=cmd,
        cwd=cwd,
        passed=passed,
        exit_code=exit_code,
        stdout_summary=stdout_summary,
        stderr_summary=stderr_summary,
        verify_ran=True,
        kernel_result=kernel_result,
        rpc=rpc,
    )
