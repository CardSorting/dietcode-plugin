/**
 * AgentContext RPC operations — graph/kanban cognitive tools via persistent session.
 * Maps legacy Hermes op names onto BroccoliDB v30 capability surfaces.
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

	const ctx = await getAgentContext();

	switch (op) {
		case "warm": {
			await getAgentContext();
			return { success: true, warmed: true };
		}
		case "heal": {
			await ctx.reasoning.selfHealGraph();
			const spider = ctx.graph.spider;
			await spider.bootstrapGraph();
			const integrityResult = await spider.verifyGraphIntegrity(false);
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return {
				success: true,
				epistemic: { healed: true },
				structural: {
					ghostNodesPruned: integrityResult.pruned,
				},
				totalHealed: integrityResult.pruned,
			};
		}
		case "add_knowledge": {
			const kbId = String(args.kb_id ?? args.kbId ?? "auto");
			const type = String(args.type ?? "fact");
			const content = String(args.content ?? "");
			const tags = parseTags(args.tags);
			const result = await ctx.graph.addKnowledge({
				kbId,
				type: type as never,
				content,
				tags: tags ?? [],
			});
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return { success: true, kbId: result.kbId };
		}
		case "query_graph": {
			const query = String(args.query ?? "");
			const limit = Math.max(1, Math.min(Number(args.limit) || 10, 100));
			const tags = parseTags(args.tags);
			const search = await ctx.query.search({
				text: query,
				limit,
				tags,
			});
			return {
				success: true,
				resultCount: search.items.length,
				results: search.items.map((r) => ({
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
			const taskContext = await ctx.tasks.getContext({ taskId });
			return { success: true, taskId, context: taskContext.context };
		}
		case "append_shared_memory": {
			const memory = String(args.memory ?? "");
			await ctx.query.appendSharedMemory({ memory });
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return { success: true, message: "Memory appended to shared rulebook." };
		}
		case "verify_sovereignty": {
			const nodeId = String(args.kb_id ?? args.kbId ?? "");
			const result = await ctx.reasoning.verifySovereignty({ nodeId });
			return {
				success: true,
				kbId: nodeId,
				isValid: result.isValid,
				metrics: result.metrics,
				caveat: null,
				verdict: result.isValid ? "SOVEREIGN" : "UNRELIABLE",
			};
		}
		default:
			return { success: false, error: `unhandled op: ${op}` };
	}
}
