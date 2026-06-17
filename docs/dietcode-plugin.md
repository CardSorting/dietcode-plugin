# DietCode Plugin

DietCode is a Hermes plugin that installs a governed agent execution substrate:
BroccoliDB for repository context, JoyZoning for mutation lifecycle governance,
JSDP for rolling-horizon planning, and a **native mutation runtime** (`dietcode_kernel`)
aligned with LUMI / codemarie-new.

**Current version:** 1.11.0 — Native mutation (kernel subtree removed)

## What changed in v1.11.0

Replaces the macOS `kernel/` socket bridge with Python native mutation:

- `lib/agent/native_mutation.py` — coherence tokens, governed patch, verify, drift detection
- `dietcode_kernel` — status, search, coherence, patch, verify, refresh (no binary)
- `/dietcode mutation` replaces `/dietcode kernel` in doctor console
- `read_file` auto-tracks hashes when `HERMES_KANBAN_TASK` is set
- `make distill` syncs BroccoliDB v30 + optional skills from codemarie-new

See [CHANGELOG.md](../CHANGELOG.md).

## What changed in v1.10.0

BroccoliDB v30 distill — capabilities, orchestration runtime, Hermes RPC adapter.
Run `make distill` after pulling codemarie-new updates.

## Manifest

```yaml
name: dietcode
version: 1.11.0
kind: standalone
auto_enable: true
```

Hermes hooks:

- `on_session_start`
- `on_session_end`
- `pre_tool_call`
- `post_tool_call`
- `transform_tool_result`

## Authority model

| Layer | Responsibility |
| --- | --- |
| **Native mutation** | Governed patch/verify via `dietcode_kernel` + `.dietcode/mutation-state.json` |
| **JoyZoning** | Lifecycle journal (`begin`, `patch`, `verify`, `request_review`) |
| **Convergence gate** | Completion authority — no auto `kanban_complete` |
| **BroccoliDB** | Repository graph, audit, queue — independent of mutation runtime |
| **Roadmap** | Per-project `ROADMAP.md` steering, schema gates, kanban policy |

Closed loop:

```text
intent → dietcode_kernel patch → receipt → journal → verify → convergence
```

## Installation

```bash
mkdir -p ~/.hermes/plugins
cp -R dietcode-plugin ~/.hermes/plugins/dietcode
cd ~/.hermes/plugins/dietcode/broccolidb
npm ci
python ../install.py
```

Flags:

| Flag | Effect |
| --- | --- |
| `--skip-npm` | Skip `npm ci` (dependencies already installed) |

## Runtime verification

```text
/dietcode doctor
/dietcode mutation
/dietcode mutation status
/roadmap cockpit
```

Doctor covers:

- Plugin registration and hook wiring.
- Tool module load status and toolset completeness.
- Runtime layout and stale shim detection.
- BroccoliDB root, `node_modules`, RPC availability.
- JoyZoning and JSDP configuration.
- Native mutation workspace safety and revision state.

```bash
make verify
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Configuration

### Native mutation

No separate binary or socket config. Workspace must resolve to the user project
via `HERMES_KANBAN_WORKSPACE` (never the plugin install tree).

Use `dietcode_kernel(action='coherence')` before multi-file edits and
`dietcode_kernel(action='refresh')` after external changes.

### Roadmap checkpoint

Per-project `ROADMAP.md` steering with evidence autofill, schema gates, and
kanban completion policy. **Full reference:** [roadmap.md](roadmap.md).

```yaml
dietcode:
  roadmap:
    enabled: true
    auto_install_skills: true
    nudge_on_roadmap_write: true
    progress_enabled: true
    stale_checkpoint_days: 7
    warn_on_stale_before_complete: true
    block_kanban_on_validation_pending: true
    block_kanban_on_invalid_schema: false
    block_kanban_on_bootstrap_incomplete: false
    block_writes_outside_workspace: true
```

Quick verification:

```text
/roadmap cockpit
/roadmap doctor
/dietcode roadmap
make verify    # in plugin dev checkout — smoke + audit + 121 tests
```

Install seeds roadmap defaults via `install.py` when keys are absent.

### Environment variables

| Variable | Purpose |
| --- | --- |
| `HERMES_KANBAN_WORKSPACE` | User project root — mutation state, ROADMAP.md, BroccoliDB context ([roadmap.md](roadmap.md)) |
| `HERMES_KANBAN_TASK` | Active task scope — JoyZoning, coherence tokens, read_file hash tracking |
| `JOYZONING_SCOPE_ID` | Explicit JoyZoning scope override |
| `DIETCODE_WORKSPACE_ROOT` | Explicit workspace override |
| `HERMES_BROCCOLIDB_ROOT` | Explicit BroccoliDB root path |
| `HERMES_BROCCOLIDB_DB` | Explicit SQLite database path |
| `HERMES_BROCCOLIDB_RPC` | Set `0`/`false` to disable persistent RPC worker |
| `JOYZONING_JSDP_ROLE` | JSDP role for bounded-role context |
| `JOYZONING_JSDP_CHAIN_ID` | JSDP chain identifier |
| `JOYZONING_WORKSPACE_ROOT` | Workspace root for JSDP harness |
| `JOYZONING_JZ_CLI` | Explicit JoyZoning CLI path |

## Operational workflow

1. Install plugin and run `npm ci` in `broccolidb/`.
2. Set `HERMES_KANBAN_WORKSPACE` to your project root.
3. Run `/dietcode doctor` and `/dietcode mutation status`.
4. Use `joyzoning(action="context")` before governed work — includes roadmap brief and gates.
5. Maintain `ROADMAP.md` at project root: `/roadmap cockpit` or `roadmap(action='guide')`.
6. Governed edits: `dietcode_kernel(action='coherence')` → patch → `joyzoning(action='verify')`.
7. Complete kanban only after convergence **and** roadmap gates allow it (`/roadmap explain-gate`).

## Platform notes

BroccoliDB, JoyZoning, JSDP, native mutation, and roadmap steering work on
all platforms (macOS, Linux). No macOS-only binary required.

## Development

BroccoliDB TypeScript:

```bash
cd broccolidb
npm run build
npm test
```

Python plugin:

```bash
make verify                  # roadmap smoke + audit + unit tests (plugin checkout)
python3 -m unittest discover -s tests -p 'test_*.py'
make distill                 # sync broccolidb from codemarie-new
```

After changes, restart Hermes or reload the plugin:

```text
/dietcode doctor
/dietcode tools
/dietcode mutation status
```
