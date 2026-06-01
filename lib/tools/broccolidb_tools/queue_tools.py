"""
BroccoliQ Tools — Sharded queue, hive integrity, and swarm coordination.
"""
from tools.registry import registry
from plugins.dietcode.lib.tools.broccolidb_tools.runner import check_requirements, run_db_rpc


def broccolidb_queue_status(task_id: str = None) -> str:
    """Report SqliteQueue job counts grouped by status."""
    return run_db_rpc("queue_status")


def broccolidb_shard_status(task_id: str = None) -> str:
    """List active BroccoliQ database shards and connection health."""
    return run_db_rpc("shard_status")


def broccolidb_hive_integrity(task_id: str = None) -> str:
    """Run a one-shot BroccoliQ IntegrityWorker audit across all shards."""
    return run_db_rpc("hive_integrity", timeout=120)


registry.register(
    name="broccolidb_queue_status",
    toolset="broccolidb",
    schema={
        "name": "broccolidb_queue_status",
        "description": (
            "Report BroccoliQ SqliteQueue job counts by status (pending, processing, done, failed). "
            "Use before tuning background workers or diagnosing stuck jobs."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    handler=lambda args, **kw: broccolidb_queue_status(task_id=kw.get("task_id")),
    check_fn=check_requirements,
    emoji="📬",
)

registry.register(
    name="broccolidb_shard_status",
    toolset="broccolidb",
    schema={
        "name": "broccolidb_shard_status",
        "description": (
            "List active BroccoliQ database shards and verify each shard connection is healthy. "
            "Use when scaling agent swarms or debugging SQLITE_BUSY contention."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    handler=lambda args, **kw: broccolidb_shard_status(task_id=kw.get("task_id")),
    check_fn=check_requirements,
    emoji="🧩",
)

registry.register(
    name="broccolidb_hive_integrity",
    toolset="broccolidb",
    schema={
        "name": "broccolidb_hive_integrity",
        "description": (
            "Run a BroccoliQ IntegrityWorker audit across all database shards. "
            "Checks physical SQLite integrity and logical orphan consistency."
        ),
        "parameters": {"type": "object", "properties": {}},
    },
    handler=lambda args, **kw: broccolidb_hive_integrity(task_id=kw.get("task_id")),
    check_fn=check_requirements,
    emoji="🛡️",
)
