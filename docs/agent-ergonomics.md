# Agent ergonomics

Operator workflow for governed mutation cycles and long-horizon roadmap steering.
Distilled from LUMI / codemarie-new — native mutation replaces the legacy macOS
socket bridge.

## Native mutation operator loop

```text
1. /dietcode mutation status          → workspace revision, drift, coherence tokens
2. dietcode_kernel(action='status')   → same via tool JSON
3. dietcode_kernel(action='coherence', paths=[…])  → before multi-file edits
4. dietcode_kernel(action='patch')    → governed mutation with receipts
5. dietcode_kernel(action='verify')   → run verification command
6. joyzoning(action='verify')         → journal verification into lifecycle
7. convergence_status                 → kanban_complete_allowed gate
```

State lives in `.dietcode/mutation-state.json` under the project workspace.
`read_file` auto-tracks file hashes when `HERMES_KANBAN_TASK` is set.

### Storage

| Path | Purpose |
| --- | --- |
| `.dietcode/mutation-state.json` | Workspace revision, tracked hashes, coherence tokens |
| `.dietcode/mutation-history.json` | Optional local mutation receipt history |
| `~/.dietcode/session/mutation-receipts.json` | Session-scoped receipt tail |

### Slash commands

| Command | Output |
| --- | --- |
| `/dietcode mutation` | Native mutation health JSON |
| `/dietcode mutation status` | Compact workspace revision + drift summary |
| `/dietcode doctor` | Full integration health (includes mutation probe) |

### Agent-facing hints

`dietcode_kernel` patch/verify results are journaled into JoyZoning via
`post_tool_call` hooks. Pair governed patches with `joyzoning(action='begin')`
and `joyzoning(action='patch')` for lifecycle coherence.

ROADMAP.md writes (via `write_file`, `patch`, or `dietcode_kernel`) receive
`_roadmap_write_hint` with `preferred_command: roadmap(action='validate')`.

### When mutation feels wrong

1. **Check workspace** — `HERMES_KANBAN_WORKSPACE` must point at the project root, not the plugin install tree.
2. **Check status** — `dietcode_kernel(action='status')` for revision drift and coherence token expiry.
3. **Refresh anchors** — `dietcode_kernel(action='refresh', paths=[…])` after external edits.
4. **Re-issue coherence** — `dietcode_kernel(action='coherence', paths=[…])` before retrying patch.
5. **Explain roadmap gates** — `/roadmap explain-gate` when kanban_complete is blocked.

## Roadmap checkpoint operator loop

Long-horizon steering surface for product and architecture coherence. Every
response is **scoped to the resolved Hermes project workspace** via
`project_fingerprint` → `project_steering_digest` → `project_identity_line`.

**Full reference:** [roadmap.md](roadmap.md) — schema contract, config, example JSON,
gates, workspace resolution, write guard, code soup audit, anti-patterns.

