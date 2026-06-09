# Kernel bridge operations

Operator guide for the DietCode Hermes kernel bridge (`dietcode_kernel` tool,
`~/.dietcode/control.sock`). The kernel is an **optional authority layer** on
macOS. BroccoliDB, JoyZoning, and governance work without it; Linux installs
degrade gracefully (no binary, no socket — no blocking).

## Authority model

| Layer | Role |
| --- | --- |
| **Kernel** | Physical mutation (`patch`) and verification (`verify.run`) |
| **JoyZoning** | Lifecycle journal (`mutation_record_patch`, `mutation_verify`) |
| **Convergence gate** | Completion authority — kanban is never auto-completed |
| **Raw Hermes writes** | Allowed by default; warn/block is opt-in |

Closed loop:

```text
intent → patch → receipt → journal → verify → verification journal → convergence
```

## Safe defaults (install)

`python install.py` seeds:

```yaml
dietcode:
  kernel:
    bridge:
      enabled: true
      mutations_enabled: false   # patch gate closed until you opt in
      raw_write_policy: warn     # hints only when gate is open
```

Raw writes are **never hard-blocked** unless **both**:

1. `raw_write_policy: block`
2. `DIETCODE_KERNEL_RAW_WRITE_BLOCK=1`

No env fuse is set by install.

## Enable warn mode (Phase 3A)

Use when the kernel bridge is healthy but you still want raw `write_file` /
`patch` to work — with hints to prefer `dietcode_kernel`.

```yaml
dietcode:
  kernel:
    bridge:
      enabled: true
      mutations_enabled: true      # opens patch gate when workspace + socket OK
      raw_write_policy: warn
```

Ensure workspace resolves to your project (not the plugin or kernel subtree):

```bash
export HERMES_KANBAN_WORKSPACE=/path/to/your/project
/dietcode kernel status
```

Expect `would_warn_on_raw_write: true` when `patch_allowed: true`.

## Enable block mode (Phase 3B)

Use when the kernel should reject raw Hermes writes in favor of
`dietcode_kernel(action='patch')`.

```yaml
dietcode:
  kernel:
    bridge:
      mutations_enabled: true
      raw_write_policy: block
```

```bash
export DIETCODE_KERNEL_RAW_WRITE_BLOCK=1
```

Doctor must show `would_block_raw_writes: true`. Without the env fuse, `block`
policy still **warns only**.

## Rollback to raw writes

1. Set `raw_write_policy: allow` (or `warn` if you only want hints off).
2. Unset the env fuse: `unset DIETCODE_KERNEL_RAW_WRITE_BLOCK`
3. Optionally close the patch gate: `mutations_enabled: false`
4. Restart Hermes or reload the plugin.
5. Confirm: `/dietcode kernel status` → `would_block_raw_writes: false`

Raw `write_file` / `patch` resume immediately; JoyZoning journals from prior
kernel patches remain in the journal DB.

## Run rehearsal

Quick integration check (disposable workspace, real socket when available):

```bash
cd /path/to/dietcode-plugin
python scripts/kernel_phase3_rehearsal.py
```

Full loop including verify and convergence (no auto-complete):

```bash
python scripts/kernel_bridge_e2e.py
```

## Kernel subcommands

```text
/dietcode kernel status              # operator summary (text)
/dietcode kernel                     # full JSON health payload
/dietcode kernel progress              # human summary (e.g. patch applying: src/foo.py, 38s elapsed)
/dietcode kernel progress --timeline   # ordered phase timeline with durations
/dietcode kernel progress --last 5     # summarize recent operations
/dietcode kernel progress --operation <id>  # filter tail/timeline to one operation
/dietcode kernel progress --tail       # JSONL tail (~/.dietcode/session/kernel-progress.jsonl)
/dietcode kernel progress --current    # full current-state JSON snapshot
/dietcode kernel last-error            # last normalized bridge error envelope
/dietcode kernel explain-gate          # closed gates, fixes, raw-write behavior
```

Progress is emitted automatically for `dietcode_kernel` patch, verify, status,
and search. Logs live under `~/.dietcode/session/` (see [agent-ergonomics.md](agent-ergonomics.md)).

If an operation is silent for 15+ seconds, doctor and `kernel status` report
**stale progress** and the log records `bridge.progress_stalled`.

## Interpret doctor output

Run `/dietcode doctor` after config changes.

| Signal | Meaning |
| --- | --- |
| `workspace safe_for_mutation: false` | Point `HERMES_KANBAN_WORKSPACE` at your project; never plugin/kernel roots |
| `patch_allowed: false` | Gate closed — check `mutations_enabled`, socket, token, workspace |
| `would_warn_on_raw_write: true` | Raw writes get `_kernel_raw_write_warning` when used |
| `would_block_raw_writes: true` | Raw writes blocked at `pre_tool_call` (config + fuse) |
| `Kernel verify … available` | `dietcode_kernel(action='verify')` ready |
| `socket=offline` | Run `make -C kernel restart-agent-server-fast` (macOS) |
| `platform_supported: false` | Linux — kernel optional; bridge hooks no-op for mutation |

## Failure modes

| Failure | Behavior |
| --- | --- |
| Socket dies mid-patch | Patch returns `bridge_transport_error` / `bridge_rpc_error`; no journal on failure |
| Token missing | `bridge_token_unavailable`; patch/verify blocked at client |
| Workspace deleted / invalid | `bridge_workspace_unsafe` or unresolved; gates close |
| Verify timeout | `bridge_rpc_timeout`; no `verify_ran`; journal skipped |
| JoyZoning journal unavailable | Tool success unchanged; `_journal_warning` on result |
| Block policy + fuse but gate closed | Falls back to allow/warn — raw writes not blocked |

## macOS kernel build

```bash
make -C kernel kernel
make -C kernel restart-agent-server-fast   # control.sock + token
```

## Troubleshooting (observability)

| Symptom | Check |
| --- | --- |
| Silent patch | `/dietcode kernel progress --current` |
| Socket offline | `/dietcode kernel status` |
| Token missing | `/dietcode kernel status` |
| Unsafe workspace | `/dietcode kernel explain-gate` |
| Patch gate closed | `/dietcode kernel explain-gate` |
| Verify command rejected | `/dietcode kernel status` (allowlist) |
| Journal unavailable | Tool result `_journal_warning` (mutation unchanged) |

## Related docs

- [agent-ergonomics.md](agent-ergonomics.md) — operator workflow and progress phases
- [architecture.md](architecture.md) — authority split and hook flow
- [dietcode-plugin.md](dietcode-plugin.md) — install, config, workflow
- [tools-reference.md](tools-reference.md) — `dietcode_kernel` tool
- [kernel/MIGRATION.md](../kernel/MIGRATION.md) — phase history
- [kernel/docs/verify-gate.md](../kernel/docs/verify-gate.md) — verify.run allowlist
- [CHANGELOG.md](../CHANGELOG.md) — release notes
