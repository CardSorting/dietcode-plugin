# -*- coding: utf-8 -*-
"""Declarative DietCode hook chains — single source for registration order."""
from __future__ import annotations

import importlib
from typing import Any, Callable

# (module_path, handler_attribute)
HookSpec = tuple[str, str]

HOOK_CHAINS: dict[str, tuple[HookSpec, ...]] = {
    "on_session_start": (
        ("plugins.dietcode.lib.runtime.kanban_hooks", "_on_session_start"),
        ("plugins.dietcode.lib.runtime.joyzoning_hooks", "_on_session_start"),
        ("plugins.dietcode.lib.runtime.jsdp_hooks", "_on_session_start"),
        ("plugins.dietcode.lib.runtime.roadmap_hooks", "_on_session_start"),
    ),
    "on_session_end": (
        ("plugins.dietcode.lib.runtime.joyzoning_hooks", "_on_session_end"),
        ("plugins.dietcode.lib.runtime.roadmap_hooks", "_on_session_end"),
    ),
    "post_tool_call": (
        ("plugins.dietcode.lib.runtime.joyzoning_hooks", "_post_tool_call"),
        ("plugins.dietcode.lib.runtime.mutation_hooks", "_post_tool_call"),
        ("plugins.dietcode.lib.runtime.kanban_hooks", "_on_post_tool_call"),
        ("plugins.dietcode.lib.runtime.roadmap_hooks", "_post_tool_call"),
        ("plugins.dietcode.lib.runtime.audit_hooks", "_post_tool_call"),
    ),
    "pre_tool_call": (
        ("plugins.dietcode.lib.runtime.joyzoning_hooks", "_pre_tool_call"),
        ("plugins.dietcode.lib.runtime.roadmap_hooks", "_pre_tool_call"),
    ),
    "transform_tool_result": (
        ("plugins.dietcode.lib.runtime.mutation_hooks", "on_mutation_journal_transform"),
        ("plugins.dietcode.lib.runtime.roadmap_hooks", "on_roadmap_write_transform"),
        ("plugins.dietcode.lib.runtime.governance_hooks", "on_transform_tool_result"),
    ),
}


def load_hook_chain(hook_name: str) -> tuple[Callable[..., Any], ...]:
    """Import and return handlers for a hook chain (cached by caller)."""
    specs = HOOK_CHAINS.get(hook_name, ())
    handlers: list[Callable[..., Any]] = []
    for module_path, attr in specs:
        mod = importlib.import_module(module_path)
        handlers.append(getattr(mod, attr))
    return tuple(handlers)


def validate_hook_registry() -> list[str]:
    """Return human-readable failures when declared hook handlers are missing."""
    failures: list[str] = []
    for hook_name, specs in HOOK_CHAINS.items():
        for module_path, attr in specs:
            try:
                mod = importlib.import_module(module_path)
            except Exception as exc:
                failures.append(f"{hook_name}: cannot import {module_path}: {exc}")
                continue
            if not hasattr(mod, attr):
                failures.append(f"{hook_name}: {module_path} missing attribute {attr}")
    return failures
