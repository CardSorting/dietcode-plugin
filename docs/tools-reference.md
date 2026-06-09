# Tools Reference

DietCode exposes slash commands and registered Hermes tools across BroccoliDB,
JoyZoning, convergence, kanban bridge, and the **kernel authority bridge**.

## Slash commands

### `/dietcode`

Integration console.

| Subcommand | Purpose |
| --- | --- |
| `status` | Full integration health report. |
| `doctor` | Strict health report with refreshed tool load state. |
| `tools` | Tool module load report. |
| `broccolidb` | BroccoliDB root and RPC availability. |
| `kernel` | Full kernel health JSON (binary, socket, bridge, workspace, verify). |
| `kernel status` | Compact operator summary (bridge, policy, gates, allowlist count). |
| `kernel progress` | Human summary of current operation phase. |
| `kernel progress --timeline` | Ordered phase timeline with per-phase durations. |
| `kernel progress --last N` | Summarize last N operations (id, action, status, duration). |
| `kernel progress --operation <id>` | Filter `--tail` / `--timeline` to one operation. |
| `kernel progress --tail` | JSON tail of `~/.dietcode/session/kernel-progress.jsonl`. |
| `kernel progress --current` | Full current-state JSON snapshot. |
| `kernel last-error` | Last normalized kernel bridge error envelope. |
| `kernel explain-gate` | Closed gates, config/env fixes, raw-write behavior. |
| `kernel perf --last 10` | Phase timing breakdown (p50/p95 per bucket). |
| `kernel perf --ux --last 10` | Perceived responsiveness (ack latency, silent gaps). |
| `kernel watch` | Compact single-line live operation summary. |
| `kernel watch --follow` | Auto-refresh summary every ~1.5s (up to 30s). |
| `kernel cockpit` | One-screen summary: state, gates, last patch/verify, next action. |

### `/broccolidb`

Knowledge graph and audit console.

| Subcommand | Purpose |
| --- | --- |
| `status` | Connection, knowledge node, edge, and workspace metrics. |
| `query <term>` | Search the knowledge graph. |
| `audit` | Run skeptical sovereignty checks on knowledge nodes. |
| `heal` | Prune unreliable knowledge items. |

### `/broccoliq`

Sharded queue console.

| Subcommand | Purpose |
| --- | --- |
| `queue` | Job counts by status across shards. |
| `shards` | Active shard list and health. |
| `integrity` | One-shot IntegrityWorker audit. |

### `/joyzoning`

Layering and governance console.

| Subcommand | Purpose |
| --- | --- |
| `status` or `audit` | Structural composition audit. |
| `check <file>` | Validate layer tags and imports for one file. |
| `suggest <file>` | Suggest a layer assignment. |
| `refactor <file>` | Produce a dependency inversion refactor blueprint. |

## Kernel bridge tool

### `dietcode_kernel`

Governed macOS kernel bridge. Requires opt-in config (`mutations_enabled: true`
for patch; verify available when bridge healthy).

| Action | Purpose | Gate |
| --- | --- | --- |
| `status` | Kernel workspace status via RPC | Bridge enabled |
| `search` | Literal search in workspace | Safe workspace + socket |
| `patch` | Coherent file mutation with `mutationReceipt` | Patch gate open |
| `verify` | Run allowlisted `verify.run` command | Safe workspace + socket |

Patch parameters: `workspace`, `path`, `unified_diff` or `line_search`/`line_replace`, optional `task_id`.

Verify parameters: `workspace`, `command`, optional `cwd`, `task_id`.

Default verify allowlist prefixes: `make test`, `make kernel`, `git diff --check`,
`npm test`, `./verify.sh`. Extend via `dietcode.kernel.bridge.verify_allowlist`.

Successful patch/verify results are journaled into JoyZoning automatically via
hooks. Kanban completion is **not** auto-triggered.

Implementation: `lib/tools/kernel_bridge_tools.py`, `lib/agent/kernel_bridge_client.py`.

