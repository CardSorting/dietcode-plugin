# -*- coding: utf-8 -*-
"""Feature-gated hook helpers — skip handlers when subsystems are disabled."""
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Optional, TypeVar

F = TypeVar("F", bound=Callable[..., Any])


def _feature_active(feature: str) -> bool:
    from plugins.dietcode.lib.agent import features

    checks: dict[str, Callable[[], bool]] = {
        "joyzoning": features.is_joyzoning_enabled,
        "roadmap": features.is_roadmap_enabled,
        "governance": features.is_governance_enabled,
        "completion_gate": features.is_completion_gate_enabled,
        "jsdp": features.is_jsdp_enabled,
        "joyzoning_journal": features.is_joyzoning_journal_enabled,
    }
    checker = checks.get(feature)
    if checker is None:
        return True
    return bool(checker())


def when_enabled(feature: str) -> Callable[[F], F]:
    """No-op the wrapped hook when a runtime feature flag is off."""

    def decorator(fn: F) -> F:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if not _feature_active(feature):
                return None
            return fn(*args, **kwargs)

        return wrapper  # type: ignore[return-value]

    return decorator


def skip_unless(feature: str) -> Callable[[F], F]:
    """Alias for ``when_enabled`` — reads naturally on early-return hooks."""
    return when_enabled(feature)
