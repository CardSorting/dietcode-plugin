# DietCode Plugin

DietCode is a Hermes plugin that installs a governed agent execution substrate:
BroccoliDB for repository context, JoyZoning
for mutation lifecycle governance, JSDP for rolling-horizon planning, and an
**optional macOS kernel authority bridge** for coherent physical mutation.

**Current version:** 1.9.4 — Sonic Kernel UX

## What changed in v1.9.4

High-tempo kernel operator UX without mutation safety changes:

- Ultra-fast operation acknowledgement (`… PATCH accepted — path`)
- Kinetic `/dietcode kernel watch --follow` with spinner and in-place refresh
- `FAST PATH ACTIVE` indicator for drift-free patch apply
- Predictive ETA when history confidence is sufficient
- `scripts/kernel_sonic_bench.py`

See [releases/v1.9.4.md](releases/v1.9.4.md).

## What changed in v1.9.3

Release-grade operator UX for long kernel bridge operations:

- `/dietcode kernel cockpit` — one-screen state, gates, next action
- Normalized operation states across progress, watch, and perf UX
- `/dietcode kernel perf --ux` — latency budgets (ack, first progress, silent window)
- `scripts/kernel_cockpit_smoke.py` — smoke checks without live mutation

See [releases/v1.9.3.md](releases/v1.9.3.md).

## What changed in v1.9.2

Conservative bridge latency reductions without weakening safety gates:

- Preflight readiness cache (`preflight_cache_ttl_ms`)
- Workspace open reuse (`workspace_open_cache`)
- Progress JSONL batching (`progress_flush_interval_ms`)
- Per-workspace mutation lock + patch fast path (no drift)
- `/dietcode kernel perf --last 10` and `scripts/kernel_bridge_perf.py`

See [releases/v1.9.2.md](releases/v1.9.2.md).

## What changed in v1.9.1

Structured kernel progress telemetry and operator recovery hints — observability
only, no mutation authority changes:

- `/dietcode kernel progress` — human summaries, `--timeline`, `--last N`, `--operation <id>`
- `/dietcode kernel last-error` — normalized envelopes with `next_action`, `safe_to_retry`, retry/diagnostic/rollback commands
- `/dietcode kernel explain-gate` — closed gates, config/env fixes, raw-write behavior
- `dietcode_kernel` results include `_kernel_operator_hints` and `_kernel_error_envelope`

See [releases/v1.9.1.md](releases/v1.9.1.md) and [agent-ergonomics.md](agent-ergonomics.md).

## What changed in v1.9.0

The kernel is no longer a standalone archive you run beside Hermes. It is an
**optional authority layer** integrated through the plugin bridge:

- `dietcode_kernel(action='patch')` — governed file mutation with coherence receipts.
- `dietcode_kernel(action='verify')` — allowlisted verification journaled into JoyZoning.
- Raw Hermes `write_file` / `patch` — warn or block when the patch gate is open (opt-in).
- Safe defaults — mutations off, warn-only raw-write policy, no env fuse.

See [releases/v1.9.0.md](releases/v1.9.0.md) and [kernel-bridge-operations.md](kernel-bridge-operations.md).

## Manifest

```yaml
name: dietcode
version: 1.9.4
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
| **Kernel** | Physical mutation (`patch`) and verification (`verify.run`) via RPC |
| **JoyZoning** | Lifecycle journal (`begin`, `patch`, `verify`, `request_review`) |
| **Convergence gate** | Completion authority — no auto `kanban_complete` |
| **BroccoliDB** | Repository graph, audit, queue — independent of kernel |
| **Raw Hermes writes** | Default allow; warn/block when patch gate open |

Closed loop:

```text
intent → patch → receipt → journal → verify → verification journal → convergence
```

### Integration phases (complete arc)

| Phase | Scope |
| --- | --- |
| 1 | Kernel quarantined in `kernel/` |
| 1.5 | Workspace boundary — never mutate plugin or kernel roots |
| 2A | Bridge preflight (read-only RPC) |
| 2B | Opt-in `dietcode_kernel(action='patch')` |
| 2C | Kernel receipt → JoyZoning journal |
| 3A | Raw write warning when patch gate open |
| 3B | Hard block with config + `DIETCODE_KERNEL_RAW_WRITE_BLOCK=1` |
| 4 | Verify loop → verification journal |
| 5 | Operations manual, `/dietcode kernel status`, failure audit |
| 6 | Progress telemetry, slash commands, agent hints |
| 6B | Human summaries, timeline, multi-op views, stress tests |
| 7 | Readiness cache, workspace reuse, batching, mutation lock, perf telemetry |
| 7B | Ack, heartbeats, watch mode, pre-stage, keep-warm, perf UX |
| 7C | Cockpit, operation states, next-action hints, UX budgets |
| 7D | Sonic pass — kinetic watch, fast ack, ETA, event hooks |

Details: [../kernel/MIGRATION.md](../kernel/MIGRATION.md)

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
| `--build-kernel` | Build `kernel/build/dietcode-kernel` on macOS |

Install seeds safe kernel defaults:

```yaml
dietcode:
  kernel:
    workspace_root_source: hermes_project
    bridge:
      enabled: true
      mutations_enabled: false
      raw_write_policy: warn
