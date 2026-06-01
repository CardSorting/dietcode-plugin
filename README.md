# Hermes DietCode plugin

Standalone **drag-and-drop** plugin for [Hermes Agent](https://github.com/NousResearch/hermes-agent):
BroccoliDB, BroccoliQ, JoyZoning governance, and JSDP.

**Version 1.8.0** · MIT · Python ≥ 3.10 · Node.js for BroccoliDB

---

## Quick start

```bash
./scripts/install-to-hermes.sh
# restart Hermes
/dietcode doctor
```

No manual YAML edits. No pip required.

---

## What you get

| Component | Description |
|-----------|-------------|
| **BroccoliDB** | Epistemic graph DB — knowledge, structural analysis, task context |
| **BroccoliQ** | Sharded queue / hive for multi-agent coordination |
| **JoyZoning** | Layered architecture enforcement on agent writes |
| **JSDP** | Bounded mutation roles and handoff validation |
| **Kanban bridge** | Syncs board state into BroccoliQ for worker intelligence |

---

## Install options

| Method | Command |
|--------|---------|
| **One-step (recommended)** | `./scripts/install-to-hermes.sh` |
| **Manual copy** | `cp -R dietcode ~/.hermes/plugins/dietcode` then `python3 ~/.hermes/plugins/dietcode/install.py` |
| **pip (optional)** | `pip install -e .` |

BroccoliDB Node deps (once):

```bash
cd ~/.hermes/plugins/dietcode/broccolidb && npm ci
```

---

## Verify

```bash
hermes plugins list          # dietcode enabled
/dietcode doctor             # full health report
/joyzoning status            # layering audit
```

---

## Documentation

Full reference in **[docs/](./docs/README.md)**:

| Doc | Topics |
|-----|--------|
| [docs/installation.md](./docs/installation.md) | Profiles, upgrade, uninstall |
| [docs/configuration.md](./docs/configuration.md) | config.yaml, env vars |
| [docs/architecture.md](./docs/architecture.md) | Hooks, bootstrap, layout |
| [docs/tools-reference.md](./docs/tools-reference.md) | All agent tools |
| [docs/operator-guide.md](./docs/operator-guide.md) | Slash commands, workflows |
| [docs/broccolidb.md](./docs/broccolidb.md) | RPC worker, path resolution |
| [docs/joyzoning-and-governance.md](./docs/joyzoning-and-governance.md) | Layers, convergence, JSDP |
| [docs/troubleshooting.md](./docs/troubleshooting.md) | Common fixes |
| [docs/development.md](./docs/development.md) | Sync from fork, testing |

---

## Package layout

```
dietcode-plugin/
├── dietcode/              ← copy to ~/.hermes/plugins/dietcode/
├── docs/                  ← comprehensive documentation
├── scripts/
│   ├── install-to-hermes.sh
│   └── sync-from-fork.sh
├── shim/plugins/          pip namespace shim
├── pyproject.toml
└── README.md
```

---

## Seamless integration

- `plugin.yaml` → **`auto_enable: true`** — Hermes enables on first discovery
- **`install.py`** — merges `plugins.enabled`, `toolsets`, governance defaults
- **`_bootstrap.py`** — drag-and-drop namespace alias (`plugins.dietcode`)
- **Bundled `broccolidb/`** — no separate clone required

---

## Requirements

- Hermes Agent with plugin support
- Node.js + npm (BroccoliDB RPC)
- Optional: API keys in `~/.hermes/.env` for cloud embeddings

---

## Maintainers

```bash
./scripts/sync-from-fork.sh /path/to/diet-hermes-main-master
./scripts/install-to-hermes.sh
```

See [docs/development.md](./docs/development.md).
