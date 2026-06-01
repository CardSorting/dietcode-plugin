# -*- coding: utf-8 -*-
"""DietCode runtime hook handlers (canonical implementation)."""

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

__all__ = [
    "on_transform_tool_result",
    "_on_session_start",
    "_on_session_end",
    "_pre_tool_call",
    "_post_tool_call",
    "_kanban_on_session_start",
    "_on_post_tool_call",
    "_jsdp_on_session_start",
]
