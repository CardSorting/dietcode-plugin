# Tools Reference

DietCode exposes both slash commands and registered Hermes tools.

## Slash Commands

### `/dietcode`

Integration console.

| Subcommand | Purpose |
| --- | --- |
| `status` | Full integration health report. |
| `doctor` | Strict health report with refreshed tool load state. |
| `tools` | Tool module load report. |
| `broccolidb` | BroccoliDB root and RPC availability. |

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

## BroccoliDB Tools

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

Additional structural tools are registered from
`lib/tools/broccolidb_tools/structural_tools.py` and JoyZoning-specific
BroccoliDB helpers are registered from
`lib/tools/broccolidb_tools/joyzoning_tools.py`.

## JoyZoning Tools

### `joyzoning`

Unified governed-work primitive. Supported actions:

| Action | Purpose |
| --- | --- |
| `context` | Load operational context for the active scope. |
| `doctor` | Run JoyZoning checks. |
| `status` | Read convergence state. |
| `begin` | Start a mutation scope. |
| `patch` | Record substantive patching. |
| `verify` | Record verification results. |
| `request_review` | Move the scope to review. |
| `events` | Tail runtime journal events. |
| `role_context` | Load JSDP role context. |
| `validate_handoff` | Validate JSDP handoff text. |

### Granular lifecycle tools

| Tool | Purpose |
| --- | --- |
| `convergence_status` | Read convergence state. |
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

## Kanban Bridge Tools

DietCode also registers kanban bridge tools from
`lib/tools/kanban_broccolidb_tools.py` and
`lib/tools/kanban_broccolidb_bridge.py`. These tools mirror kanban state into
BroccoliDB/BroccoliQ and enforce JoyZoning completion gates when kanban task
environment is available.
