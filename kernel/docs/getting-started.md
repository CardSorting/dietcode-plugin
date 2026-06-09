# Getting started

> **Goal:** Build the kernel, start the socket, and validate the coherence-core
> archive on your Mac. For Hermes integration, use the plugin bridge after this
> baseline is green.

[← Doc index](README.md) · [← Kernel README](../README.md) ·
[Plugin operator guide](../../docs/kernel-bridge-operations.md)

| Step | Action | Success signal |
| --- | --- | --- |
| 1 | [Prerequisites](#prerequisites) | Tools installed |
| 2 | [Build the kernel](#1-build-the-kernel) | `build/dietcode-kernel` exists |
| 3 | [Start the socket](#2-start-the-socket) | `rpc.ping` succeeds |
| 4 | [Open a workspace](#3-open-a-workspace) | Project bound to session |
| 5 | [Validate the archive](#4-validate-the-archive) | `make validate` green |
| 6 | [Plugin integration](#5-plugin-integration-optional) | E2E script passes |

Run from `dietcode-plugin/kernel/` or prefix commands with `make -C kernel`.

---

## Prerequisites

- **macOS** (Apple Silicon or Intel)
- **Xcode Command Line Tools** — `clang++`, `make`
- **Python 3.11+** — harnesses and `dietcode_agent_client.py`

No Node.js, no AppKit app bundle, no cloud account.

---

## 1. Build the kernel

The kernel is the **only** component allowed to change files on disk through
the governed RPC surface.

```bash
make kernel
```

First build compiles all sources (~45s). Subsequent builds are incremental (~1s
for a single changed file).

| Artifact | Path |
| --- | --- |
| Binary | `build/dietcode-kernel` |
| Object cache | `build/obj/` |

From plugin root: `make -C kernel kernel` or `python install.py --build-kernel`

---

## 2. Start the socket

```bash
make restart-agent-server-fast   # or make restart-agent-server after C++ changes
python3 scripts/dietcode_agent_client.py --wait-ready --compact
python3 scripts/dietcode_agent_client.py rpc rpc.ping
```

| Path | Role |
| --- | --- |
| `~/.dietcode/control.sock` | Unix socket (mode `0600`) |
| `~/.dietcode/session.token` | RPC auth token |

If ping fails, see [error-codes.md](error-codes.md) and restart with
`make restart-agent-server-fast`.

After C++ changes:

```bash
make kernel && make restart-agent-server-fast
```

---

## 3. Open a workspace

```bash
python3 scripts/dietcode_agent_client.py rpc workspace.openFolder \
  --params '{"path":"/path/to/your/project"}'
```

For Hermes, set `HERMES_KANBAN_WORKSPACE` to the same project path. Never point
the workspace at the plugin or `kernel/` subtree — the plugin workspace boundary
blocks mutation there.

Harnesses often set `DIETCODE_REPO_ROOT` (Makefile sets this to `kernel/` for
subtree builds).

---

## 4. Validate the archive

**Recommended — full CI-equivalent check:**

```bash
make validate
```

This runs:

1. `coherence-core-v0.1` — live coherence token tests + recovery smoke
2. `test-docs-code-drift` — docs ↔ contracts ↔ Makefile alignment

**Baseline only:**

```bash
make coherence-core-v0.1
```

| Step | Proves |
| --- | --- |
| `test-coherence-tokens-fast` | Issuance + `coherence_mismatch` enforcement |
| `coherence-recovery-smoke-fast` | Stale block → refresh → retry → verify |

Tag when green: **coherence-core-v0.1**.

---

## 5. Plugin integration (optional)

After the kernel baseline is green, validate the Hermes bridge from plugin root:

```bash
cd ../..   # dietcode-plugin root
python install.py --skip-npm
python scripts/kernel_phase3_rehearsal.py
python scripts/kernel_bridge_e2e.py
```

Inside Hermes:

```text
/dietcode kernel status
```

Enable governed mutation: set `dietcode.kernel.bridge.mutations_enabled: true`
in Hermes config. See [../../docs/kernel-bridge-operations.md](../../docs/kernel-bridge-operations.md).

---

## Daily workflow

```bash
# After pulling C++ changes
make kernel && make restart-agent-server-fast

# Quick health check
make validate

# RPC smoke
python3 scripts/dietcode_agent_client.py --self-test --compact
```

---

## Next steps

| Task | Doc |
| --- | --- |
| Hermes operator guide | [../../docs/kernel-bridge-operations.md](../../docs/kernel-bridge-operations.md) |
| Coherence tokens | [coherence-tokens.md](coherence-tokens.md) |
| RPC reference | [kernel-rpc.md](kernel-rpc.md) |
| Full test ladder | [testing.md](testing.md) |
| Env vars and paths | [agent-environment.md](agent-environment.md) |
| Integration phases | [../MIGRATION.md](../MIGRATION.md) |
