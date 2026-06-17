# -*- coding: utf-8 -*-
"""LUMI cognitive-memory tool aliases — same behavior as broccolidb_* without VS Code."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from tools.registry import registry, tool_error

from plugins.dietcode.lib.tools.broccolidb_tools.graph_tools import (
    broccolidb_add_knowledge,
    broccolidb_append_shared_memory,
    broccolidb_get_task_context,
    broccolidb_query_graph,
)
from plugins.dietcode.lib.tools.broccolidb_tools.runner import check_requirements
from plugins.dietcode.lib.tools.broccolidb_tools.structural_tools import (
    broccolidb_blast_radius,
    broccolidb_heal,
)


def _default_task_id(task_id: str = "") -> str:
    tid = (task_id or "").strip()
    if tid:
        return tid
    for key in ("HERMES_KANBAN_TASK", "DIETCODE_TASK_ID"):
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return ""


def _rpc(op: str, args: dict, *, flush: bool = True) -> str:
    from plugins.dietcode.lib.tools.broccolidb_tools.agent_rpc import run_agent_rpc

    return run_agent_rpc(op, args, flush=flush)


def _parse_rpc(raw: str) -> dict:
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def query_cognitive_memory(text: str, limit: int = 5, **_: object) -> str:
    """Alias for broccolidb_query_graph (codemarie query_cognitive_memory)."""
    if not (text or "").strip():
        return tool_error("text is required")
    return broccolidb_query_graph(query=text.strip(), limit=limit)


def create_cognitive_snapshot(content: str, metadata: str = "", **_: object) -> str:
    """Alias for broccolidb_add_knowledge (codemarie create_cognitive_snapshot)."""
    if not (content or "").strip():
        return tool_error("content is required")
    tags = (metadata or "").strip() or "snapshot,cognitive"
    return broccolidb_add_knowledge(kb_id="auto", type="fact", content=content.strip(), tags=tags)


def mem_blast(path: str, maxDepth: int = 2, task_id: str = "", **_: object) -> str:
    """Alias for broccolidb_blast_radius (codemarie mem_blast). maxDepth reserved for API parity."""
    if not (path or "").strip():
        return tool_error("path is required")
    _ = maxDepth
    return broccolidb_blast_radius(file_path=path.strip(), task_id=_default_task_id(task_id) or None)


def mem_heal(task_id: str = "", **_: object) -> str:
    """Alias for broccolidb_heal (codemarie mem_heal)."""
    _ = _default_task_id(task_id)
    return broccolidb_heal(task_id=_ or None)


def mem_append_shared(memory: str, **_: object) -> str:
    """Alias for broccolidb_append_shared_memory."""
    if not (memory or "").strip():
        return tool_error("memory is required")
    return broccolidb_append_shared_memory(memory=memory.strip())


def mem_context(path: str = "", task_id: str = "", limit: int = 50, **_: object) -> str:
    """File co-change context (path) or task-scoped BroccoliDB context (task_id)."""
    file_path = (path or "").strip()
    if file_path:
        raw = _rpc("get_context_graph", {"path": file_path, "limit": limit}, flush=False)
        data = _parse_rpc(raw)
        if not data.get("success"):
            return raw
        connections = data.get("connections") or []
        if not connections:
            return json.dumps({"message": f"No semantic correlations found for '{file_path}'."})
        lines = [f"- {c.get('path', '?')} (weight: {c.get('weight', 0)})" for c in connections]
        return json.dumps(
            {
                "message": (
                    f"Semantic context for '{file_path}':\n\n"
                    + "\n".join(lines)
                    + "\n\nThese files are frequently co-modified based on task history."
                )
            }
        )
    tid = _default_task_id(task_id)
    if not tid:
        return tool_error("path or task_id is required")
    return broccolidb_get_task_context(task_id=tid)


def mem_get_shared(**_: object) -> str:
    """Read swarm shared rulebook — broccolidb get_shared_memory RPC."""
    return _rpc("get_shared_memory", {}, flush=False)


def mem_link(sourceId: str, targetId: str, relation: str, weight: float = 1.0, **_: object) -> str:
    """Link knowledge nodes — alias for link_knowledge RPC."""
    if not sourceId or not targetId or not relation:
        return tool_error("sourceId, targetId, and relation are required")
    return _rpc(
        "link_knowledge",
        {
            "sourceId": sourceId,
            "targetId": targetId,
            "relation": relation,
            "weight": weight,
        },
    )


def mem_merge(sourceId: str, targetId: str, **_: object) -> str:
    """Merge knowledge nodes — alias for merge_knowledge RPC."""
    if not sourceId or not targetId:
        return tool_error("sourceId and targetId are required")
    return _rpc("merge_knowledge", {"sourceId": sourceId, "targetId": targetId})


def mem_choke(limit: int = 10, **_: object) -> str:
    """Detect architectural chokepoints from repository churn history."""
    return _rpc("detect_chokepoints", {"limit": limit}, flush=False)


def mem_centrality(id: str = "", **_: object) -> str:
    """Node degree centrality for a knowledge graph item."""
    kb_id = (id or "").strip()
    if not kb_id:
        return tool_error("id is required")
    return _rpc("get_node_centrality", {"id": kb_id}, flush=False)


def mem_subgraph(id: str = "", rootId: str = "", maxDepth: int = 2, **_: object) -> str:
    """Extract a bounded knowledge subgraph from a root node."""
    root = (id or rootId or "").strip()
    if not root:
        return tool_error("id is required")
    return _rpc("extract_subgraph", {"id": root, "maxDepth": maxDepth}, flush=False)


def mem_hubs(limit: int = 10, **_: object) -> str:
    """Highly-connected hub nodes in the knowledge graph."""
    raw = _rpc("get_global_hubs", {"limit": limit}, flush=False)
    data = _parse_rpc(raw)
    if not data.get("success"):
        return raw
    hubs = data.get("hubs") or []
    if not hubs:
        return json.dumps({"message": "No hub nodes found."})
    blocks = []
    for hub in hubs:
        blocks.append(
            f"[Hub: {hub.get('kbId', '?')}] Score: {hub.get('score', 0)}\n"
            f"Content: {hub.get('content', '')}"
        )
    return json.dumps({"message": "\n---\n".join(blocks)})


def mem_refresh(id: str = "", **_: object) -> str:
    """Refresh confidence for a knowledge node."""
    kb_id = (id or "").strip()
    if not kb_id:
        return tool_error("id is required")
    raw = _rpc("refresh_knowledge", {"id": kb_id})
    data = _parse_rpc(raw)
    if data.get("success"):
        return json.dumps({"message": f"Successfully refreshed confidence for knowledge node {kb_id}."})
    return raw


def mem_blame(path: str = "", **_: object) -> str:
    """Last repository modification record for a file path."""
    file_path = (path or "").strip()
    if not file_path:
        return tool_error("path is required")
    raw = _rpc("blame_path", {"path": file_path}, flush=False)
    data = _parse_rpc(raw)
    if not data.get("success"):
        return raw
    blame = data.get("blame")
    if not blame:
        return json.dumps({"message": f"No historical modification record found for '{file_path}'."})
    ts_raw = blame.get("lastTimestamp", 0)
    ts_val = float(ts_raw or 0)
    if ts_val > 1e12:
        ts = datetime.fromtimestamp(ts_val / 1000, tz=timezone.utc).isoformat()
    elif ts_val > 0:
        ts = datetime.fromtimestamp(ts_val, tz=timezone.utc).isoformat()
    else:
        ts = "unknown"
    return json.dumps(
        {
            "message": (
                f"Blame for '{file_path}':\n\n"
                f"Last modified by: {blame.get('lastAuthor', 'unknown')}\n"
                f"Node ID: {blame.get('lastNodeId', '')}\n"
                f"Message: {blame.get('lastMessage', '')}\n"
                f"Time: {ts}"
            )
        }
    )


def mem_bundle(task_id: str = "", agentId: str = "", **_: object) -> str:
    """Cognitive intelligence bundle for the active agent."""
    aid = (agentId or _default_task_id(task_id) or "").strip()
    if not aid:
        return tool_error("agentId or task_id is required")
    raw = _rpc("get_agent_bundle", {"agentId": aid}, flush=False)
    data = _parse_rpc(raw)
    if not data.get("success"):
        return raw
    bundle = data.get("bundle") or {}
    return json.dumps({"message": f"Successfully fetched cognitive bundle:\n\n{json.dumps(bundle, indent=2)}"})


def mem_changelog(baseId: str = "", headId: str = "", **_: object) -> str:
    """Structural changelog between two repository references."""
    base = (baseId or "").strip()
    head = (headId or "").strip()
    if not base or not head:
        return tool_error("baseId and headId are required")
    raw = _rpc("generate_changelog", {"baseId": base, "headId": head}, flush=False)
    data = _parse_rpc(raw)
    if not data.get("success"):
        return raw
    return json.dumps({"message": data.get("changelog", "")})


def mem_forecast(sourceStreamId: str = "", targetStreamId: str = "", task_id: str = "", **_: object) -> str:
    """Speculative merge risk forecast between two agent streams."""
    source = (sourceStreamId or "").strip()
    target = (targetStreamId or _default_task_id(task_id) or "").strip()
    if not source:
        return tool_error("sourceStreamId is required")
    if not target:
        return tool_error("targetStreamId or task_id is required")
    raw = _rpc(
        "simulate_merge_forecast",
        {"sourceStreamId": source, "targetStreamId": target},
        flush=False,
    )
    data = _parse_rpc(raw)
    if not data.get("success"):
        return raw
    forecast = data.get("forecast") or {}
    report = f"Merge Forecast for {source} -> {target}:\n\n"
    report += f"Risk Level: {'HIGH' if forecast.get('isHighRisk') else 'LOW'}\n"
    conflicts = forecast.get("conflicts") or []
    report += f"Direct Conflicts: {len(conflicts)}\n"
    if conflicts:
        report += f"Files: {', '.join(conflicts)}\n"
    overlaps = forecast.get("semanticOverlaps") or []
    if overlaps:
        report += "\nSemantic Overlaps detected:\n"
        for overlap in overlaps:
            report += f"- {overlap.get('path', '?')}: {overlap.get('reason', '')}\n"
    return json.dumps({"message": report})


def mem_claim(resource: str = "", timeoutMs: int = 60000, **_: object) -> str:
    """Claim exclusive access to a swarm resource."""
    res = (resource or "").strip()
    if not res:
        return tool_error("resource is required")
    _ = timeoutMs  # Hermes mutex uses fixed TTL; param kept for LUMI parity
    raw = _rpc("acquire_lock", {"resource": res})
    data = _parse_rpc(raw)
    if data.get("success"):
        return json.dumps({"message": f"Resource '{res}' successfully claimed."})
    return raw


def mem_release(resource: str = "", **_: object) -> str:
    """Release a previously claimed swarm resource."""
    res = (resource or "").strip()
    if not res:
        return tool_error("resource is required")
    raw = _rpc("release_lock", {"resource": res})
    data = _parse_rpc(raw)
    if data.get("success"):
        return json.dumps({"message": f"Resource '{res}' has been released."})
    return raw


def mem_snapshot(content: str = "", metadata: str = "", **_: object) -> str:
    """Create a cognitive snapshot node — alias for create_cognitive_snapshot."""
    if not (content or "").strip():
        return tool_error("content is required")
    raw = create_cognitive_snapshot(content=content.strip(), metadata=metadata)
    data = _parse_rpc(raw)
    if data.get("error"):
        return raw
    if data.get("success"):
        kb_id = data.get("kbId") or "unknown"
        return json.dumps({"message": f"Successfully created cognitive graph node with ID: {kb_id}"})
    return raw


_ALIAS_REGISTRATIONS = (
    (
        "query_cognitive_memory",
        query_cognitive_memory,
        "Query cognitive memory — alias for broccolidb_query_graph (LUMI vocabulary).",
        {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Semantic query text"},
                "limit": {"type": "integer", "description": "Max results (default 5)"},
            },
            "required": ["text"],
        },
    ),
    (
        "create_cognitive_snapshot",
        create_cognitive_snapshot,
        "Persist a cognitive snapshot — alias for broccolidb_add_knowledge.",
        {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Snapshot body"},
                "metadata": {"type": "string", "description": "Optional tags/metadata string"},
            },
            "required": ["content"],
        },
    ),
    (
        "mem_blast",
        mem_blast,
        "Structural blast radius — alias for broccolidb_blast_radius.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path to analyze"},
                "maxDepth": {"type": "integer", "description": "Traversal depth (parity; spider uses structural graph)"},
                "task_id": {"type": "string", "description": "Optional kanban task id"},
            },
            "required": ["path"],
        },
    ),
    (
        "mem_heal",
        mem_heal,
        "Graph self-heal — alias for broccolidb_heal.",
        {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
        },
    ),
    (
        "mem_append_shared",
        mem_append_shared,
        "Append to swarm shared rulebook — alias for broccolidb_append_shared_memory.",
        {
            "type": "object",
            "properties": {"memory": {"type": "string", "description": "Guideline or fact to append"}},
            "required": ["memory"],
        },
    ),
    (
        "mem_context",
        mem_context,
        "File co-change context or task context from BroccoliDB.",
        {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "File path for co-change context graph"},
                "task_id": {"type": "string", "description": "Kanban task id for task-scoped context"},
                "limit": {"type": "integer"},
            },
        },
    ),
    (
        "mem_get_shared",
        mem_get_shared,
        "Read shared rulebook entries from workspace sharedMemoryLayer.",
        {"type": "object", "properties": {}},
    ),
    (
        "mem_link",
        mem_link,
        "Link cognitive knowledge nodes — alias for link_knowledge.",
        {
            "type": "object",
            "properties": {
                "sourceId": {"type": "string"},
                "targetId": {"type": "string"},
                "relation": {"type": "string"},
                "weight": {"type": "number"},
            },
            "required": ["sourceId", "targetId", "relation"],
        },
    ),
    (
        "mem_merge",
        mem_merge,
        "Merge knowledge nodes — alias for merge_knowledge.",
        {
            "type": "object",
            "properties": {
                "sourceId": {"type": "string"},
                "targetId": {"type": "string"},
            },
            "required": ["sourceId", "targetId"],
        },
    ),
    (
        "mem_choke",
        mem_choke,
        "Architectural chokepoint detection from BroccoliDB history.",
        {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max chokepoints (default 10)"}},
        },
    ),
    (
        "mem_centrality",
        mem_centrality,
        "Node degree centrality for a knowledge graph item.",
        {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Knowledge node id"}},
            "required": ["id"],
        },
    ),
    (
        "mem_subgraph",
        mem_subgraph,
        "Extract a bounded knowledge subgraph from a root node.",
        {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Root knowledge node id"},
                "rootId": {"type": "string", "description": "Alias for id"},
                "maxDepth": {"type": "integer", "description": "Traversal depth (default 2)"},
            },
        },
    ),
    (
        "mem_hubs",
        mem_hubs,
        "Highly-connected hub nodes in the knowledge graph.",
        {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max hubs (default 10)"}},
        },
    ),
    (
        "mem_refresh",
        mem_refresh,
        "Refresh confidence for a knowledge node.",
        {
            "type": "object",
            "properties": {"id": {"type": "string", "description": "Knowledge node id"}},
            "required": ["id"],
        },
    ),
    (
        "mem_blame",
        mem_blame,
        "Last repository modification record for a file path.",
        {
            "type": "object",
            "properties": {"path": {"type": "string", "description": "File path to blame"}},
            "required": ["path"],
        },
    ),
    (
        "mem_bundle",
        mem_bundle,
        "Cognitive intelligence bundle for the active agent.",
        {
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Kanban task / agent stream id"},
                "agentId": {"type": "string", "description": "Explicit agent stream id"},
            },
        },
    ),
    (
        "mem_changelog",
        mem_changelog,
        "Structural changelog between two repository snapshot references.",
        {
            "type": "object",
            "properties": {
                "baseId": {"type": "string", "description": "Base ref or commit id"},
                "headId": {"type": "string", "description": "Head ref or commit id"},
            },
            "required": ["baseId", "headId"],
        },
    ),
    (
        "mem_forecast",
        mem_forecast,
        "Speculative merge risk forecast between agent streams.",
        {
            "type": "object",
            "properties": {
                "sourceStreamId": {"type": "string", "description": "Source stream/ref"},
                "targetStreamId": {"type": "string", "description": "Target stream/ref (defaults to task_id)"},
                "task_id": {"type": "string", "description": "Current task id when target omitted"},
            },
            "required": ["sourceStreamId"],
        },
    ),
    (
        "mem_claim",
        mem_claim,
        "Claim exclusive access to a swarm resource.",
        {
            "type": "object",
            "properties": {
                "resource": {"type": "string", "description": "File path or concept key"},
                "timeoutMs": {"type": "integer", "description": "Lock TTL hint (parity)"},
            },
            "required": ["resource"],
        },
    ),
    (
        "mem_release",
        mem_release,
        "Release a previously claimed swarm resource.",
        {
            "type": "object",
            "properties": {"resource": {"type": "string", "description": "Resource to release"}},
            "required": ["resource"],
        },
    ),
    (
        "mem_snapshot",
        mem_snapshot,
        "Create a cognitive snapshot node in the knowledge graph.",
        {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Snapshot body"},
                "metadata": {"type": "string", "description": "Optional tags/metadata"},
            },
            "required": ["content"],
        },
    ),
)

for _name, _handler, _desc, _params in _ALIAS_REGISTRATIONS:
    registry.register(
        name=_name,
        toolset="broccolidb",
        schema={"name": _name, "description": _desc, "parameters": _params},
        handler=lambda args, _fn=_handler, **kw: _fn(**(args if isinstance(args, dict) else {})),
        check_fn=check_requirements,
        emoji="🧠",
    )
