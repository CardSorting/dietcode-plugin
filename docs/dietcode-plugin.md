# DietCode Plugin

DietCode is a Hermes plugin that installs a governed agent execution substrate:
BroccoliDB for repository and knowledge graph context, BroccoliQ for sharded
queue coordination, JoyZoning for mutation lifecycle governance, and JSDP for
rolling-horizon planning.

## Manifest

The plugin is declared in `plugin.yaml`:

```yaml
name: dietcode
version: 1.8.0
kind: standalone
auto_enable: true
```

It provides these Hermes hooks:

- `on_session_start`
- `on_session_end`
- `pre_tool_call`
- `post_tool_call`
- `transform_tool_result`

## Installation

Install the plugin at the canonical Hermes path:

```bash
mkdir -p ~/.hermes/plugins
cp -R dietcode-plugin ~/.hermes/plugins/dietcode
cd ~/.hermes/plugins/dietcode/broccolidb
npm ci
```

The install helper can enable the plugin and add the `dietcode` toolset to the
Hermes configuration:

```bash
python ~/.hermes/plugins/dietcode/install.py
```

## Runtime Verification

Use the DietCode doctor after installation:

```text
/dietcode doctor
```

The report covers:

- Plugin registration.
- Governance transform hook wiring.
- Tool module load status.
- Toolset completeness.
- Runtime layout and stale shim detection.
- BroccoliDB root, `node_modules`, and RPC availability.
- JoyZoning and JSDP configuration.

## Configuration

DietCode reads Hermes config when available and falls back to scoped
environment variables in worker contexts.

Common environment variables:

| Variable | Purpose |
| --- | --- |
| `HERMES_BROCCOLIDB_ROOT` | Explicit path to the bundled or workspace BroccoliDB root. |
| `HERMES_BROCCOLIDB_DB` | Explicit SQLite database path for the BroccoliDB worker. |
| `HERMES_BROCCOLIDB_RPC` | Set to `0`, `false`, or `no` to disable the persistent RPC worker. |
| `HERMES_KANBAN_WORKSPACE` | Workspace root used for BroccoliDB and JSDP discovery. |
| `HERMES_KANBAN_TASK` | Active task scope for JoyZoning and kanban gates. |
| `JOYZONING_SCOPE_ID` | Explicit JoyZoning scope override. |
| `JOYZONING_JSDP_ROLE` | JSDP role for bounded-role context. |
| `JOYZONING_JSDP_CHAIN_ID` | JSDP chain identifier. |
| `JOYZONING_WORKSPACE_ROOT` | Workspace root passed to the JSDP harness. |
| `JOYZONING_JZ_CLI` | Explicit path to the JoyZoning CLI. |

## Operational Model

The plugin is designed to be installed as one directory. Python files register
Hermes hooks and tools, while the nested `broccolidb/` package provides the
TypeScript runtime used by the CLI and RPC worker.

Recommended workflow:

1. Install the plugin and run `npm ci` in `broccolidb/`.
2. Run `/dietcode doctor`.
3. Run `/broccolidb status` or `broccolidb_status` before graph-heavy work.
4. Use `joyzoning(action="context")` before governed mutation work.
5. Record mutation lifecycle with `begin`, `patch`, `verify`, and
   `request_review`.
6. Complete kanban work only after review/convergence gates allow it.

## Development

Run TypeScript checks for the bundled package:

```bash
cd broccolidb
npm run build
npm test
```

For Python-facing changes, restart Hermes or reload the plugin, then run:

```text
/dietcode doctor
/dietcode tools
```
