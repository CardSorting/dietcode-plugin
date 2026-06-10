"""Auto-rolling roadmap checkpoint — project steering surface for long-horizon work."""
from __future__ import annotations

from plugins.dietcode.lib.agent.roadmap.cockpit import build_cockpit_payload, format_cockpit_report
from plugins.dietcode.lib.agent.roadmap.doctor import run_checks
from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import (
    checkpoint_brief,
    operational_status,
    probe_roadmap_available,
    template_brief,
    validate_roadmap,
)
from plugins.dietcode.lib.agent.roadmap.explain_gate import build_explain_gate_payload
from plugins.dietcode.lib.agent.roadmap.gate import build_roadmap_gate_state, require_fresh_checkpoint_before_complete
from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints
from plugins.dietcode.lib.agent.roadmap.progress import build_progress_snapshot, read_progress_current
from plugins.dietcode.lib.agent.roadmap.session import emit_roadmap_event, session_brief

__all__ = [
    "build_agent_operator_hints",
    "build_explain_gate_payload",
    "build_agent_operator_hints",
    "build_progress_snapshot",
    "build_roadmap_gate_state",
    "build_cockpit_payload",
    "checkpoint_brief",
    "emit_roadmap_event",
    "format_cockpit_report",
    "operational_status",
    "probe_roadmap_available",
    "read_progress_current",
    "run_checks",
    "session_brief",
    "template_brief",
    "validate_roadmap",
    "require_fresh_checkpoint_before_complete",
]
