# Kernel migration (Phase 1)

Quarantined copy of the DietCode-IDE kernel/coherence-core archive inside
`dietcode-plugin/kernel/`. Hermes hooks and mutation routing are **not** wired
yet — this subtree builds and validates independently.

## What was migrated

| Source (DietCode-IDE) | Destination |
| --- | --- |
| `src/` | `kernel/src/` |
| `Makefile` | `kernel/Makefile` |
| `scripts/dietcode_agent_client.py` | `kernel/scripts/` |
| `scripts/dietcode_coherence.py` | `kernel/scripts/` |
| `scripts/test_coherence_tokens.py` | `kernel/scripts/` |
| `scripts/coherence_recovery_smoke.py` | `kernel/scripts/` |
| `scripts/release_versions.py` | `kernel/scripts/` |
| `scripts/agent_contracts.py` | `kernel/scripts/` |
| `scripts/agent_test_support.py` | `kernel/scripts/` |
| `scripts/test_docs_code_drift.py` | `kernel/scripts/` |
| `scripts/fixtures/coherence_recovery/` | `kernel/scripts/fixtures/` |
| `scripts/fixtures/recovery/` | `kernel/scripts/fixtures/` |
| `scripts/fixtures/release/` | `kernel/scripts/fixtures/` |
| Selected `docs/*.md` (coherence + RPC reference) | `kernel/docs/` |
| `README.md` | `kernel/README.md` |

## Not migrated

- `agent-bridge/` (removed from archive; do not restore)
- `integrations/` Hermes wiring (Phase 2)
- `cockpit/`, `legacy_ui/`, `benchmarks/`
- `runtime/memory/broccoliq/` (superseded by plugin `broccolidb/`)
- Broader harness ladder (`verify-agent-runtime-full`, shell workflow tests, etc.)

## Build and validate

```bash
make -C kernel kernel      # → kernel/build/dietcode-kernel
make -C kernel validate    # coherence-core-v0.1 + docs drift (macOS)
```

CI: `.github/workflows/kernel-validate.yml` (macOS only).

Plugin surfaces:

- `python install.py` — reports kernel build status (`kernel` key); optional `--build-kernel`
- `/dietcode kernel` or `/dietcode doctor` — platform, binary, socket, token probes

## Path assumptions (fixed vs broken)

### Fixed automatically

Scripts use `REPO_ROOT = Path(__file__).resolve().parents[1]`, which resolves to
`kernel/` when scripts live under `kernel/scripts/`. Therefore:

- Binary default: `kernel/build/dietcode-kernel`
- Docs drift: `kernel/docs/`, `kernel/Makefile`, `kernel/README.md`
- C++ includes: relative to `kernel/src/` (unchanged)

### Still global / shared (intentional)

| Path | Notes |
| --- | --- |
| `~/.dietcode/control.sock` | Kernel control socket (not plugin-local) |
| `~/.dietcode/session.token` | RPC auth token |
| `~/.dietcode/session/` | Approval / recovery state |
| `~/.dietcode/runtime-memory/` | BroccoliQ memory layer (kernel C++) |

### Broken or stale until Phase 2

| Assumption | Issue |
| --- | --- |
| `DIETCODE_REPO_ROOT=$(CURDIR)` in Makefile | Points at `kernel/`, not the Hermes workspace — correct for harnesses, wrong for agent workspace open |
| `resources/bin/dietcode-agent-client` | Not copied; use `kernel/scripts/dietcode_agent_client.py` |
| Docs reference repo-root `ARCHIVE.md`, `benchmarks/` | Paths in prose still describe standalone DietCode-IDE layout |
| `test_docs_code_drift` root README checks | `kernel/README.md` still reads like standalone archive (drift tests pass) |
| Plugin `install.py` does not auto-start socket | Doctor reports socket offline until `make -C kernel restart-agent-server-fast` |
| Hermes `write_file` / `patch` | Unchanged — no kernel authority yet |
| `DIETCODE_APP_PATH` unset | Plugin doctor uses `kernel/build/dietcode-kernel`; client scripts use same default |

### Linux / non-macOS

