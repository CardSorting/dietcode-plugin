/**
 * Bounded queue metrics — SQL GROUP BY (no full-table row scans).
 */
import { sql, type Kysely } from "kysely";
import type { Schema } from "../db/DatabaseSchema.js";

export interface QueueStatusAggregate {
	byStatus: Record<string, number>;
	total: number;
}

export async function aggregateQueueByStatus(
	db: Kysely<Schema>,
): Promise<QueueStatusAggregate> {
	const rows = await db
		.selectFrom("queue_jobs")
		.select(["status", sql<number>`count(*)`.as("count")])
		.groupBy("status")
		.execute();

	const byStatus: Record<string, number> = {};
	let total = 0;
	for (const row of rows) {
		const n = Number(row.count) || 0;
		byStatus[row.status] = n;
		total += n;
	}
	return { byStatus, total };
}
