"""JSDP harness — autonomous tool (operators need zero Hermes config)."""
from __future__ import annotations

import json
from typing import Optional

from tools.registry import registry, tool_error

# Primary names (memorable). Technical names remain as aliases.
_ACTIONS = frozenset({"guide", "start", "apply", "advance"})
_LEGACY_MAP = {
    "status": "guide",
    "prepare": "start",
    "commit": "apply",
    "step": "advance",
    "hint": "guide",
    "export": "start",
    "prompt": "start",
    "write_proposal": "apply",
    "validate": "apply",
    "diff": "apply",
    "import": "apply",
    "doctor": "guide",
    "next": "advance",
    "verify": "advance",
    "continue": "advance",
}


def _jsdp_available() -> bool:
    from plugins.dietcode.lib.agent.joyzoning.jsdp_autonomous import probe_jsdp_available
    return probe_jsdp_available()


def jsdp(
    action: str,
    *,
    proposal_json: str = "",
    goal: str = "",
    nodes: int = 3,
    force: bool = False,
    workspace: Optional[str] = None,
) -> str:
    """Autonomous JSDP — JoyZoning owns the DAG; Hermes plans 3–5 nodes per cycle."""
    raw = (action or "").strip().lower()
    act = _LEGACY_MAP.get(raw, raw)
    if act not in _ACTIONS:
        return tool_error(
            f"Unknown action {action!r}. Use: start | apply | advance | guide. "
            "No setup — JoyZoning kanban dispatch is enough."
        )

    try:
        from plugins.dietcode.lib.agent.joyzoning import jsdp_autonomous as auto
    except ImportError as exc:
        return tool_error(f"JSDP autonomous module unavailable: {exc}")

    try:
        if act == "guide":
            return json.dumps(auto.operational_status(workspace=workspace))

        if act == "start":
            return json.dumps(
                auto.prepare_planning(workspace=workspace, goal=goal, nodes=nodes)
            )

        if act == "apply":
            if not proposal_json.strip():
                return tool_error(
                    "proposal_json required for apply — call start first, then pass horizon JSON (≤5 nodes)."
                )
            return json.dumps(
                auto.commit_proposal(
                    proposal_json,
                    workspace=workspace,
                    nodes=nodes,
                    force=force,
                )
            )

        if act == "advance":
            return json.dumps(auto.autonomous_step(workspace=workspace))

        return tool_error("unreachable")
    except Exception as exc:
        from plugins.dietcode.lib.agent.joyzoning.jsdp_harness_client import JsdpHarnessError
        if isinstance(exc, JsdpHarnessError):
            return tool_error(str(exc))
        return tool_error(f"jsdp failed: {exc}")


def jsdp_horizon(**kwargs) -> str:
    return jsdp(**kwargs)


registry.register(
    name="jsdp",
    toolset="joyzoning",
    schema={
        "name": "jsdp",
        "description": (
            "Autonomous long-horizon delivery (rolling horizon). Operators: dispatch from JoyZoning only. "
            "Agents: start → apply(proposal_json) → advance (repeat). guide = where am I. "
            "No Hermes yaml, no manual jz paths."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["guide", "start", "apply", "advance"],
                    "description": (
                        "guide=phase + next call; start=session bootstrap + planning context; "
                        "apply=commit ≤5-node horizon JSON; advance=run next harness step"
                    ),
                },
                "proposal_json": {
                    "type": "string",
                    "description": "Horizon JSON (required for apply)",
                },
                "goal": {
                    "type": "string",
                    "description": "Optional init goal if no PROJECT_SPEC.md (start)",
                },
                "nodes": {
                    "type": "integer",
                    "minimum": 3,
                    "maximum": 5,
                    "default": 3,
                },
                "force": {
                    "type": "boolean",
                    "default": False,
                },
                "workspace": {
                    "type": "string",
                    "description": "Auto-detected from kanban — override only if needed",
                },
            },
            "required": ["action"],
        },
    },
    handler=lambda args, **kw: jsdp(
        action=args.get("action", ""),
        proposal_json=args.get("proposal_json", ""),
        goal=args.get("goal", ""),
        nodes=int(args.get("nodes", 3) or 3),
        force=bool(args.get("force", False)),
        workspace=args.get("workspace"),
    ),
    check_fn=_jsdp_available,
    emoji="🧭",
)

registry.register(
    name="jsdp_horizon",
    toolset="joyzoning",
    schema={
        "name": "jsdp_horizon",
        "description": "Alias for jsdp — use start | apply | advance | guide.",
        "parameters": {
            "type": "object",
            "properties": {
                "action": {"type": "string"},
                "proposal_json": {"type": "string"},
                "goal": {"type": "string"},
                "nodes": {"type": "integer", "default": 3},
                "force": {"type": "boolean", "default": False},
                "workspace": {"type": "string"},
            },
            "required": ["action"],
        },
    },
    handler=lambda args, **kw: jsdp(
        action=args.get("action", ""),
        proposal_json=args.get("proposal_json", ""),
        goal=args.get("goal", ""),
        nodes=int(args.get("nodes", 3) or 3),
        force=bool(args.get("force", False)),
        workspace=args.get("workspace"),
    ),
    check_fn=_jsdp_available,
    emoji="🧭",
)
