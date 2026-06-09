# DietCode kernel documentation

> **Quarantined macOS kernel** inside `dietcode-plugin/kernel/` — headless
> `dietcode-kernel` with operational coherence enforcement. Hermes integration
> is wired through the **plugin kernel authority bridge** (v1.9.0).

[← Plugin docs](../../docs/README.md) · [← Kernel README](../README.md) ·
**Health check:** `make validate` · Baseline tag: **coherence-core-v0.1**

---

## Plugin integration (read this first for Hermes)

Normal Hermes operation does **not** call kernel scripts directly. The plugin
bridge owns the integration surface:

```text
dietcode_kernel → kernel_bridge_client → dietcode_agent_client.py → dietcode-kernel
```

| Doc | Purpose |
| --- | --- |
| [../../docs/kernel-bridge-operations.md](../../docs/kernel-bridge-operations.md) | Operator manual — warn/block, rollback, doctor |
| [../../docs/architecture.md](../../docs/architecture.md) | Hook flow, authority split, patch gate |
| [../MIGRATION.md](../MIGRATION.md) | Phase 1–5 integration history |
| [../../docs/tools-reference.md](../../docs/tools-reference.md) | `dietcode_kernel` tool reference |

Closed loop:

```text
intent → patch → receipt → journal → verify → verification journal → convergence
```

---

## Repository strategy

This subtree is a reproducible archive of:

1. A macOS mutation kernel (`dietcode-kernel`)
2. Coherence token enforcement (v0.1)
3. Python harnesses that prove issuance, blocking, and recovery
4. Contract docs locked by `make test-docs-code-drift`

| Question | Answer |
| --- | --- |
| What ships? | Binary + methodology + tests |
| What proves it? | `make validate` |
| What tag marks green? | **coherence-core-v0.1** |
| How does Hermes use it? | Plugin bridge — see MIGRATION.md Phase 2–5 |

---

## I want to…

| I want to… | Go here |
| --- | --- |
| Operate the bridge in Hermes | [../../docs/kernel-bridge-operations.md](../../docs/kernel-bridge-operations.md) |
| Build kernel and run the baseline | [getting-started.md](getting-started.md) |
| Confirm my machine matches the archive | [testing.md](testing.md) → `make validate` |
| Call kernel RPC from Python | [kernel-rpc.md](kernel-rpc.md) |
| Understand coherence tokens | [coherence-tokens.md](coherence-tokens.md) |
| Look up an error code | [error-codes.md](error-codes.md) |

---

## Learn the model

| Doc | Audience | Time |
| --- | --- | --- |
| [coherence-tokens.md](coherence-tokens.md) | Token issuance, mismatch, recovery | ~15 min |
| [checkpoint-model.md](checkpoint-model.md) | Six-gate map | ~15 min |
| [architecture.md](architecture.md) | Kernel C++ wiring | ~10 min |

### Coherence and checkpoints

| Topic | Doc |
| --- | --- |
| Coherence tokens (v0.1) | [coherence-tokens.md](coherence-tokens.md) |
| Drift gate | [workspace-drift.md](workspace-drift.md) |
| Approval | [approval-lifecycle.md](approval-lifecycle.md) |
| Verify + completion | [verify-gate.md](verify-gate.md) |
| Agent loop | [agent-ergonomics.md](agent-ergonomics.md) |

---

## Run and validate

| Doc | Purpose |
| --- | --- |
| [getting-started.md](getting-started.md) | First build, socket, workspace |
| [testing.md](testing.md) | `validate`, coherence-core-v0.1, harness ladder |
| [agent-environment.md](agent-environment.md) | Paths, env vars, `restart-agent-server` |

```bash
make validate
```

Plugin integration scripts (from plugin root):

```bash
python scripts/kernel_phase3_rehearsal.py
python scripts/kernel_bridge_e2e.py
```

---

## Build agents and integrations

| Doc | Purpose |
| --- | --- |
| [kernel-rpc.md](kernel-rpc.md) | JSON-RPC methods + Python CLI |
| [agent-tooling.md](agent-tooling.md) | Grep/diff/patch contracts |
| [agent-shell-tooling.md](agent-shell-tooling.md) | Bounded `shell.*` methods |
| [runtime-invariants.md](runtime-invariants.md) | Frozen determinism rules |

**Hermes integration path:** plugin `lib/agent/kernel_bridge_client.py` wraps
`scripts/dietcode_agent_client.py` and `scripts/dietcode_coherence.py`.

**Direct harness path:** use scripts in this directory for low-level RPC testing.

---

## When something breaks

| Symptom | First step | Guide |
| --- | --- | --- |
| Kernel offline | `make restart-agent-server-fast` | [error-codes.md](error-codes.md) |
| Bridge gate closed in Hermes | `/dietcode kernel status` | [../../docs/kernel-bridge-operations.md](../../docs/kernel-bridge-operations.md) |
| `coherence_mismatch` | Re-read with `taskId` | [coherence-tokens.md](coherence-tokens.md) |
| Drift block | `workspace.refreshAnchor` | [workspace-drift.md](workspace-drift.md) |

---

## Operations reference

| Doc | Purpose |
| --- | --- |
| [file-structure.md](file-structure.md) | Subtree map |
| [error-codes.md](error-codes.md) | `string_code` catalog |

---

## For maintainers

After changing kernel RPC, Makefile targets, or `agent_contracts.py`:

```bash
make test-docs-code-drift
```

Contract sources: `scripts/agent_contracts.py`, `scripts/test_docs_code_drift.py`.

After changing plugin bridge behavior, update:

- [../../docs/kernel-bridge-operations.md](../../docs/kernel-bridge-operations.md)
- [../MIGRATION.md](../MIGRATION.md)
- [../../docs/architecture.md](../../docs/architecture.md)
