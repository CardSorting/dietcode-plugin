"""
BroccoliDB/BroccoliQ native execution surface — canonical method registry.

Keep in sync with ``broccolidb/infrastructure/hermes/rpc_handlers.ts`` (RPC_VERSION).
"""
from __future__ import annotations

# Mirror rpc_handlers.RPC_VERSION
RPC_VERSION = 4

RPC_METHODS = frozenset({
    "ping",
    "rpc_health",
    "dashboard_snapshot",
    "queue_status",
    "shard_status",
    "hive_integrity",
    "proposal_action",
    "hive_sync",
    "hive_drift",
    "hive_board_intel",
    "agent_invoke",
    "pool_flush",
    "batch",
})

AGENT_OPS = frozenset({
    "warm",
    "heal",
    "add_knowledge",
    "query_graph",
    "get_task_context",
    "append_shared_memory",
    "verify_sovereignty",
})

_HERMES_RPC_SCRIPT = "infrastructure/hermes/hermes_rpc.ts"
_HERMES_HANDLERS_SCRIPT = "infrastructure/hermes/rpc_handlers.ts"
_HERMES_ONESHOT_SCRIPT = "infrastructure/hermes/hermes_oneshot.ts"


def warm_db_rpc(*, block: bool = False, preload_agent: bool = False) -> bool:
    """Pre-start the persistent RPC worker (dashboard poll / kanban sync latency)."""
    from plugins.dietcode.lib.tools.broccolidb_tools.db_gateway import rpc_available, run_db_rpc

    if not rpc_available():
        return False
    if block:
        if preload_agent:
            raw = run_db_rpc(
                "agent_invoke",
                {"op": "warm", "args": {}, "flush": False},
                timeout=30,
            )
        else:
            raw = run_db_rpc("rpc_health", timeout=20)
        try:
            import json
            return bool(json.loads(raw).get("success"))
        except Exception:
            return False

    import threading

    def _warm() -> None:
        try:
            run_db_rpc("rpc_health", timeout=15)
            if preload_agent:
                run_db_rpc(
                    "agent_invoke",
                    {"op": "warm", "args": {}, "flush": False},
                    timeout=30,
                )
        except Exception:
            pass

    threading.Thread(target=_warm, name="broccolidb-rpc-warm", daemon=True).start()
    return True
