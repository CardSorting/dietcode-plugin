# Coherence tokens (v0.1)

**Low-level enforcement primitive** beneath checkpoint 2 (Drift). Drift is broad — *something changed*. Coherence mismatch is precise — *this task is mutating from stale observed state*.

> DietCode uses coherence tokens so agents can only mutate the workspace they actually observed.

[workspace-drift.md](workspace-drift.md) · [kernel-rpc.md](kernel-rpc.md) · [error-codes.md](error-codes.md)

---

## What it answers

1. Did the workspace change since this task read?
2. Did any anchored file change?
3. Is verification older than the latest mutation context?

No graph. No ledger. Caps: **40 tasks**, **100 anchors/task**, **30 min TTL**. Hashes only files actually read.

---

## Counters

| Counter | When it increments |
|---------|-------------------|
| `workspaceRevision` | Kernel mutation; patch apply/batch |
| `verifyRevision` | Successful `verify.run` |

---

## Issuing reads

Coherence is issued on these methods when `taskId` is set:

- `file.read`
- `file.readBatch`
- `file.readRange`
- `file.readAround`
- `file.stat`
- `workspace.status`

### Batch response

```json
{
  "results": {
    "src/a.ts": { "ok": true, "text": "..." },
    "src/b.ts": { "ok": true, "text": "..." }
  },
  "coherence": {
    "tokenId": "coh_123",
    "workspaceRevision": 41,
    "verifyRevision": 7,
    "anchors": {
      "src/a.ts": "fnv1a:...",
      "src/b.ts": "fnv1a:..."
    }
  }
}
```

### Single-file response

```json
{
  "text": "...",
  "coherence": {
    "tokenId": "coh_123",
    "workspaceRevision": 41,
    "verifyRevision": 7,
    "anchors": {
      "src/foo.ts": "fnv1a:abc123deadbeef00"
    }
  }
}
```

Anchors use kernel content hash (`fnv1a:<hex>`).

---

## Mutation params

Required when `taskId` is set on `patch.apply` / `patch.applyBatch`:

```json
{
  "taskId": "task_12",
  "coherenceTokenId": "coh_123",
  "expectedWorkspaceRevision": 41
}
```

---

## Stale response

```json
{
  "error": {
    "string_code": "coherence_mismatch",
    "reason": "anchored_file_changed",
    "changedPaths": ["src/foo.ts"],
    "currentWorkspaceRevision": 42,
    "requiredAction": "refresh_context"
  }
}
```

**Recovery:** re-read affected paths with the same `taskId`, regenerate patch from live content, retry with fresh token.

---

## Python recovery loop

`scripts/dietcode_coherence.py` implements the governed retry path used by harnesses:

```text
patch.apply → coherence_mismatch
  → emit context.stale
  → file.read changedPaths (taskId) → context.refreshed
  → rebuild patch from live content
  → emit coherence.retry (one automatic attempt)
  → success OR coherence.operator_required
```

Smoke proof: `scripts/coherence_recovery_smoke.py`

```bash
make coherence-recovery-smoke-fast
```

Full gate (rebuild + restart):

```bash
make coherence-recovery-smoke
```

---

## Layering with drift

For governed mutations (`taskId` set), the kernel checks **coherence before drift**. Agents receive `coherence_mismatch` (precise stale context) rather than `workspaceDriftRequired` (broad workspace change). See [workspace-drift.md](workspace-drift.md).

---

## Agent loop

```text
read (taskId) → coherence token
prepare patch → include coherenceTokenId + expectedWorkspaceRevision
patch.apply → kernel validates
coherence_mismatch → refresh context and retry once
valid → approval → mutation → verify
```

---

## Release gate

```bash
make coherence-core-v0.1
```

| Step | Proves |
|------|--------|
| `test-coherence-tokens` | Kernel issuance + enforcement (incl. `file.readBatch`) |
| `coherence-recovery-smoke-fast` | Python recovery vertical |

Tag: **coherence-core-v0.1**. Full CI: `make validate`.

---

## Related

- [agent-ergonomics.md](agent-ergonomics.md) — agent-facing loop
- [checkpoint-model.md](checkpoint-model.md) — gate map
- [testing.md](testing.md) — validation ladder
