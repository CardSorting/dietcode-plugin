# -*- coding: utf-8 -*-
"""DietCode plugin health / doctor surface."""
from __future__ import annotations

import json
import shlex
from pathlib import Path
from typing import Any, Optional

from plugins.dietcode.tools_loader import EXPECTED_DIETCODE_TOOLS, get_load_report

try:
    from plugins.dietcode.contracts import validate_runtime_contract
    from plugins.dietcode.guard import (
        dietcode_governance_hook_active,
        dietcode_tools_in_registry,
        is_dietcode_plugin_registered,
    )
except ImportError:
    def is_dietcode_plugin_registered() -> bool:  # type: ignore[misc]
        return False

    def dietcode_tools_in_registry() -> bool:  # type: ignore[misc]
        return False

    def dietcode_governance_hook_active() -> bool:  # type: ignore[misc]
        return False

    def validate_runtime_contract(**kwargs):  # type: ignore[misc]
        from plugins.dietcode.contracts import ContractReport

        return ContractReport()

_HELP = """\
/dietcode — BroccoliDB, JoyZoning, and JSDP integration console

Subcommands:
  status / doctor          Full integration health report
  operator                 Unified gate brief — agent_next_call and recovery_steps
  tools                    Tool module load report
  broccolidb               BroccoliDB root + RPC availability
  mutation                 Native mutation workspace health (dietcode_kernel)
  mutation status          Workspace revision, drift, coherence state
  roadmap                      Roadmap feature health JSON
  roadmap cockpit              One-screen roadmap operator summary
  roadmap progress             Roadmap tool activity summary
  roadmap progress --timeline  Activity timeline
  roadmap progress --current   Full progress + gate snapshot JSON
  roadmap watch                Compact last-action line
  roadmap explain-gate         Closed schema/freshness gates and kanban_complete policy
"""


def _broccolidb_health() -> dict[str, Any]:
    try:
        from plugins.dietcode.paths import is_valid_broccolidb_root, resolve_broccolidb_root
        from plugins.dietcode.lib.tools.broccolidb_tools.db_gateway import rpc_available
        from plugins.dietcode.lib.tools.broccolidb_tools.runner import check_requirements
    except ImportError as exc:
        return {"ok": False, "error": str(exc)}

    root = resolve_broccolidb_root()
    plugin_root = None
    node_modules_ok = False
    try:
        from plugins.dietcode.paths import get_plugin_root

        candidate = get_plugin_root() / "broccolidb"
        if is_valid_broccolidb_root(candidate):
            plugin_root = str(candidate.resolve())
            node_modules_ok = (candidate / "node_modules").is_dir()
    except Exception:
        pass

    root_path = Path(root) if root else None
    if root_path and is_valid_broccolidb_root(root_path):
        node_modules_ok = node_modules_ok or (root_path / "node_modules").is_dir()

    return {
        "ok": bool(root),
        "root": root,
        "plugin_bundled_root": plugin_root,
        "node_modules_installed": node_modules_ok,
        "requirements_met": check_requirements(),
        "rpc_available": rpc_available() if root else False,
    }


