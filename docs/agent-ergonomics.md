# Agent ergonomics and kernel observability

Phase 6 operator workflow for long coherent mutation cycles. The kernel bridge
works; this pass makes it **legible** — agents and operators can see what phase
the system is in without adding mutation authority.

## Quick operator loop

```text
1. /dietcode kernel status          → gates, socket, workspace
2. dietcode_kernel(action='patch') → governed mutation
3. /dietcode kernel progress       → live phase + elapsed_ms
4. dietcode_kernel(action='verify')→ allowlisted verify.run
5. /dietcode kernel last-error     → normalized failure envelope (if any)
```

Progress is written automatically. You do not need to opt in.

## Progress storage

| Path | Purpose |
| --- | --- |
| `~/.dietcode/session/kernel-progress.jsonl` | Append-only structured event log |
| `~/.dietcode/session/kernel-progress-current.json` | Latest operation snapshot |

Events include: `correlation_id`, `operation_id`, monotonic `ts_mono`, `duration_ms`,
`phase`, `string_code`, `taskId`, `action`, `path`, `workspace_root`, `elapsed_ms`,
`attempt`.

### Phases

| Phase | Meaning |
| --- | --- |
| `bridge.preflight` | Operation started; config/workspace checks |
| `socket.ready` | Control socket + token available |
| `workspace.open` | Kernel workspace opened on validated root |
| `coherence.read` | Coherence-aware file read |
| `coherence.anchor_refresh` | Anchor refresh / coherence retry |
| `patch.validate` | Patch validation RPC |
| `patch.apply` | Governed mutation RPC |
| `approval.waiting` | Kernel approval required |
| `verify.running` | `verify.run` in flight |
| `journal.recording` | JoyZoning journal hook (non-blocking) |
| `convergence.checking` | Verify journal + convergence context |
| `done` | Operation completed successfully |
| `error` | Operation failed |
| `bridge.progress_stalled` | No progress update for 15s |

## Slash commands

| Command | Output |
| --- | --- |
| `/dietcode kernel progress` | Human summary (e.g. `patch applying: src/foo.py, attempt 2, 38s elapsed`) |
| `/dietcode kernel progress --timeline` | Ordered phase timeline with durations |
| `/dietcode kernel progress --last 5` | Summary of last N operations |
| `/dietcode kernel progress --operation <id>` | Filter `--tail` / `--timeline` to one operation |
| `/dietcode kernel progress --tail` | JSON tail of progress JSONL |
| `/dietcode kernel progress --current` | Full current snapshot JSON |
| `/dietcode kernel last-error` | Last normalized error envelope |
| `/dietcode kernel explain-gate` | Closed gates, fixes, raw-write behavior |

Error and warn envelopes include: `next_action`, `safe_to_retry`, `retry_command`,
`diagnostic_command`, `rollback_command` (when relevant).

`/dietcode doctor` and `/dietcode kernel status` also surface **stale progress**
when an operation has not updated for 15 seconds.

## Agent-facing hints

`dietcode_kernel` responses include `_kernel_operator_hints`:

- `workspace_root` — resolved mutation workspace
- `mutation_safe` — whether workspace passes safe_for_mutation
- `patch_allowed` — whether governed patch is available
- `preferred_command` — exact tool invocation shape
- `missing_gate` — closed gate id when patch unavailable
- `recovery_suggestion` — plain-language next step
- `suggested_slash_command` — operator command to run

On failure, `_kernel_error_envelope` adds:

- `human_message`, `operator_action`, `retryable`, `phase`, `raw_error` summary

Raw `write_file` / `patch` warn/block payloads (Phase 3A/3B) include the same
`preferred_command`, `recovery_suggestion`, and `suggested_slash_command` fields.

## When the kernel feels stuck

Work through this list in order — each step is read-only or diagnostic:

1. **Check progress** — `/dietcode kernel progress`  
   Human summary: `patch applying…`, `waiting for approval…`, `verify running…`, or `stalled: last phase …`.

2. **Check timeline** — `/dietcode kernel progress --timeline`  
   See which phase is taking time and how long each step lasted.

3. **Check last error** — `/dietcode kernel last-error`  
   Normalized envelope with `next_action`, `safe_to_retry`, and `retry_command`.

4. **Explain gates** — `/dietcode kernel explain-gate`  
   Lists closed gates, exact config/env fix, whether the fix is safe, and current `raw_write_policy` behavior.

5. **Verify socket/token** — `/dietcode kernel status`  
   `socket=live` and `token=ok` required for governed patch/verify.

6. **Fallback to raw writes** — patch gate closed or kernel unavailable  
   Raw `write_file` / `patch` remain available unless block mode is active (config + `DIETCODE_KERNEL_RAW_WRITE_BLOCK=1`).

7. **Rollback block mode** — if raw writes are hard-blocked  
   Set `raw_write_policy: allow` (or `warn`), unset `DIETCODE_KERNEL_RAW_WRITE_BLOCK`, reload Hermes.  
   `/dietcode kernel explain-gate` shows the exact rollback line when block mode is on.

For multiple operations in one session: `/dietcode kernel progress --last 5` or  
`/dietcode kernel progress --operation <operation_id> --timeline`.

## Performance (Phase 7)

Measure before tuning: `/dietcode kernel perf --last 10`

Optional bridge config (safe defaults seeded by install):

```yaml
dietcode:
  kernel:
    bridge:
      preflight_cache_ttl_ms: 5000
      workspace_open_cache: true
      progress_flush_interval_ms: 250
      verify_timeout_ms: 0          # 0 = use request_timeout_sec
      max_concurrent_mutations_per_workspace: 1
```

Bench script: `python scripts/kernel_bridge_perf.py --compact`

## Troubleshooting

| Symptom | Likely cause | What to run |
| --- | --- | --- |
| Silent patch | Long RPC without visible phase | `/dietcode kernel progress --current` |
| Socket offline | `control.sock` down | `/dietcode kernel status` → `make -C kernel restart-agent-server-fast` |
| Token missing | `session.token` absent | Restart agent server |
| Unsafe workspace | Plugin/kernel root resolved | Set `HERMES_KANBAN_WORKSPACE` → `/dietcode kernel explain-gate` |
| Patch gate closed | `mutations_enabled: false` | `/dietcode kernel explain-gate` |
| Verify command rejected | Not on allowlist | `/dietcode kernel status` (allowlist count) |
| Journal unavailable | JoyZoning disabled/DB down | Patch still succeeds; check `_journal_warning` on result |
| Stalled operation | No progress for 15s+ | `/dietcode kernel progress` — look for `bridge.progress_stalled` |

## Constraints (unchanged)

- No new mutation authority
- Safety fuses and convergence gate preserved
- Kanban never auto-completed from kernel progress
- Linux degrades gracefully (no socket — progress commands still work; logs empty)

## Related

- [kernel-bridge-operations.md](kernel-bridge-operations.md) — bridge config and rollback
- [tools-reference.md](tools-reference.md) — `dietcode_kernel` tool
- [../kernel/docs/agent-ergonomics.md](../kernel/docs/agent-ergonomics.md) — native kernel checkpoint model
