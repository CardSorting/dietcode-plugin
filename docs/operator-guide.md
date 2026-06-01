# Operator guide

Day-to-day commands and workflows for running DietCode with Hermes.

---

## Slash commands

| Command | Aliases | Purpose |
|---------|---------|---------|
| `/dietcode` | `/dc` | Integration health console |
| `/joyzoning` | `/jz` | Layering compliance engine |
| `/broccolidb` | `/bdb` | BroccoliDB epistemic database console |
| `/broccoliq` | `/bq` | BroccoliQ queue / shard / integrity |

### /dietcode

```
/dietcode status          Cached integration report
/dietcode doctor          Strict contract + layout checks
/dietcode tools           Tool module load report
/dietcode broccolidb      BroccoliDB root + RPC only
/dietcode help
```

### /joyzoning

```
/joyzoning status         Full structural composition audit
/joyzoning audit          Alias for status
/joyzoning check <file>   Layer tags + imports for one file
/joyzoning suggest <file> Optimal layer assignment
/joyzoning refactor <file> Dependency inversion specs
```

Runs TypeScript via BroccoliDB RPC (SpiderEngine + joy-zoning utils).

### /broccolidb

```
/broccolidb status        Database + RPC health
/broccolidb query         Graph query entry
/broccolidb audit         Structural audit
/broccolidb heal          Self-heal pass
```

### /broccoliq

```
/broccoliq queue          Queue status metrics
/broccoliq shards         Shard health
/broccoliq integrity      Hive integrity check
```

---

## CLI commands (Hermes)

```bash
hermes plugins list                    # dietcode should be enabled
hermes plugins enable dietcode
python3 ~/.hermes/plugins/dietcode/install.py

# Kanban (when kanban toolset enabled)
hermes kanban list
hermes kanban show <task-id>
hermes kanban joyzoning-doctor         # diet-hermes fork only
```

---

## Governed mutation workflow

Standard Hermes-native flow for kanban workers with JoyZoning enabled:

```
begin → patch → verify → request_review → convergence_mark_converged → kanban_complete
```

### Step-by-step (agent)

1. **`joyzoning(action='context')`** — scope bindings, convergence state, next actions.
2. **`joyzoning(action='begin', goal='...')`** — open mutation scope.
3. Implement changes with `patch` / `write_file`.
   - Governance hook may block layer violations on `.ts`/`.js` when enabled.
4. **`joyzoning(action='patch', mutation_id=..., summary='...')`** — record substantive edits.
5. **`joyzoning(action='verify', mutation_id=..., report='...')`** — verification evidence.
6. **`joyzoning(action='request_review', summary='...')`** — ReadyForReview; **stop here**.
7. Operator approves → **`convergence_mark_converged(...)`**.
8. **`kanban_complete(...)`** — `pre_tool_call` gate blocks premature complete.

### Kanban + BroccoliQ linkage

When spawned as a kanban worker:

1. `kanban_show()` — current task
2. `kanban_broccolidb_context()` — hive intelligence for task
3. Work through mutation lifecycle
4. `kanban_broccolidb_record(summary='...')` — persist decisions
5. `convergence_mark_converged` then `kanban_complete`

Orchestrators: `kanban_broccolidb_board_intel()` before fan-out;
`kanban_broccolidb_drift()` periodically.

---

## Governance-only mode (no full JoyZoning lifecycle)

Default throughput posture:

```yaml
joyzoning:
  enabled: false
  governance:
    enabled: true
    layer_tags_required: false
```

- Write/patch transform hook active
- No journal, no convergence gates, no `kanban_complete` block
- Layer tags optional; light import-depth rules still apply in `auto` validation mode

---

## JSDP bounded roles

When `joyzoning.jsdp.enabled: true`:

1. Set `JOYZONING_JSDP_ROLE` (or `joyzoning.jsdp.role`) on worker env
2. Session start fires `jsdp role_started` hook
3. Agent calls `joyzoning(action='role_context')` or `jsdp_role_context`
4. Use `jsdp_validate_handoff` at role boundaries

---

## Health monitoring

Run after install, upgrade, or BroccoliDB npm changes:

```
/dietcode doctor
```

Key fields to watch:

| Field | Healthy |
|-------|---------|
| `registered` | `true` |
| `contract_ok` | `true` |
| `governance_hook_active` | `true` (when governance enabled) |
| `broccolidb.rpc_available` | `true` |
| `broccolidb.node_modules_installed` | `true` |
| `tools.registry_missing` | `[]` |

---

## Layer taxonomy (JoyZoning)

Layers (inner → outer):

1. **domain** — business rules, entities
2. **core** — use cases, orchestration
3. **infrastructure** — adapters, persistence
4. **plumbing** — utilities, cross-cutting
5. **ui** — presentation

Optional file headers: `[LAYER: DOMAIN]` etc. when `layer_tags_required: true`.

Runtime events use `RuntimeLayer.REPRESENTATION` (legacy alias `HABITAT`) for agent-facing artifacts.
