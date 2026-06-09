# Runtime invariants

Frozen invariants for deterministic agent execution against `dietcode-kernel`. Locked by `make test-docs-code-drift` (part of `make validate`). RPC reference: [kernel-rpc.md](kernel-rpc.md).

```bash
rg 'INVARIANT:|stale_content|beforeContentHash|sortOrder' src/ scripts/ docs/
make verify-agent-runtime
```

---

## State synchronization

| Surface | Invariant | Verify |
|---------|-----------|--------|
| File text read | Editor buffer preferred; disk fallback via `TextForSearchAtPath` | `readSource` on `file.stat` / `patch.validate` |
| Content identity | `StableHashForString` (16 hex, FNV-1a) | `contentHash`, `beforeContentHash` |
| Stale writes | `expectBeforeHash` on `patch.apply` rejects drift | `stale_content` error |
| Task-scoped writes | `coherenceTokenId` + `expectedWorkspaceRevision` when `taskId` set | `coherence_mismatch` error — [coherence-tokens.md](coherence-tokens.md) |
| Coherence reads | `file.read`, `file.readBatch`, `file.readRange`, `file.readAround`, `file.stat`, `workspace.status` with `taskId` | Issue anchors + token — [coherence-tokens.md](coherence-tokens.md) |
| Mutation proof | `mutationReceipt` on successful `patch.apply` | `validate_mutation_receipt()` |

Agents must treat `beforeContentHash` from `patch.validate` as the precondition for `patch.apply`.

```bash
python3 scripts/dietcode_agent_client.py --raw-response --json patch.validate --params-file patch.json
# apply with expectBeforeHash from validation.beforeContentHash
```

---

## Grep determinism

| Invariant | Value |
|-----------|-------|
| Match mode | `literal_substring` only |
| Traversal order | Sorted absolute paths before scan |
| Result order | `sortOrder: path_line_column` |
| Skip accounting | `filesSkippedOversize`, `filesSkippedExcluded`, `filesSkippedUnreadable`, `filesSkippedBinary` |
| Timing | `scanDurationMs` (server-measured) |

Two identical queries with identical workspace state must return identical `(path, line, column)` tuples.

```bash
make test-runtime-determinism
```

---

## Patch mutation safety

| Stage | Contract |
|-------|----------|
| `patch.validate` | Returns `beforeContentHash`, `patchFingerprint`, `readSource` |
| `patch.apply` | Checks `expectBeforeHash` **before** re-validation; emits `mutationReceipt` on success |
| Rollback | `restorePatchRecords` verifies `beforeHash` / `postHash` |

Error `stale_content` (4004): content changed between validate and apply. Recovery: re-run `patch.validate`.

---

## RPC envelope rules

- Exactly one terminal envelope per request (`id`, `ok`, `result` | `error`)
- Errors include `string_code`, `request_id`, `category`, `retryable`, `recovery_hint`
- Success payloads validated by frozen key sets in `scripts/agent_contracts.py`

---

## Verification ladder

```bash
make test-runtime-determinism
make test-grep-diff-tooling
make test-deterministic-retrieval
make verify-agent-runtime
```

---

## Partial success signals (pass 6)

Read and mutation success payloads may include:

| Key | Meaning |
|-----|---------|
| `complete` | `false` when truncated, paginated, or scan-limited |
| `partial` | `true` when warnings/skips/fallback reads occurred |
| `warnings` | Stable tokens (`results_truncated`, `requires_confirmation`, etc.) |
| `fallbackUsed` | Disk read fallback was used |
| `recoveryHint` | Next safe action token when incomplete |
| `nextRecommendedCommand` | RPC method to call next |

Errors include `nextRecommendedCommand` alongside `recovery_hint`.

Enriched surfaces: `patch.applyBatch` (success), `workspace.snapshot`, `diff.hunks`, `patch.hunks`.

```bash
make test-partial-success-closure
make test-agent-workflow-smoke
make test-cli-agent-failures
```

---

