"""Central DietCode runtime feature flags and config cache control."""
from __future__ import annotations

from typing import Any


def is_joyzoning_enabled() -> bool:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config

        return bool(get_joyzoning_config().enabled)
    except Exception:
        return False


def is_roadmap_enabled() -> bool:
    try:
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config

        return bool(get_roadmap_config().enabled)
    except Exception:
        return False


def is_governance_enabled() -> bool:
    try:
        from plugins.dietcode.lib.agent.governance_exemptions import is_governance_enforcement_enabled

        return bool(is_governance_enforcement_enabled())
    except Exception:
        return False


def is_completion_gate_enabled() -> bool:
    try:
        from plugins.dietcode.lib.agent.audit.config import get_completion_gate_config

        return bool(get_completion_gate_config().enabled)
    except Exception:
        return False


def is_jsdp_enabled() -> bool:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config

        cfg = get_joyzoning_config()
        return bool(cfg.enabled and cfg.jsdp_enabled and cfg.jsdp_role)
    except Exception:
        return False


def is_joyzoning_journal_enabled() -> bool:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config

        cfg = get_joyzoning_config()
        return bool(cfg.enabled and cfg.execution_journal)
    except Exception:
        return False


def features_snapshot() -> dict[str, bool]:
    """Return active runtime feature flags for doctor and contract surfaces."""
    return {
        "joyzoning": is_joyzoning_enabled(),
        "roadmap": is_roadmap_enabled(),
        "governance": is_governance_enabled(),
        "completion_gate": is_completion_gate_enabled(),
        "jsdp": is_jsdp_enabled(),
        "joyzoning_journal": is_joyzoning_journal_enabled(),
    }


def invalidate_all_config_caches() -> None:
    """Bust cached Hermes config reads across DietCode subsystems."""
    for module_path in (
        "plugins.dietcode.lib.agent.joyzoning.config",
        "plugins.dietcode.lib.agent.roadmap.config",
        "plugins.dietcode.lib.agent.audit.config",
    ):
        try:
            import importlib

            mod = importlib.import_module(module_path)
            mod._config_cache = None  # type: ignore[attr-defined]
            mod._config_cache_at = 0.0  # type: ignore[attr-defined]
        except Exception:
            pass
    try:
        from plugins.dietcode.tools_loader import invalidate_load_cache

        invalidate_load_cache()
    except Exception:
        pass


def build_runtime_snapshot(*, scope_id: str | None = None) -> dict[str, Any]:
    """Unified runtime diagnostics — features, hook chains, and gate layers."""
    from plugins.dietcode.hooks import hook_chain_summary
    from plugins.dietcode.lib.agent.gates.kanban_complete import (
        evaluate_kanban_complete_gates,
        gate_layers_payload,
    )

    gate_result = evaluate_kanban_complete_gates(scope_id, evaluate_all=True)
    from plugins.dietcode.lib.agent.config_hub import runtime_config_snapshot

    return {
        "features": features_snapshot(),
        "config": runtime_config_snapshot(),
        "hook_chains": hook_chain_summary(),
        "gates": gate_layers_payload(gate_result),
    }
