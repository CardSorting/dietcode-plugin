"""Hermes JoyZoning runtime event journal — local execution record only."""
from __future__ import annotations

from typing import Any, Optional

from plugins.dietcode.lib.agent.joyzoning.boundaries import layer_for_event
from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, read_scope_env


def emit_runtime_event(
    event_type: str,
    *,
    scope_id: str = "",
    session_id: str = "",
    run_id: str = "",
    correlation_id: str = "",
    payload: Optional[dict[str, Any]] = None,
) -> Optional[str]:
    """Append an operational event to the JoyZoning journal when enabled."""
    cfg = get_joyzoning_config()
    if not cfg.enabled or not cfg.execution_journal:
        return None

    layer = layer_for_event(event_type)
    session_id = session_id or read_scope_env("HERMES_SESSION_ID")
    run_id = run_id or read_scope_env("HERMES_KANBAN_RUN_ID")

    from plugins.dietcode.lib.agent.joyzoning.journal import get_journal

    return get_journal().append_event(
        event_type=event_type,
        layer=layer.value,
        scope_id=scope_id,
        session_id=session_id,
        run_id=run_id,
        correlation_id=correlation_id,
        payload=payload,
    )


def format_runtime_stream(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize journal rows for tools and observability."""
    return [
        {
            "id": e.get("id"),
            "timestamp": e.get("timestamp"),
            "layer": e.get("layer"),
            "type": e.get("event_type"),
            "scopeId": e.get("scope_id"),
            "sessionId": e.get("session_id"),
            "runId": e.get("run_id"),
            "correlationId": e.get("correlation_id"),
            "payload": e.get("payload", {}),
            "source": "hermes-runtime",
        }
        for e in events
    ]
