# -*- coding: utf-8 -*-
"""JSDP (JoyZoning rolling-horizon) lifecycle hooks."""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _on_session_start(*, session_id: str = "", **_: Any) -> None:
    """Emit ``jsdp.role_started`` when a dispatched worker carries a JSDP role."""
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, resolve_scope_id
        from plugins.dietcode.lib.agent.joyzoning.runtime_events import emit_runtime_event

        cfg = get_joyzoning_config()
        if not cfg.enabled or not cfg.jsdp_enabled:
            return
        if not cfg.jsdp_role:
            return
        emit_runtime_event(
            "jsdp.role_started",
            scope_id=resolve_scope_id(),
            session_id=session_id,
            payload={"role": cfg.jsdp_role, "chain_id": cfg.jsdp_chain_id},
        )
    except Exception as exc:
        logger.warning("dietcode jsdp on_session_start: %s", exc)
