/**
 * AgentContext RPC operations — graph/kanban cognitive tools via persistent session.
 * Maps legacy Hermes op names onto BroccoliDB v30 capability surfaces.
 */
import { getAgentContext, flushAgentContext } from "./agent_session.js";
import {
	blameFilePath,
	detectChokepoints,
	generateRepoChangelog,
	getContextGraphForPath,
	simulateMergeForecast,
} from "./graph_intelligence.js";

export const AGENT_OPS = [
	"warm",
	"heal",
	"add_knowledge",
	"query_graph",
	"get_task_context",
	"append_shared_memory",
	"get_shared_memory",
	"get_context_graph",
	"detect_chokepoints",
	"link_knowledge",
	"merge_knowledge",
	"get_node_centrality",
	"extract_subgraph",
	"get_global_hubs",
	"refresh_knowledge",
	"blame_path",
	"get_agent_bundle",
	"generate_changelog",
	"simulate_merge_forecast",
	"acquire_lock",
	"release_lock",
	"spider_gate",
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
		case "get_shared_memory": {
			const shared = await ctx.query.getSharedMemory();
			return {
				success: true,
				memories: shared.memories,
				count: shared.count,
			};
		}
		case "get_context_graph": {
			const filePath = String(args.path ?? "");
			const limit = Math.max(1, Math.min(Number(args.limit) || 50, 100));
			const branch = args.branch ? String(args.branch) : undefined;
			if (!filePath.trim()) {
				return { success: false, error: "path is required", error_code: "INVALID_ARGUMENT" };
			}
			const connections = await getContextGraphForPath(ctx, filePath, limit, branch);
			return { success: true, path: filePath, connections };
		}
		case "detect_chokepoints": {
			const limit = Math.max(1, Math.min(Number(args.limit) || 10, 50));
			const branch = args.branch ? String(args.branch) : undefined;
			const chokepoints = await detectChokepoints(ctx, limit, branch);
			return { success: true, chokepoints };
		}
		case "link_knowledge": {
			const sourceId = String(args.sourceId ?? args.source_id ?? "");
			const targetId = String(args.targetId ?? args.target_id ?? "");
			const relation = String(args.relation ?? "related");
			const weight = Number(args.weight) || 1.0;
			if (!sourceId || !targetId || !relation) {
				return { success: false, error: "sourceId, targetId, and relation are required", error_code: "INVALID_ARGUMENT" };
			}
			await ctx.graph.linkKnowledge({ sourceId, targetId, relation, weight });
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return { success: true, linked: true, sourceId, targetId, relation };
		}
		case "merge_knowledge": {
			const sourceId = String(args.sourceId ?? args.source_id ?? "");
			const targetId = String(args.targetId ?? args.target_id ?? "");
			if (!sourceId || !targetId) {
				return { success: false, error: "sourceId and targetId are required", error_code: "INVALID_ARGUMENT" };
			}
			await ctx.graph.mergeKnowledge({ sourceId, targetId });
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return { success: true, merged: true, sourceId, targetId };
		}
		case "get_node_centrality": {
			const kbId = String(args.id ?? args.kb_id ?? args.kbId ?? "");
			if (!kbId.trim()) {
				return { success: false, error: "id is required", error_code: "INVALID_ARGUMENT" };
			}
			const centrality = await ctx.graph.getNodeCentrality({ kbId });
			return { success: true, centrality };
		}
		case "extract_subgraph": {
			const rootId = String(args.id ?? args.rootId ?? args.kb_id ?? args.kbId ?? "");
			const maxDepth = Math.max(1, Math.min(Number(args.maxDepth ?? args.max_depth) || 2, 6));
			if (!rootId.trim()) {
				return { success: false, error: "id is required", error_code: "INVALID_ARGUMENT" };
			}
			const subgraph = await ctx.graph.extractSubgraph({ startId: rootId, maxDepth });
			return { success: true, subgraph };
		}
		case "get_global_hubs": {
			const limit = Math.max(1, Math.min(Number(args.limit) || 10, 50));
			const { hubs } = await ctx.query.getGlobalCentrality({ limit });
			const enriched = [];
			for (const hub of hubs) {
				try {
					const node = await ctx.graph.getKnowledge({ kbId: hub.kbId });
					enriched.push({
						...hub,
						content: (node.item.content || "").substring(0, 500),
					});
				} catch {
					enriched.push({ ...hub, content: "" });
				}
			}
			return { success: true, hubs: enriched };
		}
		case "refresh_knowledge": {
			const kbId = String(args.id ?? args.kb_id ?? args.kbId ?? "");
			if (!kbId.trim()) {
				return { success: false, error: "id is required", error_code: "INVALID_ARGUMENT" };
			}
			await ctx.graph.refreshKnowledge({ kbId });
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return { success: true, refreshed: true, kbId };
		}
		case "blame_path": {
			const filePath = String(args.path ?? "");
			const branch = args.branch ? String(args.branch) : undefined;
			if (!filePath.trim()) {
				return { success: false, error: "path is required", error_code: "INVALID_ARGUMENT" };
			}
			const blame = await blameFilePath(ctx, filePath, branch);
			return { success: true, path: filePath, blame };
		}
		case "get_agent_bundle": {
			const agentId = String(args.agentId ?? args.agent_id ?? args.task_id ?? args.taskId ?? "");
			if (!agentId.trim()) {
				return { success: false, error: "agentId is required", error_code: "INVALID_ARGUMENT" };
			}
			const { bundle } = await ctx.query.getAgentBundle({ agentId });
			return { success: true, agentId, bundle };
		}
		case "generate_changelog": {
			const baseRef = String(args.baseId ?? args.base_id ?? args.baseRef ?? "");
			const headRef = String(args.headId ?? args.head_id ?? args.headRef ?? "");
			if (!baseRef.trim() || !headRef.trim()) {
				return { success: false, error: "baseId and headId are required", error_code: "INVALID_ARGUMENT" };
			}
			const changelog = await generateRepoChangelog(ctx, baseRef, headRef);
			return { success: true, baseRef, headRef, changelog };
		}
		case "simulate_merge_forecast": {
			const sourceRef = String(args.sourceStreamId ?? args.source_stream_id ?? args.source ?? "");
			const targetRef = String(
				args.targetStreamId ?? args.target_stream_id ?? args.target ?? args.task_id ?? args.taskId ?? "",
			);
			if (!sourceRef.trim() || !targetRef.trim()) {
				return {
					success: false,
					error: "sourceStreamId and targetStreamId are required",
					error_code: "INVALID_ARGUMENT",
				};
			}
			const forecast = await simulateMergeForecast(ctx, sourceRef, targetRef);
			return { success: true, sourceRef, targetRef, forecast };
		}
		case "acquire_lock": {
			const resource = String(args.resource ?? "");
			if (!resource.trim()) {
				return { success: false, error: "resource is required", error_code: "INVALID_ARGUMENT" };
			}
			const { acquired } = await ctx.coordination.acquireLock({ resource });
			if (!acquired) {
				return {
					success: false,
					error: `Failed to acquire lock on '${resource}'`,
					error_code: "LOCK_UNAVAILABLE",
				};
			}
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return { success: true, acquired: true, resource };
		}
		case "release_lock": {
			const resource = String(args.resource ?? "");
			if (!resource.trim()) {
				return { success: false, error: "resource is required", error_code: "INVALID_ARGUMENT" };
			}
			await ctx.coordination.releaseLock({ resource });
			if (params.flush !== false) {
				await flushAgentContext();
			}
			return { success: true, released: true, resource };
		}
		case "spider_gate": {
			const scope = String(args.scope ?? "changed-files") === "all" ? "all" : "changed-files";
			const gate = await ctx.graph.spider.gate({ scope, includeTypes: false });
			const findings = (gate.report?.findings ?? []).slice(0, 20).map((f) => ({
				diagnosticId: f.diagnosticId,
				message: f.message,
				severity: f.severity,
				filePath: f.filePath,
			}));
			return {
				success: true,
				blocked: gate.blocked,
				exitCode: gate.exitCode,
				conclusion: gate.conclusion,
				findingCount: gate.report?.findings?.length ?? 0,
				reportId: gate.report?.reportId,
				findings,
			};
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
