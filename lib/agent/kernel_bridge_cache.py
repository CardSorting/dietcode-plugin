# -*- coding: utf-8 -*-
"""Phase 7 — short-TTL readiness caches for kernel bridge (positive checks only)."""
from __future__ import annotations

import time
from typing import Any, Optional

_READINESS_CACHE: dict[str, Any] = {
    "ok": False,
    "at": 0.0,
    "socket_path": "",
    "token_path": "",
}
_WORKSPACE_CACHE: dict[str, Any] = {
    "workspace_root": "",
    "at": 0.0,
    "confirmed": False,
}

_INVALIDATION_CODES = frozenset({
    "bridge_socket_unavailable",
    "bridge_token_unavailable",
    "bridge_transport_error",
    "bridge_workspace_unsafe",
    "bridge_workspace_unresolved",
    "bridge_rpc_timeout",
})


def _now() -> float:
    return time.monotonic()


def invalidate_readiness(*, reason: str = "") -> None:
    _READINESS_CACHE["ok"] = False
    _READINESS_CACHE["at"] = 0.0
    _READINESS_CACHE["reason"] = reason


def invalidate_workspace_cache(*, reason: str = "") -> None:
    _WORKSPACE_CACHE["workspace_root"] = ""
    _WORKSPACE_CACHE["at"] = 0.0
    _WORKSPACE_CACHE["confirmed"] = False
    _WORKSPACE_CACHE["reason"] = reason


def invalidate_on_error(string_code: str) -> None:
    code = str(string_code or "").strip()
    if code in _INVALIDATION_CODES:
        invalidate_readiness(reason=code)
        invalidate_workspace_cache(reason=code)


def cache_readiness(*, socket_path: str, token_path: str) -> None:
    _READINESS_CACHE.update({
        "ok": True,
        "at": _now(),
        "socket_path": socket_path,
        "token_path": token_path,
        "reason": "",
    })


def get_cached_readiness(*, ttl_sec: float, socket_path: str, token_path: str) -> bool:
    if not _READINESS_CACHE.get("ok"):
        return False
    if ttl_sec <= 0:
        return False
    if (_now() - float(_READINESS_CACHE.get("at") or 0.0)) > ttl_sec:
        return False
    if _READINESS_CACHE.get("socket_path") != socket_path:
        return False
    if _READINESS_CACHE.get("token_path") != token_path:
        return False
    return True


def mark_workspace_open(workspace_root: str) -> None:
    _WORKSPACE_CACHE.update({
        "workspace_root": str(workspace_root or ""),
        "at": _now(),
        "confirmed": True,
        "reason": "",
    })


def workspace_open_cache_hit(
    *,
    enabled: bool,
    workspace_root: str,
    ttl_sec: float = 5.0,
) -> bool:
    if not enabled:
        return False
    ws = str(workspace_root or "")
    if not ws or not _WORKSPACE_CACHE.get("confirmed"):
        return False
    if _WORKSPACE_CACHE.get("workspace_root") != ws:
        return False
    if ttl_sec <= 0:
        return False
    return (_now() - float(_WORKSPACE_CACHE.get("at") or 0.0)) <= ttl_sec


def reset_bridge_caches() -> None:
    """Test helper."""
    invalidate_readiness()
    invalidate_workspace_cache()
