# Changelog

## v1.9.4 — Sonic Kernel UX (2026-06-09)

Adds high-tempo kernel cockpit feedback, kinetic watch mode, fast-path indicators,
predictive ETA, and ultra-fast operation acknowledgement without changing mutation safety.

### Highlights

- **Ultra-fast ack** — `… PATCH accepted — path` flushed before heavy work (<50ms target).
- **Kinetic watch** — `/dietcode kernel watch --follow` with spinner, in-place refresh, ANSI colors.
- **Micro-phase suppression** — sub-100ms noise hidden on healthy fast paths.
- **Sonic fast path** — `FAST PATH ACTIVE` when drift-free coherence apply runs.
- **Predictive ETA** — history-based remaining time when confidence is sufficient.
- **Event hooks** — optional local shell hooks (`event_hooks_enabled: false` by default).
- **Bench** — `scripts/kernel_sonic_bench.py`.
- **Tests** — `tests/test_kernel_sonic.py`.

See [docs/releases/v1.9.4.md](docs/releases/v1.9.4.md).

## v1.9.3 — Kernel Cockpit Responsiveness (2026-06-09)

Adds live cockpit views, operation states, next-action hints, heartbeat UX, and
responsiveness metrics for long-running kernel bridge operations.

### Highlights

- **Cockpit** — `/dietcode kernel cockpit` one-screen summary (gates, state, last patch/verify, next action).
- **Operation states** — idle, accepted, preparing, validating, applying, verifying, stalled, complete, etc.
- **UX perf budgets** — `/dietcode kernel perf --ux` with ack / first-progress / silent-window thresholds.
- **Watch polish** — state symbols (UTF-8 or ASCII fallback) and single recommended next action.
- **Smoke** — `scripts/kernel_cockpit_smoke.py`.
- **Tests** — `tests/test_kernel_cockpit.py`.

See [docs/releases/v1.9.3.md](docs/releases/v1.9.3.md).

## v1.9.2 — Kernel Bridge Performance Pass (2026-06-09)

Adds bridge readiness caching, workspace-open reuse, progress write batching, mutation
locking, and phase-level performance telemetry for faster coherent patch workflows
without weakening safety gates.

### Highlights

- **Readiness cache** — socket+token positive cache with TTL; invalidate on errors.
- **Workspace open reuse** — skip redundant open when same root recently confirmed.
- **Progress batching** — JSONL buffered; current snapshot immediate; flush on terminal phases.
- **Patch fast path** — no drift → `apply_patch_with_coherence` (recovery loop only when needed).
- **Mutation lock** — serialize patch/verify per workspace; reads/search unaffected.
- **Perf surface** — `/dietcode kernel perf --last 10`, `scripts/kernel_bridge_perf.py`.
- **Tests** — `tests/test_kernel_bridge_perf.py`.

See [docs/releases/v1.9.2.md](docs/releases/v1.9.2.md).

## v1.9.1 — Kernel Observability Polish (2026-06-09)

Adds structured kernel progress telemetry, timeline views, gate explanations, and
operator recovery hints for long-running coherent patch and verify operations.

### Highlights

- **Progress telemetry** — JSONL + current snapshot under `~/.dietcode/session/`;
  phases from `bridge.preflight` through `done` / `error`; 15s stall detection.
- **Operator commands** — `kernel progress` (human summary), `--timeline`,
  `--last N`, `--operation <id>`, `last-error`, `explain-gate`.
- **Agent hints** — `_kernel_operator_hints`, `_kernel_error_envelope` with
  `next_action`, `safe_to_retry`, `retry_command`, `diagnostic_command`,
  `rollback_command`.
- **Docs** — [docs/agent-ergonomics.md](docs/agent-ergonomics.md),
  “When the kernel feels stuck” runbook.
- **Tests** — `tests/test_kernel_progress.py` (Phase 6 + 6B stress cases).

No mutation behavior changes. No new authority. See [docs/releases/v1.9.1.md](docs/releases/v1.9.1.md).

## v1.9.0 — Kernel Authority Bridge (2026-06-09)

Adds optional DietCode kernel authority bridge for coherent patching, verification,
JoyZoning journaling, and gated raw-write interception, with safe defaults and
rollback controls.

Documentation updated to reflect the full integration arc (Phases 1–5), authority
split, and operator workflow. Start at [README.md](README.md) and
[docs/README.md](docs/README.md).

### Integration arc

| Phase | Scope |
| --- | --- |
| 1 | Kernel quarantined in `kernel/` |
| 1.5 | Workspace boundary (`lib/kernel_workspace.py`) |
| 2A | Bridge preflight (read-only RPC) |
| 2B | Opt-in `dietcode_kernel(action='patch')` |
| 2C | Receipt → JoyZoning journal |
| 3A | Raw write warning when patch gate open |
| 3B | Hard block with config + env fuse |
| 4 | Verify loop → verification journal |
| 5 | Operations manual, status surface, failure audit |

Closed loop:

```text
intent → patch → receipt → journal → verify → verification journal → convergence
```

### Highlights

- **Optional authority layer** — macOS kernel bridge; Linux degrades gracefully.
- **Safe defaults** — `mutations_enabled: false`, `raw_write_policy: warn`, no env fuse.
- **Raw write block** — only with `raw_write_policy: block` + `DIETCODE_KERNEL_RAW_WRITE_BLOCK=1` + open patch gate.
- **Operator surface** — `/dietcode kernel status`, `docs/kernel-bridge-operations.md`.
- **Validation** — `scripts/kernel_phase3_rehearsal.py`, `scripts/kernel_bridge_e2e.py`, failure-mode tests.

See [docs/releases/v1.9.0.md](docs/releases/v1.9.0.md) and [kernel/MIGRATION.md](kernel/MIGRATION.md).

## v1.8.0 and earlier

Prior releases: BroccoliDB, BroccoliQ, JoyZoning governance, and JSDP Hermes integration.
