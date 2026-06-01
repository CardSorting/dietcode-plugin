/**
 * Kanban → BroccoliQ hive sync (CLI wrapper — logic in hermes/rpc_handlers.ts).
 */
import { setDbPath } from "../db/Config.js";
import {
	type KanbanHiveSyncPayload,
	runHiveSync,
} from "../hermes/rpc_handlers.js";

async function main() {
	const dbPath = process.env.HERMES_BROCCOLIDB_DB;
	if (dbPath) setDbPath(dbPath);

	const raw = process.env.KANBAN_HIVE_SYNC_PAYLOAD;
	if (!raw) {
		throw new Error("KANBAN_HIVE_SYNC_PAYLOAD missing");
	}
	const payload = JSON.parse(raw) as KanbanHiveSyncPayload;
	const result = await runHiveSync(payload);
	console.log(JSON.stringify(result));
}

main().catch((err) => {
	console.log(
		JSON.stringify({
			success: false,
			error: err instanceof Error ? err.message : String(err),
		}),
	);
	process.exitCode = 1;
});