## BroccoliDB tools

| Tool | Purpose |
| --- | --- |
| `broccolidb_init` | Initialize and index the current repository. |
| `broccolidb_status` | Report context graph health and statistics. |
| `broccolidb_audit` | Run a full structural audit. |
| `broccolidb_refactor` | Generate a refactoring plan for a file. |
| `broccolidb_add_knowledge` | Add a knowledge graph node. |
| `broccolidb_query_graph` | Search the knowledge graph. |
| `broccolidb_get_task_context` | Retrieve context for a task. |
| `broccolidb_append_shared_memory` | Add a global shared rule. |
| `broccolidb_verify_sovereignty` | Audit a knowledge node's confidence. |
| `broccolidb_queue_status` | Report queue jobs grouped by status. |
| `broccolidb_shard_status` | Report shard health. |
| `broccolidb_hive_integrity` | Run a sharded integrity audit. |

Additional tools: `lib/tools/broccolidb_tools/structural_tools.py`,
`lib/tools/broccolidb_tools/joyzoning_tools.py`.

## JoyZoning tools

### `joyzoning`

Unified governed-work primitive.

| Action | Purpose |
| --- | --- |
| `context` | Load operational context for the active scope. |
| `doctor` | Run JoyZoning checks. |
| `status` | Read convergence state. |
| `begin` | Start a mutation scope. |
| `patch` | Record substantive patching (lifecycle journal). |
| `verify` | Record verification results (lifecycle journal). |
| `request_review` | Move the scope to review. |
| `events` | Tail runtime journal events. |
| `role_context` | Load JSDP role context. |
| `validate_handoff` | Validate JSDP handoff text. |

When the kernel bridge is active, prefer `dietcode_kernel(action='patch'|'verify')`
for physical mutation — JoyZoning hooks journal kernel receipts automatically.

### Granular lifecycle tools

| Tool | Purpose |
| --- | --- |
| `convergence_status` | Read convergence state and `kanban_complete_allowed`. |
| `mutation_begin` | Start a bounded mutation. |
| `mutation_record_patch` | Record a patch summary. |
| `mutation_verify` | Record verification results. |
| `convergence_request_review` | Request operator review. |
| `convergence_mark_converged` | Mark a reviewed scope converged. |
| `runtime_events_tail` | Read recent runtime events. |
| `jsdp_validate_handoff` | Validate required JSDP handoff sections. |
| `jsdp_role_context` | Load bounded-role JSDP context. |

### JSDP rolling horizon

| Tool | Actions | Purpose |
| --- | --- | --- |
| `jsdp` | `guide`, `start`, `apply`, `advance` | Autonomous rolling-horizon delivery loop. |
| `jsdp_horizon` | Alias actions | Compatibility alias for `jsdp`. |

## Kanban bridge tools

Registered from `lib/tools/kanban_broccolidb_tools.py` and
`lib/tools/kanban_broccolidb_bridge.py`. Mirror kanban state into
BroccoliDB/BroccoliQ and enforce JoyZoning completion gates when kanban task
environment is available.

## Raw Hermes write tools

| Tool | Kernel bridge interaction |
| --- | --- |
| `write_file` | Warn/block when patch gate open (policy-dependent) |
| `patch` | Warn/block when patch gate open (policy-dependent) |
| `read_file` | Never blocked by kernel router |
| `dietcode_kernel` | Never blocked — preferred mutation path |

Warning metadata: `_kernel_raw_write_warning` with `string_code: kernel_raw_write_warn`.
Block payload: `string_code: kernel_raw_write_blocked`, `preferred_tool: dietcode_kernel`.

## Operator scripts

| Script | Purpose |
| --- | --- |
| `scripts/kernel_phase3_rehearsal.py` | Raw write warn + kernel patch + journal |
| `scripts/kernel_bridge_e2e.py` | Full loop: patch → verify → journal → convergence |

See [kernel-bridge-operations.md](kernel-bridge-operations.md).
