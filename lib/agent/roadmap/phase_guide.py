"""Operator + agent clarity for roadmap checkpoints — single source of truth for phases."""
from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from plugins.dietcode.lib.agent.roadmap.schema import REQUIRED_SECTIONS


class RoadmapPhase(str, Enum):
    BOOTSTRAP = "bootstrap"
    BOOTSTRAP_FILL = "bootstrap_fill"
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
| Bootstrap placeholders remain | roadmap(action='apply_bootstrap_fill', context='write') |
| Closed gates / kanban blocked | /roadmap explain-gate |
| Activity timeline | /roadmap progress --timeline |

Write guard: ROADMAP.md only in the Hermes project workspace — out-of-tree writes blocked at pre_tool_call.
Skill file: optional-skills/dietcode/auto-rolling-roadmap/SKILL.md
""".strip()

AGENT_PLAYBOOK = """
Roadmap autonomous loop (agents)

1. roadmap(action='guide')       — phase, health, steering_line, project_steering_digest, _roadmap_operator_hints
2. roadmap(action='checkpoint')  — evidence bundle + bootstrap_fill_plan when placeholders remain
3. roadmap(action='apply_bootstrap_fill') — preview/write per-project evidence autofill
4. Edit ROADMAP.md at workspace root only — never ~/.hermes/plugins/dietcode
5. roadmap(action='validate')    — confirm schema + bootstrap completeness before finishing
6. roadmap(action='explain_gate') — when gates block kanban_complete or schema is unclear
7. Return Required Final Assistant Response summary (not the full file)

Every roadmap tool response includes steering_line and write_guard hints.
Per-project identity lives in project_identity_line, project_steering_digest.identity_line, project_fingerprint, and bootstrap_fill_plan when placeholders remain.
Prime directive: did the latest work strengthen or weaken center of gravity?
Section 9 code soup audit is mandatory every pass. Keep Now ≤ 5 items.
""".strip()


def determine_phase(
    *,
    roadmap_exists: bool,
    sections_missing: list[str],
    health_status: Optional[str],
    validation_valid: Optional[bool] = None,
    bootstrap_incomplete: bool = False,
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

    if bootstrap_incomplete:
        return {
            "phase": RoadmapPhase.BOOTSTRAP_FILL.value,
            "operator_summary": (
                "Bootstrap template phrases remain — preview roadmap(action='apply_bootstrap_fill'), "
                "apply with context='write', then validate."
            ),
            "agent_next_call": "roadmap(action='apply_bootstrap_fill', context='write')",
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
    from plugins.dietcode.lib.agent.roadmap.agent_steering import format_agent_steering_line
    from plugins.dietcode.lib.agent.roadmap.operator import build_agent_operator_hints
    from plugins.dietcode.lib.agent.roadmap.steering_context import enrich_payload_with_steering

    enriched = enrich_payload_with_steering(payload)
    guide = phase_info or {}
    gate = enriched.get("roadmap_gate")
    operator_hints = build_agent_operator_hints(
        action=str(enriched.get("action") or ""),
        gate=gate if isinstance(gate, dict) else None,
        workspace=str(enriched.get("workspace") or ""),
        last_error=enriched.get("last_error") if isinstance(enriched.get("last_error"), dict) else None,
    )
    steering_line = format_agent_steering_line(workspace=str(enriched.get("workspace") or "") or None)
    digest = enriched.get("project_steering_digest") if isinstance(enriched.get("project_steering_digest"), dict) else {}
    identity_line = operator_hints.get("project_identity_line") or digest.get("identity_line")
    return {
        **enriched,
        "success": enriched.get("success", enriched.get("ok", True)),
        "ok": enriched.get("ok", enriched.get("success", True)),
        **guide,
        "execution_path": "roadmap_checkpoint",
        "agent_playbook": AGENT_PLAYBOOK,
        "operator_playbook": OPERATOR_PLAYBOOK,
        "required_section_count": len(REQUIRED_SECTIONS),
        "steering_line": steering_line or None,
        "project_identity_line": identity_line or None,
        "_roadmap_operator_hints": {
            **operator_hints,
            "skill_path": enriched.get("skill_path"),
            "recovery_suggestion": operator_hints.get("recovery_suggestion")
            or guide.get("operator_summary")
            or enriched.get("operator_summary"),
            "next_action": operator_hints.get("next_action")
            or (enriched.get("recommended_next_action") or {}).get("command")
            or guide.get("agent_next_call")
            or enriched.get("agent_next_call"),
        },
    }
