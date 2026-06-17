# -*- coding: utf-8 -*-
"""Governance transform_tool_result hook — DietCode production surface."""
from __future__ import annotations

from typing import Any, Optional

from plugins.dietcode.lib.runtime.hook_guards import when_enabled


@when_enabled("governance")
def on_transform_tool_result(
    tool_name: str = "",
    args: Optional[dict[str, Any]] = None,
    result: Any = None,
    **_: Any,
) -> Optional[str]:
    """Intercept tool outputs, scan modified files, and block architectural leaks."""
    if not isinstance(args, dict):
        args = {}
    from plugins.dietcode.lib.agent.governance_exemptions import enforce_governance_on_mutation

    return enforce_governance_on_mutation(tool_name, args, result)
