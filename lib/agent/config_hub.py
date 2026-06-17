"""Unified DietCode runtime configuration — single read surface for subsystems."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DietCodeRuntimeConfig:
    joyzoning: Any
    roadmap: Any
    completion_gate: Any


def get_runtime_config() -> DietCodeRuntimeConfig:
    from plugins.dietcode.lib.agent.audit.config import get_completion_gate_config
    from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config
    from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config

    return DietCodeRuntimeConfig(
        joyzoning=get_joyzoning_config(),
        roadmap=get_roadmap_config(),
        completion_gate=get_completion_gate_config(),
    )


def runtime_config_snapshot() -> dict[str, Any]:
    """JSON-friendly config summary for doctor and status surfaces."""
    cfg = get_runtime_config()
    jz = cfg.joyzoning
    rm = cfg.roadmap
    cg = cfg.completion_gate
    return {
        "joyzoning": {
            "enabled": bool(jz.enabled),
            "execution_journal": bool(jz.execution_journal),
            "jsdp_enabled": bool(jz.jsdp_enabled),
            "jsdp_role": jz.jsdp_role or None,
        },
        "roadmap": {
            "enabled": bool(rm.enabled),
            "auto_install_skills": bool(rm.auto_install_skills),
            "progress_enabled": bool(rm.progress_enabled),
        },
        "completion_gate": {
            "enabled": bool(cg.enabled),
            "score_threshold": cg.score_threshold,
            "spider_gate_required": bool(cg.spider_gate_required),
        },
    }
