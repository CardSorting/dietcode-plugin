# -*- coding: utf-8 -*-
"""DietCode system-prompt guidance — injected when diet tools are loaded."""
from __future__ import annotations

from typing import AbstractSet

KANBAN_BROCCOLIDB_GUIDANCE = (
    "## BroccoliDB orchestration (when available)\n"
    "\n"
    "When `broccolidb/` is present in the workspace, you also have "
    "`kanban_broccolidb_*` tools that mirror board state into the BroccoliDB "
    "hive layer for durable cross-agent intelligence:\n"
    "\n"
    "1. After `kanban_show()`, call `kanban_broccolidb_context()` to load "
    "linked knowledge and prior decisions for your task.\n"
    "2. Before `kanban_complete()`, call `kanban_broccolidb_record(summary=...)` "
    "for architectural decisions downstream workers should retrieve.\n"
    "3. Orchestrators: call `kanban_broccolidb_board_intel()` before fan-out "
    "to see board status plus BroccoliDB metrics.\n"
    "4. Use `kanban_broccolidb_sync(event=...)` after material lifecycle "
    "changes if auto-sync is disabled.\n"
    "5. Orchestrators: run `kanban_broccolidb_drift()` periodically to "
    "detect kanban/hive mismatches before they compound.\n"
    "6. Before broad exploration in Plan Mode, call `project_map(path=…)` or "
    "`project_map(query=…)` for starting files, risks, and fact-check probes.\n"
)

MUTATION_KERNEL_GUIDANCE = (
    "## Governed native mutation (tool: `dietcode_kernel`)\n"
    "\n"
    "Use `dietcode_kernel` for coherence-aware patches and verification — no external binary.\n"
    "State lives in `.dietcode/mutation-state.json` under the project workspace.\n"
    "\n"
    "| Action | When |\n"
    "|--------|------|\n"
    "| `dietcode_kernel(action='status')` | Workspace revision, tracked hashes, coherence tokens |\n"
    "| `dietcode_kernel(action='search', query=…)` | Literal search before patching |\n"
    "| `dietcode_kernel(action='coherence', paths=[…])` | Issue token before multi-file edits |\n"
    "| `dietcode_kernel(action='patch', path=…, unified_diff=…)` | Governed patch with anchor checks |\n"
    "| `dietcode_kernel(action='verify', command=…)` | Run verification command; journals to JoyZoning |\n"
    "| `dietcode_kernel(action='refresh', paths=[…])` | Refresh file anchors after external edits |\n"
    "\n"
    "Pair with JoyZoning: `joyzoning(action='begin')` → patch → `joyzoning(action='verify')`.\n"
    "ROADMAP.md patches via `dietcode_kernel` receive the same `_roadmap_write_hint` as write_file.\n"
    "Reads via `read_file` auto-track hashes when `HERMES_KANBAN_TASK` is set.\n"
)

