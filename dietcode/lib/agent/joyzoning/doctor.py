"""JoyZoning production health checks — shared by tool and CLI."""
from __future__ import annotations

from typing import Any, Optional


def run_checks(*, scope_id: Optional[str] = None) -> dict[str, Any]:
    from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, read_scope_env, resolve_scope_id
    from plugins.dietcode.lib.agent.joyzoning.convergence import get_convergence_state
    from plugins.dietcode.lib.agent.joyzoning.journal import get_journal
    from plugins.dietcode.lib.agent.joyzoning.workflow import _resolve_cluster

    cfg = get_joyzoning_config()
    sid = resolve_scope_id(scope_id)
    state, anchor, cluster = _resolve_cluster(sid)
    checks: list[dict[str, Any]] = []

    def _check(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": ok, "detail": detail})

    _check("joyzoning.enabled", cfg.enabled)
    _check(
        "execution_journal",
        True,
        "enabled" if cfg.execution_journal else "disabled (opt-in; lower latency)",
    )

    try:
        journal = get_journal()
        journal.get_convergence(anchor)
        integrity = journal.integrity_check()
        _check("journal_db", True, "readable")
        _check("journal_integrity", integrity.get("success") is True, str(integrity))
    except Exception as exc:
        _check("journal_db", False, str(exc))
        _check("journal_integrity", False, str(exc))

    _check("convergence_state", True, f"{state.value} (anchor={anchor}, cluster={len(cluster)})")

    try:
        in_worker = bool(
            read_scope_env("HERMES_KANBAN_RUN_ID") or read_scope_env("HERMES_KANBAN_TASK")
        )
        has_kanban = bool(read_scope_env("HERMES_KANBAN_TASK"))
        _check(
            "scope_env_kanban",
            has_kanban or not in_worker,
            read_scope_env("HERMES_KANBAN_TASK") or ("unset" if not in_worker else "missing in worker"),
        )
    except Exception as exc:
        _check("scope_env", False, str(exc))

    if cfg.jsdp_harness_enabled or cfg.jsdp_enabled:
        try:
            from plugins.dietcode.lib.agent.joyzoning.jsdp_harness_client import (
                resolve_jz_executable,
                resolve_workspace_root,
                rolling_horizon_operational_hint,
            )
            root = resolve_workspace_root()
            hint = rolling_horizon_operational_hint()
            _check("jsdp_harness_workspace", True, root)
            _check(
                "jsdp_harness_present",
                hint.get("harness_present") is True,
                ".jsdp/ missing — run jz jsdp init in workspace" if not hint.get("harness_present") else "ok",
            )
            jz = resolve_jz_executable()
            _check("jsdp_jz_cli", True, jz)
        except Exception as exc:
            _check("jsdp_harness", False, str(exc))
    else:
        _check("jsdp_harness", True, "disabled (set joyzoning.jsdp.harness.enabled)")

    ok = all(c["ok"] for c in checks)
    recommendations: list[str] = []
    if not cfg.enabled:
        recommendations.append("Set joyzoning.enabled: true in config.yaml")
    if cfg.enabled and not cfg.jsdp_harness_enabled:
        recommendations.append(
            "Enable joyzoning.jsdp.harness.enabled for rolling-horizon jsdp tool"
        )
    if cfg.jsdp_harness_enabled and not cfg.jsdp_jz_cli:
        recommendations.append(
            "Set joyzoning.jsdp.harness.jz_cli to JoyZoning scripts/joyzoning path"
        )
    for chk in checks:
        if not chk.get("ok"):
            recommendations.append(f"Fix: {chk.get('name')} — {chk.get('detail', '')}")

    return {
        "success": ok,
        "ok": ok,
        "scope_id": sid,
        "anchor_scope_id": anchor,
        "scope_cluster": cluster,
        "convergence_state": state.value,
        "checks": checks,
        "recommendations": recommendations,
    }
