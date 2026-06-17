# Tools Reference

DietCode exposes slash commands and registered Hermes tools across BroccoliDB,
JoyZoning, convergence, kanban bridge, and the **native mutation runtime**
(`dietcode_kernel`).

## Slash commands

### `/dietcode`

Integration console.

| Subcommand | Purpose |
| --- | --- |
| `status` | Full integration health report. |
| `doctor` | Strict health report with refreshed tool load state. |
| `tools` | Tool module load report. |
| `broccolidb` | BroccoliDB root and RPC availability. |
| `mutation` | Native mutation health JSON (workspace, revision, drift). |
| `mutation status` | Compact operator summary (workspace revision, coherence tokens). |
| `roadmap` | Roadmap feature health with `project_identity_line`. |
| `roadmap cockpit` | One-screen roadmap operator summary. |

### `/broccolidb`

Knowledge graph and audit console.

| Subcommand | Purpose |
| --- | --- |
| `status` | Connection, knowledge node, edge, and workspace metrics. |
| `query <term>` | Search the knowledge graph. |
| `audit` | Run skeptical sovereignty checks on knowledge nodes. |
| `heal` | Prune unreliable knowledge items. |

### `/joyzoning`

Layering and governance console.

| Subcommand | Purpose |
| --- | --- |
| `status` or `audit` | Structural composition audit. |
| `check <file>` | Validate layer tags and imports for one file. |
| `suggest <file>` | Suggest a layer assignment. |
| `refactor <file>` | Produce a dependency inversion refactor blueprint. |

## Native mutation tool

### `dietcode_kernel`

Governed native mutation runtime (Python port of LUMI `NativeMutationManager`).
State in `.dietcode/mutation-state.json` — no macOS binary or socket bridge.

| Action | Purpose |
| --- | --- |
| `status` | Workspace revision, tracked hashes, coherence tokens |
| `search` | Literal search in workspace |
| `coherence` | Issue coherence token before multi-file edits |
| `patch` | Coherent file mutation with `mutationReceipt` |
| `verify` | Run verification command in workspace |
| `refresh` | Refresh file anchors after external edits |

Patch parameters: `workspace`, `path`, `unified_diff` or `line_search`/`line_replace`,
optional `task_id`, `coherenceTokenId`, `expectedWorkspaceRevision`.

Verify parameters: `workspace`, `command`, optional `cwd`, `task_id`.

Successful patch/verify results are journaled into JoyZoning automatically via
hooks. `read_file` auto-tracks file hashes when `HERMES_KANBAN_TASK` is set.

Implementation: `lib/tools/mutation_tools.py`, `lib/agent/native_mutation.py`.

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

Prefer `dietcode_kernel(action='patch'|'verify')` for governed physical mutation —
JoyZoning hooks journal patch/verify receipts automatically.

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

### Auto-rolling roadmap checkpoint (native toolset: `roadmap`)

**Deep reference:** [roadmap.md](roadmap.md) — decision tree, slash commands, freshness
algorithm, kanban integration, section authoring, contributor guide.

| Tool | Actions | Purpose |
| --- | --- | --- |
| `roadmap` | `guide`, `checkpoint`, `evidence`, `status`, `doctor`, `cockpit`, `validate`, `template`, `progress`, `watch`, `last_error`, `explain_stale`, `explain_gate`, `apply_bootstrap_fill` | Per-project steering for `ROADMAP.md` |
| `roadmap_checkpoint` | Alias actions | Compatibility alias for `roadmap` |

#### Per-project response fields

Every roadmap action returns (via `clarity_envelope`):

- `project_identity_line` — one-line brief · stack · verify
- `project_steering_digest` — CI, quality tools, governance, verify commands, bootstrap status
- `steering_line` — multi-line live steering for prompts
- `_roadmap_operator_hints` — `write_guard`, `next_action`, `recovery_suggestion`

When bootstrap template phrases remain: `bootstrap_fill_plan`, optional
`bootstrap_autofill_preview`, and `roadmap(action='apply_bootstrap_fill')`.

#### Native integration

- `joyzoning(action='context')` → session brief, `project_identity_line`, merged `next_actions`
- `joyzoning(action='roadmap')` → cockpit payload with `recommended_next_action`
- `/dietcode roadmap cockpit` → roadmap steering merged (Project, Identity, Verify)
- `session.start` → roadmap phase, `first_call`, steering digest
- Writes to `ROADMAP.md` → `_roadmap_write_hint` → `roadmap(action='validate')`
- Tool calls → `roadmap.*` journal events with identity in progress telemetry

Slash commands:

| Command | Purpose |
| --- | --- |
| `/roadmap cockpit` | One-screen operator summary |
| `/roadmap doctor` | Install skill + health checks (shows Identity line) |
| `/roadmap explain-gate` | Closed gates and kanban_complete policy |
| `/roadmap checkpoint [context]` | Checkpoint briefing; `apply autofill preview/write` contexts |
| `/roadmap progress --current` | Full progress + gate snapshot JSON |
| `/dietcode roadmap` | Feature health JSON with `project_identity_line` |
| `/dietcode roadmap cockpit` | Cockpit via dietcode console |

Skill: `optional-skills/dietcode/auto-rolling-roadmap/SKILL.md` (auto-installed when `dietcode.roadmap.auto_install_skills` is true).

Verification: `make verify` (smoke + audit + operator smoke + unit tests)

## Kanban bridge tools

Registered from `lib/tools/kanban_broccolidb_tools.py` and
`lib/tools/kanban_broccolidb_bridge.py`. Mirror kanban state into
BroccoliDB and enforce JoyZoning completion gates when kanban task
environment is available.

## Raw Hermes write tools

| Tool | Native mutation interaction |
| --- | --- |
| `write_file` | ROADMAP.md writes receive `_roadmap_write_hint`; pair with JoyZoning |
| `patch` | Same ROADMAP.md nudges; prefer `dietcode_kernel` for coherence-aware edits |
| `read_file` | Auto-tracks file hashes for active kanban task (`HERMES_KANBAN_TASK`) |
| `dietcode_kernel` | Preferred governed mutation path |

## Operator scripts

| Script | Purpose |
| --- | --- |
| `scripts/roadmap_audit.py` | Production roadmap audit |
| `scripts/roadmap_smoke.py` | Roadmap smoke checks |
| `scripts/roadmap_operator_smoke.py` | Operator ergonomics smoke |

See [roadmap.md](roadmap.md) and [architecture.md](architecture.md).