```

## Runtime verification

```text
/dietcode doctor
/dietcode kernel status
/dietcode kernel progress           # human summary of current operation
/dietcode kernel progress --timeline
/dietcode kernel last-error
/dietcode kernel explain-gate
/dietcode kernel          # full JSON health payload
```

Doctor covers:

- Plugin registration and hook wiring.
- Tool module load status and toolset completeness.
- Runtime layout and stale shim detection.
- BroccoliDB root, `node_modules`, RPC availability.
- JoyZoning and JSDP configuration.
- Kernel subtree, bridge preflight, workspace safety, patch gate, raw-write policy, verify bridge.

Shell validation (macOS):

```bash
python scripts/kernel_phase3_rehearsal.py
python scripts/kernel_bridge_e2e.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

## Configuration

### Kernel bridge

```yaml
dietcode:
  kernel:
    workspace_root_source: hermes_project   # or env:DIETCODE_WORKSPACE_ROOT, explicit
    bridge:
      enabled: true
      mutations_enabled: false              # set true to open patch gate
      raw_write_policy: warn                # allow | warn | block
      verify_allowlist: []                  # extends default prefixes
```

| `raw_write_policy` | Behavior when patch gate open |
| --- | --- |
| `allow` | No hints on raw writes |
| `warn` | Non-blocking hint to prefer `dietcode_kernel` |
| `block` | Hard block only with `DIETCODE_KERNEL_RAW_WRITE_BLOCK=1` |

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
| `HERMES_KANBAN_WORKSPACE` | User project root — kernel mutation, ROADMAP.md, BroccoliDB context ([roadmap.md](roadmap.md)) |
| `HERMES_KANBAN_TASK` | Active task scope for JoyZoning and coherence |
| `JOYZONING_SCOPE_ID` | Explicit JoyZoning scope override |
| `DIETCODE_KERNEL_RAW_WRITE_BLOCK` | Env fuse for Phase 3B hard block (`1` to enable) |
| `DIETCODE_WORKSPACE_ROOT` | Explicit workspace when `workspace_root_source: env:...` |
| `HERMES_BROCCOLIDB_ROOT` | Explicit BroccoliDB root path |
| `HERMES_BROCCOLIDB_DB` | Explicit SQLite database path |
| `HERMES_BROCCOLIDB_RPC` | Set `0`/`false` to disable persistent RPC worker |
| `JOYZONING_JSDP_ROLE` | JSDP role for bounded-role context |
| `JOYZONING_JSDP_CHAIN_ID` | JSDP chain identifier |
| `JOYZONING_WORKSPACE_ROOT` | Workspace root for JSDP harness |
| `JOYZONING_JZ_CLI` | Explicit JoyZoning CLI path |

Kernel socket paths (global, not plugin-local):

| Path | Role |
| --- | --- |
| `~/.dietcode/control.sock` | Kernel JSON-RPC socket |
| `~/.dietcode/session.token` | RPC auth token |

## Operational workflow

### Without kernel (Linux or macOS default)

1. Install plugin and run `npm ci` in `broccolidb/`.
2. Run `/dietcode doctor`.
3. Use `joyzoning(action="context")` before governed work — includes roadmap brief and gates.
4. Maintain `ROADMAP.md` at project root: `/roadmap cockpit` or `roadmap(action='guide')`.
5. Record lifecycle with `begin` → `patch` → `verify` → `request_review`.
6. Complete kanban only after convergence **and** roadmap gates allow it (`/roadmap explain-gate`).

### With kernel bridge (macOS, opt-in)

1. Build kernel: `make -C kernel kernel && make -C kernel restart-agent-server-fast`
2. Set `HERMES_KANBAN_WORKSPACE` to your project (not the plugin directory).
3. Enable mutations: `dietcode.kernel.bridge.mutations_enabled: true`
4. Confirm: `/dietcode kernel status` → `patch_allowed=true`
5. Mutate via `dietcode_kernel(action='patch', ...)`.
6. Verify via `dietcode_kernel(action='verify', command='./verify.sh')`.
7. Review convergence: `convergence_status` — kanban blocked until operator marks converged.

Rollback to raw writes: [kernel-bridge-operations.md](kernel-bridge-operations.md#rollback-to-raw-writes)

## Platform notes

| Platform | Kernel bridge |
| --- | --- |
| **macOS** | Full bridge when binary built and socket running |
| **Linux** | `platform_supported: false` — plugin degrades gracefully; no blocking |

BroccoliDB, JoyZoning, and JSDP are fully usable on all platforms.

## Development

BroccoliDB TypeScript:

```bash
cd broccolidb
npm run build
npm test
```

Python / kernel bridge:

```bash
make verify                  # roadmap smoke + audit + unit tests (plugin checkout)
python3 -m unittest discover -s tests -p 'test_*.py'
make -C kernel validate    # macOS kernel coherence baseline
```

After changes, restart Hermes or reload the plugin:

```text
/dietcode doctor
/dietcode tools
/dietcode kernel status
```
