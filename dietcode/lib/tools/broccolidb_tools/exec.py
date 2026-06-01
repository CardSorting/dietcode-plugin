"""
BroccoliDB/BroccoliQ execution facade — single import surface for tools and CLI.

    from plugins.dietcode.lib.tools.broccolidb_tools.exec import run_db_rpc, run_agent_rpc, warm_db_rpc
"""
from plugins.dietcode.lib.tools.broccolidb_tools.agent_rpc import run_agent_rpc
from plugins.dietcode.lib.tools.broccolidb_tools.db_gateway import (
    rpc_available,
    run_db_rpc,
    run_db_rpc_batch,
    run_oneshot_rpc,
    shutdown_gateway,
)
from plugins.dietcode.lib.tools.broccolidb_tools.db_native import (
    AGENT_OPS,
    RPC_METHODS,
    RPC_VERSION,
    warm_db_rpc,
)
from plugins.dietcode.lib.tools.broccolidb_tools.runner import (
    check_requirements,
    resolve_broccolidb_db_path,
    resolve_broccolidb_root,
    run_hive_board_intel,
    run_hive_drift,
    run_hive_sync,
)

__all__ = [
    "AGENT_OPS",
    "RPC_METHODS",
    "RPC_VERSION",
    "check_requirements",
    "resolve_broccolidb_db_path",
    "resolve_broccolidb_root",
    "rpc_available",
    "run_agent_rpc",
    "run_db_rpc",
    "run_db_rpc_batch",
    "run_hive_board_intel",
    "run_hive_drift",
    "run_hive_sync",
    "run_oneshot_rpc",
    "shutdown_gateway",
    "warm_db_rpc",
]
