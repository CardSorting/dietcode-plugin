/**
 * Canonical BroccoliDB/BroccoliQ RPC handlers — single implementation for
 * hermes_rpc.ts (persistent worker) and thin CLI wrappers (hive_*.ts).
 */
import * as crypto from "node:crypto";
import { sql } from "kysely";
import { buildDashboardSnapshot } from "../dashboard/snapshot_core.js";
import { getActiveShards, getDb } from "../db/Config.js";
import { IntegrityWorker } from "../db/IntegrityWorker.js";
import { runAgentInvoke } from "./agent_invoke.js";
import { flushDbPool } from "./agent_session.js";
import { aggregateQueueByStatus } from "./queue_metrics.js";

export const RPC_VERSION = 4;

export const RPC_METHODS = [
	"ping",
	"rpc_health",
	"dashboard_snapshot",
	"queue_status",
	"shard_status",
	"hive_integrity",
	"proposal_action",
	"hive_sync",
	"hive_drift",
	"hive_board_intel",
	"agent_invoke",
	"pool_flush",
	"batch",
] as const;

export type RpcMethod = (typeof RPC_METHODS)[number];

const TASK_ID_RE = /^t_[a-z0-9]{6,32}$/i;

export interface KanbanHiveSyncPayload {
	task_id: string;
	title: string;
	body?: string;
	assignee?: string;
	status: string;
	priority?: number;
	result?: string | null;
	created_at?: number;
	started_at?: number | null;
	completed_at?: number | null;
	board?: string;
	event: string;
	shard_id?: string;
	signal_events?: string[];
	run_id?: string | null;
	tenant?: string | null;
	/** @deprecated use joyzoning_scope */
	habitat_task?: string;
	joyzoning_scope?: string;
	convergence_state?: string;
}

function resolveJoyzoningScope(payload: KanbanHiveSyncPayload): string | null {
	return (
		payload.joyzoning_scope?.trim() ||
		payload.habitat_task?.trim() ||
		null
	);
}

function joyzoningForensicJson(payload: KanbanHiveSyncPayload): string | null {
	const scope = resolveJoyzoningScope(payload);
	if (!scope && !payload.convergence_state) {
		return null;
	}
	return JSON.stringify({
		joyzoning_scope: scope,
		convergence_state: payload.convergence_state ?? null,
	});
}

export interface HiveDriftPayload {
	shard_id?: string;
	task_ids: string[];
}

export interface HiveBoardIntelPayload {
	shard_id?: string;
	queue_limit?: number;
	hive_limit?: number;
}

function normalizeTaskId(taskId: string): string {
	const tid = taskId.trim().toLowerCase();
	if (!TASK_ID_RE.test(tid)) {
		throw new Error(`invalid task_id format: ${taskId}`);
	}
	return tid;
}

function clampLimit(value: unknown, fallback: number, max: number): number {
	const n = typeof value === "number" ? value : fallback;
	return Math.max(1, Math.min(Math.floor(n), max));
}

export async function runPing(): Promise<Record<string, unknown>> {
	return { success: true, pong: true, rpc_version: RPC_VERSION };
}

export async function runRpcHealth(): Promise<Record<string, unknown>> {
	const shards = getActiveShards().length ? getActiveShards() : ["main"];
	const shardId = shards.includes("kanban") ? "kanban" : shards[0]!;
	const db = await getDb(shardId);
	await db.selectFrom("queue_settings" as never).selectAll().limit(1).execute();
	return {
		success: true,
		rpc_version: RPC_VERSION,
		shard_id: shardId,
		shards,
		healthy: true,
	};
}

export async function runQueueStatus(): Promise<Record<string, unknown>> {
	const shards = getActiveShards().length ? getActiveShards() : ["main"];
	const byStatus: Record<string, number> = {};
	let total = 0;
	for (const shardId of shards) {
		const db = await getDb(shardId);
		const agg = await aggregateQueueByStatus(db);
		for (const [status, count] of Object.entries(agg.byStatus)) {
			byStatus[status] = (byStatus[status] ?? 0) + count;
		}
		total += agg.total;
	}
	return { success: true, total, byStatus, shards };
}

export async function runShardStatus(): Promise<Record<string, unknown>> {
	const shards = getActiveShards();
	const listed = shards.length ? shards : ["main"];
	const detail: Array<Record<string, unknown>> = [];
	for (const shardId of listed) {
		try {
			const db = await getDb(shardId);
			const probe = await db
				.selectFrom("queue_settings" as never)
				.selectAll()
				.limit(1)
				.execute();
			detail.push({ shardId, healthy: true, probeRows: probe.length });
		} catch (e) {
			detail.push({
				shardId,
				healthy: false,
				error: e instanceof Error ? e.message : String(e),
			});
		}
	}
	return { success: true, shardCount: detail.length, shards: detail };
}

