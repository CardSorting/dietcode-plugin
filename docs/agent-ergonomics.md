# Agent ergonomics and kernel observability

Phase 6 operator workflow for long coherent mutation cycles. The kernel bridge
works; this pass makes it **legible** — agents and operators can see what phase
the system is in without adding mutation authority.

## Quick operator loop

```text
1. /dietcode kernel cockpit        → one-screen state, gates, next action
2. /dietcode kernel status          → gates, socket, workspace
3. dietcode_kernel(action='patch') → governed mutation (instant ack in progress + result)
4. /dietcode kernel watch          → compact live line with operation state
5. /dietcode kernel progress       → human summary + next-phase hints
6. dietcode_kernel(action='verify')→ allowlisted verify.run
7. /dietcode kernel perf --ux      → responsiveness budgets
8. /dietcode kernel last-error     → normalized failure envelope (if any)
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
| `operation.accepted` | Immediate ack — operation_id, phase sequence, next hint |
| `patch.staging` | Pre-apply mutation summary (files, bytes, taskId, verify hint) |
| `bridge.heartbeat` | Coalesced long-phase heartbeat (still verifying…, elapsed) |
| `bridge.preflight` | Config/workspace checks after ack |
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
| `/dietcode kernel watch` | Compact single-line live summary |
| `/dietcode kernel watch --follow` | Auto-refresh every ~1.5s (up to 30s) |
| `/dietcode kernel perf --ux --last 10` | Ack latency, silent gaps, UX budget pass/fail |
| `/dietcode kernel cockpit` | One-screen operator summary |

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

## Responsiveness (Phase 7B)

Perceived performance without weakening safety gates:

- **Instant ack** — `operation.accepted` within ~100ms; `_kernel_acknowledgement` on tool results
- **Next-phase hints** — `next: patch.validate`, etc.; stall events include `waiting_reason`
- **Heartbeats** — coalesced `bridge.heartbeat` during verify/approval/coherence/patch/journal
- **Watch mode** — `/dietcode kernel watch` compact lines like `PATCH 7fd2 applying src/foo.py (12s)`
- **Pre-stage summary** — `patch.staging` before apply (files, bytes, taskId, verify hint)
- **UX perf** — `/dietcode kernel perf --ux --last 10` (ack latency, silent windows)
- **Long-run tiers** — 30s / 60s / 120s stress notes with suggested diagnostics

Optional warm idle state:

```yaml
dietcode:
  kernel:
    bridge:
      keep_warm: false
      keep_warm_idle_timeout_ms: 120000
      keep_warm_ping_interval_ms: 30000
```

## Cockpit (Phase 7C)

Release-grade operator UX — no mutation semantics changes.

### Operation states

Progress, watch, cockpit, and `perf --ux` normalize phases into:

`idle` · `accepted` · `preparing` · `validating` · `recovering` · `applying` ·
`verifying` · `journaling` · `blocked` · `stalled` · `failed` · `complete`

### Symbols

UTF-8 terminals: `✓` complete · `!` warning · `✕` failed · `…` running  
ASCII fallback: set `DIETCODE_ASCII_ONLY=1`

### Next action (exactly one)

Every cockpit/progress view recommends one of:

`wait` · `check last-error` · `run explain-gate` · `retry` · `rollback block mode` ·
`start kernel socket` · `enable mutations` · `set workspace root`

### UX budgets (`perf --ux`)

| Metric | Budget |
| --- | --- |
| Time to acknowledgement | < 100ms |
| Time to first progress | < 500ms |
| Silent window (active) | < 5s |

Smoke: `python scripts/kernel_cockpit_smoke.py`

## Sonic tempo (Phase 7D)

High-tempo UX — **GOTTA GO FAST (with receipts)**. No mutation semantics changes.

- **Instant ack** — `… PATCH accepted — src/foo.py` flushed before heavy work (<50ms target)
- **Kinetic watch** — `/dietcode kernel watch --follow` — spinner, in-place line refresh, ANSI colors
- **Micro-phase suppression** — sub-100ms noise hidden unless error/stall/recovery/approval
- **Fast path** — `FAST PATH ACTIVE` when `mode: sonic_fast_path`
- **ETA** — `~3s remaining` when history confidence is high (hidden otherwise)
- **Event hooks** — optional local shell hooks (`event_hooks_enabled: false` by default)

```yaml
dietcode:
  kernel:
    bridge:
      event_hooks_enabled: false
      event_hooks:
        operation_accepted: "echo dietcode ack"
        operation_failed: "echo dietcode fail"
        verify_passed: "echo dietcode verify ok"
        stalled: "echo dietcode stalled"
