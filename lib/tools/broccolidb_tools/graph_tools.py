"""
BroccoliDB Graph Tools — Knowledge graph CRUD, search, and memory.

Uses native AgentContext RPC (persistent worker) when available; falls back to
one-shot AgentContext bootstrap via run_agent_context_script.
"""
from tools.registry import registry
from plugins.dietcode.lib.tools.broccolidb_tools.runner import check_requirements
from plugins.dietcode.lib.tools.broccolidb_tools.agent_rpc import run_agent_rpc


def broccolidb_add_knowledge(kb_id: str, type: str, content: str, tags: str = None) -> str:
    """Add a new cognitive node to the BroccoliDB Knowledge Graph."""
    return run_agent_rpc(
        "add_knowledge",
        {"kb_id": kb_id, "type": type, "content": content, "tags": tags or ""},
    )


def broccolidb_query_graph(query: str, tags: str = None, limit: int = 10) -> str:
    """Search the BroccoliDB Knowledge Graph with confidence metrics."""
    return run_agent_rpc(
        "query_graph",
        {"query": query, "tags": tags or "", "limit": limit},
        flush=False,
    )


def broccolidb_get_task_context(task_id: str) -> str:
    """Retrieve contextual intelligence for a task."""
    return run_agent_rpc(
        "get_task_context",
        {"task_id": task_id},
        flush=False,
    )


def broccolidb_append_shared_memory(memory: str) -> str:
    """Contribute a global guideline to the swarm-wide Shared Rulebook."""
    return run_agent_rpc("append_shared_memory", {"memory": memory})


def broccolidb_verify_sovereignty(kb_id: str) -> str:
    """Verify structural & epistemic sovereignty of a knowledge node."""
    return run_agent_rpc(
        "verify_sovereignty",
        {"kb_id": kb_id},
        flush=False,
    )


# ─── Registrations ───

registry.register(
    name="broccolidb_add_knowledge",
    toolset="broccolidb",
    schema={
        "name": "broccolidb_add_knowledge",
        "description": (
            "Add a knowledge node (fact, rule, hypothesis, or conclusion) to the "
            "BroccoliDB Knowledge Graph. Use this to persist architectural decisions, "
            "verified facts, or working hypotheses. Nodes can be linked and queried later."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {
                    "type": "string",
                    "description": "Unique ID for the node, or 'auto' to auto-generate",
                },
                "type": {
                    "type": "string",
                    "enum": ["fact", "vector", "rule", "hypothesis", "conclusion"],
                    "description": "The category of knowledge",
                },
                "content": {
                    "type": "string",
                    "description": "The text payload of the knowledge node",
                },
                "tags": {
                    "type": "string",
                    "description": "Optional comma-separated tags (e.g., 'rules,architecture')",
                },
            },
            "required": ["kb_id", "type", "content"],
        },
    },
    handler=lambda args, **kw: broccolidb_add_knowledge(
        kb_id=args.get("kb_id"),
        type=args.get("type"),
        content=args.get("content"),
        tags=args.get("tags"),
    ),
    check_fn=check_requirements,
    emoji="💭",
)

registry.register(
    name="broccolidb_query_graph",
    toolset="broccolidb",
    schema={
        "name": "broccolidb_query_graph",
        "description": (
            "Search the BroccoliDB Knowledge Graph by content substring with optional "
            "tag filtering. Results are ranked by epistemic confidence (sovereignty score). "
            "Use this to recall previously stored facts, decisions, or architectural rules."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Substring query to search within node content",
                },
                "tags": {
                    "type": "string",
                    "description": "Optional comma-separated tags to filter by",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return (default 10)",
                },
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: broccolidb_query_graph(
        query=args.get("query"),
        tags=args.get("tags"),
        limit=args.get("limit", 10),
    ),
    check_fn=check_requirements,
    emoji="🔍",
)

registry.register(
    name="broccolidb_get_task_context",
    toolset="broccolidb",
    schema={
        "name": "broccolidb_get_task_context",
        "description": (
            "Fetch the cognitive context window for a task, resolving its "
            "knowledge dependency graph. Returns linked knowledge nodes, "
            "shared memory rules, and structural context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "string",
                    "description": "The unique Task ID to fetch context for",
                }
            },
            "required": ["task_id"],
        },
    },
    handler=lambda args, **kw: broccolidb_get_task_context(
        task_id=args.get("task_id")
    ),
    check_fn=check_requirements,
    emoji="📋",
)

registry.register(
    name="broccolidb_append_shared_memory",
    toolset="broccolidb",
    schema={
        "name": "broccolidb_append_shared_memory",
        "description": (
            "Add a global architectural rule or guideline to the Shared Rulebook. "
            "Shared memory is visible to all agents in the workspace. Use this for "
            "cross-cutting concerns like 'all API routes must validate auth tokens'."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "memory": {
                    "type": "string",
                    "description": "The architectural guideline or rule to share globally",
                }
            },
            "required": ["memory"],
        },
    },
    handler=lambda args, **kw: broccolidb_append_shared_memory(
        memory=args.get("memory")
    ),
    check_fn=check_requirements,
    emoji="🧠",
)

registry.register(
    name="broccolidb_verify_sovereignty",
    toolset="broccolidb",
    schema={
        "name": "broccolidb_verify_sovereignty",
        "description": (
            "Perform a Skeptical Audit on a knowledge node to verify structural and "
            "epistemic sovereignty. Analyzes: git signals (commit distance, file churn), "
            "reinforcement (supporting nodes), evidence discounting, and adaptive confidence threshold."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "kb_id": {
                    "type": "string",
                    "description": "The unique Knowledge Node ID to audit",
                }
            },
            "required": ["kb_id"],
        },
    },
    handler=lambda args, **kw: broccolidb_verify_sovereignty(
        kb_id=args.get("kb_id")
    ),
    check_fn=check_requirements,
    emoji="🛡️",
)
