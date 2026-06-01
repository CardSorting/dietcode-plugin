# -*- coding: utf-8 -*-
"""Runtime contract validation for the DietCode plugin."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_REQUIRED_HOOKS = (
    "on_session_start",
    "on_session_end",
    "pre_tool_call",
    "post_tool_call",
    "transform_tool_result",
)

_GUIDANCE_BUILDER_ATTR = "_dietcode_guidance_builder"


@dataclass
class ContractReport:
    ok: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checks: dict[str, Any] = field(default_factory=dict)

    def add_error(self, msg: str) -> None:
        self.ok = False
        self.errors.append(msg)

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)


def _governance_enabled_in_config() -> bool:
    try:
        from plugins.dietcode.lib.agent.governance_exemptions import is_governance_enforcement_enabled

        return bool(is_governance_enforcement_enabled())
    except Exception:
        return False


def _dietcode_in_default_toolsets() -> bool:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        toolsets = cfg.get("toolsets") if isinstance(cfg, dict) else None
        if not isinstance(toolsets, list):
            return False
        return "dietcode" in toolsets
    except Exception:
        return False


def _plugin_disabled_in_config() -> bool:
    try:
        from hermes_cli.config import load_config

        cfg = load_config()
        plugins = cfg.get("plugins") if isinstance(cfg, dict) else None
        if not isinstance(plugins, dict):
            return False
        disabled = plugins.get("disabled") or []
        if not isinstance(disabled, list):
            return False
        return "dietcode" in disabled
    except Exception:
        return False


def _hook_names_present() -> dict[str, bool]:
    try:
        from hermes_cli.plugins import get_plugin_manager

        pm = get_plugin_manager()
        hooks = pm._hooks
        return {
            name: any(
                cb.__name__ == f"dietcode_{name}" or cb.__name__.startswith("dietcode_")
                for cb in hooks.get(name, [])
            )
            for name in _REQUIRED_HOOKS
        }
    except Exception:
        return {name: False for name in _REQUIRED_HOOKS}


def validate_runtime_contract(*, strict: bool = False) -> ContractReport:
    """Validate DietCode integration invariants for production deployments."""
    from plugins.dietcode.guard import dietcode_tools_in_registry, is_dietcode_plugin_registered
    from plugins.dietcode.tools_loader import get_load_report

    report = ContractReport()
    load = get_load_report()
    registered = is_dietcode_plugin_registered()
    tools_ok = dietcode_tools_in_registry()
    hooks = _hook_names_present()
    governance_on = _governance_enabled_in_config()
    expected = _dietcode_in_default_toolsets()
    disabled = _plugin_disabled_in_config()

    report.checks = {
        "plugin_registered": registered,
        "tools_in_registry": tools_ok,
        "modules_failed": load.failed,
        "registry_missing": load.registry_missing,
        "hooks": hooks,
        "governance_config_enabled": governance_on,
        "dietcode_in_toolsets": expected,
        "dietcode_disabled_in_config": disabled,
    }

    if disabled and expected:
        report.add_error(
            "dietcode is in toolsets but listed in plugins.disabled — tools/hooks will not load"
        )

    if not registered:
        if expected and not disabled:
            report.add_error("DietCode plugin did not register (discover_plugins failure or import error)")
        elif strict:
            report.add_error("DietCode plugin not registered on PluginManager")

    if load.failed:
        report.add_error(f"Tool module import failures: {list(load.failed.keys())}")

    if load.registry_missing:
        report.add_error(f"Registry missing expected tools: {load.registry_missing}")

    if not tools_ok and registered:
        report.add_error("DietCode registered but expected registry tools are absent")

    missing_hooks = [name for name, present in hooks.items() if not present]
    if registered and missing_hooks:
        report.add_error(f"DietCode hook chains missing: {missing_hooks}")

    if governance_on and not hooks.get("transform_tool_result"):
        report.add_error(
            "joyzoning.governance.enabled is true but transform_tool_result hook is not wired "
            "(enable the DietCode plugin and add dietcode to toolsets)"
        )

    if registered and governance_on and hooks.get("transform_tool_result"):
        if not expected:
            report.add_warning(
                "joyzoning.governance.enabled is true and the transform hook is active, but "
                "dietcode is not in toolsets — layering enforcement runs on write_file/patch "
                "without JoyZoning tools in the session. Add dietcode to toolsets or set "
                "joyzoning.governance.enabled: false to disable."
            )
        try:
            from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config

            if not get_joyzoning_config().enabled:
                report.add_warning(
                    "joyzoning.enabled is false but governance enforcement is on — file "
                    "mutations are still scanned; enable joyzoning for lifecycle tools and gates."
                )
        except Exception:
            pass

    try:
        from plugins.dietcode.audit import (
            broccolidb_bundle_symlink_ok,
            duplicate_diet_hooks,
            legacy_shim_dirs_absent,
            removed_habitat_modules_absent,
            runtime_layout_ok,
            scan_stale_joyzoning_config_keys,
        )

        layout_ok, layout_missing = runtime_layout_ok()
        report.checks["runtime_layout_ok"] = layout_ok
        report.checks["runtime_layout_missing"] = layout_missing
        if not layout_ok:
            report.add_error(f"DietCode runtime layout incomplete: {layout_missing}")

        shims_gone, shim_dirs = legacy_shim_dirs_absent()
        report.checks["legacy_shim_dirs_absent"] = shims_gone
        report.checks["legacy_shim_dirs_present"] = shim_dirs
        if not shims_gone:
            report.add_error(f"Legacy DietCode shim plugins still on disk: {shim_dirs}")

        habitat_gone, habitat_files = removed_habitat_modules_absent()
        report.checks["habitat_modules_absent"] = habitat_gone
        report.checks["habitat_modules_present"] = habitat_files
        if not habitat_gone:
            report.add_error(f"Removed Habitat modules still present: {habitat_files}")

        symlink_ok, symlink_detail = broccolidb_bundle_symlink_ok()
        report.checks["broccolidb_bundle_symlink_ok"] = symlink_ok
        report.checks["broccolidb_bundle_symlink_detail"] = symlink_detail
        if not symlink_ok:
            report.add_warning(f"BroccoliDB plugin bundle layout: {symlink_detail}")

        stale_cfg = scan_stale_joyzoning_config_keys()
        report.checks["stale_joyzoning_config_keys"] = stale_cfg
        if stale_cfg:
            report.add_warning(
                f"config.yaml joyzoning section contains removed keys: {stale_cfg}"
            )

        no_dupes, dupe_issues = duplicate_diet_hooks()
        report.checks["no_duplicate_diet_hooks"] = no_dupes
        if registered and not no_dupes:
            report.add_error(f"Duplicate diet hook registrations: {dupe_issues}")

        from plugins.dietcode.audit import scan_stale_doc_paths

        stale_docs = scan_stale_doc_paths()
        report.checks["stale_doc_paths"] = stale_docs
        if stale_docs:
            report.add_warning(
                f"Fork docs reference removed integration paths ({len(stale_docs)} lines)"
            )
    except Exception as exc:
        report.add_warning(f"Audit checks skipped: {exc}")

    try:
        from hermes_cli.plugins import get_plugin_manager

        pm = get_plugin_manager()
        if not getattr(pm, _GUIDANCE_BUILDER_ATTR, None):
            report.add_warning("Prompt guidance builder not registered on PluginManager")
    except Exception:
        pass

    try:
        from hermes_cli.plugins import get_bundled_plugins_dir
        from plugins.dietcode.paths import is_valid_broccolidb_root

        bundled_plugin = get_bundled_plugins_dir() / "dietcode"
        for rel in (
            "lib/runtime/governance_hooks.py",
            "lib/runtime/joyzoning_hooks.py",
            "lib/runtime/kanban_hooks.py",
            "lib/runtime/jsdp_hooks.py",
            "slash_commands.py",
            "lib/tools/broccolidb.py",
            "audit.py",
            "public.py",
        ):
            if not (bundled_plugin / rel).is_file():
                report.add_error(f"DietCode layout missing required file: {rel}")

        root_pkg = get_bundled_plugins_dir().parent / "broccolidb" / "package.json"
        plugin_pkg = get_bundled_plugins_dir() / "dietcode" / "broccolidb" / "package.json"
        if root_pkg.is_file() and plugin_pkg.is_file():
            import json

            try:
                root_data = json.loads(root_pkg.read_text(encoding="utf-8"))
                plugin_data = json.loads(plugin_pkg.read_text(encoding="utf-8"))
                if root_data.get("version") != plugin_data.get("version"):
                    report.add_warning(
                        "Root broccolidb/ and plugins/dietcode/broccolidb/ version mismatch — sync trees"
                    )
            except (json.JSONDecodeError, OSError):
                pass
        bundled = get_bundled_plugins_dir() / "dietcode" / "broccolidb"
        if not is_valid_broccolidb_root(bundled):
            report.add_warning("Plugin bundle broccolidb/ missing or invalid (run npm ci in bundle)")
    except Exception:
        pass

    return report
