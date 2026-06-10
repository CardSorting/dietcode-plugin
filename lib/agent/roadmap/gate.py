"""Roadmap steering gates — kanban_complete enforcement and explain-gate diagnostics."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config, resolve_workspace_root
from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence
from plugins.dietcode.lib.agent.roadmap.freshness import assess_checkpoint_freshness
from plugins.dietcode.lib.agent.roadmap.schema import validate_roadmap_content
from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state

GateCheck = dict[str, Any]


def _roadmap_path(workspace: str) -> Path:
    return Path(workspace) / "ROADMAP.md"


def collect_gate_inputs(
    *,
    workspace: Optional[str] = None,
    evidence: Optional[dict[str, Any]] = None,
    roadmap_text: Optional[str] = None,
    validation: Any = None,
) -> dict[str, Any]:
    """Gather validation and freshness signals for gate evaluation."""
    cfg = get_roadmap_config()
    root = resolve_workspace_root(workspace)
    path = _roadmap_path(root)
    text = roadmap_text
    core = None
    if text is None and validation is None:
        from plugins.dietcode.lib.agent.roadmap.roadmap_core import read_roadmap_core

        core = read_roadmap_core(root)
        text = core.text
        validation = core.validation
    elif text is None:
        text = ""
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
    elif not text and evidence and evidence.get("_roadmap_text"):
        text = str(evidence["_roadmap_text"])

    if evidence is None:
        evidence = (
            gather_evidence(root, include_code_soup=False, tier="light", roadmap_text=text or None)
            if cfg.enabled
            else {}
        )

    roadmap = evidence.get("roadmap") or {}
    if validation is None:
        validation = validate_roadmap_content(text) if text else None
    freshness = assess_checkpoint_freshness(
        recent_checkpoint_date=roadmap.get("recent_checkpoint_date"),
        git_commits=(evidence.get("git") or {}).get("recent_commits") or [],
        schema_valid=validation.valid if validation else None,
        stale_days=cfg.stale_checkpoint_days,
    )
    ws_state = read_state(root)

    return {
        "config": cfg,
        "workspace": root,
        "roadmap_path": str(path),
        "roadmap_present": path.is_file(),
        "validation": validation.to_dict() if validation else None,
        "freshness": freshness,
        "workspace_state": ws_state or None,
    }


def _check_enabled(_: dict[str, Any], inputs: dict[str, Any]) -> bool:
    return bool((inputs.get("config") or get_roadmap_config()).enabled)


def _check_roadmap_present(_: dict[str, Any], inputs: dict[str, Any]) -> bool:
    return bool(inputs.get("roadmap_present"))


def _check_schema_valid(_: dict[str, Any], inputs: dict[str, Any]) -> bool:
    validation = inputs.get("validation") or {}
    if not inputs.get("roadmap_present"):
        return True
    return validation.get("valid") is True


def _check_checkpoint_fresh(_: dict[str, Any], inputs: dict[str, Any]) -> bool:
    if not inputs.get("roadmap_present"):
        return True
    return not bool((inputs.get("freshness") or {}).get("stale"))


def _check_skill_installed(_: dict[str, Any], inputs: dict[str, Any]) -> bool:
    root = inputs.get("workspace") or resolve_workspace_root()
    skill = (
        Path(root)
        / "optional-skills"
        / "dietcode"
        / "auto-rolling-roadmap"
        / "SKILL.md"
    )
    return skill.is_file()


def _check_validation_current(_: dict[str, Any], inputs: dict[str, Any]) -> bool:
    if not inputs.get("roadmap_present"):
        return True
    ws = inputs.get("workspace_state") or {}
    return not bool(ws.get("validation_pending"))


_GATE_CHECKS: tuple[GateCheck, ...] = (
    {
        "id": "roadmap_enabled",
        "label": "Roadmap feature enabled",
        "is_open": _check_enabled,
        "why_closed": "dietcode.roadmap.enabled is false",
        "fix": "Set dietcode.roadmap.enabled: true in Hermes config",
        "safe": True,
        "blocks_kanban_complete": False,
    },
    {
        "id": "roadmap_present",
        "label": "ROADMAP.md exists",
        "is_open": _check_roadmap_present,
        "why_closed": "No steering surface at workspace root",
        "fix": "roadmap(action='checkpoint') to bootstrap ROADMAP.md",
        "safe": True,
        "blocks_kanban_complete": False,
    },
    {
        "id": "workspace_skill_installed",
        "label": "Auto-rolling roadmap skill installed",
        "is_open": _check_skill_installed,
        "why_closed": "optional-skills/dietcode/auto-rolling-roadmap/SKILL.md missing",
        "fix": "roadmap(action='doctor') or reload session (auto_install_skills)",
        "safe": True,
        "blocks_kanban_complete": False,
    },
    {
        "id": "schema_valid",
        "label": "ROADMAP.md schema valid",
        "is_open": _check_schema_valid,
        "why_closed": "Schema validation failed — checkpoint pass incomplete",
        "fix": "Edit ROADMAP.md, then roadmap(action='validate')",
        "safe": True,
        "blocks_kanban_complete": False,
    },
    {
        "id": "validation_current",
        "label": "ROADMAP.md validated after last edit",
        "is_open": _check_validation_current,
        "why_closed": "ROADMAP.md changed since last schema validation",
        "fix": "roadmap(action='validate') before kanban_complete",
        "safe": True,
        "blocks_kanban_complete": True,
    },
    {
        "id": "checkpoint_fresh",
        "label": "Recent checkpoint fresh",
        "is_open": _check_checkpoint_fresh,
        "why_closed": "Checkpoint stale vs project activity or missing date",
        "fix": "roadmap(action='checkpoint', context='stale refresh')",
        "safe": True,
        "blocks_kanban_complete": True,
    },
)


def evaluate_gate_checks(inputs: dict[str, Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Return (closed_gates, open_gate_ids) in kernel explain-gate shape."""
    closed: list[dict[str, Any]] = []
    open_ids: list[str] = []
    for check in _GATE_CHECKS:
        is_open_fn: Callable[..., bool] = check["is_open"]
        if is_open_fn(check, inputs):
            open_ids.append(str(check["id"]))
        else:
            closed.append({
                "id": check["id"],
                "label": check["label"],
                "why": check["why_closed"],
                "fix": check["fix"],
                "safe_to_apply": bool(check["safe"]),
                "blocks_kanban_complete": bool(check.get("blocks_kanban_complete")),
            })
    return closed, open_ids


