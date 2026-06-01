/**
 * AgentContext RPC operations — graph/kanban cognitive tools via persistent session.
 */
import { getAgentContext, flushAgentContext } from "./agent_session.js";

export const AGENT_OPS = [
	"warm",
	"heal",
	"add_knowledge",
	"query_graph",
	"get_task_context",
	"append_shared_memory",
	"verify_sovereignty",
] as const;

export type AgentOp = (typeof AGENT_OPS)[number];

function parseTags(raw: unknown): string[] | undefined {
	if (Array.isArray(raw)) {
		return raw.map(String).filter(Boolean);
	}
	const s = String(raw ?? "").trim();
	if (!s) return undefined;
	return s.split(",").map((t) => t.trim()).filter(Boolean);
}

export async function runAgentInvoke(
	params: Record<string, unknown>,
): Promise<Record<string, unknown>> {
	const op = String(params.op ?? "").trim() as AgentOp;
	const args =
		params.args && typeof params.args === "object"
			? (params.args as Record<string, unknown>)
			: {};

	if (!op || !AGENT_OPS.includes(op)) {
		return {
			success: false,
			error: `unknown agent op: ${op || "(empty)"}`,
			error_code: "UNKNOWN_AGENT_OP",
		};
	}

	const context = await getAgentContext();

	switch (op) {
		case "warm": {
			await getAgentContext();
			return { success: true, warmed: true };
		}
		case "heal": {
			const healResult = await context.selfHealGraph();
			const spider = context.spider;
			await spider.bootstrapGraph();
			const integrityResult = await spider.verifyGraphIntegrity(false);
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return {
				success: true,
				epistemic: {
					prunedNodes: healResult.prunedNodes.length,
					prunedNodeIds: healResult.prunedNodes.slice(0, 20),
					prunedEdges: healResult.prunedEdges,
				},
				structural: {
					ghostNodesPruned: integrityResult.pruned,
				},
				totalHealed: healResult.prunedNodes.length + integrityResult.pruned,
			};
		}
		case "add_knowledge": {
			const kbId = String(args.kb_id ?? args.kbId ?? "auto");
			const type = String(args.type ?? "fact");
			const content = String(args.content ?? "");
			const tags = parseTags(args.tags);
			const newId = await context.addKnowledge(kbId, type as never, content, {
				tags: tags ?? [],
			});
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return { success: true, kbId: newId };
		}
		case "query_graph": {
			const query = String(args.query ?? "");
			const limit = Math.max(1, Math.min(Number(args.limit) || 10, 100));
			const tags = parseTags(args.tags);
			const results = await context.searchKnowledge(query, tags, limit);
			return {
				success: true,
				resultCount: results.length,
				results: results.map((r) => ({
					id: r.itemId,
					type: r.type,
					content: (r.content || "").substring(0, 500),
					confidence: r.confidence,
					tags: r.tags,
					edgeCount: (r.edges || []).length,
				})),
			};
		}
		case "get_task_context": {
			const taskId = String(args.task_id ?? args.taskId ?? "");
			const taskContext = await context.getTaskContext(taskId);
			return { success: true, taskId, context: taskContext };
		}
		case "append_shared_memory": {
			const memory = String(args.memory ?? "");
			await context.appendSharedMemory(memory);
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return { success: true, message: "Memory appended to shared rulebook." };
		}
		case "verify_sovereignty": {
			const nodeId = String(args.kb_id ?? args.kbId ?? "");
			const result = await context.verifySovereignty(nodeId);
			const caveat = await context.reasoningService.getSovereignCaveat(nodeId).catch(
				() => "",
			);
			return {
				success: true,
				kbId: nodeId,
				isValid: result.isValid,
				metrics: result.metrics,
				caveat: caveat || null,
				verdict: result.isValid ? "SOVEREIGN" : "UNRELIABLE",
			};
		}
		default:
			return { success: false, error: `unhandled op: ${op}` };
	}
}
