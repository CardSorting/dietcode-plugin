# Testing and validation

> **“Is this archive healthy on my machine?”** → `make validate`

[← Doc index](README.md) · [getting-started](getting-started.md) · [troubleshooting](troubleshooting.md)

---

## Command map

| I want to… | Command |
|------------|---------|
| Full archive validate (CI target) | `make validate` |
| Coherence baseline only | `make coherence-core-v0.1` |
| Coherence tokens only | `make test-coherence-tokens` |
| Recovery smoke only | `make coherence-recovery-smoke-fast` |
| Docs ↔ code alignment | `make test-docs-code-drift` |
| Quick CLI smoke | `make agent-self-test` |
| Broader RPC ladder | `make verify-agent-runtime-full` |

---

## Primary gate: validate

```bash
make validate
```

| Step | Proves |
|------|--------|
| `coherence-core-v0.1` | Live kernel coherence + recovery smoke |
| `test-docs-code-drift` | Makefile targets, error codes, contract keys, doc cross-links |

GitHub Actions (`.github/workflows/coherence-core.yml`) runs the same target on `macos-latest`.

Tag when green: **coherence-core-v0.1**.

---

## Coherence-core-v0.1

```bash
make coherence-core-v0.1
```

Builds kernel once, restarts socket, then:

| Step | Script | Checks |
|------|--------|--------|
| `test-coherence-tokens-fast` | `scripts/test_coherence_tokens.py` | `file.read` + `file.readBatch` issue tokens; stale revision rejected; missing token rejected |
| `coherence-recovery-smoke-fast` | `scripts/coherence_recovery_smoke.py` | Stale patch blocked → context refreshed → safe retry → verify passes |

Fixtures: `scripts/fixtures/coherence_recovery/`

---

## Coherence token tests (with rebuild)

```bash
make test-coherence-tokens
```

Same as fast variant but forces `kernel` + `restart-agent-server-fast` first. Use after C++ changes.

Fast iteration (server already matches HEAD):

```bash
make test-coherence-tokens-fast
```

---

## Coherence recovery smoke

```bash
make coherence-recovery-smoke-fast
```

Full gate (rebuild + restart first):

```bash
make coherence-recovery-smoke
```

Orchestrator proves the Python recovery path in `scripts/dietcode_coherence.py` — not a removed bridge client.

---

## Docs drift

```bash
make test-docs-code-drift
```

Locks:

- Makefile `REQUIRED_MAKE_TARGETS`
- Error recovery hints ↔ `error-codes.md` ↔ runtime diagnostics
- Coherence cross-doc alignment (`coherence_mismatch`, issuing reads)
- Agent tooling and shell method documentation
- README / getting-started baseline mentions

Source: `scripts/agent_contracts.py`, `scripts/test_docs_code_drift.py`

---

## Kernel harness ladder (optional)

Broader than coherence-core — run after significant RPC changes:

| Target | Focus |
|--------|-------|
| `make agent-self-test` | CLI + socket transport |
| `make control-smoke` | Control plane smoke |
| `make test-agent-workflow-smoke` | Patch workflows |
| `make test-agent-shell-tooling` | Bounded shell |
| `make test-agent-shell-workflows` | Shell workflow integration |
| `make test-authority-boundaries` | Journal vs live authority |
| `make verify-agent-runtime-full` | Full agent-runtime release ladder |

Restart when C++ changed:

```bash
make restart-agent-server
```

---

## Authority unit tests (offline)

```bash
make test-mutation-authority
make test-diff-authority
make test-verification-authority
```

No live kernel required.

---

## Benchmark track (not gated)

Frozen results under `benchmarks/agent_success/`. Live runners need restored `agent-bridge/` from git history. See [benchmarks/README.md](../benchmarks/README.md) and [AGENT_RUNTIME_RELIABILITY.md](../AGENT_RUNTIME_RELIABILITY.md).

Does **not** gate coherence-core.

---

## Build performance

Kernel build uses incremental object compilation (`build/obj/`). First compile ~45s; typical incremental ~1s. `coherence-core-v0.1` avoids redundant full rebuilds across nested make targets.

---

## Agent runtime release ladder (historical)

```bash
make verify-agent-runtime-full
make release-check-agent-runtime
```

Contract versions: `scripts/release_versions.py`, kernel `rpc.version` response.
