# Architecture

DietCode is a Python Hermes plugin with a bundled TypeScript BroccoliDB runtime.
Physical mutation uses the **native mutation runtime** (`dietcode_kernel`) aligned
with codemarie-new / LUMI — not a macOS kernel binary.

## Authority split

```text
┌─────────────────────────────────────────────────────────────────┐
│                        Hermes Agent                              │
│  write_file / patch (raw)  │  dietcode_kernel (governed)       │
└────────────┬───────────────┴──────────────┬──────────────────────┘
             │ JoyZoning gates               │ native patch / verify
             ▼                               ▼
┌────────────────────────┐       ┌───────────────────────────────┐
│  JoyZoning journal     │◄──────│  NativeMutationManager        │
│  convergence gates     │ receipt│  .dietcode/mutation-state.json│
└────────────────────────┘       └───────────────────────────────┘
             │
             ▼
┌────────────────────────┐
│  BroccoliDB             │  (graph + hive — independent layer)
└────────────────────────┘
```

| Layer | Path / surface | Role |
| --- | --- | --- |
| **Native mutation** | `lib/agent/native_mutation.py`, `dietcode_kernel` | Governed patch, verify, coherence tokens |
| **JoyZoning** | `lib/agent/joyzoning/` | Lifecycle journal, convergence |
| **BroccoliDB** | `broccolidb/` | Repository graph, audit, hive RPC |
| **Roadmap** | `lib/agent/roadmap/` | Per-project `ROADMAP.md` steering |
| **Governance** | `lib/agent/governance_exemptions.py` | Import/layer policy transforms |

Closed loop:

```text
intent → dietcode_kernel patch → receipt → JoyZoning journal → verify → convergence
```

## Runtime layers

| Path | Responsibility |
| --- | --- |
| `plugin.yaml` | Hermes manifest and hook declaration. |
| `hooks.py` | Composed Hermes hook handlers. |
| `lib/agent/native_mutation.py` | Coherence tokens, patch, verify, workspace state. |
| `lib/workspace_root.py` | Project workspace resolution (never plugin install tree). |
| `lib/tools/kernel_bridge_tools.py` | `dietcode_kernel` Hermes tool registration. |
| `lib/runtime/mutation_hooks.py` | Journal patch/verify into JoyZoning. |
| `lib/agent/joyzoning/` | Config, journal, convergence, JSDP helpers. |
| `broccolidb/` | TypeScript graph, policy, database, Hermes RPC worker. |

## Hook flow

```text
_ON_SESSION_START  = (kanban_start, jz_start, jsdp_start, roadmap_start)
_ON_SESSION_END    = (jz_end, roadmap_end)
_PRE_TOOL_CALL     = (jz_pre, roadmap_pre)
_POST_TOOL_CALL    = (jz_post, mutation_post, kanban_post, roadmap_post)
_TRANSFORM_TOOL_RESULT = (on_mutation_journal_transform, on_roadmap_write_transform, governance)
```

## Workspace boundary

`lib/workspace_root.py` resolves `HERMES_KANBAN_WORKSPACE` (or config) and rejects
writes when the path is inside the plugin install tree.

Probe: `/dietcode mutation status` or `dietcode_kernel(action='status')`.