Kernel build is skipped gracefully. `lib/kernel_health.py` reports
`platform_supported: false` with no error spam. BroccoliDB, JoyZoning, and
JSDP remain fully usable.

## Phase 1.5 — workspace-root boundary

Plugin module `lib/kernel_workspace.py` resolves the Hermes **user** workspace
separately from `plugin_root` and `kernel_root`:

| `dietcode.kernel.workspace_root_source` | Resolves from |
| --- | --- |
| `hermes_project` (default) | `HERMES_KANBAN_WORKSPACE` → kanban config → `cwd` |
| `env:DIETCODE_WORKSPACE_ROOT` | `DIETCODE_WORKSPACE_ROOT` env |
| `explicit` | `dietcode.kernel.workspace_root` config path |

Validation blocks mutation when workspace is missing, equals `plugin_root` or
`kernel_root`, or is not writable. `/dietcode doctor` reports all three roots
and `safe_for_mutation`.

Kernel **build** cwd remains `kernel/` only; `DIETCODE_REPO_ROOT` is stripped
from the build subprocess env so harness defaults cannot leak into install.

Tests: `tests/test_kernel_workspace.py`

## Phase 2A — bridge preflight (read-only)

`lib/agent/kernel_bridge_client.py` wraps `kernel/scripts/dietcode_agent_client.py`
directly (no agent-bridge). Exposes:

- `connect_preflight()`, `ensure_socket_ready()`, `read_kernel_token()`
- `send_kernel_rpc()`, `open_workspace()`, `workspace_status()`, `search_literal()`

All workspace operations require `safe_for_mutation` from `lib/kernel_workspace.py`.
`dietcode.kernel.bridge.mutations_enabled` defaults to `false`. Hermes
`write_file` / `patch` are unchanged until Phase 3.

Doctor reports `bridge_preflight` + `patch_gate` under the kernel section.

Tests: `tests/test_kernel_bridge_client.py`

## Phase 2B — opt-in patch tool

Hermes tool `dietcode_kernel` (`lib/tools/kernel_bridge_tools.py`):

| action | Bridge call |
| --- | --- |
| `status` | `workspace_status()` |
| `search` | `search_literal()` |
| `patch` | `apply_kernel_patch()` via `dietcode_coherence.recover_and_apply_patch` |

Patch requires `bridge.enabled`, `bridge.mutations_enabled`, safe workspace,
socket, and token. Disabled patch returns `bridge_patch_disabled`.

Tests: `tests/test_kernel_bridge_tools.py`

## Phase 2C — kernel receipt → JoyZoning journal

When `dietcode_kernel(action="patch")` succeeds with a kernel `mutationReceipt`,
Hermes hooks record the mutation in the JoyZoning lifecycle journal without
blocking raw `write_file` / `patch` yet.

| Authority | Role |
| --- | --- |
| **Kernel** | Physical mutation authority (`dietcode_kernel` patch RPC) |
| **JoyZoning** | Lifecycle journal / completion authority (`mutation_record_patch`) |

Modules:

- `lib/agent/kernel_receipt_journal.py` — receipt → journal bridge
- `lib/runtime/kernel_hooks.py` — `post_tool_call` + `transform_tool_result`

Journal runs only when `ok == true`, `action == patch`, and
`kernel.mutationReceipt` is present. Missing receipt fields are not invented.
Journal failure emits a non-fatal `_journal_warning`; kernel patch success is
unchanged.

Tests: `tests/test_kernel_receipt_journal.py`

## Phase 3A — warn on raw Hermes writes

When the kernel bridge patch gate is open, `pre_tool_call` detects raw
`write_file` / `patch` (and known aliases) and emits a non-blocking hint to
prefer `dietcode_kernel(action='patch')`. Raw tools still execute.

Config: `dietcode.kernel.bridge.raw_write_policy` — `allow` | `warn` (default) | `block`.

| Value | Phase 3A behavior |
| --- | --- |
| `allow` | No hints |
| `warn` | Hint when patch gate open |
| `block` | Still warn-only until Phase 3B guard (`DIETCODE_KERNEL_RAW_WRITE_BLOCK=1`) |

