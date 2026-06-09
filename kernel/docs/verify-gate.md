# Verify gate

**Checkpoints 5–6 · Verification & completion** — *Did the result pass? Can this task be called done?*

[checkpoint-model.md](checkpoint-model.md) · [kernel-rpc.md](kernel-rpc.md)

A governed task is **not done** when the agent stops. It is done when the workspace is **verified** or **explicitly waived**.

---

## Task validity states

| `verificationState` | Meaning |
|---------------------|---------|
| `none` | No mutations — completion without verify |
| `verification_required` | Workspace mutated; verify pending |
| `verified` | Verify passed — task may complete |
| `verification_failed` | Verify ran and failed |
| `verification_waived` | Operator waived verify |

Task `status` mirrors the gate: `completed` only after `verified` or `verification_waived`.

---

## Event loop (kernel + harness)

```text
patch.apply success
    → workspace.mutated (kernel)

agent process exits
    → if mutations: verification still required (not completed)

verify.run passed
    → verify.completed (kernel)
    → harness may emit task.completed

verify.run failed
    → verify.failed (kernel)
    → status remains verification_failed
```

Pass `taskId` in RPC params to associate events with a governed task.

---

## Kernel RPCs

| RPC | Purpose |
|-----|---------|
| `verify.run` | Execute allowlisted command |
| `verify.status` | Poll running verify |

Default allowlist prefixes: `make test`, `make kernel`, `git diff --check`, `npm test`, `./verify.sh`.

```bash
python3 scripts/dietcode_agent_client.py rpc verify.run \
  --params '{"command":"./verify.sh","taskId":"task_1"}'
```

---

## Verify command resolution

`scripts/dietcode_verification_authority.py` resolves commands in order:

1. Explicit `command` in `verify.run`
2. `./verify.sh` in workspace root
3. `make test` if Makefile has `test` target
4. `npm test` / `npm run verify` from `package.json`

Harnesses should prefer workspace-native `verify.sh`.

---

## Operator actions (RPC / harness)

| Action | How |
|--------|-----|
| Run verify | `verify.run` with resolved command |
| Retry task | Re-run agent loop from refreshed context |
| Show failing output | Read `verify.status` / last verify result |
| Waive verification | Explicit harness or operator flag at checkpoint 5 |
| Cancel task | Stop agent; do not emit `task.completed` |

There is no in-tree HTTP task API. Integration is kernel RPC + Python harnesses.

---

## Core rule

> A task is not “done” just because the agent stopped. It is done when the workspace is either verified or explicitly waived.

This closes the loop: read anchors → coherence → drift → approval → mutation → **verify** → completion.

---

## Related

- [approval-lifecycle.md](approval-lifecycle.md)
- [coherence-tokens.md](coherence-tokens.md)
- [testing.md](testing.md) — `coherence-recovery-smoke-fast` includes verify pass
