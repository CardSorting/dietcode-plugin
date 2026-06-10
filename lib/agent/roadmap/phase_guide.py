"""Operator + agent clarity for roadmap checkpoints — single source of truth for phases."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from plugins.dietcode.lib.agent.roadmap.schema import REQUIRED_SECTIONS


class RoadmapPhase(str, Enum):
    BOOTSTRAP = "bootstrap"
    STRUCTURE_REPAIR = "structure_repair"
    COHERENCE_RECOVERY = "coherence_recovery"
    CHECKPOINT = "checkpoint"
    VALIDATE_PENDING = "validate_pending"


OPERATOR_PLAYBOOK = """
Auto-rolling roadmap checkpoint (operators)

The roadmap is the project's steering surface — not a backlog or wishlist.

| Your job | Command |
|----------|---------|
| See one-screen status | /roadmap cockpit or /dietcode roadmap cockpit |
| Check schema health | /roadmap doctor or roadmap(action='doctor') |
| Before major direction changes | roadmap(action='checkpoint') |
| After agent edits ROADMAP.md | roadmap(action='validate') |
| Closed gates / kanban blocked | /roadmap explain-gate |
| Activity timeline | /roadmap progress --timeline |

Skill file: optional-skills/dietcode/auto-rolling-roadmap/SKILL.md
""".strip()

AGENT_PLAYBOOK = """
Roadmap autonomous loop (agents)

1. roadmap(action='guide')       — phase, health, exact next call
2. roadmap(action='checkpoint')  — evidence bundle + 16-step algorithm
3. Edit ROADMAP.md per skill     — evolve, compress, archive stale items
4. roadmap(action='validate')    — confirm schema before finishing
5. roadmap(action='explain_gate') — when gates block kanban_complete or schema is unclear
6. Return Required Final Assistant Response summary (not the full file)

Prime directive: did the latest work strengthen or weaken center of gravity?
Section 9 code soup audit is mandatory every pass. Keep Now ≤ 5 items.
""".strip()


def determine_phase(
    *,
    roadmap_exists: bool,
    sections_missing: list[str],
    health_status: Optional[str],
    validation_valid: Optional[bool] = None,
) -> dict[str, Any]:
    """Return phase, summaries, and next calls."""
    if validation_valid is False:
        return {
            "phase": RoadmapPhase.VALIDATE_PENDING.value,
            "operator_summary": "ROADMAP.md failed schema validation — repair before next checkpoint.",
            "agent_next_call": "roadmap(action='validate') then fix reported issues",
            "agent_blocked": False,
        }

    if not roadmap_exists:
        return {
            "phase": RoadmapPhase.BOOTSTRAP.value,
            "operator_summary": "No ROADMAP.md — run a checkpoint pass to create the steering surface.",
            "agent_next_call": "roadmap(action='checkpoint') then roadmap(action='template') if needed",
            "agent_blocked": False,
        }

    if len(sections_missing) > 6:
        return {
            "phase": RoadmapPhase.STRUCTURE_REPAIR.value,
            "operator_summary": (
                f"ROADMAP.md missing {len(sections_missing)} sections — repair schema without losing history."
            ),
            "agent_next_call": "roadmap(action='checkpoint', context='repair schema')",
            "agent_blocked": False,
        }

    if health_status in {"Fragmenting", "Overloaded", "Blocked", "Drifting"}:
        return {
            "phase": RoadmapPhase.COHERENCE_RECOVERY.value,
            "operator_summary": (
                f"Roadmap health is {health_status} — run coherence recovery and demote overloaded Now items."
            ),
            "agent_next_call": "roadmap(action='checkpoint', context='coherence recovery')",
            "agent_blocked": False,
        }

    return {
        "phase": RoadmapPhase.CHECKPOINT.value,
        "operator_summary": "Roadmap present — checkpoint after meaningful direction or risk changes.",
        "agent_next_call": "roadmap(action='checkpoint')",
        "agent_blocked": False,
    }


def clarity_envelope(payload: dict[str, Any], *, phase_info: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Attach operator/agent clarity fields to roadmap tool responses."""
    from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints

    guide = phase_info or {}
    gate = payload.get("roadmap_gate")
    operator_hints = build_agent_operator_hints(
        action=str(payload.get("action") or ""),
        gate=gate if isinstance(gate, dict) else None,
        workspace=str(payload.get("workspace") or ""),
        last_error=payload.get("last_error") if isinstance(payload.get("last_error"), dict) else None,
    )
    enriched = {
        **payload,
        "success": payload.get("success", payload.get("ok", True)),
        "ok": payload.get("ok", payload.get("success", True)),
        **guide,
        "execution_path": "roadmap_checkpoint",
        "agent_playbook": AGENT_PLAYBOOK,
        "operator_playbook": OPERATOR_PLAYBOOK,
        "required_section_count": len(REQUIRED_SECTIONS),
        "_roadmap_operator_hints": {
            **operator_hints,
            "skill_path": payload.get("skill_path"),
            "recovery_suggestion": operator_hints.get("recovery_suggestion") or guide.get("operator_summary") or payload.get("operator_summary"),
            "next_action": operator_hints.get("next_action") or guide.get("agent_next_call") or payload.get("agent_next_call"),
        },
    }
    return enriched