def _blocking_closed_gates(
    closed: list[dict[str, Any]],
    *,
    cfg: Any,
) -> list[dict[str, Any]]:
    """Gates that block kanban_complete given current config."""
    blocking: list[dict[str, Any]] = []
    for gate in closed:
        gate_id = str(gate.get("id") or "")
        if gate_id == "schema_valid" and cfg.block_kanban_on_invalid_schema:
            blocking.append(gate)
            continue
        if not gate.get("blocks_kanban_complete"):
            continue
        if gate_id == "checkpoint_fresh" and not cfg.warn_on_stale_before_complete:
            continue
        if gate_id == "validation_current" and not cfg.block_kanban_on_validation_pending:
            continue
        blocking.append(gate)
    return blocking


def gate_state_from_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    """Kernel-style gate snapshot from precomputed inputs."""
    cfg = inputs.get("config") or get_roadmap_config()
    closed, open_ids = evaluate_gate_checks(inputs)
    freshness = inputs.get("freshness") or {}
    validation = inputs.get("validation") or {}
    ws_state = inputs.get("workspace_state") or {}

    blocking = _blocking_closed_gates(closed, cfg=cfg)
    kanban_allowed = not cfg.enabled or not blocking

    if ws_state.get("validation_pending"):
        preferred = "roadmap(action='validate')"
    elif freshness.get("stale"):
        preferred = "roadmap(action='checkpoint')"
    elif validation.get("valid") is False:
        preferred = "roadmap(action='validate')"
    else:
        preferred = "roadmap(action='guide')"

    return {
        "enabled": cfg.enabled,
        "workspace": inputs.get("workspace"),
        "roadmap_present": inputs.get("roadmap_present"),
        "schema_valid": validation.get("valid"),
        "schema_complete": validation.get("schema_complete"),
        "checkpoint_fresh": not bool(freshness.get("stale")),
        "checkpoint_stale": bool(freshness.get("stale")),
        "stale_reason": freshness.get("reason"),
        "stale_summary": freshness.get("summary"),
        "kanban_complete_allowed": kanban_allowed,
        "closed_gates": closed,
        "open_gates": open_ids,
        "closed_gate_count": len(closed),
        "blocking_gate_count": len(blocking),
        "blocking_gates": blocking,
        "checkpoint_allowed": kanban_allowed,
        "preferred_command": preferred,
        "validation_pending": bool(ws_state.get("validation_pending")),
        "workspace_state": ws_state or None,
    }


def build_roadmap_gate_state(
    *,
    workspace: Optional[str] = None,
    inputs: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Kernel-style gate snapshot for cockpit, explain_gate, and pre_tool_call."""
    if inputs is None:
        from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot

        return get_workspace_snapshot(workspace, tier="light").gate_state
    return gate_state_from_inputs(inputs)


def require_fresh_checkpoint_before_complete(*, workspace: Optional[str] = None) -> Optional[str]:
    """Return block message when kanban_complete violates roadmap steering gates."""
    cfg = get_roadmap_config()
    if not cfg.enabled:
        return None

    state = build_roadmap_gate_state(workspace=workspace)
    if state.get("kanban_complete_allowed"):
        return None

    closed = state.get("closed_gates") or []
    blocking = _blocking_closed_gates(closed, cfg=cfg)
    if blocking:
        first = blocking[0]
        return (
            f"ROADMAP steering gate closed ({first.get('label')}) — {first.get('why')}. "
            f"Fix: {first.get('fix')}. Diagnostic: /roadmap explain-gate"
        )

    return "ROADMAP steering gate closed — /roadmap explain-gate"
