# Configuration

DietCode reads Hermes `config.yaml` and process environment. Most users need **no manual config**
after install — `install.py` and `auto_enable` handle the basics.

Config file location: `~/.hermes/config.yaml` (or `$HERMES_HOME/config.yaml` for profiles).

---

## Seamless defaults (applied by install.py)

When `install.py` runs or the plugin registers, these merges happen **only if missing**:

| Key | Value merged |
|-----|--------------|
| `plugins.enabled` | appends `dietcode` |
| `plugins.disabled` | removes `dietcode` if present |
| `toolsets` | appends `dietcode` |
| `joyzoning.governance.enabled` | `true` (only when key absent) |

Existing explicit values are **not overwritten**.

---

## plugins section

```yaml
plugins:
  enabled:
    - dietcode
  disabled: []   # do not list dietcode here
```

| Mechanism | Behavior |
|-----------|----------|
| `plugin.yaml` → `auto_enable: true` | Hermes auto-enables on discovery (user/entrypoint/project plugins) |
| `plugins.enabled` | Explicit opt-in list; empty list + auto_enable still loads DietCode |
| `plugins.disabled` | Hard block — plugin skipped even with auto_enable |

CLI:

```bash
hermes plugins list
hermes plugins enable dietcode
hermes plugins disable dietcode
```

---

## toolsets

DietCode tools live in the `dietcode` toolset (plus toolset tags `broccolidb`, `joyzoning` on individual tools).

```yaml
toolsets:
  - hermes-cli
  - dietcode
```

Platform-specific tool gating (CLI vs gateway vs kanban worker) follows Hermes `tools.<platform>.enabled/disabled`.
Kanban dispatcher workers typically receive the `dietcode` toolset via worker env injection when using the diet-hermes fork.

---

## joyzoning section

Full reference for governed agent work:

```yaml
joyzoning:
  # Full lifecycle: journal, convergence gates, kanban integration.
  # Off by default — governance can run independently.
  enabled: false

  # Per-tool SQLite journal (adds latency). Off by default.
  execution_journal: false
  journal_path: ""

  # Scope binding for multi-agent / kanban workers
  scope_id: ""

  convergence:
    review_before_complete: true

  governance:
    # Transform hook on write_file/patch — ON by default after install.py
    enabled: true
    # When false: [LAYER: TYPE] headers optional; light validation only
    layer_tags_required: false
    # auto | full | light
    validation_mode: auto
    extra_exempt_paths: []

  jsdp:
    enabled: false
    role: ""
    chain_id: ""
    harness:
      enabled: false
      workspace_root: ""
      jz_cli: ""
```

### Recommended profiles

**Throughput default** (governance without full lifecycle):

```yaml
joyzoning:
  enabled: false
  governance:
    enabled: true
    layer_tags_required: false
```

**Full governed kanban workers**:

```yaml
joyzoning:
  enabled: true
  execution_journal: false
  governance:
    enabled: true
  convergence:
    review_before_complete: true
```

**Strict layer tagging**:

```yaml
joyzoning:
  governance:
    enabled: true
    layer_tags_required: true
    validation_mode: full
```

---

## kanban section (BroccoliDB root override)

```yaml
kanban:
  broccolidb:
    root: /absolute/or/relative/path/to/broccolidb
```

Used when BroccoliDB lives outside the plugin bundle (monorepo checkout). See [broccolidb.md](./broccolidb.md) for resolution order.

---

## Environment variables

### BroccoliDB

| Variable | Purpose |
|----------|---------|
| `HERMES_BROCCOLIDB_ROOT` | Force BroccoliDB root (kanban dispatcher sets this) |
| `HERMES_BROCCOLIDB_DB` | SQLite database path for RPC worker |
| `HERMES_BROCCOLIDB_DISABLE_PLUGIN_FALLBACK` | `1` to skip plugin-dir resolution |

### JoyZoning / JSDP (kanban workers)

| Variable | Purpose |
|----------|---------|
| `JOYZONING_SCOPE_ID` | Active mutation scope |
| `JOYZONING_JSDP_ROLE` | JSDP role name |
| `JOYZONING_JSDP_CHAIN_ID` | JSDP chain identifier |
| `JOYZONING_WORKSPACE_ROOT` | JSDP harness workspace |
| `JOYZONING_JZ_CLI` | Path to joy-zoning CLI |
| `JOYZONING_JSDP_HARNESS` | `1`/`true` to enable harness |

### Kanban

| Variable | Purpose |
|----------|---------|
| `HERMES_KANBAN_TASK` | Current task id (worker) |
| `HERMES_KANBAN_BOARD` | Board isolation boundary |
| `HERMES_KANBAN_WORKSPACE` | Workspace seed for broccolidb path walk |

### Hermes profiles

| Variable | Purpose |
|----------|---------|
| `HERMES_HOME` | Profile root (`~/.hermes` or `~/.hermes/profiles/<name>`) |

Secrets (API keys) belong in `~/.hermes/.env`, not `config.yaml`.

---

## Prompt guidance

When DietCode tools are active, the plugin registers a guidance builder on `PluginManager`
(`_dietcode_guidance_builder`). Hermes injects JoyZoning + kanban/BroccoliQ instructions into
the system prompt via `agent/prompt_bridge.py` on diet-hermes forks, or when the fork wires
prompt injection for loaded plugins.

Guidance covers mutation lifecycle, kanban linkage, and JSDP role startup — see `dietcode/prompts.py`.
