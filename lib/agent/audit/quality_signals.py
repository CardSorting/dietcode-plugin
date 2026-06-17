"""Quality-audit tool capture registry — single source for post_tool_call hooks."""
from __future__ import annotations

QUALITY_CAPTURE_TOOLS: frozenset[str] = frozenset({
    "broccolidb_violations",
    "broccolidb_joyzoning_audit",
    "broccolidb_entropy",
    "joyzoning",
    "mutation_verify",
})


def is_quality_capture_tool(tool_name: str) -> bool:
    return (tool_name or "").strip() in QUALITY_CAPTURE_TOOLS
