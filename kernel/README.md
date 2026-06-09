<p align="center">
  <img src="resources/logo.svg" width="160" height="160" alt="DietCode logo">
</p>

<h1 align="center">DietCode Kernel</h1>

<p align="center">
  <strong>Quarantined kernel/coherence-core subtree inside <code>dietcode-plugin</code> — local mutation authority with operational coherence enforcement.</strong>
</p>

<p align="center">
  <em>Phase 1: build + validate only. Hermes integration is not wired yet — see <a href="MIGRATION.md">MIGRATION.md</a>.</em>
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-4CAF50.svg?style=flat-square" alt="MIT License"></a>
  <img src="https://img.shields.io/badge/platform-macOS-lightgrey.svg?style=flat-square" alt="macOS">
  <img src="https://img.shields.io/badge/baseline-coherence--core--v0.1-blue.svg?style=flat-square" alt="coherence-core-v0.1">
</p>

<p align="center">
  <a href="#start-here">Start here</a> ·
  <a href="#what-this-repository-is">What it is</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#documentation">Docs</a> ·
  <a href="#troubleshooting">Help</a>
</p>

---

## Start here

Pick the path that matches why you opened this repo.

| You are… | Do this first | Then read |
|----------|---------------|-----------|
| **New — want the idea in 5 minutes** | [docs/brief.md](docs/brief.md) | [docs/coherence-tokens.md](docs/coherence-tokens.md) |
| **New — want to run it now** | [Quick start](#quick-start) below | [docs/getting-started.md](docs/getting-started.md) |
| **Skeptical — prove the claims** | `make validate` | [docs/testing.md](docs/testing.md) |
| **Building an agent integration** | [docs/kernel-rpc.md](docs/kernel-rpc.md) | [docs/agent-ergonomics.md](docs/agent-ergonomics.md) |
| **Understanding the archive strategy** | [ARCHIVE.md](ARCHIVE.md) | [docs/archive-note.md](docs/archive-note.md) |
| **Going deep on design** | [docs/philosophy.md](docs/philosophy.md) | [docs/whitepaper.md](docs/whitepaper.md) |

**One command health check** (builds kernel, runs coherence tests, locks docs):

```bash
make validate
```

Tag when green: **coherence-core-v0.1**.

---

## What this repository is

DietCode is a **frozen kernel/coherence-core archive** for macOS. It preserves a reproducible methodology — not a shipping product — for governing agent-mediated code mutation through a single local authority.

### What you get

| Deliverable | Location |
|-------------|----------|
| Mutation kernel | `build/dietcode-kernel` |
| Coherence enforcement (v0.1) | `src/platform/macos/control/` |
| Python RPC CLI | `scripts/dietcode_agent_client.py` |
| Recovery helpers | `scripts/dietcode_coherence.py` |
| Live proof tests | `scripts/test_coherence_tokens.py`, `coherence_recovery_smoke.py` |
| Runnable baseline | `make validate` → tag **coherence-core-v0.1** |

```text
agent or script → dietcode_agent_client.py → dietcode-kernel → your project
```

### What you do not get

| Not included | Notes |
|--------------|-------|
| IDE / web UI | Cockpit and AppKit editor removed |
| TypeScript agent-bridge | Python integration path only |
| Cloud platform | Local socket + local verify commands |
| Gated benchmarks | `benchmarks/` is frozen research |

Full map of retained vs removed: [ARCHIVE.md](ARCHIVE.md).

### The three layers

| Layer | Role |
|-------|------|
| **Kernel** | Sole process that may change files; issues coherence tokens |
| **Control plane** | JSON-RPC server, drift / approval / verify gates |
| **Harnesses** | Python CLI, coherence tests, recovery smoke, contract lock |

---

## Coherence model

Operational coherence binds agent context to kernel revision **before** drift, approval, patch, and verify gates evaluate a mutation.

| Layer | Question | Typical block |
|-------|----------|---------------|
| **Coherence** | Is this task's observed context still valid? | `coherence_mismatch` |
| **Drift** | Did the workspace change underneath it? | `workspaceDriftRequired` |
| **Approval** | Is this mutation cleared? | `approvalRequired` |
| **Verify** | Did the result pass? | `verify.failed` |

| Step | Kernel enforcement |
|------|-------------------|
| **Read** | `file.read` / `file.readBatch` with `taskId` issues a coherence token |
| **Patch** | `patch.apply` requires `coherenceTokenId` + `expectedWorkspaceRevision` |
| **Stale** | `coherence_mismatch` blocks the write; refresh context and retry |
| **Recovery** | `dietcode_coherence.py` + `coherence_recovery_smoke.py` prove the retry path |

Concept papers: [docs/brief.md](docs/brief.md) · Technical: [docs/coherence-tokens.md](docs/coherence-tokens.md) · Gates: [docs/checkpoint-model.md](docs/checkpoint-model.md)

---

## Quick start

**Prerequisites:** macOS · Xcode CLT (`clang++`, `make`) · Python 3.11+

Detailed walkthrough: [docs/getting-started.md](docs/getting-started.md)

### Step 1 — Clone and validate

```bash
git clone <repo>
cd DietCode-IDE
make validate
```

First kernel build takes ~45s; incremental rebuilds are ~1s. `make validate` is the CI target (`.github/workflows/coherence-core.yml`).

**Success looks like:** final line `validate — coherence-core-v0.1 + docs drift: OK`

### Step 2 — Start the kernel

```bash
make restart-agent-server-fast
python3 scripts/dietcode_agent_client.py --wait-ready --compact
python3 scripts/dietcode_agent_client.py rpc rpc.ping
```

| Path | Role |
|------|------|
| `~/.dietcode/control.sock` | Unix socket |
| `~/.dietcode/session.token` | RPC auth token |

After `git pull` with C++ changes: `make kernel && make restart-agent-server-fast`

### Step 3 — Open a workspace and call RPC

```bash
python3 scripts/dietcode_agent_client.py rpc workspace.openFolder \
  --params '{"path":"/path/to/your/project"}'
```

RPC reference: [docs/kernel-rpc.md](docs/kernel-rpc.md) · Env vars: [docs/agent-environment.md](docs/agent-environment.md)

### Step 4 — Read the model (optional but recommended)

| Time | Document |
|------|----------|
| 5 min | [docs/brief.md](docs/brief.md) — executive companion |
| 15 min | [docs/coherence-tokens.md](docs/coherence-tokens.md) + [docs/checkpoint-model.md](docs/checkpoint-model.md) |
| 20 min | [docs/philosophy.md](docs/philosophy.md) — why governed mutation |
| 45 min | [docs/whitepaper.md](docs/whitepaper.md) — full technical spec |

---

## Core commands

| Command | When to use |
|---------|-------------|
| `make validate` | **Primary** — full archive health (CI equivalent) |
| `make kernel` | Build `build/dietcode-kernel` |
| `make coherence-core-v0.1` | Coherence baseline only (no docs drift) |
| `make test-coherence-tokens` | Live token tests (rebuild + `restart-agent-server`) |
| `make coherence-recovery-smoke-fast` | Recovery smoke (server already running) |
| `make restart-agent-server-fast` | Restart socket without rebuild |
| `make restart-agent-server` | Rebuild kernel + restart socket |
| `make test-docs-code-drift` | Docs ↔ contracts alignment only |

Full ladder: [docs/testing.md](docs/testing.md)

---

## Documentation

Complete index: [docs/README.md](docs/README.md)

### Concept papers (start here for the idea)

| Doc | Time | What it covers |
|-----|------|----------------|
| [docs/brief.md](docs/brief.md) | ~5 min | Archive strategy, coherence layering, proof hierarchy |
| [docs/philosophy.md](docs/philosophy.md) | ~20 min | Governed mutation worldview, archive honesty |
| [docs/whitepaper.md](docs/whitepaper.md) | ~45 min | Full runtime spec, validation matrix, architecture |

### Coherence and checkpoints

| Doc | Topic |
|-----|-------|
| [docs/coherence-tokens.md](docs/coherence-tokens.md) | Token issuance, `coherence_mismatch`, recovery |
| [docs/checkpoint-model.md](docs/checkpoint-model.md) | Six-gate map |
| [docs/workspace-drift.md](docs/workspace-drift.md) | Drift gate (checkpoint 2) |
| [docs/approval-lifecycle.md](docs/approval-lifecycle.md) | Approval gate (checkpoint 3) |
| [docs/verify-gate.md](docs/verify-gate.md) | Verify + completion (checkpoints 5–6) |

### Run, integrate, reference

| Doc | Topic |
|-----|-------|
| [docs/getting-started.md](docs/getting-started.md) | Build, socket, validate |
| [docs/testing.md](docs/testing.md) | `make validate`, harness ladder |
| [docs/kernel-rpc.md](docs/kernel-rpc.md) | JSON-RPC methods + Python CLI |
| [docs/agent-ergonomics.md](docs/agent-ergonomics.md) | Agent loop and blocking responses |
| [docs/agent-tooling.md](docs/agent-tooling.md) | Grep/diff/patch contracts |
| [docs/troubleshooting.md](docs/troubleshooting.md) | Failure playbook |
| [docs/error-codes.md](docs/error-codes.md) | `string_code` catalog |

### Archive and structure

| Doc | Topic |
|-----|-------|
| [ARCHIVE.md](ARCHIVE.md) | Retained vs removed index |
| [docs/archive-note.md](docs/archive-note.md) | Why surfaces were removed |
| [docs/file-structure.md](docs/file-structure.md) | Repository map |
| [docs/architecture.md](docs/architecture.md) | Kernel wiring |

---

## Troubleshooting

| Symptom | First command |
|---------|---------------|
| Kernel offline | `make restart-agent-server-fast` |
| Errors after `git pull` | `make kernel && make restart-agent-server-fast` |
| Coherence blocks patch | Re-read with `taskId` — [docs/coherence-tokens.md](docs/coherence-tokens.md) |
| Drift blocks patch | `workspace.refreshAnchor` — [docs/workspace-drift.md](docs/workspace-drift.md) |
| Not sure install is healthy | `make validate` |

Playbook: [docs/troubleshooting.md](docs/troubleshooting.md) · Error codes: [docs/error-codes.md](docs/error-codes.md)

---

## Repository layout

```text
build/dietcode-kernel           # Headless kernel binary
src/kernel/                     # Entry + workspace session
src/platform/macos/control/     # JSON-RPC, coherence tokens, gates
scripts/                        # CLI, coherence harnesses, fixtures
docs/                           # Coherence model + kernel reference
benchmarks/                     # Frozen research (not gated)
```

Detail: [docs/file-structure.md](docs/file-structure.md)

---

## License

MIT — see [LICENSE](LICENSE).