ROADMAP_GUIDANCE = (
    "## Auto-rolling roadmap checkpoint (tool: `roadmap`)\n"
    "\n"
    "Maintain `ROADMAP.md` as the project's living steering surface — not a backlog or wishlist.\n"
    "\n"
    "| Call | When |\n"
    "|------|------|\n"
    "| `roadmap(action='guide')` | Phase, health, `_roadmap_operator_hints`, `agent_next_call` |\n"
    "| `roadmap(action='cockpit')` | One-screen operator summary (health, schema, code soup) |\n"
    "| `roadmap(action='checkpoint', context=…)` | Before editing ROADMAP.md — evidence + algorithm + pre-audit |\n"
    "| `roadmap(action='validate')` | After editing — confirm 12-section schema before finishing |\n"
    "| `roadmap(action='template')` | Bootstrap skeleton when ROADMAP.md is missing |\n"
    "| `roadmap(action='apply_bootstrap_fill')` | Preview/write evidence autofill to resolve bootstrap placeholders |\n"
    "| `roadmap(action='doctor')` | Install skill + run production health checks |\n"
    "| `roadmap(action='progress')` | Operator activity summary (JSONL telemetry) |\n"
    "| `roadmap(action='progress', context='--current')` | Full progress + gate snapshot JSON |\n"
    "| `roadmap(action='watch')` | Compact last-action line |\n"
    "| `roadmap(action='explain_stale')` | Why checkpoint may be outdated vs git |\n"
    "| `roadmap(action='explain_gate')` | Closed schema/freshness gates — fixes and next call |\n"
    "| `roadmap(action='last_error')` | Last failure or validation issue |\n"
    "| `roadmap(action='evidence')` | Read-only project signals |\n"
    "| `roadmap(action='status')` | Parse current ROADMAP.md without mutating |\n"
    "\n"
    "Native integration: `joyzoning(action='context')` includes `roadmap_checkpoint` brief and next_actions.\n"
    "Quick steering: `joyzoning(action='roadmap')` returns the roadmap cockpit payload.\n"
    "ROADMAP.md writes via write_file/patch receive `_roadmap_write_hint` → validate before closing.\n"
    "Operator: `/roadmap cockpit` · `/roadmap explain-gate` · `/dietcode roadmap cockpit` · alias `roadmap_checkpoint`\n"
    "Prime directive: did the latest work strengthen or weaken the project's center of gravity?\n"
    "Skill: `auto-rolling-roadmap` at `optional-skills/dietcode/auto-rolling-roadmap/SKILL.md`.\n"
    "Section 9 (Centralization & Code Soup Audit) is mandatory — use `code_soup_pre_audit` from checkpoint.\n"
    "Keep Now to 1–5 actionable items; finish with validate, then return checkpoint summary (not full file).\n"
    "Per-project steering on every response:\n"
    "- `project_identity_line` — one-line brief · stack · verify command\n"
    "- `project_steering_digest` — entity card (CI, quality tools, governance, verify, bootstrap status)\n"
    "- `project_fingerprint` — raw repo signals inside checkpoint `evidence`\n"
    "\n"
    "When bootstrap template phrases remain:\n"
    "- `bootstrap_fill_plan` with `tasks[].suggested_replacement` from evidence\n"
    "- Preview: `roadmap(action='apply_bootstrap_fill')` · Write: `context='write'`\n"
    "\n"
    "ROADMAP.md has 12 required sections (see docs/roadmap.md). Schema-complete ≠ bootstrap-complete.\n"
    "Workspace: set HERMES_KANBAN_WORKSPACE — never write ROADMAP.md in the plugin install tree.\n"
    "Full reference: docs/roadmap.md (config, gates, example JSON, anti-patterns).\n"
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
    "2. `joyzoning(action='operator')` — unified gate brief when kanban_complete is blocked.\n"
    "3. `joyzoning(action='doctor')` if anything looks miswired.\n"
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
    "## Kanban + BroccoliDB linkage\n"
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
    "## Roadmap steering (tool: `roadmap`)\n"
    "\n"
    "Long-horizon coherence: `roadmap_checkpoint` in `joyzoning(action='context')` shows phase and first_call.\n"
    "Quick steering: `joyzoning(action='roadmap')` returns cockpit + `recommended_next_action`.\n"
    "After direction changes: `roadmap(action='checkpoint')` → edit ROADMAP.md → `roadmap(action='validate')`.\n"
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


COMPLETION_GATE_GUIDANCE = (
    "## Quality audit completion gate\n"
    "\n"
    "When `joyzoning.governance.completion_gate.enabled` is true, `kanban_complete` runs a "
    "three-tier gate: JoyZoning convergence → roadmap steering → Spider/hardening score.\n"
    "\n"
    "| Call | When |\n"
    "|------|------|\n"
    "| `joyzoning(action='operator')` | Unified gate brief — `agent_next_call`, `recovery_steps` |\n"
    "| `joyzoning(action='status')` | Convergence + all gate layers |\n"
    "| `roadmap(action='explain_gate')` | Roadmap schema/freshness gates |\n"
    "| `broccolidb_violations()` | Structural findings before complete |\n"
    "| `joyzoning(action='verify', report='…', passed=true)` | Record verification evidence |\n"
    "\n"
    "Do not call `kanban_complete` while `kanban_complete_allowed` is false — pre_tool_call blocks it.\n"
)


def build_dietcode_guidance(valid_tool_names: AbstractSet[str]) -> str:
    """Return DietCode prompt block when matching tools are loaded."""
    if not valid_tool_names:
        return ""

    parts: list[str] = []
    has_joyzoning = "joyzoning" in valid_tool_names
    has_roadmap = "roadmap" in valid_tool_names or "roadmap_checkpoint" in valid_tool_names
    has_broccolidb_bridge = any(n.startswith("kanban_broccolidb_") for n in valid_tool_names)
    has_kanban_worker = "kanban_show" in valid_tool_names
    has_mutation_kernel = "dietcode_kernel" in valid_tool_names
    has_completion_gate = False
    try:
        from plugins.dietcode.lib.agent.features import is_completion_gate_enabled

        has_completion_gate = is_completion_gate_enabled()
    except Exception:
        pass

    if has_roadmap:
        try:
            from plugins.dietcode.lib.agent.roadmap.agent_steering import format_agent_steering_line

            live = format_agent_steering_line()
            if live:
                parts.append(live)
        except Exception:
            pass
        parts.append(ROADMAP_GUIDANCE)
    if has_mutation_kernel:
        parts.append(MUTATION_KERNEL_GUIDANCE)
    if has_joyzoning:
        parts.append(JOYZONING_GUIDANCE)
    elif has_kanban_worker and has_broccolidb_bridge:
        parts.append(KANBAN_BROCCOLIDB_GUIDANCE)
    if has_completion_gate and has_joyzoning:
        parts.append(COMPLETION_GATE_GUIDANCE)

    return "\n\n".join(parts)
