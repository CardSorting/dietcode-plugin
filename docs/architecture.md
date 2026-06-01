# Architecture

DietCode is split into a Python Hermes plugin surface and a bundled TypeScript
BroccoliDB runtime.

## Runtime Layers

| Path | Responsibility |
| --- | --- |
| `plugin.yaml` | Hermes manifest and hook declaration. |
| `_bootstrap.py` | Aliases the plugin tree to `plugins.dietcode` for drag-and-drop installs. |
| `hooks.py` | Registers composed Hermes hook handlers. |
| `public.py` | Stable import surface for plugin hooks and slash commands. |
| `tools_loader.py` | Imports tool modules and validates expected registry entries. |
| `health.py` | Builds `/dietcode status` and `/dietcode doctor` reports. |
| `contracts.py` | Runtime contract checks for hooks, tools, layout, and docs. |
| `audit.py` | Static and runtime audits for stale paths, layout parity, and duplicate hooks. |
| `lib/runtime/` | Hook implementations for governance, kanban, JoyZoning, and JSDP. |
| `lib/tools/` | Hermes tool registrations and Python facades. |
| `lib/agent/joyzoning/` | JoyZoning config, journal, convergence, scope, and JSDP helpers. |
| `broccolidb/` | TypeScript package for graph, policy, database, queue, and RPC logic. |

## Hook Flow

`hooks.py` composes the plugin hooks into one DietCode-owned callback per hook
type. This avoids duplicate hook registration while still letting specialized
runtime modules handle their own concerns.

Flow:

1. Hermes discovers and enables the plugin.
2. `_bootstrap.py` ensures absolute imports under `plugins.dietcode.*` resolve.
3. `hooks.register(ctx)` registers DietCode callbacks with the Hermes plugin
   manager.
4. `tools_loader.load_dietcode_tools()` imports tool modules so their registry
   decorators run.
5. `health.build_status_report()` checks hook state, tool registration, runtime
   contracts, BroccoliDB, JoyZoning, and JSDP.

## Tool Loading

The composite `dietcode` toolset is expected to include tools from these
domains:

- `broccolidb`: graph, audit, refactor, structural analysis, and queue tools.
- `joyzoning`: mutation lifecycle, convergence, runtime events, and JSDP tools.
- kanban bridge tools: task sync and completion gates backed by BroccoliDB.

`tools_loader.py` owns module import order and reports missing or failed modules
through `/dietcode tools`.

## BroccoliDB Boundary

Python tools do not directly reimplement the TypeScript database and graph
logic. They call into `broccolidb/` through:

- CLI commands in `broccolidb/cli/index.ts`.
- one-shot TypeScript execution for isolated commands.
- a persistent JSON-RPC worker at `broccolidb/infrastructure/hermes/hermes_rpc.ts`.
- AgentContext RPC helpers for graph and knowledge operations.

This keeps Hermes-facing Python code thin and leaves database, graph, and policy
behavior in the TypeScript package.

## State And Scope

DietCode scopes work with Hermes and JoyZoning identifiers:

- `HERMES_KANBAN_TASK`
- `HERMES_KANBAN_WORKSPACE`
- `HERMES_KANBAN_RUN_ID`
- `HERMES_SESSION_ID`
- `JOYZONING_SCOPE_ID`

JoyZoning resolves an explicit scope first, then environment-provided task or
session identifiers, then falls back to `default`.
