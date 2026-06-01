/**
 * BroccoliQ pool module — re-exports the canonical BufferedDbPool singleton
 * used throughout broccolidb. Keeps @noorm/broccoliq import paths stable.
 */
export {
  BufferedDbPool,
  dbPool,
  type WriteOp,
  type Increment,
  type DbLayer,
} from '../BufferedDbPool.js';

export type { WhereCondition, IBufferedDbPool } from './types.js';
export { normalizeWhere, isIncrement, LAYER_PRIORITY } from './types.js';
