/**
 * Persistent AgentContext for the Hermes RPC worker — amortizes Connection/Workspace
 * bootstrap across graph tool calls (avoids per-call tsx + AgentContext cold start).
 */
import { AgentContext } from "../../core/agent-context.js";
import { Connection } from "../../core/connection.js";
import { Workspace } from "../../core/workspace.js";
import { dbPool } from "../db/BufferedDbPool.js";

let _contextPromise: Promise<AgentContext> | null = null;

export async function getAgentContext(): Promise<AgentContext> {
	if (!_contextPromise) {
		_contextPromise = (async () => {
			const conn = new Connection();
			const pool = conn.getPool();
			const userId = "local-user";
			const workspaceId = "local-workspace";
			const workspace = new Workspace(pool, userId, workspaceId);
			// workspace.init() uses public pool APIs (push/selectOne) — same as cli/index.ts
			await workspace.init();
			return new AgentContext(workspace, pool, userId);
		})();
	}
	return _contextPromise;
}

export async function flushAgentContext(): Promise<void> {
	const ctx = await getAgentContext();
	await ctx.flush();
}

export async function flushDbPool(): Promise<void> {
	await dbPool.flush();
}

export function resetAgentSession(): void {
	_contextPromise = null;
}
