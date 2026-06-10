"""Architectural layer boundaries — representation vs runtime vs mutation vs verification."""
from __future__ import annotations

from enum import Enum


class RuntimeLayer(str, Enum):
    """Strict separation of concerns (never collapse)."""

    REPRESENTATION = "representation"  # operator cognition / observability (non-authoritative)
    RUNTIME = "runtime"  # Hermes execution authority
    MUTATION = "mutation"  # JSDP / patch providers
    VERIFICATION = "verification"  # tests, git, static checks
    CONVERGENCE = "convergence"  # review → accept-merge → converge
    ORCHESTRATION = "orchestration"  # kanban, delegation, scheduling

    HABITAT = "representation"  # deprecated alias — use REPRESENTATION


# Event types → owning layer (for journal tagging and observability streams).
_EVENT_LAYER: dict[str, RuntimeLayer] = {
    "session.start": RuntimeLayer.RUNTIME,
    "session.end": RuntimeLayer.RUNTIME,
    "tool.start": RuntimeLayer.RUNTIME,
    "tool.complete": RuntimeLayer.RUNTIME,
    "tool.blocked": RuntimeLayer.RUNTIME,
    "mutation.proposed": RuntimeLayer.MUTATION,
    "mutation.patched": RuntimeLayer.MUTATION,
    "mutation.verified": RuntimeLayer.VERIFICATION,
    "convergence.review_requested": RuntimeLayer.CONVERGENCE,
    "convergence.ready_for_review": RuntimeLayer.CONVERGENCE,
    "convergence.converged": RuntimeLayer.CONVERGENCE,
    "convergence.rejected": RuntimeLayer.CONVERGENCE,
    "representation.snapshot": RuntimeLayer.REPRESENTATION,
    "habitat.snapshot": RuntimeLayer.REPRESENTATION,  # legacy journal label
    "jsdp.role_started": RuntimeLayer.MUTATION,
    "jsdp.role_complete": RuntimeLayer.MUTATION,
    "jsdp.handoff_validated": RuntimeLayer.MUTATION,
    "kanban.sync": RuntimeLayer.ORCHESTRATION,
    "roadmap.session_started": RuntimeLayer.REPRESENTATION,
    "roadmap.guide": RuntimeLayer.REPRESENTATION,
    "roadmap.checkpoint_brief": RuntimeLayer.REPRESENTATION,
    "roadmap.validated": RuntimeLayer.REPRESENTATION,
    "roadmap.doctor": RuntimeLayer.REPRESENTATION,
    "roadmap.cockpit": RuntimeLayer.REPRESENTATION,
    "roadmap.template": RuntimeLayer.REPRESENTATION,
    "roadmap.evidence": RuntimeLayer.REPRESENTATION,
    "roadmap.status": RuntimeLayer.REPRESENTATION,
    "roadmap.tool_call": RuntimeLayer.REPRESENTATION,
    "roadmap.roadmap_file_mutated": RuntimeLayer.REPRESENTATION,
    "roadmap.session_ended": RuntimeLayer.REPRESENTATION,
    "roadmap.explain_gate": RuntimeLayer.REPRESENTATION,
    "roadmap.explain_stale": RuntimeLayer.REPRESENTATION,
    "roadmap.progress": RuntimeLayer.REPRESENTATION,
    "roadmap.watch": RuntimeLayer.REPRESENTATION,
    "roadmap.last_error": RuntimeLayer.REPRESENTATION,
}


def layer_for_event(event_type: str) -> RuntimeLayer:
    return _EVENT_LAYER.get(event_type, RuntimeLayer.RUNTIME)


# Authority rules (documented in code — enforced by plugins/tools).
REPRESENTATION_MUST_NOT = frozenset({
    "execute_tools",
    "mutate_files",
    "approve_merges",
    "own_execution_leases",
})

HABITAT_MUST_NOT = REPRESENTATION_MUST_NOT  # deprecated alias

RUNTIME_OWNS = frozenset({
    "agent_loop",
    "tool_dispatch",
    "approval_routing",
    "session_state",
    "execution_journal",
})

MUTATION_PROVIDER_OWNS = frozenset({
    "patch_planning",
    "handoff_synthesis",
    "role_scoped_proposals",
})
