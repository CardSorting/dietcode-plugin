/**
 * DietCode dashboard snapshot — JSON to stdout for hermes_cli/dietcode_broccolidb.py.
 *
 * Invoked via: npx tsx infrastructure/dashboard/snapshot.ts (cwd = broccolidb root)
 * Prefer Hermes RPC (`dashboard_snapshot`) when the persistent worker is available.
 */
import { setDbPath } from "../db/Config.js";
import { buildDashboardSnapshot } from "./snapshot_core.js";

const dbEnv = process.env.HERMES_BROCCOLIDB_DB;
if (dbEnv) setDbPath(dbEnv);

async function main() {
	const snapshot = await buildDashboardSnapshot();
	console.log(JSON.stringify(snapshot));
}

main().catch((e: unknown) => {
	const message = e instanceof Error ? e.message : String(e);
	console.log(JSON.stringify({ success: false, error: message }));
	process.exit(1);
});
