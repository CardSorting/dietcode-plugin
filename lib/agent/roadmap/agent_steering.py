"""Live agent steering — compact lines for prompts, session start, and operator watch."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional


def _truncate(text: str, limit: int = 120) -> str:
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1] + "…"


def _project_context_lines(steering: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    brief = steering.get("steering_brief") or steering.get("steering_identity") or steering.get("project_name")
    if brief:
        lines.append(f"Project: {brief}")

    stack = steering.get("stack_summary")
    archetype = steering.get("project_archetype")
    if stack and stack not in (brief or ""):
        stack_line = f"Stack: {stack}"
        if archetype and archetype != "project":
            stack_line += f" ({archetype.replace('-', ' ')})"
        lines.append(stack_line)
    elif archetype and archetype != "project":
        lines.append(f"Archetype: {archetype.replace('-', ' ')}")

    tagline = steering.get("readme_tagline") or steering.get("package_description")
    if tagline and tagline not in (brief or ""):
        lines.append(f"Purpose: {_truncate(str(tagline), 140)}")

    agent_rules = steering.get("agent_rules_files") or []
    if agent_rules:
        lines.append(f"Agent rules: {', '.join(agent_rules[:3])}")

    make_targets = steering.get("makefile_targets") or []
    if make_targets:
        lines.append(f"Makefile: {', '.join(make_targets[:4])}")

    if steering.get("has_backstage_catalog"):
        lines.append("Backstage: catalog-info.yaml present")

    cog = steering.get("center_of_gravity_excerpt")
    if cog:
        lines.append(f"Center of gravity: {_truncate(str(cog), 140)}")

    health = steering.get("health_status")
    now_count = steering.get("now_item_count")
    soup = steering.get("code_soup_risk")
    status_bits: list[str] = []
    if health:
        status_bits.append(f"health={health}")
    if now_count is not None:
        status_bits.append(f"Now={now_count}")
    if soup:
        status_bits.append(f"soup={soup}")
    if status_bits:
        lines.append("Roadmap: " + ", ".join(status_bits))

    checkpoint = steering.get("recent_checkpoint_date")
    if checkpoint:
        lines.append(f"Last checkpoint: {checkpoint}")
    elif steering.get("roadmap_exists"):
        lines.append("Last checkpoint: unparsed — refresh section 11")

    return lines


def format_agent_steering_line(*, workspace: Optional[str] = None) -> str:
    """Live ROADMAP steering for system-prompt injection (kernel cockpit pattern)."""
    try:
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config

        if not get_roadmap_config().enabled:
            return ""
    except Exception:
        return ""

    try:
        from plugins.dietcode.lib.agent.roadmap.operator import is_bootstrap_incomplete, recommend_next_action
        from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

        steering = build_steering_context(workspace=workspace)
        if not steering.get("workspace"):
            return (
                "## ROADMAP live steering\n"
                "Workspace unresolved — set `kanban.workspace` or `HERMES_KANBAN_WORKSPACE` before editing ROADMAP.md."
            )

        path = steering.get("roadmap_path") or f"{steering['workspace']}/ROADMAP.md"
        bootstrap_inc = is_bootstrap_incomplete(
            roadmap_exists=bool(steering.get("roadmap_exists")),
            workspace_state={
                "bootstrap_complete": steering.get("bootstrap_complete"),
                "bootstrap_placeholder_count": steering.get("bootstrap_placeholder_count"),
            },
        )
        phase = "bootstrap_fill" if bootstrap_inc else ""
        next_rec = recommend_next_action(
            phase=phase,
            roadmap_exists=bool(steering.get("roadmap_exists")),
            bootstrap_incomplete=bootstrap_inc,
        )
        parts = [
            "## ROADMAP live steering",
            *(_project_context_lines(steering) or []),
            f"Write ROADMAP.md only at: `{path}` (source: {steering.get('workspace_source', 'auto')}).",
            "Out-of-workspace writes are blocked at pre_tool_call.",
            f"Next: `{next_rec.get('command')}` — {next_rec.get('detail')}",
        ]
        if steering.get("bootstrap_complete") is False:
            parts.append(
                f"Bootstrap incomplete ({steering.get('bootstrap_placeholder_count', '?')} template phrase(s) remain)."
            )
            try:
                from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import build_bootstrap_fill_plan
                from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence

                root = steering.get("workspace")
                if root:
                    path = steering.get("roadmap_path")
                    text = ""
                    if path:
                        try:
                            text = Path(str(path)).read_text(encoding="utf-8", errors="replace")
                        except OSError:
                            pass
                    evidence = gather_evidence(root, tier="light", roadmap_text=text)
                    plan = build_bootstrap_fill_plan(roadmap_text=text, evidence=evidence)
                    from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import format_bootstrap_fill_hint

                    hint = format_bootstrap_fill_hint(plan)
                    if hint:
                        parts.append(hint)
            except Exception:
                pass
        return "\n".join(parts)
    except Exception as exc:
        return (
            "## ROADMAP live steering\n"
            f"Steering unavailable ({type(exc).__name__}) — run `/roadmap cockpit` or `roadmap(action='guide')`."
        )


def build_live_steering_brief(*, workspace: Optional[str] = None) -> dict[str, Any]:
    """Structured live steering for session hooks and joyzoning context."""
    from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

    steering = build_steering_context(workspace=workspace)
    out: dict[str, Any] = {
        "steering_line": format_agent_steering_line(workspace=steering.get("workspace") or workspace) or None,
        **steering,
    }
    if steering.get("bootstrap_complete") is False:
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import attach_bootstrap_steering_fields

        out.update(attach_bootstrap_steering_fields(steering, tier="light"))
    return out