def _joyzoning_health() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config
        from plugins.dietcode.lib.agent.governance_exemptions import (
            GOVERNANCE_POLICY_VERSION,
            is_governance_enforcement_enabled,
        )

        cfg = get_joyzoning_config()
        return {
            "ok": True,
            "enabled": cfg.enabled,
            "jsdp_enabled": cfg.jsdp_enabled,
            "jsdp_role": cfg.jsdp_role or None,
            "governance_enforcement": is_governance_enforcement_enabled(),
            "governance_policy_version": GOVERNANCE_POLICY_VERSION,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _toolset_health() -> dict[str, Any]:
    try:
        from toolsets import resolve_toolset

        names = set(resolve_toolset("dietcode"))
        missing = sorted(EXPECTED_DIETCODE_TOOLS - names)
        return {
            "ok": not missing,
            "tool_count": len(names),
            "missing_from_toolset": missing,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _runtime_health() -> dict[str, Any]:
    try:
        from plugins.dietcode.audit import (
            duplicate_diet_hooks,
            legacy_shim_dirs_absent,
            runtime_layout_ok,
        )

        layout_ok, layout_missing = runtime_layout_ok()
        shims_gone, shim_dirs = legacy_shim_dirs_absent()
        no_dupes, dupe_issues = duplicate_diet_hooks()
        return {
            "ok": layout_ok and shims_gone and no_dupes,
            "layout_ok": layout_ok,
            "layout_missing": layout_missing,
            "legacy_shims_absent": shims_gone,
            "legacy_shim_dirs": shim_dirs,
            "no_duplicate_hooks": no_dupes,
            "duplicate_hook_issues": dupe_issues,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _mutation_health() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.workspace_root import build_workspace_health
        from plugins.dietcode.lib.agent.native_mutation import NativeMutationManager

        ws_health = build_workspace_health()
        root = ws_health.get("resolved_workspace_root")
        status = None
        if root:
            mgr = NativeMutationManager.get_instance()
            status = mgr.get_status(Path(root))
        return {
            "ok": bool(ws_health.get("safe_for_mutation")),
            "mode": "native_mutation",
            "workspace": ws_health,
            "runtime_status": status,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _roadmap_health() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config, resolve_workspace_root
        from plugins.dietcode.lib.agent.roadmap.doctor import run_checks

        cfg = get_roadmap_config()
        root = resolve_workspace_root()
        doctor = run_checks(workspace=root)
        steering_line = None
        roadmap_path = None
        steering_brief = None
        project_archetype = None
        project_steering_digest = None
        try:
            from plugins.dietcode.lib.agent.roadmap.agent_steering import build_live_steering_brief

            live = build_live_steering_brief(workspace=root)
            steering_line = live.get("steering_line")
            roadmap_path = live.get("roadmap_path")
            steering_brief = live.get("steering_brief")
            project_archetype = live.get("project_archetype")
        except Exception:
            pass
        project_steering_digest = doctor.get("project_steering_digest")
        identity_line = doctor.get("project_identity_line") or (project_steering_digest or {}).get("identity_line")
        return {
            "ok": doctor.get("ok", False),
            "enabled": cfg.enabled,
            "auto_install_skills": cfg.auto_install_skills,
            "workspace": root,
            "roadmap_path": roadmap_path,
            "steering_line": steering_line,
            "steering_brief": steering_brief,
            "project_archetype": project_archetype,
            "project_identity_line": identity_line,
            "project_steering_digest": project_steering_digest,
            "bootstrap_fill_plan": doctor.get("bootstrap_fill_plan"),
            "roadmap_present": any(
                c.get("ok") for c in doctor.get("checks", [])
                if c.get("name") in {"roadmap_present", "roadmap_readable"}
            ),
            "checkpoint_stale": (doctor.get("checkpoint_freshness") or {}).get("stale"),
            "workspace_skill_installed": any(
                c.get("ok") for c in doctor.get("checks", [])
                if c.get("name") == "workspace_skill_installed"
            ),
            "schema_valid": (doctor.get("validation") or {}).get("valid"),
            "kanban_complete_allowed": _gates_health().get("kanban_complete_allowed"),
            "roadmap_gate": doctor.get("roadmap_gate"),
            "recommended_next_action": doctor.get("recommended_next_action"),
            "checks": doctor.get("checks"),
            "recommendations": doctor.get("recommendations"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _jsdp_health() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config

        cfg = get_joyzoning_config()
        return {
            "ok": True,
            "enabled": cfg.jsdp_enabled,
            "role": cfg.jsdp_role or None,
            "chain_id": cfg.jsdp_chain_id or None,
            "hook_module": "plugins.dietcode.lib.runtime.jsdp_hooks",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _gates_health() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.agent.features import build_runtime_snapshot

        snapshot = build_runtime_snapshot()
        gates = snapshot.get("gates") or {}
        return {
            "ok": bool(gates.get("kanban_complete_allowed", True)),
            "kanban_complete_allowed": gates.get("kanban_complete_allowed"),
            "kanban_complete_block_reason": gates.get("kanban_complete_block_reason"),
            "layers": gates.get("layers"),
            "features": snapshot.get("features"),
            "config": snapshot.get("config"),
            "hook_chains": snapshot.get("hook_chains"),
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def build_status_report(*, strict: bool = False, refresh: bool = False) -> dict[str, Any]:
    load = get_load_report(force=refresh)
    contract = validate_runtime_contract(strict=strict)
    return {
        "plugin": "dietcode",
        "registered": is_dietcode_plugin_registered(),
        "tools_in_registry": dietcode_tools_in_registry(),
        "governance_hook_active": dietcode_governance_hook_active(),
        "contract_ok": contract.ok,
        "contract_errors": contract.errors,
        "contract_warnings": contract.warnings,
        "contract_checks": contract.checks,
        "tools": {
            "modules_loaded": len(load.loaded),
            "modules_failed": load.failed,
            "registry_present": sorted(load.registry_tools),
            "registry_missing": sorted(load.registry_missing),
        },
        "toolset": _toolset_health(),
        "runtime": _runtime_health(),
        "broccolidb": _broccolidb_health(),
        "mutation": _mutation_health(),
        "joyzoning": _joyzoning_health(),
        "jsdp": _jsdp_health(),
        "roadmap": _roadmap_health(),
        "gates": _gates_health(),
    }


def format_status_report(
    report: Optional[dict[str, Any]] = None,
    *,
    doctor: bool = False,
    refresh: bool = False,
) -> str:
    data = report if report is not None else build_status_report(strict=doctor, refresh=refresh)
    lines = ["🥤 DietCode integration status", ""]

    if data.get("registered"):
        lines.append("✅ Plugin registered on PluginManager")
    else:
        lines.append("⚠️  Plugin not registered (discover_plugins may not have run)")

    if data.get("governance_hook_active"):
        lines.append("✅ Governance transform hook wired (dietcode)")
        checks = data.get("contract_checks") or {}
        if checks.get("governance_config_enabled") and not checks.get("dietcode_in_toolsets"):
            lines.append(
                "⚠️  Governance active without dietcode toolset — write/patch layering runs "
                "even when JoyZoning tools are not loaded (see joyzoning.governance.enabled)"
            )
        jz = data.get("joyzoning") or {}
        if jz.get("governance_enforcement") and not jz.get("enabled"):
            lines.append(
                "⚠️  joyzoning.enabled is false but governance is on — enable joyzoning for "
                "lifecycle tools and kanban_complete gates"
            )
    elif (data.get("joyzoning") or {}).get("governance_enforcement"):
        lines.append("⚠️  Governance enabled in config but transform hook not active")

    for err in data.get("contract_errors") or []:
        lines.append(f"❌ {err}")
    for warn in data.get("contract_warnings") or []:
        lines.append(f"⚠️  {warn}")

    tools = data.get("tools", {})
    if tools.get("modules_failed"):
        lines.append(f"⚠️  Tool modules failed: {len(tools['modules_failed'])}")
        for mod, err in tools["modules_failed"].items():
            lines.append(f"   • {mod}: {err}")
    else:
        lines.append(f"✅ Tool modules loaded: {tools.get('modules_loaded', 0)}")

    missing_reg = tools.get("registry_missing") or []
    if missing_reg:
        lines.append(f"⚠️  Registry missing {len(missing_reg)} expected tools: {', '.join(missing_reg[:8])}")
        if len(missing_reg) > 8:
            lines.append(f"   … and {len(missing_reg) - 8} more")
    else:
        lines.append(f"✅ Registry tools: {len(tools.get('registry_present') or [])}")

    ts = data.get("toolset", {})
    if ts.get("ok"):
        lines.append(f"✅ dietcode toolset: {ts.get('tool_count', 0)} tools resolved")
    else:
        lines.append(f"⚠️  dietcode toolset incomplete: {ts.get('missing_from_toolset') or ts.get('error')}")

    bdb = data.get("broccolidb", {})
    if bdb.get("ok"):
        lines.append(f"✅ BroccoliDB root: {bdb.get('root')}")
        if bdb.get("plugin_bundled_root"):
            lines.append(f"   Plugin bundle: {bdb.get('plugin_bundled_root')}")
        lines.append(
            f"   RPC: {'warm' if bdb.get('rpc_available') else 'oneshot/fallback'}"
            f" | requirements: {bdb.get('requirements_met')}"
            f" | node_modules: {bdb.get('node_modules_installed')}"
        )
        if not bdb.get("node_modules_installed"):
            lines.append("   Run: cd broccolidb && npm ci")
    else:
        lines.append(f"⚠️  BroccoliDB: {bdb.get('error') or 'root not found'}")

    mut = data.get("mutation", {})
    ws = mut.get("workspace") or {}
    if ws.get("resolved_workspace_root"):
        safe = ws.get("safe_for_mutation")
        mark = "✅" if safe else "⚠️ "
        lines.append(
            f"{mark} Mutation workspace: {ws.get('resolved_workspace_root')}"
            f" (source={ws.get('source')}, safe_for_mutation={safe})"
        )
        for err in ws.get("errors") or []:
            lines.append(f"   • {err}")
    elif ws.get("source"):
        lines.append(
            f"⚠️  Mutation workspace: unresolved — {ws.get('hint') or 'set HERMES_KANBAN_WORKSPACE'}"
        )
    runtime = mut.get("runtime_status") or {}
    if runtime.get("ok") and isinstance(runtime.get("result"), dict):
        res = runtime["result"]
        lines.append(
            f"ℹ️  Native mutation: revision={res.get('workspaceRevision')} "
            f"drift={res.get('driftDetected')} — use dietcode_kernel(action='status')"
        )
    elif mut.get("error"):
        lines.append(f"⚠️  Mutation runtime: {mut.get('error')}")

    jz = data.get("joyzoning", {})
    if jz.get("ok"):
        lines.append(
            f"✅ JoyZoning: enabled={jz.get('enabled')} "
            f"governance={jz.get('governance_enforcement')} "
            f"policy=v{jz.get('governance_policy_version')}"
        )
        if jz.get("jsdp_enabled"):
            lines.append(f"   JSDP: role={jz.get('jsdp_role') or '(unset)'}")
    else:
        lines.append(f"⚠️  JoyZoning: {jz.get('error')}")

    rt = data.get("runtime", {})
    if rt.get("ok"):
        lines.append("✅ Runtime layout complete")
    elif rt.get("error"):
        lines.append(f"⚠️  Runtime: {rt.get('error')}")
    else:
        if not rt.get("layout_ok"):
            lines.append(f"⚠️  Runtime layout missing: {rt.get('layout_missing')}")
        if not rt.get("legacy_shims_absent"):
            lines.append(f"⚠️  Legacy shim dirs still present: {rt.get('legacy_shim_dirs')}")
        if not rt.get("no_duplicate_hooks"):
            lines.append(f"⚠️  Duplicate hooks: {rt.get('duplicate_hook_issues')}")

    jsdp = data.get("jsdp", {})
    if jsdp.get("ok") and jsdp.get("enabled"):
        lines.append(f"✅ JSDP: role={jsdp.get('role') or '(unset)'} chain={jsdp.get('chain_id') or '(unset)'}")
    elif jsdp.get("ok"):
        lines.append("✅ JSDP: disabled in config")

    roadmap = data.get("roadmap", {})
    if roadmap.get("ok"):
        stale = roadmap.get("checkpoint_stale")
        mark = "⚠️ " if stale else "✅"
        lines.append(
            f"{mark} Roadmap: enabled={roadmap.get('enabled')} "
            f"present={roadmap.get('roadmap_present')} "
            f"skill_installed={roadmap.get('workspace_skill_installed')} "
            f"schema_valid={roadmap.get('schema_valid')} "
            f"stale={stale}"
        )
        if roadmap.get("steering_brief"):
            lines.append(f"   Project: {roadmap['steering_brief']}")
        if roadmap.get("project_identity_line"):
            lines.append(f"   Identity: {roadmap['project_identity_line']}")
        digest = roadmap.get("project_steering_digest") or {}
        if not roadmap.get("project_identity_line") and digest.get("identity_line"):
            lines.append(f"   Identity: {digest['identity_line']}")
        verify_cmds = digest.get("verification_commands") or []
        if verify_cmds:
            lines.append(f"   Verify: {verify_cmds[0]}")
        remaining = digest.get("bootstrap_remaining")
        if remaining and int(remaining) > 0:
            lines.append(
                f"   Bootstrap fill: {remaining} phrase(s) — roadmap(action='apply_bootstrap_fill', context='write')"
            )
        rec = roadmap.get("recommended_next_action") or {}
        if rec.get("command"):
            lines.append(f"   Next: {rec['command']}")
    elif roadmap.get("enabled") is False:
        lines.append("ℹ️  Roadmap: disabled in config")
    elif roadmap.get("error"):
        lines.append(f"⚠️  Roadmap: {roadmap.get('error')}")
    else:
        for rec in (roadmap.get("recommendations") or [])[:2]:
            lines.append(f"⚠️  Roadmap: {rec}")

    if doctor and not data.get("contract_ok", True):
        lines.append("")
        lines.append("Doctor: integration contract FAILED — fix errors above before production use.")

    return "\n".join(lines)


def handle_dietcode_command(raw_args: str) -> Optional[str]:
    argv = shlex.split((raw_args or "").strip())
    if not argv or argv[0] in ("help", "-h", "--help"):
        return _HELP

    sub = argv[0].lower()
    if sub in ("status", "doctor"):
        return format_status_report(doctor=(sub == "doctor"), refresh=(sub == "doctor"))

    if sub == "operator":
        from plugins.dietcode.lib.agent.ergonomics import build_operator_brief

        return json.dumps(build_operator_brief(), indent=2, ensure_ascii=False)

    if sub == "tools":
        load = get_load_report(force=True)
        payload = {
            "loaded": load.loaded,
            "failed": load.failed,
            "registry_tools": load.registry_tools,
            "registry_missing": load.registry_missing,
        }
        return json.dumps(payload, indent=2)

    if sub == "broccolidb":
        return json.dumps(_broccolidb_health(), indent=2)

    if sub == "mutation":
        rest = argv[1:] if len(argv) > 1 else []
        if rest and rest[0].lower() == "status":
            return json.dumps(_mutation_health(), indent=2)
        return json.dumps(_mutation_health(), indent=2)

    if sub == "roadmap":
        rest = argv[1:] if len(argv) > 1 else []
        if rest:
            roadmap_sub = rest[0].lower()
            if roadmap_sub == "cockpit":
                try:
                    from plugins.dietcode.lib.agent.roadmap.cockpit import format_cockpit_report
                except ImportError:
                    from lib.agent.roadmap.cockpit import format_cockpit_report
                return format_cockpit_report()
            if roadmap_sub == "doctor":
                try:
                    from plugins.dietcode.lib.agent.roadmap.doctor import format_doctor_report
                except ImportError:
                    from lib.agent.roadmap.doctor import format_doctor_report
                return format_doctor_report()
            if roadmap_sub == "progress":
                try:
                    from plugins.dietcode.lib.agent.roadmap.progress import format_progress_report, read_tail
                except ImportError:
                    from lib.agent.roadmap.progress import format_progress_report, read_tail
                if "--current" in rest:
                    try:
                        from plugins.dietcode.lib.agent.roadmap.progress import build_progress_snapshot
                    except ImportError:
                        from lib.agent.roadmap.progress import build_progress_snapshot
                    return json.dumps(build_progress_snapshot(), indent=2, ensure_ascii=False)
                if "--tail" in rest:
                    return json.dumps(read_tail(lines=20), indent=2)
                return format_progress_report(timeline="--timeline" in rest)
            if roadmap_sub == "watch":
                try:
                    from plugins.dietcode.lib.agent.roadmap.progress import format_watch_report
                except ImportError:
                    from lib.agent.roadmap.progress import format_watch_report
                return format_watch_report()
            if roadmap_sub in ("explain-gate", "explain_gate"):
                try:
                    from plugins.dietcode.lib.agent.roadmap.explain_gate import build_explain_gate_payload
                except ImportError:
                    from lib.agent.roadmap.explain_gate import build_explain_gate_payload
                payload = build_explain_gate_payload()
                return payload.get("report") or json.dumps(payload, indent=2, ensure_ascii=False)
        return json.dumps(_roadmap_health(), indent=2)

    return f"Unknown subcommand: {sub}\n\n{_HELP}"
