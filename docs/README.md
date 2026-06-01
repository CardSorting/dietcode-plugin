# DietCode Documentation

This directory is the operator and developer documentation for the DietCode
Hermes plugin.

## Documents

| Document | Purpose |
| --- | --- |
| [dietcode-plugin.md](dietcode-plugin.md) | Plugin overview, install flow, verification, and configuration notes. |
| [architecture.md](architecture.md) | Runtime layout, hook wiring, tool loading, and subprocess boundaries. |
| [broccolidb.md](broccolidb.md) | Bundled BroccoliDB package, RPC worker, database location, and smoke tests. |
| [broccolidb-native-execution-throughput.md](broccolidb-native-execution-throughput.md) | Native RPC execution model and throughput-oriented operating notes. |
| [tools-reference.md](tools-reference.md) | Slash commands and registered Hermes tools exposed by the plugin. |
| [../broccolidb/README.md](../broccolidb/README.md) | BroccoliDB package-level README. |
| [../broccolidb/core/policy/SPIDER.md](../broccolidb/core/policy/SPIDER.md) | Spider Engine policy notes. |

## Quick Start

```bash
cd ~/.hermes/plugins/dietcode/broccolidb
npm ci
```

Then run this inside Hermes:

```text
/dietcode doctor
```

The doctor output is the source of truth for whether hooks, tools, runtime
contracts, BroccoliDB, JoyZoning, and JSDP are wired correctly.
