# Getting started

> **Goal:** Build the kernel, start the socket, and validate the coherence-core archive on your Mac.

[← Doc index](README.md) · [← README](../README.md#quick-start)

| Step | Action | Success signal |
|------|--------|----------------|
| 1 | [Prerequisites](#prerequisites) | Tools installed |
| 2 | [Build the kernel](#1-build-the-kernel) | `build/dietcode-kernel` exists |
| 3 | [Start the socket](#2-start-the-socket) | `rpc.ping` succeeds |
| 4 | [Open a workspace](#3-open-a-workspace) | Project bound to session |
| 5 | [Validate the archive](#4-validate-the-archive) | `make validate` green |

---

## Prerequisites

- **macOS** (Apple Silicon or Intel)
- **Xcode Command Line Tools** — `clang++`, `make`
- **Python 3.11+** — harnesses and `dietcode_agent_client.py`

No Node.js, no AppKit app bundle, no cloud account.

---

## 1. Build the kernel

The kernel is the **only** component allowed to change files on disk.

```bash
make kernel
```

First build compiles all sources (~45s). Subsequent builds are incremental (~1s for a single changed file).

| Artifact | Path |
|----------|------|
| Binary | `build/dietcode-kernel` |
| Object cache | `build/obj/` |

---

## 2. Start the socket

```bash
make restart-agent-server-fast   # or make restart-agent-server after C++ changes
python3 scripts/dietcode_agent_client.py --wait-ready --compact
python3 scripts/dietcode_agent_client.py rpc rpc.ping
```

| Path | Role |
|------|------|
| `~/.dietcode/control.sock` | Unix socket (mode `0600`) |
| `~/.dietcode/session.token` | RPC auth token |

If ping fails, see [troubleshooting.md](troubleshooting.md#kernel-socket).

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

Harnesses often set `DIETCODE_REPO_ROOT` (Makefile does this automatically).

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
|------|--------|
| `test-coherence-tokens-fast` | Issuance + `coherence_mismatch` enforcement |
| `coherence-recovery-smoke-fast` | Stale block → refresh → retry → verify |

Tag when green: **coherence-core-v0.1**.

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
|------|-----|
| Coherence tokens | [coherence-tokens.md](coherence-tokens.md) |
| RPC reference | [kernel-rpc.md](kernel-rpc.md) |
| Full test ladder | [testing.md](testing.md) |
| Env vars and paths | [agent-environment.md](agent-environment.md) |
| What was removed | [archive-note.md](archive-note.md) |