Modules:

- `lib/agent/kernel_raw_write_router.py` — gate evaluation + warning metadata
- `lib/runtime/kernel_hooks.py` — `pre_tool_call` + `transform_tool_result`

Warning metadata: `string_code: kernel_raw_write_warn`, `preferred_tool: dietcode_kernel`,
`reason: bridge_ready`, `workspace_root`.

Tests: `tests/test_kernel_raw_write_router.py`

## Phase 3B — hard block raw Hermes writes

When `raw_write_policy: block` **and** `DIETCODE_KERNEL_RAW_WRITE_BLOCK=1`, raw
`write_file` / `patch` are blocked at `pre_tool_call` if the patch gate is fully
open. Same gate as Phase 3A; if any gate is closed, behavior falls back to allow/warn.

Block payload (JSON in Hermes block message):

- `ok: false`, `blocked: true`
- `string_code: kernel_raw_write_blocked`
- `preferred_tool: dietcode_kernel`
- `workspace_root`

`dietcode_kernel`, reads, search, and status are never blocked.

Tests: `tests/test_kernel_raw_write_router.py`

Rehearsal: `python scripts/kernel_phase3_rehearsal.py`

## Phase 4 — kernel verify → JoyZoning completion bridge

`dietcode_kernel(action='verify')` runs kernel `verify.run` with client-side
allowlist enforcement, then journals into JoyZoning `mutation_verify` via hooks.

| Step | Authority |
| --- | --- |
| Physical verify | Kernel `verify.run` |
| Lifecycle record | JoyZoning `record_verification` / `mutation_verify` |
| Task completion | Convergence gate (unchanged — no auto kanban_complete) |

Modules:

- `lib/agent/kernel_verify_bridge.py` — allowlist + doctor
- `lib/agent/kernel_verify_journal.py` — verify receipt → journal
- `lib/agent/kernel_bridge_client.py` — `apply_kernel_verify`

Config: `dietcode.kernel.bridge.verify_allowlist` extends kernel default prefixes.

Tests: `tests/test_kernel_verify_journal.py`, `tests/test_kernel_verify_bridge.py`

## Phase 5 — release hardening and failure-mode audit

Prepare the kernel bridge for real usage: operator docs, status surface,
failure-mode tests, and e2e rehearsal without auto-completion.

| Deliverable | Location |
| --- | --- |
| Operator manual | `docs/kernel-bridge-operations.md` |
| Status summary | `/dietcode kernel status` + `build_kernel_bridge_status_summary()` |
| Failure-mode tests | `tests/test_kernel_failure_modes.py` |
| E2E loop | `scripts/kernel_bridge_e2e.py` |
| Release notes | `CHANGELOG.md` |

**Release posture:**

- Kernel = optional authority layer (macOS); Linux degrades gracefully.
- Raw writes blocked only with `raw_write_policy: block` + `DIETCODE_KERNEL_RAW_WRITE_BLOCK=1` + open patch gate.
- Default install: `mutations_enabled: false`, `raw_write_policy: warn`, no env fuse.

**Failure modes audited:**

| Failure | Behavior |
| --- | --- |
| Socket dies mid-patch | `bridge_transport_error`; no journal |
| Token missing | `bridge_token_unavailable`; patch/verify blocked |
| Workspace deleted / unsafe | `bridge_workspace_unsafe`; gates close |
| Verify timeout | `bridge_rpc_timeout`; no verify journal |
| Journal unavailable | Non-fatal `_journal_warning`; tool success unchanged |
| Block + fuse but gate closed | Falls back to allow/warn |

Tests: `tests/test_kernel_failure_modes.py`

## Phase 6 — agent ergonomics and kernel observability

Make long coherent mutation cycles legible without adding mutation authority.

| Deliverable | Location |
| --- | --- |
| Progress telemetry | `lib/agent/kernel_progress.py` |
| JSONL + current snapshot | `~/.dietcode/session/kernel-progress.jsonl` |
| Slash commands | `/dietcode kernel progress`, `last-error`, `explain-gate` |
| Agent hints | `_kernel_operator_hints` on `dietcode_kernel` results |
| Docs | `docs/agent-ergonomics.md`, `docs/kernel-bridge-operations.md` |

