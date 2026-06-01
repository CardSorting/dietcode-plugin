"""Operator + agent clarity for autonomous JSDP — single source of truth for phases."""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Optional


class JsdpPhase(str, Enum):
    """Where you are in the rolling-horizon loop."""

    SETUP_JOYZONING = "setup_joyzoning"  # human: install JoyZoning / open desktop
    START = "start"  # agent: jsdp(start) — first session, no .jsdp
    PLAN = "plan"  # agent: jsdp(start) — need next 3–5 nodes
    APPLY_PLAN = "apply_plan"  # agent: jsdp(apply, proposal_json=…)
    EXECUTE = "execute"  # agent: jsdp(advance) — run DAG step
    REPAIR = "repair"  # agent: jsdp(advance) — failed node
    OPERATOR_MERGE = "operator_merge"  # human: operator review + convergence_mark_converged


OPERATOR_PLAYBOOK = """
JoyZoning JSDP autonomous path (operators)

You do NOT configure Hermes yaml for rolling horizon. Dispatch from JoyZoning
(Kanban → Dispatch) and the agent uses the jsdp tool automatically.

| Your job | Command / UI |
|----------|----------------|
| Start work on a card | JoyZoning → Dispatch (or jz task run) |
| Review agent output | Watch / Execution viewport |
| Approve finished work | jz task complete <id> --yes |

Optional CLI (experts only): jz jsdp doctor · jz jsdp horizon status
Full harness reference: JoyZoning docs/jsdp-convergence-harness.md
""".strip()

AGENT_PLAYBOOK = """
JSDP autonomous loop (agents) — four tool calls only

1. jsdp(action='start')     — session begin (auto-inits .jsdp/, returns planning context)
2. jsdp(action='apply', proposal_json='…') — after you author ≤5 horizon nodes as JSON
3. jsdp(action='advance')   — repeat: harness runs next / verify / continue for you
4. jsdp(action='guide')     — when unsure; returns phase + exact next call

Never: full-project import-plan, manual config paths, or 12 separate horizon CLI steps.
""".strip()


def _horizon_fields(hstatus: dict[str, Any] | None) -> dict[str, Any]:
    if not hstatus:
        return {}
    return {
        "failed": list(hstatus.get("failedNodeIds") or hstatus.get("FailedNodeIds") or []),
        "ready": list(hstatus.get("readyNodeIds") or hstatus.get("ReadyNodeIds") or []),
        "suggested": str(
            hstatus.get("suggestedAction") or hstatus.get("SuggestedAction") or ""
        ),
        "stale": bool(
            hstatus.get("horizonContextStale") or hstatus.get("HorizonContextStale")
        ),
        "dag_size": hstatus.get("dagSize") or hstatus.get("DagSize"),
    }


def determine_phase(
    *,
    cli_ok: bool,
    harness_present: bool,
    horizon: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return phase, operator_summary, agent_next_call — no jargon."""
    from plugins.dietcode.lib.agent.joyzoning.config import read_scope_env

    kanban_linked = bool(read_scope_env("HERMES_KANBAN_TASK"))
    if not cli_ok:
        return {
            "phase": JsdpPhase.SETUP_JOYZONING.value,
            "setup_required": True,
            "operator_summary": (
                "JoyZoning CLI not found on this machine. "
                "Open JoyZoning desktop (auto-setup) or clone JoyZoning and run scripts/install-diet-hermes.sh."
            ),
            "agent_next_call": None,
            "agent_blocked": True,
        }

    if not harness_present:
        return {
            "phase": JsdpPhase.START.value,
            "setup_required": False,
            "operator_summary": "Harness not initialized yet — agent will create .jsdp/ on first jsdp(start).",
            "agent_next_call": "jsdp(action='start')",
            "agent_blocked": False,
        }

    h = _horizon_fields(horizon)
    if h.get("failed"):
        return {
            "phase": JsdpPhase.REPAIR.value,
            "setup_required": False,
            "operator_summary": (
                f"Verification failed on node(s) {', '.join(h['failed'])}. "
                "Agent should repair; you review before merge."
            ),
            "agent_next_call": "jsdp(action='advance')",
            "agent_blocked": False,
        }

    suggested = (h.get("suggested") or "").lower()
    if "continue" in suggested or "repair" in suggested:
        return {
            "phase": JsdpPhase.REPAIR.value,
            "setup_required": False,
            "operator_summary": "Harness requests repair before more planning.",
            "agent_next_call": "jsdp(action='advance')",
            "agent_blocked": False,
        }

    if h.get("stale") or ("re-export" in suggested and "export" in suggested):
        return {
            "phase": JsdpPhase.PLAN.value,
            "setup_required": False,
            "operator_summary": "Planning context is stale — agent should refresh with jsdp(start).",
            "agent_next_call": "jsdp(action='start')",
            "agent_blocked": False,
        }

    if "next" in suggested or h.get("ready"):
        return {
            "phase": JsdpPhase.EXECUTE.value,
            "setup_required": False,
            "operator_summary": (
                "DAG has work ready — agent executes the next node, then advances the harness."
            ),
            "agent_next_call": "jsdp(action='advance')",
            "agent_blocked": False,
        }

    if kanban_linked and "complete" in suggested:
        return {
            "phase": JsdpPhase.OPERATOR_MERGE.value,
            "setup_required": False,
            "operator_summary": "Agent work may be ready — operator runs jz task complete --yes in JoyZoning.",
            "agent_next_call": "joyzoning(action='request_review') then stop for operator",
            "agent_blocked": False,
        }

    # Default: plan next horizon
    return {
        "phase": JsdpPhase.PLAN.value,
        "setup_required": False,
        "operator_summary": (
            "Plan the next 3–5 steps (rolling horizon). Agent calls jsdp(start), "
            "then jsdp(apply) with JSON."
        ),
        "agent_next_call": "jsdp(action='start')",
        "agent_blocked": False,
    }


def clarity_envelope(
    payload: dict[str, Any],
    *,
    cli_ok: bool = True,
    harness_present: bool = False,
    horizon: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Attach operator/agent clarity fields to any jsdp tool response."""
    guide = determine_phase(
        cli_ok=cli_ok,
        harness_present=harness_present,
        horizon=horizon or payload.get("horizon") or payload.get("horizon_status"),
    )
    return {
        **payload,
        **guide,
        "execution_path": "jsdp_autonomous",
        "agent_playbook": AGENT_PLAYBOOK,
        "operator_playbook": OPERATOR_PLAYBOOK,
    }
