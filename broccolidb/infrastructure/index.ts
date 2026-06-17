/**
 * BroccoliDB infrastructure — queue and database processing.
 *
 * Re-exports the main public API for broccolidb consumers.
 */

// Core database and pool functionality
export { setDbPath, getDb, getRawDb } from "./db/Config.js";
export { dbPool, BufferedDbPool } from "./db/pool/index.js";
export { IntegrityWorker } from "./db/IntegrityWorker.js";

// Signaling and Queue functionality
export { Signaling } from "./queue/Signaling.js";
export { SqliteQueue } from "./queue/SqliteQueue.js";
export type { Schema } from "./db/DatabaseSchema.js";
