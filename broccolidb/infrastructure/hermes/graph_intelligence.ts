/**
 * Repository-backed graph intelligence — co-change context and chokepoints.
 */
import type { AgentContext } from "../../core/agent-context.js";
import type { Workspace } from "../../core/workspace.js";
import { Repository } from "../../core/repository.js";

export type ContextConnection = { path: string; weight: number };

export type Chokepoint = { path: string; score: number; churn: number };

export type BlameInfo = {
	lastAuthor: string;
	lastNodeId: string;
	lastMessage: string;
	lastTimestamp: number;
};

function workspaceFromAgent(ctx: AgentContext): Workspace {
	return (ctx as unknown as { _serviceContext: { workspace: Workspace } })._serviceContext.workspace;
}

export async function resolveRepository(ws: Workspace): Promise<Repository> {
	try {
		return await ws.getRepo(ws.workspaceId);
	} catch {
		return new Repository(ws.getDb(), ws.workspacePath);
	}
}

export async function resolveDefaultBranch(repo: Repository): Promise<string> {
	try {
		const repoPath = repo.getBasePath();
		const doc = await repo.getDb().selectOne("repositories", [{ column: "repoPath", value: repoPath }]);
		if (doc?.defaultBranch) return String(doc.defaultBranch);
	} catch {
		// non-fatal
	}
	return "main";
}

export async function getContextGraphForPath(
	ctx: AgentContext,
	filePath: string,
	limit: number,
	branch?: string,
): Promise<ContextConnection[]> {
	const ws = workspaceFromAgent(ctx);
	const repo = await resolveRepository(ws);
	const ref = branch?.trim() || (await resolveDefaultBranch(repo));
	return repo.getContextGraph(ref, filePath, limit);
}

export async function detectChokepoints(
	ctx: AgentContext,
	limit: number,
	branch?: string,
): Promise<Chokepoint[]> {
	const ws = workspaceFromAgent(ctx);
	const repo = await resolveRepository(ws);
	const ref = branch?.trim() || (await resolveDefaultBranch(repo));
	const commits = await repo.history(ref, 300);
	const stats: Record<string, { churn: number }> = {};

	for (let i = 0; i < commits.length - 1; i++) {
		const curr = commits[i]!;
		const prev = commits[i + 1]!;
		const currTree = (curr.data?.tree || curr.tree || {}) as Record<string, string>;
		const prevTree = (prev.data?.tree || prev.tree || {}) as Record<string, string>;

		for (const p of Object.keys(currTree)) {
			if (currTree[p] !== prevTree[p]) {
				if (!stats[p]) stats[p] = { churn: 0 };
				stats[p]!.churn++;
			}
		}
	}

	return Object.entries(stats)
		.map(([path, data]) => ({
			path,
			churn: data.churn,
			score: data.churn,
		}))
		.sort((a, b) => b.score - a.score)
		.slice(0, limit);
}

function normalizeRepoPath(filePath: string): string {
	return filePath.replace(/^\/+/, "").replace(/\/\/+/g, "/");
}

export async function blameFilePath(
	ctx: AgentContext,
	filePath: string,
	branch?: string,
): Promise<BlameInfo | null> {
	const ws = workspaceFromAgent(ctx);
	const repo = await resolveRepository(ws);
	const ref = branch?.trim() || (await resolveDefaultBranch(repo));
	const commits = await repo.history(ref, 300);
	const normalizedPath = normalizeRepoPath(filePath);

	for (let i = 0; i < commits.length - 1; i++) {
		const curr = commits[i]!;
		const prev = commits[i + 1]!;
		const currTree = (curr.data?.tree || curr.tree || {}) as Record<string, string>;
		const prevTree = (prev.data?.tree || prev.tree || {}) as Record<string, string>;

		if (currTree[normalizedPath] && currTree[normalizedPath] !== prevTree[normalizedPath]) {
			return {
				lastAuthor: curr.author || "agent",
				lastNodeId: curr.id,
				lastMessage: (curr.message || "").substring(0, 100),
				lastTimestamp: curr.timestamp,
			};
		}
	}
	return null;
}

export async function generateRepoChangelog(
	ctx: AgentContext,
	baseRef: string,
	headRef: string,
): Promise<string> {
	const ws = workspaceFromAgent(ctx);
	const repo = await resolveRepository(ws);
	return repo.generateChangelog(baseRef, headRef);
}

export type MergeForecast = {
	isHighRisk: boolean;
	conflicts: string[];
	semanticOverlaps: { path: string; reason: string }[];
	lcaId: string | null;
	hasConflicts: boolean;
};

export async function simulateMergeForecast(
	ctx: AgentContext,
	sourceRef: string,
	targetRef: string,
): Promise<MergeForecast> {
	const ws = workspaceFromAgent(ctx);
	const repo = await resolveRepository(ws);
	const mergeSim = await repo.simulateMerge(sourceRef, targetRef);
	const semanticOverlaps: { path: string; reason: string }[] = [];

	const targetHistory = await repo.history(targetRef, 50);
	const targetChangedPaths = new Set<string>();
	if (targetHistory.length > 1) {
		const targetHead = targetHistory[0]!;
		const targetBase = targetHistory[targetHistory.length - 1]!;
		const headTree = (targetHead.data?.tree || targetHead.tree || {}) as Record<string, string>;
		const baseTree = (targetBase.data?.tree || targetBase.tree || {}) as Record<string, string>;
		for (const path of Object.keys(headTree)) {
			if (headTree[path] !== baseTree[path]) {
				targetChangedPaths.add(path);
			}
		}
	}

	for (const path of mergeSim.affectedPaths) {
		if (targetChangedPaths.has(path)) {
			semanticOverlaps.push({
				path,
				reason: `Direct overlap: both streams modified '${path}'`,
			});
		}
	}

	const branch = await resolveDefaultBranch(repo);
	for (const path of mergeSim.affectedPaths.slice(0, 10)) {
		let connections: ContextConnection[] = [];
		try {
			connections = await repo.getContextGraph(branch, path, 20);
		} catch {
			connections = [];
		}
		for (const conn of connections) {
			if (
				targetChangedPaths.has(conn.path) &&
				!semanticOverlaps.some((overlap) => overlap.path === conn.path)
			) {
				semanticOverlaps.push({
					path: conn.path,
					reason: `Co-change overlap with source change '${path}'`,
				});
			}
		}
	}

	return {
		isHighRisk: semanticOverlaps.length > 0 || mergeSim.hasConflicts,
		conflicts: mergeSim.affectedPaths,
		semanticOverlaps,
		lcaId: mergeSim.lcaId,
		hasConflicts: mergeSim.hasConflicts,
	};
}
