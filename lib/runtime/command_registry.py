# -*- coding: utf-8 -*-
"""Declarative DietCode slash-command registration."""
from __future__ import annotations

import importlib
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CommandSpec:
    name: str
    module: str
    attr: str
    description: str
    args_hint: str


COMMAND_SPECS: tuple[CommandSpec, ...] = (
    CommandSpec(
        "dietcode",
        "plugins.dietcode.health",
        "handle_dietcode_command",
        "DietCode integration health — BroccoliDB, JoyZoning, JSDP.",
        "[status|doctor|tools|broccolidb]",
    ),
    CommandSpec(
        "dc",
        "plugins.dietcode.health",
        "handle_dietcode_command",
        "DietCode integration health (alias).",
        "[status|doctor|tools|broccolidb]",
    ),
    CommandSpec(
        "joyzoning",
        "plugins.dietcode.slash_commands",
        "_handle_joyzoning",
        "JoyZoning layering compliance audit.",
        "[status|check <file>|…]",
    ),
    CommandSpec(
        "jz",
        "plugins.dietcode.slash_commands",
        "_handle_joyzoning",
        "JoyZoning layering audit (alias).",
        "[status|check <file>|…]",
    ),
    CommandSpec(
        "broccolidb",
        "plugins.dietcode.slash_commands",
        "_handle_broccolidb",
        "BroccoliDB epistemic database console.",
        "[status|query|audit|heal]",
    ),
    CommandSpec(
        "bdb",
        "plugins.dietcode.slash_commands",
        "_handle_broccolidb",
        "BroccoliDB console (alias).",
        "[status|query|audit|heal]",
    ),
    CommandSpec(
        "roadmap",
        "plugins.dietcode.slash_commands",
        "_handle_roadmap",
        "Native roadmap checkpoint console.",
        "[cockpit|doctor|checkpoint|validate|guide]",
    ),
    CommandSpec(
        "rm",
        "plugins.dietcode.slash_commands",
        "_handle_roadmap",
        "Roadmap checkpoint console (alias).",
        "[cockpit|doctor|checkpoint|validate|guide]",
    ),
)


def load_command_handler(spec: CommandSpec) -> Any:
    mod = importlib.import_module(spec.module)
    return getattr(mod, spec.attr)


def register_all_commands(ctx) -> None:
    """Register every declared slash command on the Hermes plugin context."""
    for spec in COMMAND_SPECS:
        ctx.register_command(
            spec.name,
            handler=load_command_handler(spec),
            description=spec.description,
            args_hint=spec.args_hint,
        )


def command_registry_summary() -> list[dict[str, str]]:
    return [
        {
            "name": spec.name,
            "handler": f"{spec.module}:{spec.attr}",
            "description": spec.description,
        }
        for spec in COMMAND_SPECS
    ]


def validate_command_registry() -> list[str]:
    failures: list[str] = []
    for spec in COMMAND_SPECS:
        try:
            load_command_handler(spec)
        except Exception as exc:
            failures.append(f"{spec.name}: cannot load {spec.module}.{spec.attr}: {exc}")
    return failures
