# Architecture

DietCode is split into a Python Hermes plugin surface, a bundled TypeScript
BroccoliDB runtime, and an optional quarantined macOS kernel subtree connected
through the **kernel authority bridge**.

## Authority split

```text
┌─────────────────────────────────────────────────────────────────┐
│                        Hermes Agent                              │
│  write_file / patch (raw)  │  dietcode_kernel (governed)         │
└────────────┬───────────────┴──────────────┬──────────────────────┘
             │ pre_tool_call warn/block      │ RPC patch / verify
             ▼                               ▼
┌────────────────────────┐       ┌───────────────────────────────┐
│  JoyZoning journal     │◄──────│  Kernel (macOS, optional)    │
│  convergence gates     │ receipt│  control.sock + coherence    │
└────────────────────────┘       └───────────────────────────────┘
             │
             ▼
┌────────────────────────┐
│  BroccoliDB / BroccoliQ │  (graph, queue — independent layer)
└────────────────────────┘
```

| Layer | Path / surface | Role |
| --- | --- | --- |
| **Kernel** | `kernel/`, `dietcode_kernel` tool | Physical mutation + verify.run |
| **Bridge** | `lib/agent/kernel_bridge_client.py` | RPC, preflight, patch gate, receipts |
| **JoyZoning** | `lib/agent/joyzoning/` | Lifecycle journal, convergence |
| **BroccoliDB** | `broccolidb/` | Repository graph, audit, queue |
| **Governance** | `lib/agent/governance_exemptions.py` | Import/layer policy transforms |
| **Raw writes** | Hermes native tools | Default allow; router warn/block opt-in |

Closed loop:

```text
intent → patch → receipt → journal → verify → verification journal → convergence
```

## Runtime layers

| Path | Responsibility |
| --- | --- |
| `plugin.yaml` | Hermes manifest and hook declaration. |
| `_bootstrap.py` | Aliases plugin tree to `plugins.dietcode` for drag-and-drop installs. |
| `hooks.py` | Composed Hermes hook handlers (kernel + JoyZoning + governance + kanban). |
| `public.py` | Stable import surface for hooks and slash commands. |
| `tools_loader.py` | Tool module imports and registry validation. |
| `health.py` | `/dietcode status`, `doctor`, `kernel status`. |
| `install.py` | Seamless defaults including safe kernel bridge config. |
| `contracts.py` | Runtime contract checks for hooks, tools, layout. |
| `audit.py` | Static audits for stale paths and layout parity. |
| `lib/kernel_workspace.py` | Workspace root resolution and safety validation. |
| `lib/kernel_health.py` | Kernel doctor, bridge status summary, build helpers. |
| `lib/agent/kernel_bridge_client.py` | RPC session, patch/verify apply, patch gate. |
| `lib/agent/kernel_receipt_journal.py` | Patch receipt → JoyZoning `record_patch`. |
| `lib/agent/kernel_verify_journal.py` | Verify result → JoyZoning `record_verification`. |
| `lib/agent/kernel_raw_write_router.py` | Raw write warn/block at `pre_tool_call`. |
| `lib/agent/kernel_verify_bridge.py` | Client-side verify command allowlist. |
| `lib/runtime/kernel_hooks.py` | Kernel pre/post/transform hook implementations. |
| `lib/tools/kernel_bridge_tools.py` | Hermes `dietcode_kernel` tool registration. |
| `lib/agent/joyzoning/` | Config, journal, convergence, JSDP helpers. |
| `kernel/` | Quarantined C++ kernel + Python harnesses (macOS). |
| `broccolidb/` | TypeScript graph, policy, database, RPC worker. |

## Hook flow

`hooks.py` composes one DietCode-owned callback per Hermes hook type to avoid
duplicate registration.

```text
_ON_SESSION_START  = (kanban_start, jz_start, jsdp_start)
_ON_SESSION_END    = (jz_end,)
_PRE_TOOL_CALL     = (kernel_pre, jz_pre)
_POST_TOOL_CALL    = (jz_post, kernel_post, kanban_post)
_TRANSFORM_TOOL_RESULT = (on_kernel_journal_transform,
                          on_kernel_raw_write_transform,
                          on_transform_tool_result)
```

Boot sequence:

