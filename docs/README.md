# DietCode plugin documentation

Comprehensive reference for the **Hermes DietCode plugin** — a standalone bundle that adds
BroccoliDB, BroccoliQ, JoyZoning governance, and JSDP to [Hermes Agent](https://github.com/NousResearch/hermes-agent).

---

## Quick start

```bash
./scripts/install-to-hermes.sh
# restart Hermes
hermes plugins list
/dietcode doctor
```

No manual YAML edits are required. See [installation.md](./installation.md) for profiles, pip, and offline installs.

---

## Documentation index

| Document | What you'll find |
|----------|------------------|
| [installation.md](./installation.md) | Drag-and-drop, install script, pip, profiles, npm ci, verification |
| [configuration.md](./configuration.md) | `config.yaml` keys, env vars, seamless defaults, toolsets |
| [architecture.md](./architecture.md) | Plugin layout, hooks, namespace bootstrap, fork facades |
| [tools-reference.md](./tools-reference.md) | Every DietCode tool grouped by subsystem |
| [operator-guide.md](./operator-guide.md) | Slash commands, kanban workflow, mutation lifecycle |
| [broccolidb.md](./broccolidb.md) | RPC worker, path resolution, database, performance |
| [joyzoning-and-governance.md](./joyzoning-and-governance.md) | Layers, governance hook, convergence, JSDP |
| [troubleshooting.md](./troubleshooting.md) | Common failures and fixes |
| [development.md](./development.md) | Sync from fork, packaging, testing, release |

---

## What DietCode provides

| Subsystem | Purpose |
|-----------|---------|
| **BroccoliDB** | Epistemic graph database — knowledge, tasks, structural analysis |
| **BroccoliQ** | Sharded SQLite queue / hive layer for multi-agent coordination |
| **JoyZoning** | Layered architecture enforcement (domain → core → infrastructure → plumbing → UI) |
| **JSDP** | Bounded mutation roles and handoff validation for governed agent work |
| **Kanban bridge** | Syncs Hermes kanban board state into BroccoliQ for cross-worker intelligence |

---

## Requirements

| Requirement | Notes |
|-------------|-------|
| Hermes Agent | Plugin system (`hermes_cli.plugins`) |
| Python | ≥ 3.10 |
| Node.js + npm | Required once for BroccoliDB RPC (`npm ci` in `broccolidb/`) |
| Optional API keys | Embedding / cloud features in `~/.hermes/.env` |

---

## Package layout

```
dietcode-plugin/
├── dietcode/                 ← install target: ~/.hermes/plugins/dietcode/
│   ├── plugin.yaml           auto_enable: true
│   ├── install.py            config merge + npm wizard
│   ├── _bootstrap.py         drag-and-drop namespace alias
│   ├── broccolidb/           bundled TypeScript runtime
│   └── lib/                  tools, hooks, joyzoning runtime
├── docs/                     ← this documentation
├── scripts/
│   ├── install-to-hermes.sh
│   └── sync-from-fork.sh
├── shim/plugins/             pip namespace shim
├── pyproject.toml            optional: pip install -e .
└── README.md
```

---

## Version

Plugin version is declared in `dietcode/plugin.yaml` and `pyproject.toml` (currently **1.8.0**).