## Retrieval determinism (pass 5)

| Invariant | Value |
|-----------|-------|
| Semantic search | Quarantined — `search.semantic` → `semantic_disabled` (4008) |
| Ranked search | Quarantined — `analysis.searchRanked` → `ranked_search_disabled` (4008) |
| Literal search | `search.literal` / `search.text` → `literal_substring`, `rankingPolicy: none` |
| Token search | `search.tokens` → conjunctive literal match, `matchReason: all_tokens_literal` |
| Path search | `search.paths` / `search.files` → `deterministic_path_match`, no `score` |
| Symbol refs | `search.references` → `symbol_exact`, sorted `path_line_column` |
| Tool registry | `tool.registry` exposes `agentSafe`, `deterministic`, `deprecated`, `replacementMethod` |

Two identical retrieval queries with identical workspace state must return identical result order and accounting. No `score`, `relevance`, or hidden ranking fields.

```bash
make test-deterministic-retrieval
python3 scripts/dietcode_agent_client.py tool.capabilities --compact
```

---

## Workspace revision (pass 3)

| RPC | Purpose |
|-----|---------|
| `workspace.revision` | Monotonic `revisionId`, `changedFiles`, `lastMutationReceipt`, `externalChangeDetected` |
| `workspace.snapshot` | Point-in-time `fileHashes`; compare with `sinceRevision` for drift |
| `operation.status` | Lookup completed mutation by `idempotencyKey` (safe retry after timeout) |

Mutating commands return `revisionBefore` / `revisionAfter`. Batch apply returns `batchMutationReceipt` with per-file receipts and `rollbackProof`.

```bash
make test-transaction-kernel
```

---

## Symlink policy (frozen)

| Policy | Value |
|--------|-------|
| Traversal | `skip_never_follow` — symlinks are counted in `filesSkippedSymlink`, never followed |
| Patch targets | `PathIsInsideWorkspace` rejects symlinks escaping workspace root |
| Accounting | `symlinkPolicy: skip_never_follow` on all search surfaces |

---

## Search parity

`search.text` and `search.todo` share the same accounting model as `workspace.grep` (`SEARCH_ACCOUNTING_KEYS` in `agent_contracts.py`).

`search.files` uses **deterministic path matching only** — no scores, no fuzzy ranking:

| Field | Value |
|-------|-------|
| `searchMode` | `deterministic_path_match` |
| `sortOrder` | `match_reason_path` (basename_exact → path_substring, then lexical path) |
| `matchReason` | `basename_exact` \| `path_substring` per result row |

---

## Symlink policy examples

| Path type | Grep/search | patch.apply | file.stat |
|-----------|-------------|-------------|-----------|
| Regular file | scanned | allowed | `isSymlink: false` |
| Symlink inside workspace | `filesSkippedSymlink++` | `symlink_target` error | `isSymlink: true` |
| Symlink escaping workspace | skipped in traversal | rejected | `pathEscapesWorkspace: true` |
| Broken symlink | skipped | rejected | `isSymlink: true`, empty contentHash ok |

```bash
make test-harness-realism
```

---

## Workspace snapshot modes

| `snapshotMode` | Scope |
|----------------|-------|
| `mutated_only` | Last changed + tracked + explicit paths (default) |
| `tracked_files` | All paths in mutation hash cache |
| `explicit_paths` | Only `paths` param |

Response includes `complete`, `truncated`, `filesHashed`, `filesSkipped`, `hashAlgorithm: fnv1a_16hex`.

---

## Intentionally not added

- Workspace-wide CRDT sync
- Semantic merge or fuzzy patch anchoring
- Probabilistic conflict resolution
- Hidden buffer coalescing

State divergence must be **visible** via hashes, receipts, and stable error codes.

---

## Related docs

- [agent-tooling.md](agent-tooling.md)
- [error-codes.md](error-codes.md)
- [kernel-rpc.md](kernel-rpc.md)
- [checkpoint-model.md](checkpoint-model.md)
