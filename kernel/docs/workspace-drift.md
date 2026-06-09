# Workspace drift

**Checkpoint 2 · Drift** — *Did the workspace change underneath the agent?*

[checkpoint-model.md](checkpoint-model.md) · [coherence-tokens.md](coherence-tokens.md)

DietCode tracks workspace **state validity** so agents cannot mutate files after the world changed underneath them.

---

## Kernel RPCs

| RPC | Permission | Purpose |
|-----|------------|---------|
| `workspace.status` | Read | Full drift snapshot |
| `workspace.snapshot` | Read | Point-in-time file hashes |
| `workspace.refreshAnchor` | Read | Re-anchor tracked files + git HEAD; bumps `contextRefreshId` |
| `workspace.continueAnyway` | Read | One-shot override (5 min) for supervised flows |

### `workspace.status` fields

- `root` — active workspace path
- `gitHead` / `gitBranch` — current git state
- `anchorGitHead` / `anchorRefreshedAt` — last refresh anchor
- `dirtyFiles` — git modified/staged/untracked paths
- `fileAnchors` — mtime/hash anchors for agent-touched files
- `affectedFiles` — human-readable drift list with `reason`
- `lastVerifiedCommand` / `lastVerifiedAt` / `lastVerifyPassed`
- `contextRefreshId` — monotonic id required after refresh
- `driftDetected` / `requiresContextRefresh`

---

## Mutation gate

**Rule:** If the world changed underneath the agent, DietCode blocks **Edit** and **Destructive** RPCs until context is refreshed.

```json
{
  "workspaceDriftRequired": true,
  "workspace": { "...": "workspace.status payload" },
  "blockedMethod": "patch.apply",
  "mode": "workspace_drift_pending"
}
```

Unblock:

1. **Refresh** — `workspace.refreshAnchor`, retry with `contextRefreshId`
2. **Continue anyway** — `workspace.continueAnyway` or `continueAnyway: true` on mutation

Kernel emits `workspace.drift.detected` when blocked.

---

## Coherence before drift

For governed mutations (`taskId` set), the kernel checks **coherence before drift**. Agents receive `coherence_mismatch` (precise stale context) rather than `workspaceDriftRequired` (broad change). Drift still applies when no task coherence envelope is active.

See [coherence-tokens.md](coherence-tokens.md).

---

## Agent loop

Harness pattern for `patch.apply` / `patch.applyBatch`:

1. `workspace.refreshAnchor`
2. Poll `workspace.status` until `driftDetected` is false
3. Retry mutation with returned `contextRefreshId`

Python: `scripts/dietcode_coherence.py` (`_complete_after_workspace_drift`).

---

## Anchoring

Hashes tracked when the agent:

- Reads files (`file.read`, `file.readRange`, `file.readAround`, `file.readBatch`)
- Applies patches (`patch.apply` / batch)

`workspace.refreshAnchor` re-reads tracked paths, clears external-change flags, snapshots git HEAD, increments `contextRefreshId`.

---

## Related

- [agent-ergonomics.md](agent-ergonomics.md)
- [kernel-rpc.md](kernel-rpc.md)
- [error-codes.md](error-codes.md) — `coherence_mismatch`