| Topic in roadmap.md | Section |
| --- | --- |
| Which call to run next | [Decision tree](roadmap.md#decision-tree-which-call-next) |
| 12-section ROADMAP.md contract | [Document contract](roadmap.md#roadmapmd-document-contract) |
| Per-section writing guide | [Section authoring guide](roadmap.md#section-authoring-guide) |
| Example `guide` / `checkpoint` / `validate` JSON | [Example payloads](roadmap.md#example-payloads) |
| `/roadmap` slash commands | [Slash command reference](roadmap.md#slash-command-reference) |
| Staleness rules (section 11) | [Freshness algorithm](roadmap.md#checkpoint-freshness-algorithm) |
| kanban_complete blocking | [Kanban integration](roadmap.md#kanban-and-joyzoning-integration) |
| All `dietcode.roadmap` config keys | [Configuration reference](roadmap.md#configuration-reference) |
| Gate IDs and kanban blocking | [Steering gates](roadmap.md#steering-gates) |
| Workspace resolution order | [Workspace resolution](roadmap.md#workspace-resolution) |
| Native write hints | [Write guard](roadmap.md#write-guard-and-native-hints) |
| Extending fingerprint / PR checklist | [Contributor guide](roadmap.md#contributor-guide) |

### Per-project identity (read this first)

Agents should never infer project context from the DietCode plugin checkout.
Every roadmap JSON payload includes:

| Field | Purpose |
| --- | --- |
| `project_identity_line` | One-line header: brief · stack · verify command |
| `project_steering_digest` | Entity card: CI, quality tools, governance, verify, bootstrap status |
| `project_fingerprint` | Raw signals inside checkpoint `evidence` |
| `bootstrap_fill_plan` | Evidence-backed placeholder replacements (when incomplete) |

Use `roadmap(action='checkpoint', context='digest')` for a compact evidence bundle
when full checkpoint payloads are too heavy.

### Operator loop

```text
1. /roadmap cockpit                              → health, identity, schema, next action
2. /roadmap doctor                               → skill + production checks + Identity line
3. /roadmap explain-gate                         → closed gates vs kanban_complete
4. roadmap(action='checkpoint')                  → evidence + code_soup_pre_audit
5. roadmap(action='apply_bootstrap_fill', context='write')  → when placeholders remain
6. Edit ROADMAP.md at workspace root only        → _roadmap_write_hint on native writes
7. roadmap(action='validate')                    → schema + bootstrap completeness gate
8. /roadmap progress --current                   → full progress + gate snapshot JSON
9. Return checkpoint summary                     → not full ROADMAP.md unless asked
```

### Agent loop

```text
1. roadmap(action='guide')                     → phase, steering_line, project_identity_line
2. roadmap(action='checkpoint')                → evidence + bootstrap_fill_plan when needed
3. roadmap(action='apply_bootstrap_fill')      → preview/write evidence autofill
4. roadmap(action='validate')                    → after edits
5. roadmap(action='explain_gate')              → when kanban_complete blocked
```

Prime directive: did the latest work strengthen or weaken **center of gravity**?
Section 9 code soup audit is mandatory. Keep Now ≤ 5 items.

### Progress storage

| Path | Purpose |
| --- | --- |
| `~/.dietcode/session/roadmap-progress.jsonl` | Append-only roadmap tool activity |
| `~/.dietcode/session/roadmap-progress-current.json` | Latest roadmap action snapshot |
| `.dietcode/roadmap-state.json` | Workspace-local validate/checkpoint memory (`validation_pending` after writes) |

### Native wiring

- Dedicated Hermes toolset: `roadmap` (tools: `roadmap`, `roadmap_checkpoint`)
- `joyzoning(action='context')` → session brief + `project_identity_line` + merged `next_actions`
- `joyzoning(action='roadmap')` → full cockpit payload
- `/dietcode roadmap cockpit` → merges roadmap steering (Project, Identity, Verify)
- Stale checkpoint blocks `kanban_complete` when `warn_on_stale_before_complete` is enabled
- Unvalidated ROADMAP.md edits block `kanban_complete` when `block_kanban_on_validation_pending` is enabled (default)
- `write_file` / `patch` / `dietcode_kernel` on `ROADMAP.md` → `_roadmap_write_hint` → validate follow-up
- Roadmap tool calls emit `roadmap.*` runtime events with `project_identity_line` in telemetry

Checkpoint evidence (tier `full`): README/arch excerpts, git history, TODO markers,
test file count, `code_soup_audit`, and embedded steering profile on every bundle.

### Verification

```bash
make verify   # smoke + production audit + operator smoke + unit tests
```

Smoke: `python scripts/roadmap_smoke.py` · operator: `python scripts/roadmap_operator_smoke.py` · audit: `python scripts/roadmap_audit.py`

## Historical kernel bridge (v1.9.x)

v1.9.0–v1.9.4 documented a macOS socket kernel bridge with progress telemetry,
cockpit UX, and raw-write warn/block policies. **v1.11.0 removed** the `kernel/`
subtree in favor of native mutation (`lib/agent/native_mutation.py`). Release
notes for the kernel era remain in [releases/](releases/).

## Related

- [architecture.md](architecture.md) — runtime layout and hook wiring
- [roadmap.md](roadmap.md) — per-project ROADMAP steering, fingerprint, bootstrap autofill
- [tools-reference.md](tools-reference.md) — `dietcode_kernel` and `roadmap` tools
