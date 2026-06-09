# BroccoliDB Native Execution Throughput

DietCode routes high-frequency BroccoliDB and BroccoliQ operations through the
native TypeScript runtime instead of reimplementing database behavior in Python.
The preferred path is the persistent Hermes JSON-RPC worker.

## Execution Paths

| Path | Use Case | Notes |
| --- | --- | --- |
| Persistent RPC worker | Repeated queue, shard, graph, and health calls. | Avoids TypeScript process startup per call. |
| One-shot RPC script | Fallback when the worker is disabled or unavailable. | Starts a fresh TypeScript process for a single method call. |
| CLI command | Operator-facing BroccoliDB commands such as init, status, audit, and refactor. | Best for coarse commands and interactive setup. |
| AgentContext RPC | Knowledge graph operations that need hydrated agent services. | Uses the same native runtime boundary. |

## Worker Contract

The persistent worker is `broccolidb/infrastructure/hermes/hermes_rpc.ts`.

Contract:

- stdout contains only JSON protocol lines.
- stderr receives logs, schema repair output, and diagnostic messages.
- the worker emits a ready line before accepting requests.
- the first request may pay database or AgentContext warmup cost.
- steady-state calls reuse the same process and database runtime.

## Operational Controls

| Variable | Behavior |
| --- | --- |
| `HERMES_BROCCOLIDB_RPC=0` | Force fallback execution instead of the persistent worker. |
| `HERMES_BROCCOLIDB_RPC_IDLE_SEC` | Adjust idle shutdown for the worker. |
| `HERMES_BROCCOLIDB_PRELOAD_AGENT=1` | Warm AgentContext during startup. |
| `HERMES_BROCCOLIDB_DB` | Pin the SQLite database path used by the worker. |

## Throughput Guidance

Use the persistent worker for repeated status, queue, shard, and graph calls. It
keeps Node, TypeScript module loading, SQLite schema checks, and AgentContext
initialization out of the hot path after warmup.

Use one-shot execution for isolated fallback calls, debugging, or environments
where a long-lived worker is not allowed.

Use CLI commands for broad operator actions where startup overhead is small
relative to the work being performed.

## Smoke Test

```bash
cd broccolidb
echo '{"id":1,"method":"rpc_health","params":{}}' | node_modules/.bin/tsx infrastructure/hermes/hermes_rpc.ts
```

The first stdout object should indicate readiness, and the second should contain
the response for request id `1`.

## Relationship to kernel authority

BroccoliDB throughput optimization is **orthogonal** to the kernel authority
bridge. BroccoliDB handles repository graph, audit, and queue RPC; the kernel
handles physical file mutation and `verify.run` through `dietcode_kernel`.

| Concern | Runtime boundary |
| --- | --- |
| Graph / queue hot path | `broccolidb/infrastructure/hermes/hermes_rpc.ts` |
| Governed file patch | `dietcode_kernel` → `kernel/build/dietcode-kernel` |

See [architecture.md](architecture.md) and [kernel-bridge-operations.md](kernel-bridge-operations.md).
