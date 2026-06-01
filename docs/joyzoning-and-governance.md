# JoyZoning and governance

JoyZoning enforces layered architecture for agent-driven code changes.
**Governance** (the transform hook) can run independently of the full JoyZoning lifecycle.

---

## Two modes

| Mode | Config | What runs |
|------|--------|-----------|
| **Governance only** | `joyzoning.enabled: false`, `governance.enabled: true` | Transform hook on writes; no journal/convergence gates |
| **Full lifecycle** | `joyzoning.enabled: true` | Journal, scope registry, convergence gates, kanban blocks |

Install defaults (`install.py`) enable governance only unless you already have explicit config.

---

## Layer model

JoyZoning classifies code into layers (dependency direction: inner → outer):

```
domain → core → infrastructure → plumbing → ui
```

**SpiderEngine** (`broccolidb/core/policy/SpiderEngine.ts`) builds the dependency graph.
**joy-zoning.ts** utilities assign layers from path heuristics and `[LAYER: TYPE]` file tags.

Governance validates:

- Import direction (inner layers must not depend on outer)
- Optional `[LAYER: TYPE]` header alignment
- Smell heuristics (in `full` validation mode)

Exempt paths: docs, `package.json`, migrations, ORM artifacts, paths in `governance.extra_exempt_paths`.

---

## Governance hook

Registered on `transform_tool_result` via `lib/runtime/governance_hooks.py`.

Triggers on governable write tools (`write_file`, `patch`, etc.) when
`is_governance_enforcement_enabled()` is true.

Behavior depends on `joyzoning.governance` config:

| Key | Effect |
|-----|--------|
| `enabled` | Master switch |
| `layer_tags_required` | Require `[LAYER:]` headers; auto-inject when true on fork |
| `validation_mode` | `auto` → light when tags optional; `full` → smell heuristics; `light` → import rules only |
| `extra_exempt_paths` | Additional skip substrings |

**Fail-closed:** violations return transformed tool results that block the write when enforcement is strict.

`governance_exemptions.py` handles repo-specific exempt paths and policy version tracking.

---

## Full JoyZoning lifecycle

When `joyzoning.enabled: true`:

### Scope registry

Each governed session binds to a `scope_id` (config, env, or kanban-injected).
`scope_registry.py` tracks active mutations per scope.

### Journal

Local SQLite journal (`journal.py`) records:

- Session start/end
- Tool call events (when `execution_journal: true`)
- Runtime events (`runtime_events.py`)

Journal path: `joyzoning.journal_path` or default under Hermes home.

### Mutation lifecycle

`mutation_lifecycle.py` + `workflow.py` implement:

```
begin → record_patch → verify → request_review → mark_converged
```

`convergence_gate.py` enforces transitions; `convergence.py` holds state machine.

### Kanban integration

`pre_tool_call` hook blocks `kanban_complete` until convergence when
`joyzoning.enabled` and `convergence.review_before_complete` are true.

`kanban_hooks.py` debounces BroccoliQ sync on post-tool events.

---

## JSDP (JoyZoning Structured Delivery Protocol)

Bounded agent roles with validated handoffs.

Config:

```yaml
joyzoning:
  jsdp:
    enabled: true
    role: implementer
    chain_id: my-feature-chain
    harness:
      enabled: true
      workspace_root: /path/to/workspace
```

Env mirrors: `JOYZONING_JSDP_ROLE`, `JOYZONING_JSDP_CHAIN_ID`, `JOYZONING_WORKSPACE_ROOT`.

Hooks:

- `on_session_start` → `jsdp role_started`
- Tools: `jsdp`, `jsdp_horizon`, `jsdp_validate_handoff`, `jsdp_role_context`

`jsdp_autonomous.py` + `jsdp_harness_client.py` connect to external harness when configured.

---

## Operator tools

| Surface | Use |
|---------|-----|
| `joyzoning` tool | Agent primary API |
| `/joyzoning status` | Human-readable audit |
| `broccolidb_joyzoning_audit` | Deep SpiderEngine pass |
| `hermes kanban joyzoning-doctor` | Scope/journal/JSDP checks (fork) |

Doctor module: `lib/agent/joyzoning/doctor.py`

---

## Configuration examples

### Minimal (install default)

```yaml
joyzoning:
  governance:
    enabled: true
```

### Strict TypeScript monorepo

```yaml
joyzoning:
  enabled: true
  governance:
    enabled: true
    layer_tags_required: true
    validation_mode: full
  convergence:
    review_before_complete: true
```

### Docs-only exempt

```yaml
joyzoning:
  governance:
    enabled: true
    extra_exempt_paths:
      - docs/
      - website/
```

---

## Legacy notes

- **Habitat / control plane removed** — no `:9470`, no external UI dependency
- **`HABITAT` layer renamed** — use `RuntimeLayer.REPRESENTATION` in new code
- **Split plugins removed** — all wiring in unified `dietcode` plugin
