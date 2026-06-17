# DietCode Documentation

Operator and developer documentation for the DietCode Hermes plugin
(**v1.11.0 — Native mutation + BroccoliDB v30**).

DietCode bundles BroccoliDB, JoyZoning, JSDP, and a **native mutation runtime**
(`dietcode_kernel`) aligned with LUMI / codemarie-new. JoyZoning owns the
lifecycle journal and convergence gates; governed patches use coherence tokens
and `.dietcode/mutation-state.json`.

```text
intent → dietcode_kernel patch → receipt → journal → verify → convergence
```

## Start here

| You are… | Read first | Then |
| --- | --- | --- |
| **Installing the plugin** | [dietcode-plugin.md](dietcode-plugin.md) | Run `/dietcode doctor` |
| **Governed mutation** | [architecture.md](architecture.md) | `/dietcode mutation status` |
| **Understanding the runtime** | [architecture.md](architecture.md) | [tools-reference.md](tools-reference.md) |
| **Governed roadmap steering** | [roadmap.md](roadmap.md) | `/roadmap cockpit` |
| **Working with BroccoliDB** | [broccolidb.md](broccolidb.md) | `/broccolidb status` |
| **Upgrading to v1.11.0** | [CHANGELOG.md](../CHANGELOG.md) | Native mutation — no `kernel/` subtree |
| **Upgrading to v1.10.0** | [CHANGELOG.md](../CHANGELOG.md) | `make distill` then `cd broccolidb && npm ci && npm run build` |
| **Agent operator loops** | [agent-ergonomics.md](agent-ergonomics.md) | `/roadmap cockpit` |

## Plugin documents

| Document | Purpose |
| --- | --- |
| [dietcode-plugin.md](dietcode-plugin.md) | Install, verification, configuration, governed workflow. |
| [architecture.md](architecture.md) | Runtime layout, hook wiring, authority split, subprocess boundaries. |
| [tools-reference.md](tools-reference.md) | Slash commands and registered Hermes tools (`dietcode_kernel`, JoyZoning, BroccoliDB). |
| [broccolidb.md](broccolidb.md) | Bundled BroccoliDB package, RPC worker, database location, smoke tests. |
| [broccolidb-native-execution-throughput.md](broccolidb-native-execution-throughput.md) | Native RPC execution model and throughput notes. |
| [agent-ergonomics.md](agent-ergonomics.md) | Native mutation loop, roadmap operator loop, progress storage. |
| [roadmap.md](roadmap.md) | Per-project ROADMAP steering: fingerprint, 12-section schema, bootstrap autofill, gates. |
| [releases/](releases/) | Historical release notes (v1.9.x kernel bridge era). |

## BroccoliDB package documents

| Document | Purpose |
| --- | --- |
| [../broccolidb/README.md](../broccolidb/README.md) | BroccoliDB package overview. |
| [../broccolidb/core/policy/SPIDER.md](../broccolidb/core/policy/SPIDER.md) | Spider Engine policy notes. |

## Quick start

```bash
cd ~/.hermes/plugins/dietcode/broccolidb
npm ci
python ../install.py --skip-npm
```

Inside Hermes:

```text
/dietcode doctor
/dietcode mutation status
/roadmap cockpit
joyzoning(action='context')
```

Distill substrate updates from codemarie-new:

```bash
make distill
cd broccolidb && npm ci && npm run build
```

## Changelog

See [../CHANGELOG.md](../CHANGELOG.md).
