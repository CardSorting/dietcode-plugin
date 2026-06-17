/**
 * Broccolidb pool module — re-exports the canonical BufferedDbPool singleton
 * used throughout broccolidb.
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
