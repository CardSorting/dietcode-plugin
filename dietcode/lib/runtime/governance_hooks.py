# -*- coding: utf-8 -*-
"""Governance transform_tool_result hook — DietCode production surface."""
from __future__ import annotations

from typing import Any, Optional


def on_transform_tool_result(
    tool_name: str = "",
    args: Optional[dict[str, Any]] = None,
    result: Any = None,
    **_: Any,
) -> Optional[str]:
    """Intercept tool outputs, scan modified files, and block architectural leaks."""
    if not isinstance(args, dict):
        args = {}
    from plugins.dietcode.lib.agent.governance_exemptions import (
        enforce_governance_on_mutation,
        is_governance_enforcement_enabled,
    )

    if not is_governance_enforcement_enabled():
        return None
    return enforce_governance_on_mutation(tool_name, args, result)
