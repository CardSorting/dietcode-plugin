# DietCode Documentation

Operator and developer documentation for the DietCode Hermes plugin
(**v1.9.0 — Kernel Authority Bridge**).

DietCode bundles BroccoliDB, BroccoliQ, JoyZoning, JSDP, and an **optional macOS
kernel authority bridge**. The kernel handles physical mutation and verification;
JoyZoning owns the lifecycle journal and convergence gates; raw Hermes writes
remain allowed by default with opt-in warn/block policies.

```text
intent → patch → receipt → journal → verify → verification journal → convergence
```

## Start here

| You are… | Read first | Then |
| --- | --- | --- |
| **Installing the plugin** | [dietcode-plugin.md](dietcode-plugin.md) | Run `/dietcode doctor` |
| **Operating the kernel bridge** | [kernel-bridge-operations.md](kernel-bridge-operations.md) | `/dietcode kernel status` |
| **Understanding the runtime** | [architecture.md](architecture.md) | [tools-reference.md](tools-reference.md) |
| **Working with BroccoliDB** | [broccolidb.md](broccolidb.md) | `/broccolidb status` |
| **Building the kernel binary** | [../kernel/README.md](../kernel/README.md) | `make -C kernel validate` |
| **Upgrading to v1.9.0** | [releases/v1.9.0.md](releases/v1.9.0.md) | [../CHANGELOG.md](../CHANGELOG.md) |

## Plugin documents

| Document | Purpose |
| --- | --- |
| [dietcode-plugin.md](dietcode-plugin.md) | Install, verification, configuration, governed workflow. |
| [architecture.md](architecture.md) | Runtime layout, hook wiring, authority split, subprocess boundaries. |
| [kernel-bridge-operations.md](kernel-bridge-operations.md) | Warn/block modes, rehearsal, rollback, doctor interpretation, failure modes. |
| [tools-reference.md](tools-reference.md) | Slash commands and registered Hermes tools (`dietcode_kernel`, JoyZoning, BroccoliDB). |
| [broccolidb.md](broccolidb.md) | Bundled BroccoliDB package, RPC worker, database location, smoke tests. |
| [broccolidb-native-execution-throughput.md](broccolidb-native-execution-throughput.md) | Native RPC execution model and throughput notes. |
| [releases/v1.9.0.md](releases/v1.9.0.md) | v1.9.0 release summary and upgrade notes. |

## Kernel subtree documents

The quarantined kernel under `kernel/` builds and validates independently. Hermes
integration is wired through the plugin bridge (`lib/agent/kernel_bridge_client.py`).

| Document | Purpose |
| --- | --- |
| [../kernel/README.md](../kernel/README.md) | Kernel build, socket, validate, quick start. |
| [../kernel/MIGRATION.md](../kernel/MIGRATION.md) | Phase 1–5 integration history. |
| [../kernel/docs/README.md](../kernel/docs/README.md) | Kernel doc index (RPC, coherence, gates). |
| [../kernel/docs/kernel-rpc.md](../kernel/docs/kernel-rpc.md) | JSON-RPC methods and Python CLI. |
| [../kernel/docs/coherence-tokens.md](../kernel/docs/coherence-tokens.md) | Coherence token model. |
| [../kernel/docs/verify-gate.md](../kernel/docs/verify-gate.md) | Kernel `verify.run` gate. |

## BroccoliDB package documents

| Document | Purpose |
| --- | --- |
| [../broccolidb/README.md](../broccolidb/README.md) | BroccoliDB package overview. |
| [../broccolidb/core/policy/SPIDER.md](../broccolidb/core/policy/SPIDER.md) | Spider Engine policy notes. |

## Quick start

```bash
cd ~/.hermes/plugins/dietcode/broccolidb
npm ci
python ../install.py --skip-npm
```

Inside Hermes:

```text
/dietcode doctor
/dietcode kernel status
```

Optional macOS kernel validation:

```bash
make -C kernel kernel
make -C kernel restart-agent-server-fast
python scripts/kernel_bridge_e2e.py
```

The doctor output is the source of truth for hooks, tools, runtime contracts,
BroccoliDB, JoyZoning, JSDP, and kernel bridge health.
