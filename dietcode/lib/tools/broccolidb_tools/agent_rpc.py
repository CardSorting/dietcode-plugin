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
