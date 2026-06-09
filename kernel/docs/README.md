# DietCode documentation

> **Kernel/coherence-core archive** — headless `dietcode-kernel` with operational coherence enforcement across agent read, patch, approval, and verify surfaces.

[← Project overview](../README.md) · **Health check:** `make validate` · Baseline tag: **coherence-core-v0.1**

---

## Repository strategy

DietCode is intentionally **not** a product repo. It is a reproducible archive of:

1. A macOS mutation kernel (`dietcode-kernel`)
2. Coherence token enforcement (v0.1)
3. Python harnesses that prove issuance, blocking, and recovery
4. Frozen contract docs locked by `make test-docs-code-drift`

Removed surfaces (cockpit, legacy UI, agent-bridge) are documented in [archive-note.md](archive-note.md). Research benchmarks live under `benchmarks/` and do **not** gate the archive.

| Question | Answer |
|----------|--------|
| What ships? | Nothing — methodology + tests |
| What proves it? | `make validate` |
| What tag marks green? | **coherence-core-v0.1** |
| Where is the map? | [ARCHIVE.md](../ARCHIVE.md) |

---

## I want to…

| I want to… | Go here |
|------------|---------|
| Understand what this repo is (no install) | [brief.md](brief.md) → [coherence-tokens.md](coherence-tokens.md) |
| Build kernel and run the baseline | [getting-started.md](getting-started.md) |
| Confirm my machine matches the archive | [testing.md](testing.md) → `make validate` |
| Fix socket / coherence / drift errors | [troubleshooting.md](troubleshooting.md) |
| Call kernel RPC from Python | [kernel-rpc.md](kernel-rpc.md) |
| See what was removed | [archive-note.md](archive-note.md) |
| Look up an error code | [error-codes.md](error-codes.md) |

---

## Learn the model

| Doc | Audience | Time |
|-----|----------|------|
| [brief.md](brief.md) | Everyone — executive companion | ~5 min |
| [philosophy.md](philosophy.md) | Why governed mutation | ~20 min |
| [whitepaper.md](whitepaper.md) | Full runtime architecture | ~45 min |
| [checkpoint-model.md](checkpoint-model.md) | Six-gate map | ~15 min |
| [architecture.md](architecture.md) | Kernel wiring | ~10 min |

### Coherence and checkpoints

| Topic | Doc |
|-------|-----|
| Coherence tokens (v0.1) | [coherence-tokens.md](coherence-tokens.md) |
| Drift gate (checkpoint 2) | [workspace-drift.md](workspace-drift.md) |
| Approval (checkpoint 3) | [approval-lifecycle.md](approval-lifecycle.md) |
| Verify + completion (5–6) | [verify-gate.md](verify-gate.md) |
| Session reload (not a gate) | [session-recovery.md](session-recovery.md) |
| Agent loop | [agent-ergonomics.md](agent-ergonomics.md) |

---

## Run and validate

| Doc | Purpose |
|-----|---------|
| [getting-started.md](getting-started.md) | First build, socket, workspace |
| [testing.md](testing.md) | `validate`, `coherence-core-v0.1`, harness ladder |
| [agent-environment.md](agent-environment.md) | Paths, env vars, `restart-agent-server` |

### Quick health check

```bash
make validate
```

Runs coherence-core-v0.1 + docs drift. GitHub Actions uses the same target on macOS.

---

## Build agents and integrations

| Doc | Purpose |
|-----|---------|
| [kernel-rpc.md](kernel-rpc.md) | JSON-RPC methods + Python CLI |
| [agent-tooling.md](agent-tooling.md) | Grep/diff/patch/retrieval contracts |
| [agent-shell-tooling.md](agent-shell-tooling.md) | Bounded `shell.*` methods |
| [runtime-invariants.md](runtime-invariants.md) | Frozen determinism rules |

Integration path: **Python only** — `scripts/dietcode_agent_client.py` and `scripts/dietcode_coherence.py`. No in-tree TypeScript bridge.

---

## When something breaks

| Symptom | First step | Guide |
|---------|------------|-------|
| Kernel offline | `make restart-agent-server-fast` | [troubleshooting.md](troubleshooting.md) |
| `coherence_mismatch` | Re-read with `taskId` | [coherence-tokens.md](coherence-tokens.md) |
| Drift block | `workspace.refreshAnchor` | [workspace-drift.md](workspace-drift.md) |
| Unknown error | Search catalog | [error-codes.md](error-codes.md) |

---

## Operations reference

| Doc | Purpose |
|-----|---------|
| [file-structure.md](file-structure.md) | Repository map |
| [archive-note.md](archive-note.md) | Removed product surfaces |
| [troubleshooting.md](troubleshooting.md) | Full failure playbook |

---

## Outside `docs/`

| Path | Purpose |
|------|---------|
| [ARCHIVE.md](../ARCHIVE.md) | Retained vs removed index |
| [AGENT_RUNTIME_RELIABILITY.md](../AGENT_RUNTIME_RELIABILITY.md) | Adversarial research track |
| [benchmarks/README.md](../benchmarks/README.md) | Frozen benchmark archive |

---

## For maintainers

After changing kernel RPC, Makefile targets, or `agent_contracts.py`:

```bash
make test-docs-code-drift
```

Contract sources: `scripts/agent_contracts.py`, `scripts/test_docs_code_drift.py`.
