# -*- coding: utf-8 -*-
"""Import DietCode tool modules and track load health."""
from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, FrozenSet

if TYPE_CHECKING:
    from hermes_cli.plugins import PluginContext

logger = logging.getLogger(__name__)

_LIB = "plugins.dietcode.lib.tools"

# Loaded exclusively by the DietCode plugin (not tools/ auto-discovery).
_TOOL_MODULES = (
    f"{_LIB}.broccolidb",
    f"{_LIB}.joyzoning_tools",
    f"{_LIB}.convergence_tools",
    f"{_LIB}.jsdp_harness_tools",
    f"{_LIB}.kanban_broccolidb_tools",
)

# Diet tool modules loaded only via plugins/dietcode/tools_loader.py (not tools/ auto-discovery).
DEFERRED_TOOL_MODULE_STEMS: frozenset[str] = frozenset({
    "broccolidb",
    "joyzoning_tools",
    "convergence_tools",
    "jsdp_harness_tools",
    "kanban_broccolidb_tools",
})

# Minimum surface the dietcode toolset must resolve (behavioral contract).
EXPECTED_DIETCODE_TOOLS: FrozenSet[str] = frozenset({
    "broccolidb_init",
    "broccolidb_queue_status",
    "broccolidb_hive_integrity",
    "joyzoning",
    "mutation_record_patch",
    "convergence_status",
    "jsdp",
    "jsdp_horizon",
    "jsdp_validate_handoff",
    "kanban_broccolidb_board_intel",
    "kanban_broccolidb_sync",
})

_DIETCODE_TOOL_PREFIXES = (
    "broccolidb_",
    "kanban_broccolidb_",
    "mutation_",
    "convergence_",
    "runtime_",
    "jsdp_",
)
_DIETCODE_TOOL_NAMES = frozenset({"joyzoning", "jsdp", "jsdp_horizon"})


@dataclass
class LoadReport:
    loaded: list[str] = field(default_factory=list)
    failed: dict[str, str] = field(default_factory=dict)
    registry_tools: list[str] = field(default_factory=list)
    registry_missing: list[str] = field(default_factory=list)


_CACHED_REPORT: LoadReport | None = None


def invalidate_load_cache() -> None:
    """Clear cached tool load report (e.g. after fixing imports without restart)."""
    global _CACHED_REPORT
    _CACHED_REPORT = None


def _is_dietcode_tool(name: str, toolset: str) -> bool:
    if toolset in {"broccolidb", "joyzoning", "dietcode"}:
        return True
    if name in _DIETCODE_TOOL_NAMES:
        return True
    return name.startswith(_DIETCODE_TOOL_PREFIXES)


def _collect_registry_tools() -> tuple[list[str], list[str]]:
    from tools.registry import registry

    present = sorted(
        name
        for name, entry in registry._tools.items()
        if _is_dietcode_tool(name, entry.toolset) and not name.startswith("_")
    )
    missing = sorted(EXPECTED_DIETCODE_TOOLS - set(present))
    return present, missing


def load_dietcode_tools(ctx: "PluginContext | None" = None, *, force: bool = False) -> LoadReport:
    """Import DietCode tool modules; return structured load report."""
    global _CACHED_REPORT
    if _CACHED_REPORT is not None and not force:
        return _CACHED_REPORT

    report = LoadReport()
    for mod_name in _TOOL_MODULES:
        try:
            importlib.import_module(mod_name)
            report.loaded.append(mod_name)
        except Exception as exc:
            report.failed[mod_name] = str(exc)
            logger.warning("DietCode: could not import tool module %s: %s", mod_name, exc)

    report.registry_tools, report.registry_missing = _collect_registry_tools()

    if ctx is not None:
        try:
            from tools.registry import registry

            for entry in registry._tools.values():
                if _is_dietcode_tool(entry.name, entry.toolset):
                    ctx._manager._plugin_tool_names.add(entry.name)
        except Exception as exc:
            logger.debug("DietCode: plugin tool name tracking skipped: %s", exc)

    if report.registry_missing:
        logger.warning(
            "DietCode: registry missing expected tools: %s",
            ", ".join(report.registry_missing),
        )
    if report.failed:
        logger.warning(
            "DietCode: %d tool module(s) failed to import",
            len(report.failed),
        )

    _CACHED_REPORT = report
    return report


def get_load_report(*, force: bool = False) -> LoadReport:
    """Return cached load report, importing modules on first call."""
    if _CACHED_REPORT is None or force:
        return load_dietcode_tools(force=force)
    return _CACHED_REPORT


def validate_dietcode_toolset() -> list[str]:
    """Return tool names expected by ``dietcode`` toolset that are absent from registry."""
    get_load_report()
    from toolsets import resolve_toolset

    resolved = set(resolve_toolset("dietcode"))
    return sorted(EXPECTED_DIETCODE_TOOLS - resolved)


def register_dietcode_toolset() -> None:
    """Ensure the composite ``dietcode`` toolset exists (static TOOLSETS or runtime)."""
    from toolsets import TOOLSETS, create_custom_toolset

    if "dietcode" not in TOOLSETS:
        create_custom_toolset(
            "dietcode",
            "BroccoliDB, BroccoliQ hive orchestration, JoyZoning, and JSDP rolling-horizon delivery",
            tools=[
                "kanban_broccolidb_context",
                "kanban_broccolidb_sync",
                "kanban_broccolidb_record",
                "kanban_broccolidb_board_intel",
                "kanban_broccolidb_drift",
            ],
            includes=["broccolidb", "joyzoning"],
        )

    missing = validate_dietcode_toolset()
    if missing:
        logger.warning("DietCode toolset missing tools after registration: %s", ", ".join(missing))

