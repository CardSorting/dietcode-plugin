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
/dietcode — BroccoliDB, BroccoliQ, JoyZoning, and JSDP integration console

Subcommands:
  status / doctor          Full integration health report
  tools                    Tool module load report
  broccolidb               BroccoliDB root + RPC availability
  kernel                   Kernel subtree + socket/token health
  kernel status            Compact operator summary (bridge, policy, gates)
  kernel progress              Human summary of current operation
  kernel progress --timeline   Ordered phase timeline with durations
  kernel progress --last N     Summarize last N operations
  kernel progress --operation <id>  Filter tail/timeline by operation_id
  kernel progress --tail       JSON tail of kernel-progress.jsonl
  kernel progress --current    Full current-state JSON snapshot
  kernel last-error            Last normalized kernel bridge error envelope
  kernel explain-gate          Closed gates, fixes, raw-write behavior
  kernel perf --last 10        Phase timing breakdown (p50/p95 by bucket)
  kernel perf --ux --last 10   Perceived responsiveness metrics (ack, silent gaps)
  kernel watch                 Compact single-line live operation summary
  kernel watch --follow        Auto-refresh summary every ~1.5s (up to 30s)
  kernel cockpit               One-screen operator summary (gates, state, next action)
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


def _kernel_health() -> dict[str, Any]:
    try:
        from plugins.dietcode.lib.kernel_health import build_kernel_health

        return build_kernel_health()
    except ImportError as exc:
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
        "kernel": _kernel_health(),
        "joyzoning": _joyzoning_health(),
        "jsdp": _jsdp_health(),
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

    kern = data.get("kernel", {})
    if kern.get("plugin_root"):
        lines.append(f"   plugin_root: {kern.get('plugin_root')}")
    if kern.get("kernel_root"):
        lines.append(f"   kernel_root: {kern.get('kernel_root')}")
    ws = kern.get("workspace") or {}
    if ws.get("resolved_workspace_root"):
        safe = ws.get("safe_for_mutation")
        mark = "✅" if safe else "⚠️ "
        lines.append(
            f"{mark} workspace: {ws.get('resolved_workspace_root')}"
            f" (source={ws.get('source')}, safe_for_mutation={safe})"
        )
        for err in ws.get("errors") or []:
            lines.append(f"   • {err}")
    elif ws.get("source"):
        lines.append(
            f"⚠️  workspace: unresolved (source={ws.get('source')})"
            f" — {ws.get('hint') or 'set HERMES_KANBAN_WORKSPACE or DIETCODE_WORKSPACE_ROOT'}"
        )
    bridge = kern.get("bridge_preflight") or {}
    if bridge.get("enabled") is False:
        lines.append("ℹ️  Kernel bridge: disabled in config")
    elif bridge.get("ok"):
        gate = bridge.get("patch_gate") or {}
        lines.append(
            f"✅ Kernel bridge preflight: {bridge.get('action', 'ok')}"
            f" | mutations_enabled={bridge.get('mutations_enabled', False)}"
            f" | patch_allowed={gate.get('patch_allowed', False)}"
        )
        if bridge.get("workspace_safe_for_mutation") is False:
            lines.append("   ⚠️  workspace not safe for kernel bridge — read/search/patch blocked")
        elif not gate.get("mutations_enabled"):
            lines.append(
                "   ℹ️  patch gate closed — set dietcode.kernel.bridge.mutations_enabled: true for dietcode_kernel(action='patch')"
            )
        elif gate.get("patch_allowed"):
            lines.append("   ✅ patch gate open — dietcode_kernel(action='patch') available")
    elif bridge.get("error"):
        err = bridge.get("error") if isinstance(bridge.get("error"), dict) else {}
        lines.append(
            f"⚠️  Kernel bridge: {err.get('string_code') or bridge.get('action')}"
            f" — {err.get('message') or bridge.get('action')}"
        )
    elif bridge.get("action") not in (None, "skipped"):
        lines.append(f"⚠️  Kernel bridge: {bridge.get('action')}")

    if kern.get("ok"):
        lines.append(
            f"✅ Kernel: binary at {kern.get('binary_path')}"
            f" | socket={'live' if kern.get('socket_reachable') else 'offline'}"
            f" | token={'ok' if kern.get('token_readable') else 'missing'}"
        )
    elif kern.get("platform_supported") is False:
        lines.append(
            f"ℹ️  Kernel: macOS-only (current: {kern.get('platform')}) — "
            "BroccoliDB/JoyZoning unaffected"
        )
    elif kern.get("subtree_present"):
        lines.append(f"⚠️  Kernel: {kern.get('hint') or 'build required'}")
    elif kern.get("error"):
        lines.append(f"⚠️  Kernel: {kern.get('error')}")

    receipt = kern.get("receipt_journal") or {}
    if receipt.get("phase"):
        lines.append(
            "ℹ️  Mutation authority: kernel = physical writes | "
            "JoyZoning = lifecycle journal/completion"
        )
        raw_router = kern.get("raw_write_router") or {}
        policy = raw_router.get("raw_write_policy") or "warn"
        would_warn = raw_router.get("would_warn_on_raw_write")
        would_block = raw_router.get("would_block_raw_writes")
        fuse = raw_router.get("env_fuse_present")
        if would_block:
            lines.append(
                f"⚠️  Raw write policy: {policy} — blocking active on write_file/patch "
                f"(DIETCODE_KERNEL_RAW_WRITE_BLOCK fuse={'on' if fuse else 'off'})"
            )
        elif would_warn:
            lines.append(
                f"⚠️  Raw write policy: {policy} — write_file/patch would warn "
                "(kernel patch gate open; prefer dietcode_kernel)"
            )
        elif policy == "block" and not fuse:
            lines.append(
                f"ℹ️  Raw write policy: {policy} — fuse unset; raw writes warn-only until "
                "DIETCODE_KERNEL_RAW_WRITE_BLOCK=1"
            )
        elif policy != "allow":
            lines.append(
                f"ℹ️  Raw write policy: {policy} — no warn yet "
                f"(patch_gate_open={raw_router.get('patch_gate_open', False)})"
            )
        else:
            lines.append(f"ℹ️  Raw write policy: {policy} — raw write hints disabled")
        if not would_block:
            lines.append(
                "   Raw Hermes write_file/patch not hard-blocked"
                if would_warn
                else "   Raw Hermes write_file/patch allowed (gate closed or policy=allow)"
            )
        if receipt.get("joyzoning_enabled"):
            lines.append(
                f"   Receipt journal (Phase {receipt.get('phase')}): "
                "successful dietcode_kernel patches → JoyZoning mutation_record_patch"
            )
        else:
            lines.append(
                "   Receipt journal: JoyZoning disabled — kernel patches succeed without lifecycle journal"
            )

    progress = kern.get("progress") or {}
    current = progress.get("current") if isinstance(progress.get("current"), dict) else None
    if current:
        lines.append(
            f"ℹ️  Kernel progress: phase={current.get('phase')} "
            f"action={current.get('action')} elapsed_ms={current.get('elapsed_ms')}"
        )
    if progress.get("stale_progress_ms"):
        lines.append(
            f"⚠️  Kernel progress stale ({progress['stale_progress_ms']}ms) — "
            "/dietcode kernel progress --current"
        )

    verify = kern.get("verify_bridge") or {}
    if verify.get("phase"):
        allowlist = verify.get("allowlist_prefixes") or []
        if verify.get("verify_action_available"):
            lines.append(
                f"✅ Kernel verify (Phase {verify.get('phase')}): dietcode_kernel(action='verify') available"
                f" | allowlist={len(allowlist)} prefixes"
            )
        else:
            lines.append(
                f"ℹ️  Kernel verify (Phase {verify.get('phase')}): unavailable"
                f" (bridge/socket/workspace gate closed)"
            )
        if allowlist:
            preview = ", ".join(str(p) for p in allowlist[:4])
            if len(allowlist) > 4:
                preview += f", … +{len(allowlist) - 4}"
            lines.append(f"   verify.run allowlist: {preview}")

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

    if sub == "kernel":
        rest = argv[1:] if len(argv) > 1 else []
        if not rest:
            return json.dumps(_kernel_health(), indent=2)
        kernel_sub = rest[0].lower()
        if kernel_sub == "status":
            try:
                from plugins.dietcode.lib.kernel_health import format_kernel_status_report
            except ImportError:
                from lib.kernel_health import format_kernel_status_report
            return format_kernel_status_report()
        if kernel_sub == "progress":
            try:
                from plugins.dietcode.lib.agent import kernel_progress as kp
            except ImportError:
                from lib.agent import kernel_progress as kp
            opts = kp.parse_progress_args(rest[1:])
            return kp.format_progress_report(
                tail=bool(opts.get("tail")),
                current_only=bool(opts.get("current")),
                timeline=bool(opts.get("timeline")),
                operation_id=opts.get("operation"),
                last=opts.get("last"),
            )
        if kernel_sub == "last-error":
            try:
                from plugins.dietcode.lib.agent import kernel_progress as kp
            except ImportError:
                from lib.agent import kernel_progress as kp
            return json.dumps(kp.read_last_error(), indent=2, ensure_ascii=False)
        if kernel_sub == "explain-gate":
            try:
                from plugins.dietcode.lib.agent import kernel_progress as kp
            except ImportError:
                from lib.agent import kernel_progress as kp
            return kp.format_gate_explanation()
        if kernel_sub == "perf":
            try:
                from plugins.dietcode.lib.agent.kernel_bridge_perf import format_perf_report, parse_perf_args
                from plugins.dietcode.lib.agent.kernel_progress_ux import format_ux_perf_report, parse_perf_ux_args
            except ImportError:
                from lib.agent.kernel_bridge_perf import format_perf_report, parse_perf_args
                from lib.agent.kernel_progress_ux import format_ux_perf_report, parse_perf_ux_args
            last_n, ux = parse_perf_ux_args(rest[1:])
            if ux:
                return format_ux_perf_report(last_operations=last_n)
            return format_perf_report(last_operations=parse_perf_args(rest[1:]))
        if kernel_sub == "watch":
            try:
                from plugins.dietcode.lib.agent.kernel_progress_ux import format_watch_report, parse_watch_args
            except ImportError:
                from lib.agent.kernel_progress_ux import format_watch_report, parse_watch_args
            opts = parse_watch_args(rest[1:])
            return format_watch_report(
                follow=bool(opts.get("follow")),
                interval_sec=float(opts.get("interval_sec") or 1.5),
                max_sec=float(opts.get("max_sec") or 30.0),
            )
        if kernel_sub == "cockpit":
            try:
                from plugins.dietcode.lib.agent.kernel_cockpit import format_cockpit_report
            except ImportError:
                from lib.agent.kernel_cockpit import format_cockpit_report
            return format_cockpit_report()
        return json.dumps(_kernel_health(), indent=2)

    return f"Unknown subcommand: {sub}\n\n{_HELP}"