Tests: `tests/test_kernel_progress.py`

## Phase 6B — observability polish under stress

Human summaries, timeline views, multi-operation filtering, enriched error
envelopes, upgraded gate explanation, silence/stress regression tests.

| Deliverable | Location |
| --- | --- |
| Human summaries | `human_progress_summary()` |
| Timeline / last N / operation filter | `format_progress_report()` flags |
| Error envelopes | `next_action`, `safe_to_retry`, `retry_command`, etc. |
| Gate explanation | closed gates, fixes, raw-write behavior |
| Release | v1.9.1 — [docs/releases/v1.9.1.md](../docs/releases/v1.9.1.md) |

Tests: `tests/test_kernel_progress.py` (`KernelProgressPolishTests`)

## Phase 7 — kernel bridge performance and throughput

Conservative latency reductions without weakening mutation safety.

| Deliverable | Location |
| --- | --- |
| Phase timing + perf buckets | `lib/agent/kernel_progress.py`, `lib/agent/kernel_bridge_perf.py` |
| Preflight readiness cache | `lib/agent/kernel_bridge_cache.py` |
| Workspace open cache | `lib/agent/kernel_bridge_cache.py` + `open_workspace()` |
| Progress JSONL batching | `lib/agent/kernel_progress.py` |
| Patch fast path (no drift) | `apply_patch_with_coherence` in `_apply_kernel_patch_rpc` |
| Verify heartbeat + optional timeout | `apply_kernel_verify()` |
| Per-workspace mutation lock | `lib/agent/kernel_mutation_lock.py` |
| Journal dedup TTL index | `kernel_receipt_journal.py`, `kernel_verify_journal.py` |
| Bench script | `scripts/kernel_bridge_perf.py` |
| Operator command | `/dietcode kernel perf --last 10` |

Config (`dietcode.kernel.bridge`): `preflight_cache_ttl_ms`, `workspace_open_cache`,
`progress_flush_interval_ms`, `verify_timeout_ms` (0 = default), `max_concurrent_mutations_per_workspace`.

Tests: `tests/test_kernel_bridge_perf.py`

**Release:** v1.9.2 — [docs/releases/v1.9.2.md](../docs/releases/v1.9.2.md)

## Phase 7B — perceived performance and responsiveness

Operator confidence during long mutations — no safety gate changes.

| Deliverable | Location |
| --- | --- |
| Immediate operation ack | `operation.accepted` in `kernel_progress.py` |
| Next-phase hints + stall reasons | `lib/agent/kernel_progress_ux.py` |
| Coalesced heartbeats | `KernelProgressTracker` + `bridge.heartbeat` |
| Watch mode | `/dietcode kernel watch` in `health.py` |
| Mutation pre-stage | `patch.staging` via `_emit_patch_staging()` |
| Optional keep-warm | `lib/agent/kernel_bridge_warm.py` + `keep_warm` config |
| UX perf metrics | `/dietcode kernel perf --ux` |
| Long-run stress tiers | 30s / 60s / 120s on progress events |

Tests: `tests/test_kernel_progress_ux.py`

## Phase 7C — live kernel cockpit final polish

Release-grade operator UX without mutation semantics changes.

| Deliverable | Location |
| --- | --- |
| One-screen cockpit | `/dietcode kernel cockpit`, `lib/agent/kernel_cockpit.py` |
| Operation states | `normalize_operation_state()` — used in progress/watch/cockpit/perf |
| Terminal symbols + ASCII fallback | `kernel_cockpit.symbol()`, `DIETCODE_ASCII_ONLY` |
| Single next-action hint | `recommend_next_action()` |
| UX latency budgets | `perf --ux` enriched metrics + pass/fail |
| Smoke script | `scripts/kernel_cockpit_smoke.py` |

**Release:** v1.9.3 — [docs/releases/v1.9.3.md](../docs/releases/v1.9.3.md)

## Next phase

- JoyZoning `taskId` ↔ `HERMES_KANBAN_TASK` alignment
