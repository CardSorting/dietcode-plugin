# Agent ergonomics

> **DietCode gives agents bounded autonomy through visible checkpoints enforced by the kernel.**

Agents should treat the kernel as a **state machine with six gates**, not a fire-and-forget file API. Full map: [checkpoint-model.md](checkpoint-model.md).

Integration surface: `scripts/dietcode_agent_client.py` + `scripts/dietcode_coherence.py`.

---

## Checkpoint queries

| RPC | Returns |
|-----|---------|
| `workspace.status` | Drift snapshot, anchors, verify state; optional `coherence` with `taskId` |
| `workspace.revision` | Revision IDs for coherence |
| `verify.status` | Verification gate state |
| `approval.list` | Pending approvals |

Use `taskId` on reads to receive coherence tokens — [coherence-tokens.md](coherence-tokens.md).

---

## Blocking responses

| Result | Action | Checkpoint |
|--------|--------|------------|
| `approvalRequired: true` | `approval.get` / `approval.resolve` | 3 |
| `workspaceDriftRequired: true` | `workspace.refreshAnchor`, retry with `contextRefreshId` | 2 |
| `coherence_mismatch` | Re-read `changedPaths` with `taskId`, regenerate patch, retry once | Pre-2 |
| `patch.apply` + receipt | Continue to verify | 4 |
| `verify.run` failure | Re-run or escalate | 5 |

### Error recovery hints

| Code | `nextRecommendedCommand` | Meaning |
|------|--------------------------|---------|
| `workspace_drift` | `workspace.status` | Refresh before retry |
| `stale_content` | `patch.validate` | Re-read before patch |
| `coherence_mismatch` | `file.read` | Stale task context |
| `approval_required` | `approval.get` | Wait for clearance |
| `approval_rejected` | `workspace.revision` | Revise plan |

---

## Verify command resolution

`scripts/dietcode_verification_authority.py`:

1. Explicit `command` in `verify.run`
2. `./verify.sh` in workspace root
3. `make test` if Makefile has `test` target
4. `npm test` / `npm run verify`

---

## Recommended loop

```text
1. file.read / patch.validate (taskId)  → coherence token (1)
2. workspace.status                     → drift check (2)
3. patch.apply (coherenceTokenId)       → mutation (4)
4. verify.run                           → verification (5)
5. Do not claim "done" until verify passes or is waived (6)
```

---

## Coherence recovery

`scripts/dietcode_coherence.py`:

```text
patch.apply → coherence_mismatch
  → context.stale
  → file.read changedPaths (taskId) → context.refreshed
  → regenerate patch from live content
  → coherence.retry (one attempt)
  → success OR coherence.operator_required
```

| Event | Meaning |
|-------|---------|
| `context.stale` | Anchors no longer match disk |
| `context.refreshed` | New coherence token issued |
| `coherence.retry` | Automatic retry |
| `coherence.operator_required` | Second mismatch — escalate |

---

## NDJSON harness events

Optional audit log via `DIETCODE_TASK_EVENT_LOG`:

| Event | Checkpoint |
|-------|------------|
| `workspace.drift.detected` | 2 |
| `context.stale` / `context.refreshed` | Coherence |
| `coherence.retry` / `coherence.operator_required` | Coherence |
| `approval.required` | 3 |
| `mutation.applied` | 4 |
| `verify.completed` | 5 |

Logs are audit trails — not gates.

---

## Do not

- Claim completion when verify has not passed
- Bypass drift with blind retries (use `workspace.refreshAnchor`)
- Skip coherence tokens when `taskId` is set
- Write files outside kernel RPC

---

## Related

- [kernel-rpc.md](kernel-rpc.md)
- [agent-tooling.md](agent-tooling.md)
- [error-codes.md](error-codes.md) — `coherence_mismatch`
