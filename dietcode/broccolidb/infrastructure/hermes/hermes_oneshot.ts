/**
 * Hermes one-shot RPC dispatch — cold path without persistent worker.
 *
 * Usage: tsx infrastructure/hermes/hermes_oneshot.ts <method> '<params-json>'
 */
import { setDbPath } from "../db/Config.js";
import { dispatchRpc } from "./rpc_handlers.js";

// IMPORTANT: stdout is reserved for the final JSON result.
// Redirect incidental logs to stderr so mixed output doesn't break callers.
console.log = (...args: unknown[]) => console.warn(...args);
console.info = (...args: unknown[]) => console.warn(...args);
console.debug = (...args: unknown[]) => console.warn(...args);

const dbEnv = process.env.HERMES_BROCCOLIDB_DB;
if (dbEnv) setDbPath(dbEnv);

const method = (process.argv[2] || "ping").trim();
let params: Record<string, unknown> = {};
if (process.argv[3]) {
	try {
		params = JSON.parse(process.argv[3]) as Record<string, unknown>;
	} catch {
		process.stdout.write(
			`${JSON.stringify({
				success: false,
				error: "invalid params JSON",
				error_code: "PARSE_ERROR",
			})}\n`,
		);
		process.exit(1);
	}
}

try {
	const result = await dispatchRpc(method, params);
	process.stdout.write(`${JSON.stringify(result)}\n`);
	process.exit(0);
} catch (e) {
	const message = e instanceof Error ? e.message : String(e);
	process.stdout.write(
		`${JSON.stringify({ success: false, error: message, error_code: "ONESHOT_ERROR" })}\n`,
	);
	process.exit(1);
}
