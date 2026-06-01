/**
 * Dashboard snapshot builder — shared by CLI snapshot.ts and Hermes RPC.
 */
import * as fs from "node:fs";
import { getActiveShards, getDb } from "../db/Config.js";
import { aggregateQueueByStatus } from "../hermes/queue_metrics.js";

async function safeSelect<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
	try {
		return await fn();
	} catch {
		return fallback;
	}
}

export async function buildDashboardSnapshot(): Promise<Record<string, unknown>> {
	const shards = getActiveShards().length ? getActiveShards() : ["main"];
	const shardId = shards.includes("kanban") ? "kanban" : shards[0]!;
	const db = await getDb(shardId);

	const knowledge = await safeSelect(
		() => db.selectFrom("knowledge").selectAll().execute(),
		[] as Array<{ edges?: string | null; hubScore?: number | null }>,
	);
	const edgeCount = knowledge.reduce(
		(acc, n) => acc + JSON.parse(n.edges || "[]").length,
		0,
	);
	const hubCount = knowledge.filter((n) => (n.hubScore || 0) > 5).length;

	let dbSizeMb = 0;
	const dbPath = process.env.HERMES_BROCCOLIDB_DB;
	if (dbPath && fs.existsSync(dbPath)) {
		dbSizeMb = Number((fs.statSync(dbPath).size / (1024 * 1024)).toFixed(2));
	}

	const sessions = await safeSelect(
		() =>
			db
				.selectFrom("hive_agent_sessions")
				.selectAll()
				.orderBy("start_time", "desc")
				.limit(20)
				.execute(),
		[],
	);

	const proposals = await safeSelect(
		() =>
			db
				.selectFrom("hive_healing_proposals")
				.selectAll()
				.orderBy("created_at", "desc")
				.limit(15)
				.execute(),
		[],
	);

	const audit = await safeSelect(
		() =>
			db
				.selectFrom("hive_audit")
				.selectAll()
				.orderBy("timestamp", "desc")
				.limit(40)
				.execute(),
		[],
	);

	const tasks = await safeSelect(
		() =>
			db
				.selectFrom("hive_tasks")
				.selectAll()
				.orderBy("updated_at", "desc")
				.limit(15)
				.execute(),
		[],
	);

	const queueAgg = await safeSelect(
		() => aggregateQueueByStatus(db),
		{ byStatus: {} as Record<string, number>, total: 0 },
	);
	const byStatus = queueAgg.byStatus;
	const queueTotal = queueAgg.total;

	const pendingProposal = proposals.find(
		(p) => (p.status || "").toLowerCase() === "pending",
	);

	return {
		success: true,
		shard_id: shardId,
		graph: {
			nodes: knowledge.length,
			edges: edgeCount,
			hub_count: hubCount,
			db_size_mb: dbSizeMb,
		},
		sessions,
		proposals,
		pending_proposal_id: pendingProposal?.id ?? null,
		audit,
		tasks,
		queue: { total: queueTotal, by_status: byStatus },
	};
}
