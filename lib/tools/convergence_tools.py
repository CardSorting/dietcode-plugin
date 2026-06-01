"""JoyZoning convergence & mutation lifecycle tools (Hermes runtime authority)."""
from __future__ import annotations

import json
import time

from tools.registry import registry, tool_error


def _joyzoning_enabled() -> bool:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config
        return get_joyzoning_config().enabled
    except Exception:
        return False


def convergence_status(scope_id: str = None) -> str:
    from plugins.dietcode.lib.agent.joyzoning.config import resolve_scope_id
    from plugins.dietcode.lib.agent.joyzoning.convergence import require_review_before_complete
    from plugins.dietcode.lib.agent.joyzoning.journal import get_journal
    from plugins.dietcode.lib.agent.joyzoning.workflow import _resolve_cluster

    sid = resolve_scope_id(scope_id)
    state, anchor, cluster = _resolve_cluster(sid)
    record = get_journal().get_convergence(anchor)
    gate = require_review_before_complete(anchor)
    return json.dumps({
        "success": True,
        "scope_id": sid,
        "anchor_scope_id": anchor,
        "scope_cluster": cluster,
        "state": state.value,
        "kanban_complete_allowed": gate is None,
        "kanban_complete_block_reason": gate,
        "record": record,
        "active_mutation": get_journal().get_active_mutation(anchor),
    })


def mutation_begin(goal: str, scope_id: str = None) -> str:
    from plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle import begin_mutation
    if not goal or not goal.strip():
        return tool_error("goal is required")
    return json.dumps(begin_mutation(goal.strip(), scope_id=scope_id))


def mutation_record_patch(
    mutation_id: str,
    summary: str = "",
    scope_id: str = None,
) -> str:
    from plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle import record_patch
    if not mutation_id:
        return tool_error("mutation_id is required")
    return json.dumps(record_patch(mutation_id, summary=summary.strip(), scope_id=scope_id))


def mutation_verify(
    mutation_id: str,
    report: str,
    passed: bool = True,
    scope_id: str = None,
) -> str:
    from plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle import record_verification
    if not mutation_id:
        return tool_error("mutation_id is required")
    if not report or not report.strip():
        return tool_error("report is required")
    return json.dumps(record_verification(
        mutation_id,
        report=report.strip(),
        passed=bool(passed),
        scope_id=scope_id,
    ))


def convergence_request_review(summary: str, scope_id: str = None) -> str:
    from plugins.dietcode.lib.agent.joyzoning.mutation_lifecycle import request_review
    if not summary or not summary.strip():
        return tool_error("summary is required")
    return json.dumps(request_review(summary.strip(), scope_id=scope_id))


def convergence_mark_converged(summary: str = "", scope_id: str = None) -> str:
    """Mark scope converged after operator review."""
    from plugins.dietcode.lib.agent.joyzoning.convergence import ConvergenceState, transition_convergence
    return json.dumps(transition_convergence(
        ConvergenceState.CONVERGED,
        scope_id=scope_id,
        summary=summary or "converged",
        force=True,
    ))


def runtime_events_tail(
    since: float = 0.0,
    scope_id: str = None,
    limit: int = 50,
) -> str:
    from plugins.dietcode.lib.agent.joyzoning.config import resolve_scope_id
    from plugins.dietcode.lib.agent.joyzoning.runtime_events import format_runtime_stream
    from plugins.dietcode.lib.agent.joyzoning.journal import get_journal

    sid = resolve_scope_id(scope_id) if scope_id else None
    since_ts = float(since or 0.0)
    if since_ts <= 0:
        since_ts = time.time() - 3600
    events = get_journal().list_events(since=since_ts, scope_id=sid, limit=limit)
    return json.dumps({
        "success": True,
        "scope_id": sid,
        "events": format_runtime_stream(events),
    })


def jsdp_validate_handoff(text: str) -> str:
    from plugins.dietcode.lib.agent.joyzoning.jsdp_protocol import validate_handoff_sections
    if not text or not text.strip():
        return tool_error("text is required")
    return json.dumps(validate_handoff_sections(text))


def jsdp_role_context(scope_id: str = None) -> str:
    from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, resolve_scope_id
    from plugins.dietcode.lib.agent.joyzoning.jsdp_protocol import role_context_prompt
    cfg = get_joyzoning_config()
    if not cfg.jsdp_enabled and not cfg.jsdp_role:
        return tool_error("JSDP not enabled — set joyzoning.jsdp.enabled or JOYZONING_JSDP_ROLE")
    role = cfg.jsdp_role or "unspecified"
    return json.dumps({
        "success": True,
        "scope_id": resolve_scope_id(scope_id),
        "role": role,
        "chain_id": cfg.jsdp_chain_id,
        "prompt": role_context_prompt(role, cfg.jsdp_chain_id),
    })


# ─── Registration ───

