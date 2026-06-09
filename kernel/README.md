<p align="center">
  <strong>DietCode Kernel — quarantined subtree inside <code>dietcode-plugin</code></strong>
</p>

<h1 align="center">DietCode Kernel</h1>

<p align="center">
  <strong>macOS mutation authority with operational coherence enforcement — integrated via the Hermes plugin bridge (v1.9.0).</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/platform-macOS-lightgrey.svg?style=flat-square" alt="macOS">
  <img src="https://img.shields.io/badge/baseline-coherence--core--v0.1-blue.svg?style=flat-square" alt="coherence-core-v0.1">
  <img src="https://img.shields.io/badge/plugin-bridge-v1.9.0-green.svg?style=flat-square" alt="plugin bridge v1.9.0">
</p>

---

## Role in the plugin

The kernel is an **optional authority layer**. Hermes agents reach it through
the plugin bridge — not by calling this subtree directly in normal operation.

```text
Hermes → dietcode_kernel tool → lib/agent/kernel_bridge_client.py
      → kernel/scripts/dietcode_agent_client.py → dietcode-kernel → your project
```

| Concern | Owner |
| --- | --- |
| Physical patch + verify.run | **Kernel** (this subtree) |
| Lifecycle journal | **JoyZoning** (plugin `lib/agent/joyzoning/`) |
| Completion | **Convergence gate** (no auto kanban_complete) |
| Raw Hermes writes | Default allow; plugin router warn/block opt-in |

Operator guide: [../docs/kernel-bridge-operations.md](../docs/kernel-bridge-operations.md)

Integration history: [MIGRATION.md](MIGRATION.md)

---

## Start here

