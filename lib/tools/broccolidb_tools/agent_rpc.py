"""
BroccoliDB AgentContext RPC — graph/kanban cognitive tools via native worker.

Routes through persistent ``agent_invoke`` when RPC is available; falls back to
one-shot ``run_agent_context_script`` (cold AgentContext bootstrap per call).
"""
from __future__ import annotations

from typing import Any

from plugins.dietcode.lib.tools.broccolidb_tools.runner import run_agent_context_script, run_db_rpc

_AGENT_CONTEXT_TIMEOUT = 120


def run_agent_rpc(
    op: str,
    args: dict[str, Any] | None = None,
    *,
    timeout: int = _AGENT_CONTEXT_TIMEOUT,
    flush: bool = True,
) -> str:
    """Execute an AgentContext operation (native RPC when available)."""
    from plugins.dietcode.lib.tools.broccolidb_tools.db_gateway import rpc_available as _rpc_available

    payload_args = dict(args or {})
    if _rpc_available():
        return run_db_rpc(
            "agent_invoke",
            {"op": op, "args": payload_args, "flush": flush},
            timeout=timeout,
        )

    return _fallback_agent_context_script(op, payload_args, timeout=timeout)


def _fallback_agent_context_script(op: str, args: dict[str, Any], *, timeout: int) -> str:
    """Cold path templates — kept in sync with agent_invoke.ts."""
    if op == "add_knowledge":
        tags = args.get("tags") or ""
        body = f"""\
  const tagsStr = {tags!r};
  const tagsArray = typeof tagsStr === 'string'
    ? tagsStr.split(',').map(t => t.trim()).filter(Boolean)
    : (Array.isArray(tagsStr) ? tagsStr : []);
  const newId = await context.addKnowledge(
    {args.get("kb_id", "auto")!r},
    {args.get("type", "fact")!r},
    {args.get("content", "")!r},
    {{ tags: tagsArray }}
  );
  console.log(JSON.stringify({{ success: true, kbId: newId }}));
"""
    elif op == "query_graph":
        limit = int(args.get("limit") or 10)
        body = f"""\
  const tagsStr = {args.get("tags") or ""!r};
  const tagsArray = tagsStr ? tagsStr.split(',').map(t => t.trim()).filter(Boolean) : undefined;
  const results = await context.searchKnowledge({args.get("query", "")!r}, tagsArray, {limit});
  console.log(JSON.stringify({{
    success: true,
    resultCount: results.length,
    results: results.map(r => ({{
      id: r.itemId,
      type: r.type,
      content: r.content.substring(0, 500),
      confidence: r.confidence,
      tags: r.tags,
      edgeCount: (r.edges || []).length,
    }})),
  }}));
"""
    elif op == "get_task_context":
        task_id = args.get("task_id") or args.get("taskId") or ""
        body = f"""\
  const taskContext = await context.getTaskContext({task_id!r});
  console.log(JSON.stringify({{ success: true, taskId: {task_id!r}, context: taskContext }}));
"""
    elif op == "append_shared_memory":
        body = f"""\
  await context.appendSharedMemory({args.get("memory", "")!r});
  console.log(JSON.stringify({{ success: true, message: 'Memory appended to shared rulebook.' }}));
"""
    elif op == "get_shared_memory":
        body = """\
  const shared = await context.query.getSharedMemory();
  console.log(JSON.stringify({
    success: true,
    memories: shared.memories,
    count: shared.count,
  }));
"""
    elif op == "get_context_graph":
        path = args.get("path", "")
        limit = int(args.get("limit") or 50)
        body = f"""\
  const {{ getContextGraphForPath }} = await import('./infrastructure/hermes/graph_intelligence.js');
  const connections = await getContextGraphForPath(context, {path!r}, {limit});
  console.log(JSON.stringify({{ success: true, path: {path!r}, connections }}));
"""
    elif op == "detect_chokepoints":
        limit = int(args.get("limit") or 10)
        body = f"""\
  const {{ detectChokepoints }} = await import('./infrastructure/hermes/graph_intelligence.js');
  const chokepoints = await detectChokepoints(context, {limit});
  console.log(JSON.stringify({{ success: true, chokepoints }}));
"""
    elif op == "link_knowledge":
        body = f"""\
  await context.graph.linkKnowledge({{
    sourceId: {args.get("sourceId", "")!r},
    targetId: {args.get("targetId", "")!r},
    relation: {args.get("relation", "related")!r},
    weight: {float(args.get("weight") or 1.0)},
  }});
  console.log(JSON.stringify({{
    success: true,
    linked: true,
    sourceId: {args.get("sourceId", "")!r},
    targetId: {args.get("targetId", "")!r},
    relation: {args.get("relation", "related")!r},
  }}));
"""
    elif op == "merge_knowledge":
        body = f"""\
  await context.graph.mergeKnowledge({{
    sourceId: {args.get("sourceId", "")!r},
    targetId: {args.get("targetId", "")!r},
  }});
  console.log(JSON.stringify({{
    success: true,
    merged: true,
    sourceId: {args.get("sourceId", "")!r},
    targetId: {args.get("targetId", "")!r},
  }}));
"""
    elif op == "get_node_centrality":
        kb_id = args.get("id") or args.get("kb_id") or args.get("kbId") or ""
        body = f"""\
  const centrality = await context.graph.getNodeCentrality({{ kbId: {kb_id!r} }});
  console.log(JSON.stringify({{ success: true, centrality }}));
"""
    elif op == "extract_subgraph":
        root_id = args.get("id") or args.get("rootId") or args.get("kb_id") or args.get("kbId") or ""
        max_depth = int(args.get("maxDepth") or args.get("max_depth") or 2)
        body = f"""\
  const subgraph = await context.graph.extractSubgraph({{ startId: {root_id!r}, maxDepth: {max_depth} }});
  console.log(JSON.stringify({{ success: true, subgraph }}));
"""
    elif op == "get_global_hubs":
        limit = int(args.get("limit") or 10)
        body = f"""\
  const {{ hubs }} = await context.query.getGlobalCentrality({{ limit: {limit} }});
  const enriched = [];
  for (const hub of hubs) {{
    try {{
      const node = await context.graph.getKnowledge({{ kbId: hub.kbId }});
      enriched.push({{ ...hub, content: (node.item.content || '').substring(0, 500) }});
    }} catch {{
      enriched.push({{ ...hub, content: '' }});
    }}
  }}
  console.log(JSON.stringify({{ success: true, hubs: enriched }}));
"""
    elif op == "refresh_knowledge":
        kb_id = args.get("id") or args.get("kb_id") or args.get("kbId") or ""
        body = f"""\
  await context.graph.refreshKnowledge({{ kbId: {kb_id!r} }});
  console.log(JSON.stringify({{ success: true, refreshed: true, kbId: {kb_id!r} }}));
"""
    elif op == "blame_path":
        path = args.get("path", "")
        body = f"""\
  const {{ blameFilePath }} = await import('./infrastructure/hermes/graph_intelligence.js');
  const blame = await blameFilePath(context, {path!r});
  console.log(JSON.stringify({{ success: true, path: {path!r}, blame }}));
"""
    elif op == "get_agent_bundle":
        agent_id = args.get("agentId") or args.get("agent_id") or args.get("task_id") or args.get("taskId") or ""
        body = f"""\
  const {{ bundle }} = await context.query.getAgentBundle({{ agentId: {agent_id!r} }});
  console.log(JSON.stringify({{ success: true, agentId: {agent_id!r}, bundle }}));
"""
    elif op == "generate_changelog":
        base_ref = args.get("baseId") or args.get("base_id") or args.get("baseRef") or ""
        head_ref = args.get("headId") or args.get("head_id") or args.get("headRef") or ""
        body = f"""\
  const {{ generateRepoChangelog }} = await import('./infrastructure/hermes/graph_intelligence.js');
  const changelog = await generateRepoChangelog(context, {base_ref!r}, {head_ref!r});
  console.log(JSON.stringify({{ success: true, baseRef: {base_ref!r}, headRef: {head_ref!r}, changelog }}));
"""
    elif op == "simulate_merge_forecast":
        source_ref = args.get("sourceStreamId") or args.get("source_stream_id") or args.get("source") or ""
        target_ref = (
            args.get("targetStreamId")
            or args.get("target_stream_id")
            or args.get("target")
            or args.get("task_id")
            or args.get("taskId")
            or ""
        )
        body = f"""\
  const {{ simulateMergeForecast }} = await import('./infrastructure/hermes/graph_intelligence.js');
  const forecast = await simulateMergeForecast(context, {source_ref!r}, {target_ref!r});
  console.log(JSON.stringify({{ success: true, sourceRef: {source_ref!r}, targetRef: {target_ref!r}, forecast }}));
"""
    elif op == "acquire_lock":
        resource = args.get("resource", "")
        body = f"""\
  const result = await context.coordination.acquireLock({{ resource: {resource!r} }});
  if (!result.acquired) {{
    console.log(JSON.stringify({{ success: false, error: 'Failed to acquire lock', error_code: 'LOCK_UNAVAILABLE' }}));
  }} else {{
    console.log(JSON.stringify({{ success: true, acquired: true, resource: {resource!r} }}));
  }}
"""
    elif op == "release_lock":
        resource = args.get("resource", "")
        body = f"""\
  await context.coordination.releaseLock({{ resource: {resource!r} }});
  console.log(JSON.stringify({{ success: true, released: true, resource: {resource!r} }}));
"""
    elif op == "spider_gate":
        scope = args.get("scope") or "changed-files"
        body = f"""\
  const gate = await context.graph.spider.gate({{ scope: {scope!r}, includeTypes: false }});
  const findings = (gate.report?.findings ?? []).slice(0, 20).map((f) => ({{
    diagnosticId: f.diagnosticId,
    message: f.message,
    severity: f.severity,
    filePath: f.filePath,
  }}));
  console.log(JSON.stringify({{
    success: true,
    blocked: gate.blocked,
    exitCode: gate.exitCode,
    conclusion: gate.conclusion,
    findingCount: gate.report?.findings?.length ?? 0,
    reportId: gate.report?.reportId,
    findings,
  }}));
"""
    elif op == "heal":
        body = """\
  const healResult = await context.selfHealGraph();
  const spider = context.spider;
  await spider.bootstrapGraph();
  const integrityResult = await spider.verifyGraphIntegrity(false);
  console.log(JSON.stringify({
    success: true,
    epistemic: {
      prunedNodes: healResult.prunedNodes.length,
      prunedNodeIds: healResult.prunedNodes.slice(0, 20),
      prunedEdges: healResult.prunedEdges,
    },
    structural: { ghostNodesPruned: integrityResult.pruned },
    totalHealed: healResult.prunedNodes.length + integrityResult.pruned,
  }));
"""
    elif op == "verify_sovereignty":
        kb_id = args.get("kb_id") or args.get("kbId") or ""
        body = f"""\
  const nodeId = {kb_id!r};
  const result = await context.reasoningService.verifySovereignty(nodeId);
  const caveat = await context.reasoningService.getSovereignCaveat(nodeId);
  console.log(JSON.stringify({{
    success: true,
    kbId: nodeId,
    isValid: result.isValid,
    metrics: result.metrics,
    caveat: caveat || null,
    verdict: result.isValid ? 'SOVEREIGN' : 'UNRELIABLE',
  }}));
"""
    else:
        import json
        from plugins.dietcode.lib.tools.broccolidb_tools.runner import _make_result

        return _make_result(False, error=f"unknown agent op: {op}", error_code="UNKNOWN_AGENT_OP")

    return run_agent_context_script(body, timeout=timeout)
