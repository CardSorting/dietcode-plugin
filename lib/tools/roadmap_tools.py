"""Auto-rolling roadmap checkpoint — first-class native steering primitive."""
from __future__ import annotations

import json
from typing import Any, Optional

from tools.registry import registry, tool_error

_ACTIONS = frozenset({
    "guide",
    "checkpoint",
    "evidence",
    "status",
    "doctor",
    "cockpit",
    "validate",
    "template",
    "apply_bootstrap_fill",
    "progress",
    "watch",
    "last_error",
    "explain_stale",
    "explain_gate",
})
_TOOLSET = "roadmap"


def _roadmap_available() -> bool:
    from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import probe_roadmap_available

    return probe_roadmap_available()


def _finish_payload(act: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize successful roadmap tool responses with clarity envelope."""
    from plugins.dietcode.lib.agent.roadmap.phase_guide import clarity_envelope

    enriched = {
        **payload,
        "action": payload.get("action") or act,
        "success": payload.get("success", payload.get("ok", True)),
        "ok": payload.get("ok", payload.get("success", True)),
    }
    return clarity_envelope(enriched)


def _record_error_progress(action: str, envelope: dict[str, Any]) -> None:
    """Record failures only — successful tool calls are journaled in roadmap_hooks."""
    try:
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config
        from plugins.dietcode.lib.agent.roadmap.progress import emit_progress

        if not get_roadmap_config().progress_enabled:
            return
        emit_progress(
            f"roadmap.{action}",
            action=action,
            payload={"error": envelope.get("message") or envelope.get("code")},
            success=False,
        )
    except Exception:
        pass


def _dispatch(
    act: str,
    *,
    context: str = "",
    user_request: str = "",
    workspace: Optional[str] = None,
) -> dict[str, Any]:
    from plugins.dietcode.lib.agent.roadmap import evidence as evidence_mod
    from plugins.dietcode.lib.agent.roadmap.cockpit import build_cockpit_payload
    from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace_root
    from plugins.dietcode.lib.agent.roadmap.doctor import run_checks
    from plugins.dietcode.lib.agent.roadmap.freshness import assess_checkpoint_freshness, format_explain_stale_report
    from plugins.dietcode.lib.agent.roadmap.progress import (
        build_progress_snapshot,
        format_progress_report,
        format_watch_report,
        read_last_error,
        read_tail,
    )
    from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import (
        apply_bootstrap_fill_brief,
        checkpoint_brief,
        operational_status,
        status_snapshot,
        template_brief,
        validate_roadmap,
    )
    from plugins.dietcode.lib.agent.roadmap.explain_gate import build_explain_gate_payload
    from plugins.dietcode.lib.agent.roadmap.skill_install import ensure_workspace_skills

    if act == "guide":
        return operational_status(workspace=workspace, context_hint=context)

    if act == "status":
        return status_snapshot(workspace=workspace)

    if act == "evidence":
        root = resolve_workspace_root(workspace)
        bundle = evidence_mod.gather_evidence(
            root,
            context_hint=context,
            user_request=user_request,
        )
        from plugins.dietcode.lib.agent.roadmap.bootstrap_fill import enrich_payload_with_bootstrap_context

        return _finish_payload(
            act,
            enrich_payload_with_bootstrap_context(
                {**bundle, "action": "evidence"},
                evidence=bundle,
            ),
        )

    if act == "checkpoint":
        return checkpoint_brief(
            workspace=workspace,
            context=context,
            user_request=user_request,
        )

    if act == "doctor":
        root = resolve_workspace_root(workspace)
        install = ensure_workspace_skills(root)
        from plugins.dietcode.lib.agent.roadmap.doctor import format_doctor_report

        report = run_checks(workspace=root)
        report["skill_install"] = install
        report["action"] = "doctor"
        report["report"] = format_doctor_report(workspace=root)
        return _finish_payload(act, report)

    if act == "cockpit":
        return build_cockpit_payload(workspace=workspace)

    if act == "validate":
        return validate_roadmap(workspace=workspace)

    if act == "template":
        return template_brief(workspace=workspace)

    if act == "apply_bootstrap_fill":
        return apply_bootstrap_fill_brief(workspace=workspace, context=context)

    if act == "progress":
        root = resolve_workspace_root(workspace)
        tail = context.strip().lower() in {"--tail", "tail"}
        timeline = "--timeline" in context.lower()
        current_snapshot = "--current" in context.lower()
        last = 5
        for token in context.split():
            if token.isdigit():
                last = int(token)
        if current_snapshot:
            return _finish_payload(
                act,
                {"action": "progress", **build_progress_snapshot(workspace=root)},
            )
        if tail:
            return _finish_payload(act, {"action": "progress", "events": read_tail(lines=last)})
        return _finish_payload(
            act,
            {
                "action": "progress",
                "report": format_progress_report(
                    timeline=timeline,
                    last=last,
                    workspace=root,
                ),
            },
        )

    if act == "watch":
        root = resolve_workspace_root(workspace)
        return _finish_payload(
            act,
            {
                "action": "watch",
                "report": format_watch_report(workspace=root),
                "snapshot": build_progress_snapshot(workspace=root),
            },
        )

    if act == "last_error":
        err = read_last_error()
        return _finish_payload(
            act,
            {
                "action": "last_error",
                "error": err,
                "present": bool(err),
                "success": not bool(err),
                "ok": not bool(err),
            },
        )

    if act == "explain_gate":
        return build_explain_gate_payload(workspace=workspace)

    if act == "explain_stale":
        from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot
        from plugins.dietcode.lib.agent.roadmap.steering_context import enrich_payload_with_steering

        root = resolve_workspace_root(workspace)
        snap = get_workspace_snapshot(root, tier="light")
        fresh = snap.gate_inputs.get("freshness") or assess_checkpoint_freshness(
            recent_checkpoint_date=(snap.evidence.get("roadmap") or {}).get("recent_checkpoint_date"),
            git_commits=((snap.evidence.get("git") or {}).get("recent_commits") or []),
            schema_valid=snap.validation.valid if snap.validation else None,
        )
        from plugins.dietcode.lib.agent.roadmap.steering_context import build_steering_context

        steering = build_steering_context(workspace=root)
        return _finish_payload(
            act,
            enrich_payload_with_steering(
                {
                    "action": "explain_stale",
                    "freshness": fresh,
                    "checkpoint_freshness": fresh,
                    "report": format_explain_stale_report(
                        fresh,
                        steering_brief=steering.get("steering_brief"),
                    ),
                    "success": not bool(fresh.get("stale")),
                    "ok": not bool(fresh.get("stale")),
                },
                workspace=root,
            ),
        )

    raise ValueError(f"unreachable action {act!r}")


def roadmap(
    action: str,
    *,
    context: str = "",
    user_request: str = "",
    workspace: Optional[str] = None,
) -> str:
    """Auto-rolling roadmap checkpoint — native project steering primitive."""
    act = (action or "").strip().lower()
    if act not in _ACTIONS:
        from plugins.dietcode.lib.agent.roadmap.errors import as_tool_error, error_envelope

        return as_tool_error(
            error_envelope(
                code="unknown_action",
                message=f"Unknown action {action!r}",
                action=act,
                safe_to_retry=True,
            )
        )

    try:
        payload = _dispatch(
            act,
            context=context,
            user_request=user_request,
            workspace=workspace,
        )
        return json.dumps(payload, ensure_ascii=False)
    except ImportError as exc:
        from plugins.dietcode.lib.agent.roadmap.errors import as_tool_error, error_envelope

        return as_tool_error(
            error_envelope(code="module_unavailable", message=str(exc), action=act, safe_to_retry=False)
        )
    except Exception as exc:
        from plugins.dietcode.lib.agent.roadmap.config import RoadmapWorkspaceError
        from plugins.dietcode.lib.agent.roadmap.errors import as_tool_error, error_envelope, from_exception

        if isinstance(exc, RoadmapWorkspaceError):
            envelope = error_envelope(
                code="workspace_unresolved",
                message=str(exc),
                action=act,
                safe_to_retry=False,
            )
        else:
            envelope = from_exception(exc, action=act)
        _record_error_progress(act, envelope)
        return as_tool_error(envelope)


def roadmap_checkpoint(**kwargs) -> str:
    """Alias for roadmap — preferred name in governed long-horizon sessions."""
    return roadmap(**kwargs)


_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": sorted(_ACTIONS),
            "description": (
                "guide=phase; checkpoint=evidence+algorithm; validate=schema; cockpit=summary; "
                "apply_bootstrap_fill=evidence autofill; progress/watch/last_error/explain_stale/explain_gate=operator observability"
            ),
        },
        "context": {
            "type": "string",
            "description": "Optional context; progress accepts --timeline, --tail, or line count",
        },
        "user_request": {
            "type": "string",
            "description": "Optional user request to include in evidence",
        },
        "workspace": {
            "type": "string",
            "description": "Auto-detected workspace — override only if needed",
        },
    },
    "required": ["action"],
}

registry.register(
    name="roadmap",
    toolset=_TOOLSET,
    schema={
        "name": "roadmap",
        "description": (
            "First-class auto-rolling roadmap checkpoint. Native project steering surface (ROADMAP.md). "
            "JoyZoning context includes roadmap_checkpoint brief. Progress at ~/.dietcode/session/roadmap-progress.jsonl. "
            "Writes to ROADMAP.md receive validate nudges. Skill: auto-rolling-roadmap."
        ),
        "parameters": _SCHEMA,
    },
    handler=lambda args, **kw: roadmap(
        action=args.get("action", ""),
        context=args.get("context", ""),
        user_request=args.get("user_request", ""),
        workspace=args.get("workspace"),
    ),
    check_fn=_roadmap_available,
    emoji="🗺️",
)

registry.register(
    name="roadmap_checkpoint",
    toolset=_TOOLSET,
    schema={
        "name": "roadmap_checkpoint",
        "description": "Alias for roadmap — guide | checkpoint | validate | cockpit | progress | watch.",
        "parameters": _SCHEMA,
    },
    handler=lambda args, **kw: roadmap(
        action=args.get("action", ""),
        context=args.get("context", ""),
        user_request=args.get("user_request", ""),
        workspace=args.get("workspace"),
    ),
    check_fn=_roadmap_available,
    emoji="🗺️",
)