registry.register(
    name="convergence_status",
    toolset="joyzoning",
    schema={
        "name": "convergence_status",
        "description": "Read Hermes-owned convergence state for the active scope (not habitat UI state).",
        "parameters": {
            "type": "object",
            "properties": {"scope_id": {"type": "string"}},
        },
    },
    handler=lambda args, **kw: convergence_status(scope_id=args.get("scope_id")),
    check_fn=_joyzoning_enabled,
    emoji="◎",
)

registry.register(
    name="mutation_begin",
    toolset="joyzoning",
    schema={
        "name": "mutation_begin",
        "description": "Start a bounded mutation scope: plan → patch → verify → converge.",
        "parameters": {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "scope_id": {"type": "string"},
            },
            "required": ["goal"],
        },
    },
    handler=lambda args, **kw: mutation_begin(
        goal=args.get("goal", ""),
        scope_id=args.get("scope_id"),
    ),
    check_fn=_joyzoning_enabled,
    emoji="🧬",
)

registry.register(
    name="mutation_record_patch",
    toolset="joyzoning",
    schema={
        "name": "mutation_record_patch",
        "description": "Record active patching on a mutation scope after substantive code edits.",
        "parameters": {
            "type": "object",
            "properties": {
                "mutation_id": {"type": "string"},
                "summary": {"type": "string"},
                "scope_id": {"type": "string"},
            },
            "required": ["mutation_id"],
        },
    },
    handler=lambda args, **kw: mutation_record_patch(
        mutation_id=args.get("mutation_id", ""),
        summary=args.get("summary", ""),
        scope_id=args.get("scope_id"),
    ),
    check_fn=_joyzoning_enabled,
    emoji="🔧",
)

registry.register(
    name="mutation_verify",
    toolset="joyzoning",
    schema={
        "name": "mutation_verify",
        "description": "Record verification results for a mutation scope (tests, checks, review prep).",
        "parameters": {
            "type": "object",
            "properties": {
                "mutation_id": {"type": "string"},
                "report": {"type": "string"},
                "passed": {"type": "boolean", "default": True},
                "scope_id": {"type": "string"},
            },
            "required": ["mutation_id", "report"],
        },
    },
    handler=lambda args, **kw: mutation_verify(
        mutation_id=args.get("mutation_id", ""),
        report=args.get("report", ""),
        passed=args.get("passed", True),
        scope_id=args.get("scope_id"),
    ),
    check_fn=_joyzoning_enabled,
    emoji="✓",
)

registry.register(
    name="convergence_request_review",
    toolset="joyzoning",
    schema={
        "name": "convergence_request_review",
        "description": "Move scope to ready_for_review — stop before kanban_complete; operator reviews.",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "scope_id": {"type": "string"},
            },
            "required": ["summary"],
        },
    },
    handler=lambda args, **kw: convergence_request_review(
        summary=args.get("summary", ""),
        scope_id=args.get("scope_id"),
    ),
    check_fn=_joyzoning_enabled,
    emoji="👁",
)

registry.register(
    name="runtime_events_tail",
    toolset="joyzoning",
    schema={
        "name": "runtime_events_tail",
        "description": "Tail Hermes execution journal events (replay/observability).",
        "parameters": {
            "type": "object",
            "properties": {
                "since": {"type": "number"},
                "scope_id": {"type": "string"},
                "limit": {"type": "integer", "default": 50},
            },
        },
    },
    handler=lambda args, **kw: runtime_events_tail(
        since=args.get("since", 0.0),
        scope_id=args.get("scope_id"),
        limit=args.get("limit", 50),
    ),
    check_fn=_joyzoning_enabled,
    emoji="📡",
)

registry.register(
    name="jsdp_validate_handoff",
    toolset="joyzoning",
    schema={
        "name": "jsdp_validate_handoff",
        "description": "Validate JSDP required handoff sections in deliverable text.",
        "parameters": {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
    },
    handler=lambda args, **kw: jsdp_validate_handoff(text=args.get("text", "")),
    check_fn=_joyzoning_enabled,
    emoji="📋",
)

registry.register(
    name="convergence_mark_converged",
    toolset="joyzoning",
    schema={
        "name": "convergence_mark_converged",
        "description": "Mark CONVERGED after operator review (use after request_review gate).",
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "scope_id": {"type": "string"},
            },
        },
    },
    handler=lambda args, **kw: convergence_mark_converged(
        summary=args.get("summary", ""),
        scope_id=args.get("scope_id"),
    ),
    check_fn=_joyzoning_enabled,
    emoji="✅",
)

registry.register(
    name="jsdp_role_context",
    toolset="joyzoning",
    schema={
        "name": "jsdp_role_context",
        "description": "Load JSDP bounded-role context for the configured chain role.",
        "parameters": {
            "type": "object",
            "properties": {"scope_id": {"type": "string"}},
        },
    },
    handler=lambda args, **kw: jsdp_role_context(scope_id=args.get("scope_id")),
    check_fn=_joyzoning_enabled,
    emoji="🔗",
)
