# -*- coding: utf-8 -*-
"""Central DietCode hook wiring — single registration surface for production."""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Session start order matters:
#   1. Kanban ↔ BroccoliQ hive sync (worker scope + debounced queue)
#   2. JoyZoning runtime (scope registry + session.start journal event)
#   3. JSDP role_started (when jsdp_role env is set)
_ON_SESSION_START: tuple[Callable[..., Any], ...] = ()
_ON_SESSION_END: tuple[Callable[..., Any], ...] = ()
_POST_TOOL_CALL: tuple[Callable[..., Any], ...] = ()
_PRE_TOOL_CALL: tuple[Callable[..., Any], ...] = ()
_TRANSFORM_TOOL_RESULT: tuple[Callable[..., Any], ...] = ()


def _joyzoning_enabled_safe() -> bool:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config

        return bool(get_joyzoning_config().enabled)
    except Exception:
        return False


def _governance_enabled_safe() -> bool:
    try:
        from plugins.dietcode.lib.agent.governance_exemptions import (
            is_governance_enforcement_enabled,
        )

        return bool(is_governance_enforcement_enabled())
    except Exception:
        return False


def _ensure_handlers() -> None:
    global _ON_SESSION_START, _ON_SESSION_END, _POST_TOOL_CALL, _PRE_TOOL_CALL, _TRANSFORM_TOOL_RESULT
    if _ON_SESSION_START:
        return
    from plugins.dietcode.lib.runtime.jsdp_hooks import _on_session_start as jsdp_start
    from plugins.dietcode.lib.runtime.governance_hooks import on_transform_tool_result
    from plugins.dietcode.lib.runtime.joyzoning_hooks import (
        _on_session_end as jz_end,
        _on_session_start as jz_start,
        _post_tool_call as jz_post,
        _pre_tool_call as jz_pre,
    )
    from plugins.dietcode.lib.runtime.kanban_hooks import (
        _on_post_tool_call as kanban_post,
        _on_session_start as kanban_start,
    )

    _ON_SESSION_START = (kanban_start, jz_start, jsdp_start)
    _ON_SESSION_END = (jz_end,)
    _POST_TOOL_CALL = (jz_post, kanban_post)
    _PRE_TOOL_CALL = (jz_pre,)
    _TRANSFORM_TOOL_RESULT = (on_transform_tool_result,)


def _run_all(hook_name: str, handlers: tuple[Callable[..., Any], ...]) -> None:
    def _wrapped(**kwargs: Any) -> None:
        _ensure_handlers()
        for handler in handlers:
            try:
                handler(**kwargs)
            except Exception as exc:
                logger.warning("DietCode hook %s (%s) failed: %s", hook_name, handler.__name__, exc)

    _wrapped.__name__ = f"dietcode_{hook_name}"
    return _wrapped


def _run_pre_tool_call(handlers: tuple[Callable[..., Any], ...]) -> Callable[..., Any]:
    def _wrapped(**kwargs: Any) -> dict[str, str] | None:
        _ensure_handlers()
        for handler in handlers:
            try:
                result = handler(**kwargs)
            except Exception as exc:
                logger.warning("DietCode pre_tool_call (%s) failed: %s", handler.__name__, exc)
                if _joyzoning_enabled_safe():
                    from plugins.dietcode.lib.agent.joyzoning.convergence_gate import block_dict

                    return block_dict(f"Convergence gate unavailable: {exc}")
                continue
            if isinstance(result, dict) and result.get("action") == "block":
                return result
        return None

    _wrapped.__name__ = "dietcode_pre_tool_call"
    return _wrapped


def _governance_unavailable_payload(exc: Exception) -> str:
    return json.dumps(
        {
            "success": False,
            "error": "[GOVERNANCE FAULT] Governance enforcement unavailable.",
            "detail": str(exc),
            "recovery_plan": (
                "Retry once after fixing the underlying error. If this persists, "
                "set joyzoning.governance.enabled: false or disable the DietCode plugin."
            ),
        },
        ensure_ascii=False,
    )


def _run_transform(handlers: tuple[Callable[..., Any], ...]) -> Callable[..., Any]:
    def _wrapped(**kwargs: Any) -> str | None:
        _ensure_handlers()
        for handler in handlers:
            try:
                result = handler(**kwargs)
            except Exception as exc:
                logger.warning("DietCode transform_tool_result (%s) failed: %s", handler.__name__, exc)
                if _governance_enabled_safe():
                    return _governance_unavailable_payload(exc)
                continue
            if isinstance(result, str) and result.strip():
                return result
        return None

    _wrapped.__name__ = "dietcode_transform_tool_result"
    return _wrapped


def register_all_hooks(ctx) -> None:
    """Register consolidated hooks (one callback per hook name — no duplicate firing)."""
    _ensure_handlers()
    ctx.register_hook("on_session_start", _run_all("on_session_start", _ON_SESSION_START))
    ctx.register_hook("on_session_end", _run_all("on_session_end", _ON_SESSION_END))
    ctx.register_hook("post_tool_call", _run_all("post_tool_call", _POST_TOOL_CALL))
    ctx.register_hook("pre_tool_call", _run_pre_tool_call(_PRE_TOOL_CALL))
    ctx.register_hook("transform_tool_result", _run_transform(_TRANSFORM_TOOL_RESULT))
