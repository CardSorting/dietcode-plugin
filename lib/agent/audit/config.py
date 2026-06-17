"""Completion gate configuration — mirrors codemarie auditCompletionGate* settings."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

_config_cache: Optional["CompletionGateConfig"] = None
_config_cache_at: float = 0.0
_CONFIG_TTL = 30.0


@dataclass(frozen=True)
class CompletionGateConfig:
    enabled: bool = False
    score_threshold: int = 50
    critical_only: bool = False
    spider_gate_required: bool = True
    spider_scope: str = "changed-files"
    fail_on_spider_warning: bool = False
    require_recent_verify: bool = False
    intent_adjusted_threshold: bool = True
    plan_regression_gate_enabled: bool = True
    advisory_escalation_enabled: bool = True
    new_violations_only: bool = False
    max_block_count: int = 10

    @classmethod
    def load(cls) -> "CompletionGateConfig":
        try:
            from hermes_cli.config import load_config

            raw = load_config() or {}
            jz = raw.get("joyzoning") if isinstance(raw, dict) else {}
            gov = jz.get("governance") if isinstance(jz, dict) else {}
            if not isinstance(gov, dict):
                gov = {}
            cg = gov.get("completion_gate") if isinstance(gov.get("completion_gate"), dict) else {}
            gov_enabled = bool(gov.get("enabled", False))
            enabled = cg.get("enabled")
            if enabled is None:
                enabled = gov_enabled
            return cls(
                enabled=bool(enabled),
                score_threshold=int(cg.get("score_threshold", 50)),
                critical_only=bool(cg.get("critical_only", False)),
                spider_gate_required=bool(cg.get("spider_gate_required", True)),
                spider_scope=str(cg.get("spider_scope") or "changed-files"),
                fail_on_spider_warning=bool(cg.get("fail_on_spider_warning", False)),
                require_recent_verify=bool(cg.get("require_recent_verify", False)),
                intent_adjusted_threshold=bool(cg.get("intent_adjusted_threshold", True)),
                plan_regression_gate_enabled=bool(cg.get("plan_regression_gate_enabled", True)),
                advisory_escalation_enabled=bool(cg.get("advisory_escalation_enabled", True)),
                new_violations_only=bool(cg.get("new_violations_only", False)),
                max_block_count=int(cg.get("max_block_count", 10)),
            )
        except Exception:
            return cls()


def get_completion_gate_config() -> CompletionGateConfig:
    global _config_cache, _config_cache_at
    now = time.monotonic()
    if _config_cache is None or (now - _config_cache_at) > _CONFIG_TTL:
        _config_cache = CompletionGateConfig.load()
        _config_cache_at = now
    return _config_cache
