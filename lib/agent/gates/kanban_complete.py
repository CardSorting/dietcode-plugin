"""Central kanban_complete gate pipeline — JoyZoning, roadmap, quality audit."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class GateLayer:
    name: str
    allowed: bool
    message: Optional[str] = None
    detail: Any = None


@dataclass(frozen=True)
class KanbanCompleteGateResult:
    allowed: bool
    block_message: Optional[str]
    layers: tuple[GateLayer, ...]

    def layer(self, name: str) -> Optional[GateLayer]:
        for layer in self.layers:
            if layer.name == name:
                return layer
        return None


def _resolve_scope(scope_id: Optional[str] = None, args: Any = None) -> str:
    if scope_id and str(scope_id).strip():
        return str(scope_id).strip()
    parsed = args if isinstance(args, dict) else {}
    task_id = parsed.get("task_id") or parsed.get("scope_id")
    if task_id and str(task_id).strip():
        return str(task_id).strip()
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import resolve_scope_id

        return resolve_scope_id(task_id)
    except Exception:
        return "default"


def _eval_joyzoning(scope_id: str) -> GateLayer:
    try:
        from plugins.dietcode.lib.agent.features import is_joyzoning_enabled
        from plugins.dietcode.lib.agent.joyzoning.convergence import require_review_before_complete

        if not is_joyzoning_enabled():
            return GateLayer("joyzoning", True)
        message = require_review_before_complete(scope_id)
        if message:
            return GateLayer("joyzoning", False, message=message)
        return GateLayer("joyzoning", True)
    except Exception as exc:
        from plugins.dietcode.lib.agent.features import is_joyzoning_enabled

        if is_joyzoning_enabled():
            return GateLayer(
                "joyzoning",
                False,
                message=f"Convergence gate unavailable: {exc}",
            )
        return GateLayer("joyzoning", True, detail={"error": str(exc)})


def _eval_roadmap() -> GateLayer:
    try:
        from plugins.dietcode.lib.agent.roadmap.gate import (
            build_roadmap_gate_state,
            require_fresh_checkpoint_before_complete,
        )

        message = require_fresh_checkpoint_before_complete()
        if message:
            detail = None
            try:
                detail = build_roadmap_gate_state()
            except Exception:
                pass
            return GateLayer("roadmap", False, message=message, detail=detail)
        return GateLayer("roadmap", True, detail=build_roadmap_gate_state())
    except ImportError:
        return GateLayer("roadmap", True)
    except Exception as exc:
        return GateLayer("roadmap", True, detail={"error": str(exc)})


def _eval_quality(scope_id: str) -> GateLayer:
    try:
        from plugins.dietcode.lib.agent.audit.quality_gate import (
            explain_quality_gate,
            kanban_complete_allowed as quality_allowed,
        )

        allowed, message, decision = quality_allowed(scope_id)
        detail = explain_quality_gate(scope_id)
        if not allowed and message:
            return GateLayer("quality", False, message=message, detail=detail)
        return GateLayer("quality", True, detail=detail)
    except ImportError:
        return GateLayer("quality", True)
    except Exception as exc:
        return GateLayer("quality", True, detail={"error": str(exc)})


def evaluate_kanban_complete_gates(
    scope_id: Optional[str] = None,
    *,
    args: Any = None,
    evaluate_all: bool = False,
) -> KanbanCompleteGateResult:
    """Evaluate kanban_complete gate tiers in canonical order.

    When ``evaluate_all`` is false (default), evaluation stops at the first
    blocking layer — used by pre_tool_call enforcement. Diagnostic surfaces
    pass ``evaluate_all=True`` to collect every layer.
    """
    scope = _resolve_scope(scope_id, args)
    layers: list[GateLayer] = []
    block_message: Optional[str] = None

    for evaluator in (
        lambda: _eval_joyzoning(scope),
        _eval_roadmap,
        lambda: _eval_quality(scope),
    ):
        layer = evaluator()
        layers.append(layer)
        if not layer.allowed and block_message is None:
            block_message = layer.message
            if not evaluate_all:
                break

    allowed = all(layer.allowed for layer in layers)
    if not allowed and block_message is None:
        block_message = next(
            (layer.message for layer in layers if not layer.allowed and layer.message),
            "kanban_complete blocked",
        )

    return KanbanCompleteGateResult(
        allowed=allowed,
        block_message=None if allowed else block_message,
        layers=tuple(layers),
    )


def first_block_message(
    scope_id: Optional[str] = None,
    *,
    args: Any = None,
) -> Optional[str]:
    """Return the first blocking message for kanban_complete, if any."""
    return evaluate_kanban_complete_gates(scope_id, args=args).block_message


def kanban_complete_allowed(
    scope_id: Optional[str] = None,
    *,
    args: Any = None,
) -> bool:
    return evaluate_kanban_complete_gates(scope_id, args=args).allowed


def gate_layers_payload(result: KanbanCompleteGateResult) -> dict[str, Any]:
    """Structured gate diagnostics for tools and explain surfaces."""
    payload: dict[str, Any] = {
        "kanban_complete_allowed": result.allowed,
        "kanban_complete_block_reason": result.block_message,
        "layers": {},
    }
    for layer in result.layers:
        entry: dict[str, Any] = {
            "allowed": layer.allowed,
            "message": layer.message,
        }
        if layer.detail is not None:
            entry["detail"] = layer.detail
        payload["layers"][layer.name] = entry
    quality = result.layer("quality")
    if quality and isinstance(quality.detail, dict):
        payload["quality_gate"] = quality.detail
    roadmap = result.layer("roadmap")
    if roadmap and isinstance(roadmap.detail, dict):
        payload["roadmap_gate"] = roadmap.detail
    return payload