export async function runHiveIntegrity(): Promise<Record<string, unknown>> {
	const worker = new IntegrityWorker(600_000);
	await worker.runAudit();
	const shards = getActiveShards();
	return {
		success: true,
		message: "Integrity audit complete",
		shards: shards.length ? shards : ["main"],
	};
}

export async function runProposalAction(
	params: Record<string, unknown>,
): Promise<Record<string, unknown>> {
	const proposalId = String(params.proposalId ?? params.proposal_id ?? "").trim();
	const action = String(params.action ?? "").toLowerCase();
	if (!proposalId || !["approve", "deny"].includes(action)) {
		return {
			success: false,
			error: "Missing proposalId or invalid action (approve|deny)",
		};
	}
	const shards = getActiveShards().length ? getActiveShards() : ["main"];
	const shardId = shards.includes("kanban") ? "kanban" : shards[0]!;
	const db = await getDb(shardId);
	const nextStatus = action === "approve" ? "approved" : "rejected";

	const row = await db
		.selectFrom("hive_healing_proposals")
		.selectAll()
		.where("id", "=", proposalId)
		.executeTakeFirst();

	if (!row) {
		return { success: false, error: "Proposal not found" };
	}

	await db
		.updateTable("hive_healing_proposals")
		.set({
			status: nextStatus,
			applied_at: action === "approve" ? Date.now() : row.applied_at,
		})
		.where("id", "=", proposalId)
		.execute();

	return { success: true, id: proposalId, status: nextStatus };
}

export async function runHiveSync(
	payload: KanbanHiveSyncPayload,
): Promise<Record<string, unknown>> {
	const taskId = normalizeTaskId(payload.task_id);
	const now = Date.now();
	const hiveId = `hive_${taskId.replace(/[^a-z0-9_\-]/g, "_")}`;
	const shardId = payload.shard_id || "kanban";

	const db = await getDb(shardId);
	const existing = await db
		.selectFrom("hive_tasks")
		.selectAll()
		.where("task_id", "=", taskId)
		.executeTakeFirst();

	const forensic = joyzoningForensicJson(payload);

	const merged = {
		id: existing?.id ?? hiveId,
		task_id: taskId,
		title: payload.title || existing?.title || taskId,
		objective: payload.title || existing?.objective || taskId,
		description: payload.body ?? existing?.description ?? "",
		initial_context: forensic ?? existing?.initial_context ?? null,
		status: payload.status || existing?.status || "unknown",
		priority: payload.priority ?? existing?.priority ?? 0,
		user_agent: payload.assignee || existing?.user_agent || "hermes",
		agent_id: payload.assignee || existing?.agent_id || null,
		result:
			payload.result !== undefined && payload.result !== null
				? payload.result
				: (existing?.result ?? null),
		created_at: payload.created_at ?? existing?.created_at ?? now,
		updated_at: now,
		started_at:
			payload.event === "start"
				? (payload.started_at ?? existing?.started_at ?? now)
				: (payload.started_at ?? existing?.started_at ?? null),
		completed_at:
			payload.event === "complete"
				? (payload.completed_at ?? existing?.completed_at ?? now)
				: (payload.completed_at ?? existing?.completed_at ?? null),
		vitals_heartbeat:
			payload.event === "heartbeat"
				? String(now)
				: (existing?.vitals_heartbeat ?? null),
	};

	await db
		.insertInto("hive_tasks")
		.values(merged)
		.onConflict((oc) =>
			oc.column("task_id").doUpdateSet({
				title: merged.title,
				objective: merged.objective,
				description: merged.description,
				initial_context: merged.initial_context,
				status: merged.status,
				priority: merged.priority,
				user_agent: merged.user_agent,
				agent_id: merged.agent_id,
				result: merged.result,
				updated_at: merged.updated_at,
				started_at: merged.started_at,
				completed_at: merged.completed_at,
				vitals_heartbeat: merged.vitals_heartbeat,
			}),
		)
		.execute();

	const signalEvents = new Set(payload.signal_events ?? ["create", "complete", "block", "start"]);
	if (signalEvents.has(payload.event)) {
		await db
			.insertInto("queue_jobs")
			.values({
				id: `kanban-${taskId}-${payload.event}-${now}-${crypto.randomUUID().slice(0, 8)}`,
				payload: JSON.stringify({
					type: "kanban_orchestration",
					task_id: taskId,
					event: payload.event,
					status: payload.status,
					board: payload.board ?? "default",
					assignee: payload.assignee,
					run_id: payload.run_id ?? null,
					tenant: payload.tenant ?? null,
					joyzoning_scope: resolveJoyzoningScope(payload),
					convergence_state: payload.convergence_state ?? null,
				}),
				status: "pending",
				priority: payload.event === "complete" ? 2 : 1,
				attempts: 0,
				maxAttempts: 5,
				runAt: now,
				error: null,
				createdAt: now,
				updatedAt: now,
			})
			.execute();
	}

	await db
		.insertInto("hive_audit")
		.values({
			id: crypto.randomUUID(),
			session_id: payload.run_id ?? null,
			type: `kanban_${payload.event}`,
			message: `Kanban hive sync: ${taskId} → ${merged.status}`,
			data: JSON.stringify({
				board: payload.board,
				event: payload.event,
				assignee: payload.assignee,
				tenant: payload.tenant,
				joyzoning_scope: resolveJoyzoningScope(payload),
				convergence_state: payload.convergence_state ?? null,
			}),
			timestamp: now,
		})
		.execute();

	// Flush BufferedDbPool write-behind queue (main shard) after hive writes
	try {
		await flushDbPool();
	} catch {
		/* non-fatal — direct Kysely path already committed kanban shard rows */
	}

	return {
		success: true,
		hiveId: merged.id,
		task_id: taskId,
		event: payload.event,
		shard_id: shardId,
		merged_status: merged.status,
	};
}

