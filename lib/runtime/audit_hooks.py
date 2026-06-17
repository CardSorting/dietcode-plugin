# -*- coding: utf-8 -*-
"""Quality audit hooks — capture tool outputs and governance blocks."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_QUALITY_TOOLS = frozenset({
    "broccolidb_violations",
    "broccolidb_joyzoning_audit",
    "broccolidb_entropy",
    "joyzoning",
    "mutation_verify",
})


def _post_tool_call(
    *,
    tool_name: str = "",
    args: Any = None,
    result: Any = None,
    **_: Any,
) -> None:
    try:
        from plugins.dietcode.lib.agent.audit.config import get_completion_gate_config
        from plugins.dietcode.lib.agent.audit.quality_gate import record_tool_quality_result
        from plugins.dietcode.lib.agent.joyzoning.config import resolve_scope_id

        if not get_completion_gate_config().enabled:
            return
        if tool_name not in _QUALITY_TOOLS:
            return
        parsed = args if isinstance(args, dict) else {}
        scope = resolve_scope_id(parsed.get("task_id") or parsed.get("scope_id"))
        if isinstance(result, str):
            record_tool_quality_result(scope, tool_name, result)
    except Exception as exc:
        logger.debug("dietcode audit post_tool_call: %s", exc)


def on_governance_block(payload: dict[str, Any], *, scope_id: Optional[str] = None) -> None:
    try:
        from plugins.dietcode.lib.agent.audit.config import get_completion_gate_config
        from plugins.dietcode.lib.agent.audit.quality_gate import record_governance_block
        from plugins.dietcode.lib.agent.joyzoning.config import resolve_scope_id

        if not get_completion_gate_config().enabled:
            return
        record_governance_block(resolve_scope_id(scope_id), payload)
    except Exception as exc:
        logger.debug("dietcode audit governance block: %s", exc)


def capture_governance_transform_result(result: Optional[str]) -> None:
    if not result or not isinstance(result, str):
        return
    try:
        data = json.loads(result)
    except json.JSONDecodeError:
        return
    if isinstance(data, dict) and data.get("error") and "GOVERNANCE" in str(data.get("error", "")).upper():
        on_governance_block(data)
