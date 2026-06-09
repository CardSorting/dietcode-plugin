# Checkpoint model

> **DietCode gives agents bounded autonomy through visible checkpoints enforced by the kernel.**

[← Doc index](README.md) · [← README](../README.md)

A checkpoint is a **single question** the control plane must answer before the agent proceeds or before a task can be called done. Every governed feature maps to exactly one checkpoint.

---

## The six checkpoints

| # | Name | Plain English | Technical question |
|---|------|---------------|-------------------|
| 1 | **Context** | Did the agent read the right files? | Did the agent read valid state? |
| 2 | **Drift** | Did the repo change while the agent worked? | Did the workspace change underneath it? |
| 3 | **Approval** | Are you OK with this edit? | Is this mutation allowed? |
| 4 | **Mutation** | Did the patch apply cleanly? | Did the patch apply without error? |
| 5 | **Verification** | Do tests still pass? | Did the result pass? |
| 6 | **Completion** | Can we mark this task finished? | Can this task be called done? |

```text
1. Context   → read anchors + coherence token
2. Drift     → workspace changed?
3. Approval  → operator clearance?
4. Mutation  → patch applied?
5. Verify    → tests passed?
6. Completion → task may close?
```

---

## 1. Context

**Question:** Did the agent read valid state?

| Surface | Mechanism |
|---------|-----------|
| Kernel | `file.read*`, `workspace.snapshot`, `workspace.status`, `patch.validate` |
| Coherence | `taskId` on reads issues token — [coherence-tokens.md](coherence-tokens.md) |
| Recovery | `workspace.refreshAnchor` |

Context is foundational. Invalid context surfaces at drift (2) or mutation (4) if not caught by coherence first.

---

## 2. Drift

**Question:** Did the workspace change underneath the agent?

| Surface | Mechanism |
|---------|-----------|
| Kernel | `workspace.status`, `workspace.refreshAnchor`, `workspace.continueAnyway` |
| Block | Edit/Destructive RPCs when `driftDetected` |
| Events | `workspace.drift.detected` |
| Doc | [workspace-drift.md](workspace-drift.md) |

**Layering:** Coherence is checked **before** drift when `taskId` is set. See [coherence-tokens.md](coherence-tokens.md).

---

## 3. Approval

**Question:** Is this mutation allowed?

| Surface | Mechanism |
|---------|-----------|
| Kernel | `approval.list`, `approval.get`, `approval.resolve` |
| Default | Autonomy 3 — destructive ops queue `approvalRequired` |
| Harness | `scripts/dietcode_coherence.py` auto-resolves in smoke tests |
| Doc | [approval-lifecycle.md](approval-lifecycle.md) |

---

## 4. Mutation

**Question:** Did the patch apply cleanly?

| Surface | Mechanism |
|---------|-----------|
| Kernel | `patch.validate` → `patch.apply` / `patch.applyBatch` |
| Receipt | `mutationReceipt`, `workspace.revision` |
| Blocks | `stale_content`, `coherence_mismatch`, drift (2), approval (3) |
| Harness | `scripts/dietcode_coherence.py` — `recover_and_apply_patch` |

---

## 5. Verification

**Question:** Did the result pass?

| Surface | Mechanism |
|---------|-----------|
| Kernel | `verify.run`, `verify.status` |
| Events | `verify.completed`, `verify.failed` |
| Resolver | `scripts/dietcode_verification_authority.py` |
| Doc | [verify-gate.md](verify-gate.md) |

Waive is an explicit operator override at checkpoint 5 only.

---

## 6. Completion

**Question:** Can this task be called done?

| Rule | Detail |
|------|--------|
| Agent exit ≠ done | Process end is not completion |
| Requires | `verified`, `verification_waived`, or `none` (no mutations) |
| Harness | NDJSON `task.completed` after verify passes |

---

## Feature audit

| Feature | Checkpoint |
|---------|------------|
| `file.read` hash anchors | 1 Context |
| Coherence tokens (`taskId`) | 1 Context (enforcement pre-2) |
| `coherence_mismatch` | Pre-drift stale context |
| `workspace.drift.detected` | 2 Drift |
| `approval.*` | 3 Approval |
| `patch.apply` + receipt | 4 Mutation |
| `workspace.mutated` | 4 → arms 5 |
| `verify.run` | 5 Verification |
| `task.completed` (harness) | 6 Completion |
| Coherence recovery smoke | Proves refresh + retry path |

---

## Noise bucket (not checkpoints)

| Feature | Role |
|---------|------|
| Kernel offline / reconnect | Transport |
| Kernel restart | [session-recovery.md](session-recovery.md) |
| NDJSON harness events | Audit trail |
| Benchmark / journal | Offline research — parallel track |

---

## Coherence hardening (v0.1)

| Area | Implementation |
|------|----------------|
| Coherence tokens | `MacControlCoherenceTokens.mm` |
| Recovery loop | `scripts/dietcode_coherence.py` |
| Verify resolver | `dietcode_verification_authority.py` |
| Agent errors | `coherence_mismatch` recovery hints |
| Release gate | `make coherence-core-v0.1` |

---

## Release baseline

```bash
make coherence-core-v0.1
```

Runs `test-coherence-tokens` and `coherence-recovery-smoke-fast` (full rebuild variant: `coherence-recovery-smoke`). See [testing.md](testing.md).

---

## Related

| Doc | Checkpoint |
|-----|------------|
| [agent-ergonomics.md](agent-ergonomics.md) | Agent API |
| [workspace-drift.md](workspace-drift.md) | 2 |
| [approval-lifecycle.md](approval-lifecycle.md) | 3 |
| [verify-gate.md](verify-gate.md) | 5–6 |
| [kernel-rpc.md](kernel-rpc.md) | RPC orchestration |
| [architecture.md](architecture.md) | Wiring |
