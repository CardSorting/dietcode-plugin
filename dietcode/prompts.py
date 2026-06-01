# -*- coding: utf-8 -*-
"""DietCode system-prompt guidance — injected when diet tools are loaded."""
from __future__ import annotations

from typing import AbstractSet

KANBAN_BROCCOLIQ_GUIDANCE = (
    "## BroccoliQ orchestration (when available)\n"
    "\n"
    "When `broccolidb/` is present in the workspace, you also have "
    "`kanban_broccolidb_*` tools that mirror board state into the BroccoliQ "
    "hive layer for durable cross-agent intelligence:\n"
    "\n"
    "1. After `kanban_show()`, call `kanban_broccolidb_context()` to load "
    "linked knowledge and prior decisions for your task.\n"
    "2. Before `kanban_complete()`, call `kanban_broccolidb_record(summary=...)` "
    "for architectural decisions downstream workers should retrieve.\n"
    "3. Orchestrators: call `kanban_broccolidb_board_intel()` before fan-out "
    "to see board status plus BroccoliQ queue/shard health.\n"
    "4. Use `kanban_broccolidb_sync(event=...)` after material lifecycle "
    "changes if auto-sync is disabled.\n"
    "5. Orchestrators: run `kanban_broccolidb_drift()` periodically to "
    "detect kanban/hive mismatches before they compound.\n"
)

JOYZONING_GUIDANCE = (
    "# JoyZoning governed work (use `joyzoning` as your primary primitive)\n"
    "\n"
    "Hermes owns execution state. JSDP synthesizes bounded mutations. "
    "Do not collapse these layers.\n"
    "\n"
    "## Start every governed session\n"
    "\n"
    "1. `joyzoning(action='context')` — scope bindings, convergence state, next_actions.\n"
    "2. `joyzoning(action='doctor')` if anything looks miswired.\n"
    "\n"
    "## Mutation lifecycle (plan → patch → verify → review → converge)\n"
    "\n"
    "Use `joyzoning` actions (or the granular `mutation_*` / `convergence_*` tools):\n"
    "\n"
    "1. `joyzoning(action='begin', goal=...)` — open bounded mutation scope.\n"
    "2. Implement changes (`patch`, `write_file`). When `joyzoning.governance.layer_tags_required` "
    "is enabled, the DietCode governance hook may block layer-tag/import violations on governable "
    "`.ts`/`.js` source (not `.md`, `package.json`, migrations, or DB/ORM artifacts). "
    "Layer tags are **optional by default**. Call `joyzoning(action='patch', mutation_id=..., summary=...)` "
    "after substantive edits.\n"
    "3. `joyzoning(action='verify', mutation_id=..., report=...)` — verification evidence.\n"
    "4. `joyzoning(action='request_review', summary=...)` — ReadyForReview; stop here.\n"
    "5. After operator approval: `convergence_mark_converged(...)`.\n"
    "6. Only then `kanban_complete(...)` — pre_tool_call gate blocks early complete.\n"
    "\n"
    "## Kanban + BroccoliQ linkage\n"
    "\n"
    "When spawned as a kanban worker, env carries `HERMES_KANBAN_TASK` and "
    "`JOYZONING_SCOPE_ID`. Call `kanban_broccolidb_context()` after `kanban_show()` "
    "for hive intelligence.\n"
    "\n"
    "## JSDP bounded roles (when enabled)\n"
    "\n"
    "- `joyzoning(action='role_context')` at session start.\n"
    "- `joyzoning(action='validate_handoff', text=...)` before handoff.\n"
    "- One role per session — do not solve future chain roles.\n"
    "\n"
    "## JSDP autonomous delivery (tool: `jsdp`)\n"
    "\n"
    "Kanban dispatch needs no extra Hermes config. Agents use four calls:\n"
    "\n"
    "| Call | When |\n"
    "|------|------|\n"
    "| `jsdp(action='start')` | Session begin — auto `.jsdp/`, planning context |\n"
    "| `jsdp(action='apply', proposal_json=…)` | After you write ≤5 horizon nodes (JSON) |\n"
    "| `jsdp(action='advance')` | Repeat until done — harness picks next/verify/continue |\n"
    "| `jsdp(action='guide')` | Unsure — returns `phase`, `operator_summary`, `agent_next_call` |\n"
    "\n"
    "Read `phase` and `agent_next_call` in every response. Skill: `jsdp-rolling-horizon`.\n"
    "\n"
    "## Do NOT\n"
    "\n"
    "- Do not skip `request_review` before `kanban_complete` on governed tasks.\n"
    "- Do not call `kanban_complete` before `convergence_mark_converged` when review gate is on.\n"
    "\n"
    "## When governance blocks a mutation\n"
    "\n"
    "- Tool results containing `[GOVERNANCE FAULT]` are **layering policy**, "
    "not provider safety refusals.\n"
    "- Do **not** apologize, refuse, or stop using tools. Follow `recovery_plan` "
    "with `read_file` / `search_files`, fix the layer tag or import direction, "
    "then retry the mutation **once**.\n"
    "- Do **not** retry the same blocked write/patch unchanged — that spirals.\n"
)


def build_dietcode_guidance(valid_tool_names: AbstractSet[str]) -> str:
    """Return DietCode prompt block when matching tools are loaded."""
    if not valid_tool_names:
        return ""

    parts: list[str] = []
    has_joyzoning = "joyzoning" in valid_tool_names
    has_broccoliq_bridge = any(n.startswith("kanban_broccolidb_") for n in valid_tool_names)
    has_kanban_worker = "kanban_show" in valid_tool_names

    if has_joyzoning:
        parts.append(JOYZONING_GUIDANCE)
    elif has_kanban_worker and has_broccoliq_bridge:
        parts.append(KANBAN_BROCCOLIQ_GUIDANCE)

    return "\n\n".join(parts)
