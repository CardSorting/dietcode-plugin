# Architecture

DietCode is a **standalone Hermes plugin** (`kind: standalone`) that consolidates what was
previously four split plugins plus a Habitat control plane. One bundle, one registration surface.

---

## Design principles

1. **Hermes-native** — no external control plane; journal, convergence, and governance run in-process.
2. **Fail-closed hooks** — governance and kanban gates block unsafe completions; hook failures log warnings.
3. **Import boundary** — core Hermes must not import `plugins.dietcode.*` directly (fork uses facades).
4. **Drag-and-drop first** — `auto_enable`, namespace bootstrap, bundled `broccolidb/`.

---

## Plugin layout

```
dietcode/
├── plugin.yaml              Manifest (auto_enable, hooks list)
├── __init__.py              register() entry point
├── _bootstrap.py            hermes_plugins.dietcode → plugins.dietcode
├── install.py               Config merge + npm wizard
├── hooks.py                 Consolidated hook chains
├── tools_loader.py          Deferred tool imports + EXPECTED_DIETCODE_TOOLS
├── paths.py                 BroccoliDB root resolution
├── health.py                /dietcode doctor
├── contracts.py             Runtime contract validation
├── audit.py                 Static layout + forbidden-import scans
├── guard.py                 Registration / governance guards
├── prompts.py               System prompt guidance builder
├── slash_commands.py        /joyzoning, /broccolidb, /broccoliq
├── public.py                Stable exports for tests
├── broccolidb/              Bundled TypeScript runtime (standalone package)
└── lib/
    ├── runtime/             Hook implementations
    │   ├── governance_hooks.py
    │   ├── joyzoning_hooks.py
    │   ├── kanban_hooks.py
    │   └── jsdp_hooks.py
    ├── agent/
    │   ├── joyzoning/       Journal, convergence, scope registry, doctor
    │   └── governance_exemptions.py
    └── tools/               Tool modules (not tools/ auto-discovery)
        ├── broccolidb.py
        ├── broccolidb_tools/
        ├── joyzoning_tools.py
        ├── convergence_tools.py
        ├── jsdp_harness_tools.py
        └── kanban_broccolidb_tools.py
```

---

## Registration flow

```
Hermes startup
  → discover_plugins()
  → read plugin.yaml (auto_enable?)
  → _load_plugin() → dietcode.register(ctx)
       → _bootstrap.ensure_namespace()
       → load_dietcode_tools()     # import 5 tool modules
       → register_dietcode_toolset()
       → register_all_hooks(ctx)
       → register slash commands
       → apply_seamless_defaults()
       → ensure_broccolidb_runtime(auto_npm=False)
```

---

## Hook chains

Registered hooks (from `plugin.yaml`):

| Hook | Handlers (order) | Role |
|------|------------------|------|
| `on_session_start` | kanban → joyzoning → jsdp | Hive sync, scope registry, role_started |
| `on_session_end` | joyzoning | Session.end journal event |
| `pre_tool_call` | joyzoning | Block early `kanban_complete` before convergence |
| `post_tool_call` | joyzoning → kanban | Journal tool events, debounced BroccoliQ sync |
| `transform_tool_result` | governance | Layer/import validation on writes |

Hook wrappers use `dietcode_<hook_name>` as callback names for contract auditing.
Individual handler failures are logged; they do not crash the agent loop.

Governance runs when `joyzoning.governance.enabled` is true **even if** `joyzoning.enabled` is false.

---

## Tool loading

DietCode tools are **not** in Hermes `tools/` auto-discovery. `tools_loader.py` imports:

1. `plugins.dietcode.lib.tools.broccolidb`
2. `plugins.dietcode.lib.tools.joyzoning_tools`
3. `plugins.dietcode.lib.tools.convergence_tools`
4. `plugins.dietcode.lib.tools.jsdp_harness_tools`
5. `plugins.dietcode.lib.tools.kanban_broccolidb_tools`

`EXPECTED_DIETCODE_TOOLS` defines the minimum registry contract checked by `/dietcode doctor`.

On diet-hermes forks, `tools/registry.py` lists these stems in `DEFERRED_TOOL_MODULE_STEMS` so
core discovery does not double-import them.

---

## Namespace bootstrap (drag-and-drop)

```
Hermes loads:  hermes_plugins.dietcode  (__init__.py on disk)
DietCode code: from plugins.dietcode.lib....

_bootstrap.ensure_namespace():
  1. Create sys.modules["plugins"] if missing
  2. Repackage loaded module as plugins.dietcode
  3. sys.modules["plugins.dietcode"] = loaded module
```

Idempotent — safe on reload if path already matches.

---

## Fork facades (diet-hermes only)

When running the **diet-hermes fork**, core code reaches DietCode only through facades:

| Facade | Purpose |
|--------|---------|
| `hermes_cli/dietcode_bridge.py` | Kanban gates, worker env, doctor, RPC helpers |
| `hermes_cli/dietcode_broccolidb.py` | Web dashboard health |
| `agent/governance_bridge.py` | Governance transform delegation |
| `agent/joy_zoning_bridge.py` | Layer tags in `file_tools` |
| `agent/prompt_bridge.py` | Plugin prompt guidance |

Vanilla Hermes + drag-and-drop plugin: tools, hooks, and slash commands work without these facades.
Kanban completion gates and dashboard integration require the fork bridges.

`audit.py` scans fork trees for forbidden direct `plugins.dietcode` imports outside facades.

---

## Removed legacy components

Do not reintroduce:

| Removed | Replacement |
|---------|-------------|
| `joyzoning_governance` plugin | `dietcode` hooks |
| `joyzoning_runtime` plugin | `dietcode/lib/runtime/` |
| `kanban_broccolidb` plugin | `kanban_broccolidb_tools` |
| `jsdp_mutation` plugin | `convergence_tools` + `jsdp_hooks` |
| Habitat control plane (`:9470`, `habitat_bridge`) | Hermes-native journal + convergence |

---

## Runtime contract

`contracts.validate_runtime_contract()` checks:

- Required hooks registered with `dietcode_*` callbacks
- Guidance builder on PluginManager
- Expected tools in registry
- Governance state vs config
- Plugin not in `plugins.disabled`

`/dietcode doctor` runs strict contract mode; `/dietcode status` is cached/non-strict.