| You are… | Do this first | Then read |
| --- | --- | --- |
| **Hermes operator** | [../docs/kernel-bridge-operations.md](../docs/kernel-bridge-operations.md) | `/dietcode kernel status` |
| **Building the kernel** | [Quick start](#quick-start) | [docs/getting-started.md](docs/getting-started.md) |
| **Proving the archive** | `make validate` | [docs/testing.md](docs/testing.md) |
| **Calling RPC from Python** | [docs/kernel-rpc.md](docs/kernel-rpc.md) | [docs/coherence-tokens.md](docs/coherence-tokens.md) |
| **Plugin integration dev** | [MIGRATION.md](MIGRATION.md) | [../docs/architecture.md](../docs/architecture.md) |

**One command health check:**

```bash
make validate
```

Tag when green: **coherence-core-v0.1**.

---

## What this subtree is

A **quarantined macOS kernel/coherence-core archive** that builds and validates
independently under `dietcode-plugin/kernel/`. It preserves reproducible
methodology for governing agent-mediated code mutation through a single local
authority.

### What you get

| Deliverable | Location |
| --- | --- |
| Mutation kernel | `build/dietcode-kernel` |
| Coherence enforcement (v0.1) | `src/platform/macos/control/` |
| Python RPC CLI | `scripts/dietcode_agent_client.py` |
| Recovery helpers | `scripts/dietcode_coherence.py` |
| Live proof tests | `scripts/test_coherence_tokens.py`, `coherence_recovery_smoke.py` |
| Runnable baseline | `make validate` → tag **coherence-core-v0.1** |

### What you do not get

| Not included | Notes |
| --- | --- |
| IDE / web UI | Cockpit and AppKit editor removed |
| TypeScript agent-bridge | Plugin uses Python bridge only |
| Cloud platform | Local socket + local verify commands |
| Automatic Hermes wiring | Use plugin `dietcode_kernel` tool and hooks |

---

## Coherence model

Operational coherence binds agent context to kernel revision before drift,
approval, patch, and verify gates evaluate a mutation.

| Layer | Question | Typical block |
| --- | --- | --- |
| **Coherence** | Is this task's observed context still valid? | `coherence_mismatch` |
| **Drift** | Did the workspace change underneath it? | `workspaceDriftRequired` |
| **Approval** | Is this mutation cleared? | `approvalRequired` |
| **Verify** | Did the result pass? | `verify.failed` |

Concept docs: [docs/coherence-tokens.md](docs/coherence-tokens.md) ·
[docs/checkpoint-model.md](docs/checkpoint-model.md)

---

## Quick start

**Prerequisites:** macOS · Xcode CLT (`clang++`, `make`) · Python 3.11+

From the plugin root:

```bash
make -C kernel kernel
make -C kernel restart-agent-server-fast
make -C kernel validate
```

Or from this directory:

```bash
make kernel
make restart-agent-server-fast
make validate
```

**Success:** final line `validate — coherence-core-v0.1 + docs drift: OK`

### Socket and workspace

| Path | Role |
| --- | --- |
| `~/.dietcode/control.sock` | Unix socket |
| `~/.dietcode/session.token` | RPC auth token |

```bash
python3 scripts/dietcode_agent_client.py rpc rpc.ping
python3 scripts/dietcode_agent_client.py rpc workspace.openFolder \
  --params '{"path":"/path/to/your/project"}'
```

After C++ changes: `make kernel && make restart-agent-server-fast`

### Plugin integration check

From plugin root:

```bash
python scripts/kernel_phase3_rehearsal.py
python scripts/kernel_bridge_e2e.py
```

---

## Core commands

| Command | When to use |
| --- | --- |
| `make validate` | **Primary** — coherence baseline + docs drift (CI) |
| `make kernel` | Build `build/dietcode-kernel` |
| `make restart-agent-server-fast` | Restart socket without rebuild |
| `make test-coherence-tokens` | Live token tests |
| `make coherence-recovery-smoke-fast` | Recovery smoke (server running) |
| `make test-docs-code-drift` | Docs ↔ contracts alignment |

Full ladder: [docs/testing.md](docs/testing.md)

---

## Documentation

Complete index: [docs/README.md](docs/README.md)

### Coherence and checkpoints

| Doc | Topic |
| --- | --- |
| [docs/coherence-tokens.md](docs/coherence-tokens.md) | Token issuance, `coherence_mismatch`, recovery |
| [docs/checkpoint-model.md](docs/checkpoint-model.md) | Six-gate map |
| [docs/workspace-drift.md](docs/workspace-drift.md) | Drift gate |
| [docs/approval-lifecycle.md](docs/approval-lifecycle.md) | Approval gate |
| [docs/verify-gate.md](docs/verify-gate.md) | Verify + completion |

### Run, integrate, reference

| Doc | Topic |
| --- | --- |
| [docs/getting-started.md](docs/getting-started.md) | Build, socket, validate |
| [docs/testing.md](docs/testing.md) | `make validate`, harness ladder |
| [docs/kernel-rpc.md](docs/kernel-rpc.md) | JSON-RPC methods + Python CLI |
| [docs/agent-ergonomics.md](docs/agent-ergonomics.md) | Agent loop and blocking responses |
| [docs/agent-tooling.md](docs/agent-tooling.md) | Grep/diff/patch contracts |
| [docs/error-codes.md](docs/error-codes.md) | `string_code` catalog |

### Plugin bridge (outside `kernel/`)

| Doc | Topic |
| --- | --- |
| [../docs/kernel-bridge-operations.md](../docs/kernel-bridge-operations.md) | Operator manual |
| [../docs/architecture.md](../docs/architecture.md) | Hook flow, authority split |
| [MIGRATION.md](MIGRATION.md) | Phase 1–5 integration history |

---

## Troubleshooting

| Symptom | First command |
| --- | --- |
| Kernel offline | `make restart-agent-server-fast` |
| `/dietcode kernel status` shows gate closed | Check `mutations_enabled`, workspace, socket |
| Coherence blocks patch | Re-read with `taskId` — [docs/coherence-tokens.md](docs/coherence-tokens.md) |
| Drift blocks patch | `workspace.refreshAnchor` — [docs/workspace-drift.md](docs/workspace-drift.md) |
| Not sure install is healthy | `make validate` |

Error codes: [docs/error-codes.md](docs/error-codes.md)

---

## Repository layout

```text
build/dietcode-kernel           # Headless kernel binary
src/kernel/                     # Entry + workspace session
src/platform/macos/control/     # JSON-RPC, coherence tokens, gates
scripts/                        # CLI, coherence harnesses, fixtures
docs/                           # Coherence model + kernel reference
```

Detail: [docs/file-structure.md](docs/file-structure.md)

---

## License

MIT — see [LICENSE](LICENSE) in plugin root.
