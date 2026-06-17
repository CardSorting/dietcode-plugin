# BroccoliDB Runtime

DietCode bundles BroccoliDB under `broccolidb/`. It is a TypeScript package that
provides repository indexing, knowledge graph storage, structural audit,
and Hermes-native RPC workers.

BroccoliDB is **independent of the native mutation runtime**. Repository graph
operations work on all platforms. Governed file patches use `dietcode_kernel`
(`lib/agent/native_mutation.py`) — see [architecture.md](architecture.md).

## Setup

Install dependencies inside the nested package:

```bash
cd broccolidb
npm ci
```

Build and test:

```bash
npm run build
npm test
```

## Root Discovery

DietCode resolves the BroccoliDB root in this order:

1. `HERMES_BROCCOLIDB_ROOT`.
2. Hermes bundled/user plugin directories for `dietcode/broccolidb`.
3. `kanban.broccolidb.root` in Hermes config.
4. Parents of `HERMES_KANBAN_WORKSPACE`, then parents of the current directory.
5. A relative `broccolidb/` directory.

Set `HERMES_BROCCOLIDB_DISABLE_PLUGIN_FALLBACK=1` to skip plugin-directory
fallbacks.

## Database Path

Set `HERMES_BROCCOLIDB_DB` to force a specific SQLite database path. If it is
unset, the bundled runner resolves the workspace database through BroccoliDB's
normal configuration.

## RPC Worker

The persistent Hermes worker lives at:

```text
broccolidb/infrastructure/hermes/hermes_rpc.ts
```

It emits JSON-RPC lines on stdout and logs on stderr. Python tools use it
through `lib/tools/broccolidb_tools/db_gateway.py`.

Controls:

| Variable | Behavior |
| --- | --- |
| `HERMES_BROCCOLIDB_RPC=0` | Disable persistent RPC and use one-shot fallback where available. |
| `HERMES_BROCCOLIDB_RPC_IDLE_SEC` | Override idle shutdown timing for the persistent worker. |
| `HERMES_BROCCOLIDB_PRELOAD_AGENT=1` | Preload AgentContext during worker startup. |

## Smoke Test

```bash
cd broccolidb
export HERMES_BROCCOLIDB_DB=/path/to/broccolidb.db
echo '{"id":1,"method":"rpc_health","params":{}}' | node_modules/.bin/tsx infrastructure/hermes/hermes_rpc.ts
```

Expected behavior:

- First stdout line: a ready JSON object.
- Second stdout line: the response for request id `1`.
- Logs and schema repair messages appear on stderr.

## Native Modules

BroccoliDB depends on `better-sqlite3`. Rebuild it after changing Node versions:

```bash
cd broccolidb
npm rebuild better-sqlite3
```
