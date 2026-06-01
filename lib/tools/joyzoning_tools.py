"""JoyZoning — first-class governed-work primitive for Hermes agents.

Single entry point ``joyzoning`` wraps convergence, mutation lifecycle, and
JSDP context. Granular ``convergence_*`` / ``mutation_*`` tools remain for
explicit calls; prefer ``joyzoning`` when unsure.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from tools.registry import registry, tool_error

_ACTIONS = frozenset({
    "context",
    "doctor",
    "status",
    "begin",
    "patch",
    "verify",
    "request_review",
    "events",
    "role_context",
    "validate_handoff",
})


def _joyzoning_enabled() -> bool:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config
        return get_joyzoning_config().enabled
    except Exception:
        return False


def joyzoning(
    action: str,
    *,
    goal: str = "",
    mutation_id: str = "",
    summary: str = "",
    report: str = "",
    passed: bool = True,
    scope_id: str = None,
    since: float = 0.0,
    limit: int = 50,
    text: str = "",
) -> str:
    """Unified JoyZoning primitive — governed mutation lifecycle."""
    act = (action or "").strip().lower()
    if act not in _ACTIONS:
        return tool_error(
            f"Unknown action {action!r}. Use one of: {', '.join(sorted(_ACTIONS))}"
        )

    if act == "context":
        from plugins.dietcode.lib.agent.joyzoning.workflow import build_operational_context
        return json.dumps(build_operational_context(scope_id=scope_id))

    if act == "doctor":
        return json.dumps(_joyzoning_doctor(scope_id=scope_id))

    if act == "status":
        from plugins.dietcode.lib.tools.convergence_tools import convergence_status
        return convergence_status(scope_id=scope_id)

    if act == "begin":
        from plugins.dietcode.lib.tools.convergence_tools import mutation_begin
        return mutation_begin(goal=goal, scope_id=scope_id)

    if act == "patch":
        from plugins.dietcode.lib.tools.convergence_tools import mutation_record_patch
        return mutation_record_patch(
            mutation_id=mutation_id,
            summary=summary,
            scope_id=scope_id,
        )

    if act == "verify":
        from plugins.dietcode.lib.tools.convergence_tools import mutation_verify
        return mutation_verify(
            mutation_id=mutation_id,
            report=report,
            passed=passed,
            scope_id=scope_id,
        )

    if act == "request_review":
        from plugins.dietcode.lib.tools.convergence_tools import convergence_request_review
        return convergence_request_review(summary=summary, scope_id=scope_id)

    if act == "events":
        from plugins.dietcode.lib.tools.convergence_tools import runtime_events_tail
        return runtime_events_tail(since=since, scope_id=scope_id, limit=limit)

    if act == "role_context":
        from plugins.dietcode.lib.tools.convergence_tools import jsdp_role_context
        return jsdp_role_context(scope_id=scope_id)

    if act == "validate_handoff":
        from plugins.dietcode.lib.tools.convergence_tools import jsdp_validate_handoff
        return jsdp_validate_handoff(text=text)

    return tool_error("unreachable")


def _joyzoning_doctor(*, scope_id: Optional[str] = None) -> dict[str, Any]:
    from plugins.dietcode.lib.agent.joyzoning.doctor import run_checks
    return run_checks(scope_id=scope_id)


# ─── Registration ───

registry.register(
    name="joyzoning",
    toolset="joyzoning",
    schema={
        "name": "joyzoning",
        "description": (
            "JoyZoning governed-work primitive. Start with action=context. "
            "Lifecycle: begin → patch → verify → request_review → convergence_mark_converged → kanban_complete. "
            "Hermes owns execution state; call convergence_mark_converged after operator review."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": sorted(_ACTIONS),
                    "description": (
                        "context=where am I; doctor=health; status=convergence; "
                        "begin|patch|verify|request_review=lifecycle; events=journal tail; "
                        "role_context|validate_handoff=JSDP; "
                        "rolling horizon=use jsdp tool (prepare/commit/step), not joyzoning"
                    ),
                },
                "goal": {"type": "string", "description": "Mutation goal (action=begin)"},
                "mutation_id": {"type": "string", "description": "Mutation id (patch/verify)"},
                "summary": {"type": "string", "description": "Patch or review summary"},
                "report": {"type": "string", "description": "Verification report (action=verify)"},
                "passed": {"type": "boolean", "default": True},
                "scope_id": {"type": "string", "description": "Override scope (default: kanban env)"},
                "since": {"type": "number", "description": "Events tail unix timestamp"},
                "limit": {"type": "integer", "default": 50},
                "text": {"type": "string", "description": "Handoff text (validate_handoff)"},
            },
            "required": ["action"],
        },
    },
    handler=lambda args, **kw: joyzoning(
        action=args.get("action", ""),
        goal=args.get("goal", ""),
        mutation_id=args.get("mutation_id", ""),
        summary=args.get("summary", ""),
        report=args.get("report", ""),
        passed=args.get("passed", True),
        scope_id=args.get("scope_id"),
        since=args.get("since", 0.0),
        limit=args.get("limit", 50),
        text=args.get("text", ""),
    ),
    check_fn=_joyzoning_enabled,
    emoji="🏛",
)
