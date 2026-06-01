# Tools reference

All DietCode tools register through the plugin's `tools_loader.py`. They appear when the
`dietcode` toolset is enabled.

**Contract tools** (must always resolve — checked by `/dietcode doctor`):

`broccolidb_init`, `broccolidb_queue_status`, `broccolidb_hive_integrity`, `joyzoning`,
`mutation_record_patch`, `convergence_status`, `jsdp`, `jsdp_horizon`, `jsdp_validate_handoff`,
`kanban_broccolidb_board_intel`, `kanban_broccolidb_sync`

---

## joyzoning (primary primitive)

| Tool | Description |
|------|-------------|
| `joyzoning` | Unified action dispatch: `context`, `doctor`, `begin`, `patch`, `verify`, `request_review`, `role_context`, etc. |

Prefer `joyzoning` over granular mutation tools for agent workflows — it encodes the full lifecycle.

---

## Mutation & convergence

| Tool | Description |
|------|-------------|
| `mutation_begin` | Open bounded mutation scope |
| `mutation_record_patch` | Record patch summary after edits |
| `mutation_verify` | Attach verification evidence |
| `convergence_status` | Current convergence state for scope |
| `convergence_request_review` | Transition to ReadyForReview |
| `convergence_mark_converged` | Mark scope converged (after operator approval) |
| `runtime_events_tail` | Tail local runtime event journal |
| `jsdp_validate_handoff` | Validate JSDP handoff payload |
| `jsdp_role_context` | Load JSDP role bindings at session start |

---

## JSDP harness

| Tool | Description |
|------|-------------|
| `jsdp` | JSDP harness operations |
| `jsdp_horizon` | Horizon / bounded planning surface |

Requires `joyzoning.jsdp.enabled` and appropriate env (`JOYZONING_JSDP_ROLE`, etc.).

---

## BroccoliDB — core

| Tool | Description |
|------|-------------|
| `broccolidb_init` | Initialize workspace / database |
| `broccolidb_status` | Runtime status |
| `broccolidb_audit` | Structural audit |
| `broccolidb_refactor` | Refactoring specifications |

---

## BroccoliDB — queue / hive (BroccoliQ)

| Tool | Description |
|------|-------------|
| `broccolidb_queue_status` | Queue depth and shard metrics |
| `broccolidb_shard_status` | Per-shard health |
| `broccolidb_hive_integrity` | Hive layer integrity check |

---

## BroccoliDB — graph / knowledge

| Tool | Description |
|------|-------------|
| `broccolidb_add_knowledge` | Insert knowledge node |
| `broccolidb_query_graph` | Graph query |
| `broccolidb_get_task_context` | Task-linked context retrieval |
| `broccolidb_append_shared_memory` | Shared memory append |
| `broccolidb_verify_sovereignty` | Sovereignty / isolation check |

---

## BroccoliDB — structural analysis

| Tool | Description |
|------|-------------|
| `broccolidb_blast_radius` | Change impact radius |
| `broccolidb_study_pack` | Study pack generation |
| `broccolidb_entropy` | Codebase entropy metrics |
| `broccolidb_detect_cycles` | Dependency cycle detection |
| `broccolidb_verify_integrity` | Graph integrity |
| `broccolidb_heal` | Self-heal pass |
| `broccolidb_violations` | List layering violations |

---

## BroccoliDB — JoyZoning (TS-side)

| Tool | Description |
|------|-------------|
| `broccolidb_joyzoning_audit` | Full codebase layering audit via SpiderEngine |
| `broccolidb_joyzoning_refactor` | Refactor specs from layering analysis |
| `broccolidb_validate_file` | Single-file layer validation |
| `broccolidb_suggest_layer` | Suggest optimal layer for a file |
| `broccolidb_check_layering` | Layering compliance check |

These invoke TypeScript via the BroccoliDB RPC worker. Require `npm ci` and warm RPC.

---

## Kanban ↔ BroccoliDB bridge

| Tool | Description |
|------|-------------|
| `kanban_broccolidb_context` | Load hive intelligence for current kanban task |
| `kanban_broccolidb_sync` | Push lifecycle event to hive |
| `kanban_broccolidb_record` | Record architectural decision before complete |
| `kanban_broccolidb_board_intel` | Board + queue combined intel (orchestrators) |
| `kanban_broccolidb_drift` | Detect kanban/hive state drift |

Requires Hermes kanban tooling and BroccoliDB root in workspace or plugin bundle.

---

## Toolset membership

Tools are tagged with toolsets `dietcode`, `broccolidb`, and/or `joyzoning`.
The aggregate `dietcode` toolset in `toolsets.py` (fork) or your `config.yaml` `toolsets` list
controls agent visibility.

Check resolution:

```bash
/dietcode tools
hermes tools   # interactive toolset UI
```