```

Bench: `python scripts/kernel_sonic_bench.py --compact`  
ASCII mode: `DIETCODE_ASCII_ONLY=1`

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

## Roadmap checkpoint operator loop

Long-horizon steering surface for product and architecture coherence:

```text
1. /roadmap cockpit              → health, schema, freshness, code soup, next action
2. /roadmap explain-stale        → why checkpoint may be outdated vs git activity
3. roadmap(action='guide')       → phase + checkpoint_freshness + operator hints
4. roadmap(action='checkpoint')  → evidence + code_soup_pre_audit + algorithm
5. Edit ROADMAP.md per skill     → auto _roadmap_write_hint on native writes
6. roadmap(action='validate')     → schema gate before closing the pass
7. /roadmap progress --current   → full progress + gate snapshot JSON
8. Return checkpoint summary     → not the full ROADMAP.md unless asked
```

Progress storage:

| Path | Purpose |
| --- | --- |
| `~/.dietcode/session/roadmap-progress.jsonl` | Append-only roadmap tool activity |
| `~/.dietcode/session/roadmap-progress-current.json` | Latest roadmap action snapshot |
| `.dietcode/roadmap-state.json` | Workspace-local validate/checkpoint memory (includes `validation_pending` after ROADMAP.md writes) |

Slash commands: `/roadmap cockpit`, `/roadmap explain-gate`, `/roadmap doctor`, `/rm validate`, `/dietcode roadmap`.

Native wiring:

- Dedicated Hermes toolset: `roadmap` (tools: `roadmap`, `roadmap_checkpoint`)
- `joyzoning(action='context')` → `roadmap_checkpoint` brief + merged `next_actions`
- `joyzoning(action='roadmap')` → full cockpit payload with `recommended_next_action`
- Stale checkpoint blocks `kanban_complete` at `pre_tool_call` when `warn_on_stale_before_complete` is enabled
- Unvalidated ROADMAP.md edits block `kanban_complete` when `block_kanban_on_validation_pending` is enabled (default)
- `roadmap(action='explain_gate')` returns kernel-style `closed_gates` / `open_gates` diagnostics
- `session.start` journal payload includes roadmap phase and `first_call`
- `write_file` / `patch` on `ROADMAP.md` → `_roadmap_write_hint` (validate follow-up)
- Roadmap tool calls emit `roadmap.*` runtime events when execution journal is on

Checkpoint evidence includes: README/architecture excerpts, git history, TODO markers, test file count, and programmatic `code_soup_audit` signals (duplicate basenames, hook registrars, config sources).

Smoke: `python scripts/roadmap_smoke.py` · operator: `python scripts/roadmap_operator_smoke.py` · audit: `python scripts/roadmap_audit.py`

## Constraints (unchanged)

- No new mutation authority
- Safety fuses and convergence gate preserved
- Kanban never auto-completed from kernel progress
- Linux degrades gracefully (no socket — progress commands still work; logs empty)

## Related

- [kernel-bridge-operations.md](kernel-bridge-operations.md) — bridge config and rollback
- [tools-reference.md](tools-reference.md) — `dietcode_kernel` tool
- [../kernel/docs/agent-ergonomics.md](../kernel/docs/agent-ergonomics.md) — native kernel checkpoint model
