# -*- coding: utf-8 -*-
"""DietCode unified plugin — BroccoliDB, BroccoliQ, JoyZoning, and JSDP for upstream Hermes."""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path


def _run_namespace_bootstrap() -> None:
    """Drag-and-drop: Hermes loads ``hermes_plugins.dietcode``; alias ``plugins.dietcode``."""
    bootstrap_path = Path(__file__).resolve().parent / "_bootstrap.py"
    spec = importlib.util.spec_from_file_location("dietcode__bootstrap", bootstrap_path)
    if spec is None or spec.loader is None:
        return
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.ensure_namespace(globals().get("__name__", ""))


_run_namespace_bootstrap()

from plugins.dietcode.health import handle_dietcode_command
from plugins.dietcode.hooks import register_all_hooks
from plugins.dietcode.prompts import build_dietcode_guidance
from plugins.dietcode.tools_loader import load_dietcode_tools, register_dietcode_toolset

_GUIDANCE_BUILDER_ATTR = "_dietcode_guidance_builder"

logger = logging.getLogger(__name__)


def _already_registered(ctx) -> bool:
    return bool(getattr(ctx._manager, "_dietcode_registered", False))


def _mark_registered(ctx) -> None:
    ctx._manager._dietcode_registered = True


def _register_commands(ctx) -> None:
    from plugins.dietcode.slash_commands import (
        _handle_broccolidb,
        _handle_broccoliq,
        _handle_joyzoning,
    )

    ctx.register_command(
        "dietcode",
        handler=handle_dietcode_command,
        description="DietCode integration health — BroccoliDB, BroccoliQ, JoyZoning, JSDP.",
        args_hint="[status|doctor|tools|broccolidb]",
    )
    ctx.register_command(
        "dc",
        handler=handle_dietcode_command,
        description="DietCode integration health (alias).",
        args_hint="[status|doctor|tools|broccolidb]",
    )
    for name, handler, desc, hint in (
        ("joyzoning", _handle_joyzoning, "JoyZoning layering compliance audit.", "[status|check <file>|…]"),
        ("jz", _handle_joyzoning, "JoyZoning layering audit (alias).", "[status|check <file>|…]"),
        ("broccolidb", _handle_broccolidb, "BroccoliDB epistemic database console.", "[status|query|audit|heal]"),
        ("bdb", _handle_broccolidb, "BroccoliDB console (alias).", "[status|query|audit|heal]"),
        ("broccoliq", _handle_broccoliq, "BroccoliQ sharded queue and hive infrastructure.", "[queue|shards|integrity]"),
        ("bq", _handle_broccoliq, "BroccoliQ console (alias).", "[queue|shards|integrity]"),
    ):
        ctx.register_command(name, handler=handler, description=desc, args_hint=hint)


def register(ctx) -> None:
    """Entry point for the Hermes plugin loader (idempotent per PluginManager)."""
    if _already_registered(ctx):
        logger.debug("DietCode plugin already registered on this manager — skipping")
        return

    report = load_dietcode_tools(ctx)
    register_dietcode_toolset()
    register_all_hooks(ctx)
    _register_commands(ctx)

    ctx._manager.__dict__[_GUIDANCE_BUILDER_ATTR] = build_dietcode_guidance

    try:
        from plugins.dietcode.install import apply_seamless_defaults, ensure_broccolidb_runtime

        apply_seamless_defaults(save=True)
        runtime = ensure_broccolidb_runtime(auto_npm=False)
        if not runtime.get("ok") and runtime.get("action") == "npm_ci_required":
            logger.info(
                "DietCode: BroccoliDB needs npm ci — run: %s",
                runtime.get("hint", "cd broccolidb && npm ci"),
            )
    except Exception as exc:
        logger.debug("DietCode seamless setup skipped: %s", exc)

    _mark_registered(ctx)
    logger.info(
        "DietCode: registered (%d tool modules, %d registry tools, %d hook chains)",
        len(report.loaded),
        len(report.registry_tools),
        5,
    )
    if report.failed:
        logger.warning("DietCode: tool import failures: %s", list(report.failed.keys()))
