# -*- coding: utf-8 -*-
"""Stable public API for DietCode integrations (tests, dashboard, extensions).

Import from here instead of reaching into ``lib/runtime`` or ``slash_commands``
unless you need internal modules.
"""
from __future__ import annotations

from plugins.dietcode.lib.runtime.governance_hooks import on_transform_tool_result
from plugins.dietcode.lib.runtime.joyzoning_hooks import (
    _on_session_end,
    _on_session_start,
    _post_tool_call,
    _pre_tool_call,
)
from plugins.dietcode.lib.runtime.kanban_hooks import (
    _on_post_tool_call,
    _on_session_start as _kanban_on_session_start,
)
from plugins.dietcode.lib.runtime.jsdp_hooks import _on_session_start as _jsdp_on_session_start
from plugins.dietcode.slash_commands import (
    _handle_broccolidb,
    _handle_broccoliq,
    _handle_joyzoning,
    run_joyzoning_gate,
)

# Historical alias used by governance tests and MCP-adjacent callers.
_on_transform_tool_result = on_transform_tool_result

__all__ = [
    "on_transform_tool_result",
    "_on_transform_tool_result",
    "run_joyzoning_gate",
    "_handle_joyzoning",
    "_handle_broccolidb",
    "_handle_broccoliq",
    "_on_session_start",
    "_on_session_end",
    "_pre_tool_call",
    "_post_tool_call",
    "_kanban_on_session_start",
    "_on_post_tool_call",
    "_jsdp_on_session_start",
]
