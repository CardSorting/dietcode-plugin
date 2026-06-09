# -*- coding: utf-8 -*-
"""Phase 7 — per-workspace mutation serialization (patch/verify)."""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

_lock_registry: dict[str, threading.Lock] = {}
_registry_guard = threading.Lock()


def _lock_for_workspace(workspace_root: str) -> threading.Lock:
    key = str(workspace_root or "").strip() or "__default__"
    with _registry_guard:
        lock = _lock_registry.get(key)
        if lock is None:
            lock = threading.Lock()
            _lock_registry[key] = lock
        return lock


@contextmanager
def mutation_lock(
    workspace_root: str,
    *,
    max_concurrent: int = 1,
) -> Iterator[None]:
    """
    Serialize patch/verify per workspace when ``max_concurrent`` is 1.

    Read/status/search callers must not acquire this lock.
    """
    if max_concurrent != 1:
        yield
        return
    lock = _lock_for_workspace(workspace_root)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def reset_mutation_locks() -> None:
    """Test helper."""
    with _registry_guard:
        _lock_registry.clear()
