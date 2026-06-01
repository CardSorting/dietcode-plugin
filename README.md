# DietCode Hermes Plugin

DietCode is a standalone Hermes Agent plugin that bundles BroccoliDB,
BroccoliQ, JoyZoning governance, and the JSDP rolling-horizon workflow into one
installable plugin directory.

The plugin provides:

- BroccoliDB knowledge graph, repository indexing, structural audit, and
  refactor planning tools.
- BroccoliQ sharded SQLite queue status, shard health, and integrity tools.
- JoyZoning governed mutation lifecycle hooks and slash commands.
- JSDP autonomous planning helpers for bounded, reviewable delivery loops.
- Hermes plugin hooks for session start/end, tool call gating, and tool result
  transformation.

## Requirements

- Hermes Agent with plugin support.
- Python runtime used by Hermes.
- Node.js 18 or newer for the bundled `broccolidb/` package.
- npm for installing the BroccoliDB TypeScript dependencies.

## Install

Copy this folder to the Hermes plugin directory:

```bash
mkdir -p ~/.hermes/plugins
cp -R dietcode-plugin ~/.hermes/plugins/dietcode
cd ~/.hermes/plugins/dietcode/broccolidb
npm ci
```

If you are working from this checkout directly, the same runtime setup is:

```bash
cd broccolidb
npm ci
```

The plugin metadata sets `auto_enable: true`. The installer can also apply the
expected Hermes defaults:

```bash
python install.py
```

Use `python install.py --skip-npm` when dependencies were already installed.

## Verify

Inside Hermes, run:

```text
/dietcode doctor
```

Useful follow-up checks:

```text
/dietcode tools
/dietcode broccolidb
/broccolidb status
/broccoliq queue
/joyzoning status
```

From the shell, validate the bundled Node package:

```bash
cd broccolidb
npm run build
npm test
```

## Project Layout

```text
.
|-- plugin.yaml                 # Hermes plugin manifest
|-- hooks.py                    # Hook registration and composition
|-- install.py                  # Config defaults and npm bootstrap helper
|-- health.py                   # /dietcode status and doctor surface
|-- slash_commands.py           # /dietcode, /broccolidb, /broccoliq, /joyzoning
|-- lib/
|   |-- agent/                  # JoyZoning runtime, policy, and JSDP state
|   |-- runtime/                # Hermes hook implementations
|   `-- tools/                  # Hermes tool registrations
|-- broccolidb/                 # Bundled TypeScript BroccoliDB package
`-- docs/                       # Operator and developer documentation
```

## Documentation

- [Documentation index](docs/README.md)
- [Plugin overview](docs/dietcode-plugin.md)
- [Architecture](docs/architecture.md)
- [BroccoliDB runtime](docs/broccolidb.md)
- [Tools reference](docs/tools-reference.md)
- [BroccoliDB package README](broccolidb/README.md)

## License

MIT. See [LICENSE](LICENSE).
