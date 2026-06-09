# -*- coding: utf-8 -*-
"""Phase 7B — optional idle warm state for kernel bridge readiness."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)

_warm_thread: threading.Thread | None = None
_warm_stop = threading.Event()
_last_activity_mono = 0.0
_last_ping_mono = 0.0
_warm_lock = threading.Lock()


def touch_bridge_activity() -> None:
    global _last_activity_mono
    _last_activity_mono = time.monotonic()


def _load_cfg() -> Any:
    try:
        from plugins.dietcode.lib.agent.kernel_bridge_client import KernelBridgeConfig
    except ImportError:
        from lib.agent.kernel_bridge_client import KernelBridgeConfig
    return KernelBridgeConfig.load()


def _warm_ping() -> None:
    cfg = _load_cfg()
    if not cfg.enabled or not cfg.keep_warm:
        return
    idle_ms = int((time.monotonic() - _last_activity_mono) * 1000)
    if idle_ms > cfg.keep_warm_idle_timeout_ms:
        return
    try:
        from plugins.dietcode.lib.agent import kernel_bridge_cache as cache
        from plugins.dietcode.lib.agent.kernel_bridge_client import (
            _socket_path,
            _token_path,
            connect_preflight,
        )
    except ImportError:
        from lib.agent import kernel_bridge_cache as cache
        from lib.agent.kernel_bridge_client import _socket_path, _token_path, connect_preflight

    ttl_sec = max(0.0, cfg.preflight_cache_ttl_ms / 1000.0)
    if cache.get_cached_readiness(
        ttl_sec=ttl_sec,
        socket_path=_socket_path(),
        token_path=_token_path(),
    ):
        return
    try:
        connect_preflight(start=False)
    except Exception as exc:
        logger.debug("keep_warm ping skipped: %s", exc)


def _warm_loop() -> None:
    global _last_ping_mono
    while not _warm_stop.wait(1.0):
        cfg = _load_cfg()
        if not cfg.enabled or not cfg.keep_warm:
            continue
        interval_sec = max(5.0, cfg.keep_warm_ping_interval_ms / 1000.0)
        now = time.monotonic()
        if (now - _last_ping_mono) < interval_sec:
            continue
        _last_ping_mono = now
        _warm_ping()


def ensure_keep_warm_started() -> None:
    global _warm_thread
    cfg = _load_cfg()
    if not cfg.keep_warm:
        return
    touch_bridge_activity()
    with _warm_lock:
        if _warm_thread is not None and _warm_thread.is_alive():
            return
        _warm_stop.clear()
        _warm_thread = threading.Thread(target=_warm_loop, name="kernel-bridge-keep-warm", daemon=True)
        _warm_thread.start()


def stop_keep_warm() -> None:
    _warm_stop.set()


def reset_keep_warm_state() -> None:
    """Test helper."""
    global _warm_thread, _last_activity_mono
    stop_keep_warm()
    _warm_thread = None
    _last_activity_mono = 0.0
