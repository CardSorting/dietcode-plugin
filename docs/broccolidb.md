# BroccoliDB

BroccoliDB is the TypeScript epistemic database bundled inside `dietcode/broccolidb/`.
Python tools communicate with it through a **persistent RPC worker** (warm subprocess) or
cold oneshot fallback.

---

## Directory layout

```
broccolidb/
├── package.json
├── core/                    Agent context, policy engine, MCP
├── infrastructure/
│   ├── hermes/              Hermes RPC worker (primary integration)
│   │   ├── hermes_rpc.ts    Persistent stdin/stdout worker
│   │   ├── hermes_oneshot.ts Cold fallback
│   │   ├── rpc_handlers.ts  RPC_VERSION = 4
│   │   ├── agent_session.ts Warm AgentContext singleton
│   │   └── ...
│   ├── db/                  SQLite pool, sharding
│   └── queue/               BroccoliQ (SqliteQueue)
├── utils/joy-zoning.ts      Layer taxonomy helpers
└── tests/
```

---

## First-time setup

```bash
cd ~/.hermes/plugins/dietcode/broccolidb
npm ci
```

Verify RPC worker:

```bash
export HERMES_BROCCOLIDB_DB=/tmp/broccolidb-smoke.db
echo '{"id":1,"method":"rpc_health","params":{}}' | node_modules/.bin/tsx infrastructure/hermes/hermes_rpc.ts
```

Expected stdout (JSON lines only):

1. `{"ready":true,...}`
2. `{"id":1,"ok":true,...}`

Logs appear on **stderr** — stdout is reserved for JSON-RPC.

---

## Path resolution

`paths.resolve_broccolidb_root()` search order:

1. `HERMES_BROCCOLIDB_ROOT` env
2. `kanban.broccolidb.root` in config.yaml
3. `dietcode/broccolidb/` beside plugin module (standalone package)
4. Walk parents from `HERMES_KANBAN_WORKSPACE` then `cwd` for `broccolidb/`
5. Relative `./broccolidb/` from cwd
6. `~/.hermes/plugins/dietcode/broccolidb/` (user plugin)
7. Bundled plugins dir (fork checkout)

Disable plugin-dir fallback:

```bash
export HERMES_BROCCOLIDB_DISABLE_PLUGIN_FALLBACK=1
```

---

## Python RPC usage

Internal API (tools use these):

```python
from plugins.dietcode.lib.tools.broccolidb_tools.exec import (
    run_db_rpc,
    run_agent_rpc,
    warm_db_rpc,
)

warm_db_rpc(block=True)
result = run_db_rpc("queue_status")
```

Gateway: `db_gateway.rpc_available()` — used by `/dietcode doctor`.

Runner: `runner.check_requirements()` — Node, tsx, package.json present.

---

## RPC protocol rules

1. **stdout** — JSON-RPC lines only
2. **stderr** — logs, schema self-heal, DbPool messages
3. **Warmup** — first request after `ready` may pay DB init cost (~1s); steady state is low ms
4. **Version** — `RPC_VERSION = 4` in `rpc_handlers.ts`; doctor checks alignment

---

## Database location

Set explicitly for production:

```bash
export HERMES_BROCCOLIDB_DB=/path/to/broccolidb.db
```

Kanban workers on diet-hermes forks may inherit workspace-scoped paths via dispatcher env.

---

## BroccoliQ (queue / hive)

BroccoliQ lives inside BroccoliDB infrastructure:

- **Queue** — sharded SQLite work queue
- **Hive** — cross-agent shared intelligence layer
- **Metrics** — `queue_metrics.ts` SQL aggregations (no full-table scan)

Tools: `broccolidb_queue_status`, `broccolidb_shard_status`, `broccolidb_hive_integrity`.

Kanban bridge tools sync board events into the hive — see [operator-guide.md](./operator-guide.md).

---

## Performance notes

| Mode | Typical latency |
|------|-----------------|
| Cold oneshot | ~1s per invocation |
| Warm RPC | ~1–2 ms steady state |

Warm the worker at session start when running high-throughput tool loops:

```python
warm_db_rpc(block=False)  # background thread
```

Subprocess env is allowlisted in `runner.py` for security — standalone scripts use `db_preamble=False`.

---

## Node native modules

After Node version changes:

```bash
cd ~/.hermes/plugins/dietcode/broccolidb
npm rebuild better-sqlite3
```

---

## Monorepo vs standalone package

| Install | broccolidb location |
|---------|---------------------|
| **This package** | Real directory inside `dietcode/broccolidb/` |
| **diet-hermes fork** | Often symlink `plugins/dietcode/broccolidb → ../../broccolidb` |

Both layouts resolve via `paths.py`. Standalone ships a full copy (~3.5 MB without `node_modules`).

---

## Smoke test from Hermes

```
/dietcode broccolidb
/broccolidb status
/broccoliq queue
```

If `rpc_available: false`, see [troubleshooting.md](./troubleshooting.md).