1. Hermes discovers and enables the plugin.
2. `_bootstrap.py` maps absolute imports under `plugins.dietcode.*`.
3. `hooks.register(ctx)` registers composed callbacks.
4. `tools_loader.load_dietcode_tools()` imports tool modules.
5. `health.build_status_report()` checks full integration including kernel bridge.

### Kernel hook behavior

| Hook | Kernel module | Behavior |
| --- | --- | --- |
| `pre_tool_call` | `kernel_raw_write_router` | Warn or block raw `write_file`/`patch` when gate open |
| `post_tool_call` | `kernel_receipt_journal`, `kernel_verify_journal` | Journal successful kernel tool results |
| `transform_tool_result` | Same + raw-write warning merge | Attach `_journal_warning`, `_kernel_raw_write_warning` |

Journal failures are **non-fatal** — kernel tool success is unchanged; warnings
are merged into the JSON result.

## Patch gate

The patch gate opens only when **all** conditions hold:

- `dietcode.kernel.bridge.enabled: true`
- `dietcode.kernel.bridge.mutations_enabled: true`
- Workspace resolves to a safe, writable user project (not plugin or kernel root)
- macOS platform supported
- Kernel binary present
- Socket reachable and token readable

When closed, `dietcode_kernel(action='patch')` returns `bridge_patch_disabled`
and raw-write router falls back to allow (no warn/block).

Probe: `/dietcode kernel status` or `build_patch_gate_state()`.

## Workspace boundary

`lib/kernel_workspace.py` resolves the Hermes user workspace separately from
`plugin_root` and `kernel_root`:

| `workspace_root_source` | Resolves from |
| --- | --- |
| `hermes_project` (default) | `HERMES_KANBAN_WORKSPACE` → kanban config → `cwd` |
| `env:DIETCODE_WORKSPACE_ROOT` | `DIETCODE_WORKSPACE_ROOT` |
| `explicit` | `dietcode.kernel.workspace_root` config path |

Mutation is blocked when workspace equals plugin root, kernel root, is missing,
or is not writable.

## Tool loading

Expected tool domains:

- **broccolidb** — graph, audit, refactor, structural analysis, queue.
- **joyzoning / convergence** — mutation lifecycle, convergence, JSDP, runtime events.
- **dietcode_kernel** — kernel bridge status, search, patch, verify.
- **kanban bridge** — task sync and completion gates backed by BroccoliDB.

`tools_loader.py` reports missing modules via `/dietcode tools`.

## BroccoliDB boundary

Python tools call into `broccolidb/` through CLI, one-shot TypeScript, or the
persistent JSON-RPC worker at `broccolidb/infrastructure/hermes/hermes_rpc.ts`.
BroccoliDB does not participate in kernel physical mutation — it provides
repository context and queue coordination in parallel.

## Kernel RPC boundary

Python bridge code wraps `kernel/scripts/dietcode_agent_client.py` and
`kernel/scripts/dietcode_coherence.py`. No in-tree TypeScript agent-bridge.

Global paths shared with standalone kernel use:

- `~/.dietcode/control.sock`
- `~/.dietcode/session.token`
- `~/.dietcode/session/` (approval state)

## State and scope

| Variable | Used by |
| --- | --- |
| `HERMES_KANBAN_TASK` | JoyZoning, coherence, kanban gates |
| `HERMES_KANBAN_WORKSPACE` | BroccoliDB, kernel workspace, JSDP |
| `HERMES_KANBAN_RUN_ID` | Session/run correlation |
| `HERMES_SESSION_ID` | Scope fallback |
| `JOYZONING_SCOPE_ID` | Explicit JoyZoning scope |

JoyZoning resolves explicit scope first, then task/session identifiers, then
`default`.

## Failure posture

| Failure | Plugin behavior |
| --- | --- |
| Kernel unavailable (Linux) | Bridge hooks no-op; no errors spam |
| Socket/token missing | Patch/verify blocked at client; gate closed |
| Journal unavailable | Tool succeeds; `_journal_warning` on result |
| Block policy + closed gate | Raw writes not blocked (fallback) |

Operator reference: [kernel-bridge-operations.md](kernel-bridge-operations.md)

## Related documents

- [dietcode-plugin.md](dietcode-plugin.md) — install and configuration
- [tools-reference.md](tools-reference.md) — tool and slash command catalog
- [../kernel/MIGRATION.md](../kernel/MIGRATION.md) — integration phase history
- [../kernel/docs/kernel-rpc.md](../kernel/docs/kernel-rpc.md) — RPC method reference
