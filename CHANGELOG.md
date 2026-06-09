# Changelog

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
