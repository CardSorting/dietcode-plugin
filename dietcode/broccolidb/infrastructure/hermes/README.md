# Hermes native RPC (`infrastructure/hermes/`)

Persistent BroccoliDB/BroccoliQ worker used by DietCode / Hermes Python tools.

## Documentation

| Doc | Contents |
|-----|----------|
| [docs/broccolidb.md](../../../docs/broccolidb.md) | RPC worker, path resolution, npm setup |
| [docs/architecture.md](../../../docs/architecture.md) | Plugin layout, hooks |
| [docs/tools-reference.md](../../../docs/tools-reference.md) | Python tool surface |
| [docs/README.md](../../../docs/README.md) | Full doc index |

## File map

| File | Role |
|------|------|
| `hermes_rpc.ts` | Persistent stdin/stdout worker (`ready` first, lazy DB warm) |
| `hermes_oneshot.ts` | Cold fallback: one JSON line on stdout, then `process.exit(0)` |
| `rpc_handlers.ts` | Canonical handlers (`dispatchRpc`, `RPC_VERSION = 4`) |
| `agent_session.ts` | Warm `AgentContext` singleton |
| `agent_invoke.ts` | Graph / kanban cognitive ops |
| `queue_metrics.ts` | SQL `GROUP BY` queue status (no full-table scan) |

## Protocol rules

1. **stdout** — JSON-RPC lines only (`{"ready":…}`, `{"id", "ok", "result"}`).
2. **stderr** — logs, schema self-heal, DbPool messages.
3. **Warmup** — first request after `ready` may pay `getDb()` / schema cost (~1 s); steady state is sub-ms to low ms per call.

## Local smoke test

```bash
cd broccolidb
export HERMES_BROCCOLIDB_DB=/path/to/broccolidb.db
echo '{"id":1,"method":"rpc_health","params":{}}' | node_modules/.bin/tsx infrastructure/hermes/hermes_rpc.ts
```

Expect: one `{"ready":true,…}` line, then one `{"id":1,"ok":true,…}` line. Logs appear on stderr.

## Python usage

```python
from plugins.dietcode.lib.tools.broccolidb_tools.exec import run_db_rpc, run_agent_rpc, warm_db_rpc

warm_db_rpc(block=True)
raw = run_db_rpc("queue_status")
```

## Node native modules

After upgrading Node, rebuild `better-sqlite3`:

```bash
cd broccolidb && npm rebuild better-sqlite3
```
