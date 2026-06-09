# Approval lifecycle

**Checkpoint 3 · Approval** — *Is this mutation allowed?*

[checkpoint-model.md](checkpoint-model.md) · [kernel-rpc.md](kernel-rpc.md)

The kernel supervises destructive workspace mutations through a pending-approval registry. Agents never mutate without kernel authority.

---

## Flow

```text
agent proposes destructive RPC
    ↓
kernel queues PendingApproval
    ↓
kernel emits approval.required
    ↓
operator or harness resolves via approval.resolve
    ↓
kernel executes (approve) or cancels (reject)
    ↓
kernel emits approval.resolved
```

---

## Autonomy levels

| Level | Behavior |
|-------|----------|
| 1 | Auto-allow destructive mutations (testing) |
| 2 | Heuristic safe-list; unsafe ops queued |
| 3 | Supervised — explicit approval required (**default**) |

`dietcode-kernel` starts at autonomy **3**.

---

## PendingApproval shape

```json
{
  "approvalId": "appr_1",
  "taskId": "task_…",
  "actionType": "patch",
  "method": "patch.apply",
  "reason": "Destructive mutation requires explicit approval.",
  "caller": "agent",
  "status": "pending",
  "preview": { "path": "src/foo.ts", "patch": "…" },
  "expiresAt": "…"
}
```

---

## Kernel RPCs

| RPC | Purpose |
|-----|---------|
| `approval.list` | List pending / resolved approvals |
| `approval.get` | Fetch one approval by id |
| `approval.resolve` | Approve or reject; executes on approve |

```bash
python3 scripts/dietcode_agent_client.py rpc approval.resolve \
  --params '{"approvalId":"appr_1","decision":"approved","resolvedBy":"operator","reason":"looks good"}'
```

Harness auto-approve: `scripts/dietcode_coherence.py` (`resolve_kernel_approval`).

---

## Timeouts

Pending approvals expire after **30 minutes**. Expired approvals return `approval_expired` — not implicit approve.

---

## Gate ordering

Approval runs after coherence and drift gates. A patch blocked by `coherence_mismatch` never reaches the approval queue.

---

## Related

- [agent-ergonomics.md](agent-ergonomics.md)
- [error-codes.md](error-codes.md)
- [coherence-tokens.md](coherence-tokens.md)