export async function runHiveDrift(
	payload: HiveDriftPayload,
): Promise<Record<string, unknown>> {
	const shardId = payload.shard_id || "kanban";
	const taskIds = [
		...new Set(
			(payload.task_ids ?? [])
				.filter((id): id is string => typeof id === "string")
				.map((id) => id.trim().toLowerCase())
				.filter((id) => TASK_ID_RE.test(id)),
		),
	];

	if (taskIds.length === 0) {
		return { success: true, rows: [], shard_id: shardId };
	}

	const db = await getDb(shardId);
	const rows = await db
		.selectFrom("hive_tasks")
		.select(["task_id", "status"])
		.where("task_id", "in", taskIds)
		.execute();

	return { success: true, rows, shard_id: shardId };
}

export async function runHiveBoardIntel(
	payload: HiveBoardIntelPayload,
): Promise<Record<string, unknown>> {
	const shardId = payload.shard_id || "kanban";
	const hiveLimit = clampLimit(payload.hive_limit, 500, 2000);

	const db = await getDb(shardId);

	const queueAgg = await aggregateQueueByStatus(db);

	const hiveRows = await db
		.selectFrom("hive_tasks")
		.select(["status", sql<number>`count(*)`.as("count")])
		.groupBy("status")
		.execute();

	const hiveByStatus: Record<string, number> = {};
	let hiveTotal = 0;
	for (const row of hiveRows) {
		const n = Number(row.count) || 0;
		hiveByStatus[row.status] = n;
		hiveTotal += n;
	}

	return {
		success: true,
		shard_id: shardId,
		queue: {
			total: queueAgg.total,
			byStatus: queueAgg.byStatus,
		},
		hive: {
			total: hiveTotal,
			byStatus: hiveByStatus,
			limit: hiveLimit,
		},
	};
}

type HandlerFn = (params: Record<string, unknown>) => Promise<Record<string, unknown>>;

export async function runPoolFlush(): Promise<Record<string, unknown>> {
	await flushDbPool();
	return { success: true, message: "BufferedDbPool flush complete" };
}

export const rpcHandlers: Record<string, HandlerFn> = {
	ping: async () => runPing(),
	rpc_health: async () => runRpcHealth(),
	dashboard_snapshot: async () => buildDashboardSnapshot(),
	queue_status: async () => runQueueStatus(),
	shard_status: async () => runShardStatus(),
	hive_integrity: async () => runHiveIntegrity(),
	proposal_action: async (p) => runProposalAction(p),
	hive_sync: async (p) => runHiveSync(p as unknown as KanbanHiveSyncPayload),
	hive_drift: async (p) => runHiveDrift(p as unknown as HiveDriftPayload),
	hive_board_intel: async (p) => runHiveBoardIntel(p as unknown as HiveBoardIntelPayload),
	agent_invoke: async (p) => runAgentInvoke(p),
	pool_flush: async () => runPoolFlush(),
};

export async function dispatchRpc(
	method: string,
	params: Record<string, unknown>,
): Promise<Record<string, unknown>> {
	if (method === "batch") {
		const calls = params.calls;
		if (!Array.isArray(calls)) {
			return { success: false, error: "batch requires calls array" };
		}
		const results: Array<Record<string, unknown>> = [];
		for (const entry of calls) {
			const subMethod = String((entry as { method?: string }).method ?? "");
			const subParams =
				(entry as { params?: Record<string, unknown> }).params ?? {};
			try {
				const out = await dispatchRpc(subMethod, subParams);
				results.push({ ok: true, method: subMethod, result: out });
			} catch (e) {
				results.push({
					ok: false,
					method: subMethod,
					error: e instanceof Error ? e.message : String(e),
				});
			}
		}
		return { success: true, results };
	}

	const handler = rpcHandlers[method];
	if (!handler) {
		return { success: false, error: `unknown method: ${method}`, error_code: "UNKNOWN_METHOD" };
	}
	return handler(params);
}
