# Architecture

> **Headless governed mutation kernel** — JSON-RPC control plane, single mutation authority, Python harness integration.

[checkpoint-model.md](checkpoint-model.md) · [coherence-tokens.md](coherence-tokens.md) · [file-structure.md](file-structure.md)

---

## System diagram

```text
┌─────────────────────────────────────────────────────────┐
│  Agents / harnesses / CI                                │
│  dietcode_agent_client.py · dietcode_coherence.py       │
└───────────────────────┬─────────────────────────────────┘
                        │ JSON lines + session.token
┌───────────────────────▼─────────────────────────────────┐
│  dietcode-kernel (C++/ObjC++)                           │
│  MacControlServer · coherence tokens · approvals        │
│  drift · verify · WorkspaceSession                      │
└───────────────────────┬─────────────────────────────────┘
                        │
                   Workspace on disk
```

No in-tree UI. No HTTP bridge. Agents integrate through the Python CLI or direct socket RPC.

---

## Kernel binary

| Item | Location |
|------|----------|
| Binary | `build/dietcode-kernel` |
| Entry | `src/kernel/main.mm`, `KernelRuntime.mm` |
| RPC dispatch | `src/platform/macos/control/MacControlServer.mm` |
| Coherence registry | `MacControlCoherenceTokens.mm` |
| Workspace ops | `src/kernel/workspace/` |
| Socket | `~/.dietcode/control.sock` |

Headless build — no AppKit editor. Workspace root comes from `WorkspaceSession` / `DIETCODE_REPO_ROOT`.

```bash
make kernel
DIETCODE_REPO_ROOT=$(pwd) ./build/dietcode-kernel --ensure-socket
```

Build uses incremental object files under `build/obj/` (~1s rebuild after small changes).

---

## Control plane categories

| Category | File | Responsibility |
|----------|------|----------------|
| File I/O | `MacControlServer+File.mm` | Reads, stats, batch reads |
| Coherence | `MacControlServer+Coherence.mm` | Token issuance and validation |
| Drift | `MacControlServer+WorkspaceDrift.mm` | Anchor tracking, refresh |
| Approval | `MacControlServer+Approval.mm` | Pending approval queue |
| Verify | `MacControlServer+VerifyGate.mm` | `verify.run` allowlist |
| Patch | `MacControlPatchService.mm` | Apply, validate, receipts |

Platform services (`src/platform/macos/services/`) provide subprocess execution, diff preview, symbol indexing — all used by kernel RPC paths.

---

## Wire format

Single-line JSON per request:

```json
{
  "id": "uuid",
  "schemaVersion": "1.6.2",
  "method": "patch.apply",
  "params": {},
  "token": "<session.token>"
}
```

Responses: `{ "id", "ok", "result" }` or `{ "id", "ok": false, "error": { "string_code", "message", ... } }`.

Token is **top-level** — never nested in `params`.

---

## Coherence layer

When `taskId` is set on reads, the kernel issues coherence tokens. Mutations must include `coherenceTokenId` + `expectedWorkspaceRevision` or receive `coherence_mismatch` **before** drift checks.

| Component | Path |
|-----------|------|
| Token registry | `MacControlCoherenceTokens.mm` |
| Recovery helpers | `scripts/dietcode_coherence.py` |
| Live tests | `scripts/test_coherence_tokens.py` |
| Recovery smoke | `scripts/coherence_recovery_smoke.py` |

---

## Session and recovery

Bounded on-disk state under `~/.dietcode/session/` (optional `DIETCODE_SESSION_DIR`):

- Pending approvals (kernel authoritative)
- Recent diffs and event ring

Not a checkpoint — transport hygiene. See [session-recovery.md](session-recovery.md).

---

## Autonomy

Default autonomy **3 (supervised)**. Destructive RPCs (`patch.apply` with `confirm`, `workspace.openFolder`, …) return `approvalRequired` until `approval.resolve`.

---

## Validation architecture

| Gate | Command | Scope |
|------|---------|-------|
| Coherence baseline | `make coherence-core-v0.1` | Tokens + recovery smoke |
| Full archive validate | `make validate` | Baseline + docs drift |
| Broader RPC ladder | `make verify-agent-runtime-full` | Optional harness depth |

CI: `.github/workflows/coherence-core.yml` runs `make validate` on macOS.

---

## Archived surfaces

Cockpit UI, HTTP bridge, TypeScript agent-bridge, Hermes integrations, and editor scaffold were experimental proofs. They are removed from the active tree. See [archive-note.md](archive-note.md).

---

## Related

- [kernel-rpc.md](kernel-rpc.md) — method reference
- [agent-ergonomics.md](agent-ergonomics.md) — agent loop
- [testing.md](testing.md) — release gates
- [ARCHIVE.md](../ARCHIVE.md) — retained vs removed map
