#!/usr/bin/env python3
# pass-viii-native
# broccoliq-memory-test
# pass-viii-native
# broccoliq-memory-test
# pass-viii-native
# broccoliq-memory-test
# broccoliq-memory-test
# broccoliq-memory-test
# pass-viii-native
# broccoliq-memory-test
# broccoliq-memory-test
# broccoliq-memory-test
# broccoliq-memory-test
"""CONTRACT: Frozen runtime contract constants — grep with `rg 'CONTRACT:' scripts/agent_contracts.py`."""

from __future__ import annotations

from typing import Any

# CONTRACT: NDJSON harness summary line schema (type=summary).
SUMMARY_SCHEMA_KEYS = frozenset({"type", "suite", "ok", "checks", "passed", "failed", "failedNames"})

# CONTRACT: NDJSON per-check line schema (type=check).
CHECK_LINE_SCHEMA_KEYS = frozenset({"type", "name", "ok"})

# CONTRACT: RPC success envelope required keys.
RPC_SUCCESS_ENVELOPE_KEYS = frozenset({"id", "ok", "result"})

# CONTRACT: RPC error envelope required keys under error object.
RPC_ERROR_ENVELOPE_KEYS = frozenset({"code", "string_code", "message"})

# CONTRACT: Optional stable diagnostic keys on server error envelopes (grep: rg 'recovery_hint' src/ scripts/).
RPC_ERROR_DIAGNOSTIC_OPTIONAL_KEYS = frozenset({
    "request_id",
    "category",
    "retryable",
    "phase",
    "queue",
    "recovery_hint",
})

# CONTRACT: NDJSON runtime diagnostic line schema (server: ~/.dietcode/agent-runtime.ndjson).
RUNTIME_DIAGNOSTIC_LINE_KEYS = frozenset({
    "type",
    "timestamp",
    "request_id",
    "method",
    "phase",
    "ok",
})

RUNTIME_DIAGNOSTIC_OPTIONAL_KEYS = frozenset({"string_code", "queue", "duration_ms"})

# CONTRACT: Diagnostic snapshot top-level keys (--diagnose).
DIAGNOSTIC_SNAPSHOT_KEYS = frozenset({
    "type",
    "ok",
    "socketActive",
    "rpcReady",
    "socket",
    "token",
    "app",
    "makefileTargets",
    "docs",
    "recentRuntimeLogs",
    "runtimeLimits",
    "socketAudit",
    "contractVersions",
    "contractInventoryVersion",
})

# CONTRACT: Stable golden failure string_code expectations (see scripts/fixtures/rpc/expected_error_codes.json).
GOLDEN_ERROR_CODES = {
    "method_not_found": -32601,
    "invalid_params": -32602,
    "invalid_request": -32600,
    "response_too_large": 413,
    "response_serialization_failed": -32603,
}

# CONTRACT: workspace.grep top-level result keys (literal substring mode).
GREP_RESPONSE_KEYS = frozenset({
    "matches",
    "query",
    "mode",
    "caseSensitive",
    "maxResults",
    "resultOffset",
    "nextResultOffset",
    "hasMore",
    "truncated",
    "scanLimitReached",
    "scannedFiles",
    "filesRead",
    "filesSkippedUnreadable",
    "filesSkippedBinary",
    "filesReadFromDisk",
    "filesReadFromEditor",
    "filesSkippedOversize",
    "filesSkippedExcluded",
    "filesSkippedSymlink",
    "symlinkPolicy",
    "sortOrder",
    "scanDurationMs",
})

# CONTRACT: Shared deterministic search accounting keys (grep/text/todo parity).
SEARCH_ACCOUNTING_KEYS = frozenset({
    "scannedFiles",
    "filesRead",
    "filesSkippedUnreadable",
    "filesSkippedBinary",
    "filesReadFromDisk",
    "filesReadFromEditor",
    "filesSkippedOversize",
    "filesSkippedExcluded",
    "filesSkippedSymlink",
    "symlinkPolicy",
    "sortOrder",
    "scanDurationMs",
    "truncated",
    "scanLimitReached",
})

# CONTRACT: search.text top-level result keys.
SEARCH_TEXT_RESPONSE_KEYS = frozenset({
    "results",
    "query",
    "mode",
    "caseSensitive",
    "maxResults",
    "resultOffset",
    "nextResultOffset",
    "hasMore",
}) | SEARCH_ACCOUNTING_KEYS

# CONTRACT: search.files top-level result keys (deterministic path match).
SEARCH_FILES_RESPONSE_KEYS = frozenset({
    "results",
    "query",
    "searchMode",
    "sortOrder",
    "maxResults",
    "truncated",
    "scanLimitReached",
    "filesConsidered",
    "filesMatched",
    "filesSkippedExcluded",
    "filesSkippedSymlink",
    "filesSkippedOversize",
    "symlinkPolicy",
    "scanDurationMs",
})

SEARCH_FILES_RESULT_KEYS = frozenset({
    "path",
    "matchReason",
})

# CONTRACT: search.todo top-level result keys.
SEARCH_TODO_RESPONSE_KEYS = frozenset({
    "results",
    "mode",
    "markers",
    "maxResults",
}) | SEARCH_ACCOUNTING_KEYS

# CONTRACT: search.literal top-level result keys (agent-safe literal substring).
SEARCH_LITERAL_RESPONSE_KEYS = frozenset({
    "results",
    "query",
    "searchMode",
    "rankingPolicy",
    "scoringDisabled",
    "agentSafe",
    "mode",
    "caseSensitive",
    "maxResults",
    "resultOffset",
    "nextResultOffset",
    "hasMore",
}) | SEARCH_ACCOUNTING_KEYS

# CONTRACT: search.tokens top-level result keys (conjunctive literal tokens).
SEARCH_TOKENS_RESPONSE_KEYS = frozenset({
    "results",
    "query",
    "tokens",
    "searchMode",
    "rankingPolicy",
    "scoringDisabled",
    "agentSafe",
    "caseSensitive",
    "maxResults",
    "resultOffset",
    "nextResultOffset",
    "hasMore",
}) | SEARCH_ACCOUNTING_KEYS

# CONTRACT: search.references top-level result keys (deterministic symbol refs).
SEARCH_REFERENCES_RESPONSE_KEYS = frozenset({
    "symbol",
    "results",
    "searchMode",
    "rankingPolicy",
    "scoringDisabled",
    "agentSafe",
    "sortOrder",
    "maxResults",
    "truncated",
    "totalReferences",
})

SEARCH_REFERENCES_RESULT_KEYS = frozenset({
    "resultIndex",
    "path",
    "line",
    "column",
    "preview",
    "matchReason",
    "lineSha256",
})

# CONTRACT: tool.registry response keys.
TOOL_REGISTRY_RESPONSE_KEYS = frozenset({
    "mode",
    "contractVersion",
    "rankingPolicy",
    "scoringDisabled",
    "tools",
})

TOOL_REGISTRY_ENTRY_KEYS = frozenset({
    "method",
    "stability",
    "deterministic",
    "agentSafe",
    "mutatesWorkspace",
    "supportsIdempotencyKey",
    "supportsDryRun",
    "requiresConfirmation",
    "deprecated",
    "contractVersion",
    "failureRecoveryHint",
    "nextRecommendedCommand",
})

# CONTRACT: Optional partial-success keys on read/mutation success payloads.
PARTIAL_SUCCESS_OPTIONAL_KEYS = frozenset({
    "complete",
    "partial",
    "warnings",
    "fallbackUsed",
    "recoveryHint",
    "nextRecommendedCommand",
})

# CONTRACT: Frozen error recovery hints (grep: rg 'RECOVERY:' scripts/fixtures/recovery/).
ERROR_RECOVERY_HINTS = {
    "stale_content": {"recovery_hint": "revalidate_patch_with_patch.validate", "nextRecommendedCommand": "patch.validate"},
    "semantic_disabled": {"recovery_hint": "use_search_literal_or_search_tokens", "nextRecommendedCommand": "search.literal"},
    "ranked_search_disabled": {"recovery_hint": "use_workspace_grep_or_search_literal", "nextRecommendedCommand": "workspace.grep"},
    "symlink_target": {"recovery_hint": "use_non_symlink_target_path", "nextRecommendedCommand": "file.stat"},
    "patch_failed": {"recovery_hint": "run_patch_preview_or_patch_validate", "nextRecommendedCommand": "patch.validate"},
    "nested_call_timeout": {"recovery_hint": "reduce_concurrency_or_retry_later", "nextRecommendedCommand": "operation.status"},
    "coherence_mismatch": {"recovery_hint": "refresh_context_and_retry_mutation", "nextRecommendedCommand": "file.read"},
    "shell_timeout": {"recovery_hint": "narrow_search_or_retry_later", "nextRecommendedCommand": "shell.rg"},
    "shell_truncated": {"recovery_hint": "narrow_range_or_paginate", "nextRecommendedCommand": "shell.sedRange"},
    "shell_binary_file": {"recovery_hint": "use_file_stat_or_skip_binary", "nextRecommendedCommand": "file.stat"},
    "shell_file_too_large": {"recovery_hint": "use_shell_head_tail_or_sedRange", "nextRecommendedCommand": "shell.sedRange"},
    "shell_directory_target": {"recovery_hint": "use_shell_cd_or_shell_rg", "nextRecommendedCommand": "shell.rg"},
    "shell_invalid_range": {"recovery_hint": "verify_line_bounds_with_shell_sedRange", "nextRecommendedCommand": "shell.sedRange"},
    "shell_outside_workspace": {"recovery_hint": "use_workspace_relative_path", "nextRecommendedCommand": "shell.pwd"},
    "shell_symlink_escape": {"recovery_hint": "use_non_symlink_target_path", "nextRecommendedCommand": "file.stat"},
    "shell_command_not_allowed": {"recovery_hint": "use_documented_shell_methods", "nextRecommendedCommand": "tool.capabilities"},
    "shell_rg_failed": {"recovery_hint": "verify_pattern_and_path", "nextRecommendedCommand": "shell.rg"},
}

# CONTRACT: tool.capabilities response keys.
TOOL_CAPABILITIES_RESPONSE_KEYS = frozenset({
    "mode",
    "contractVersion",
    "agentSafeMethods",
    "deprecatedMethods",
    "deterministicSearchMethods",
    "mutatingMethods",
    "internalNamespaces",
    "semanticSearchDisabled",
    "rankingPolicy",
    "scoringDisabled",
})

# CONTRACT: Quarantined semantic/ranked search error codes (numeric 4008).
SEMANTIC_QUARANTINE_ERROR_CODES = frozenset({
    "semantic_disabled",
    "ranked_search_disabled",
})

# CONTRACT: workspace.revision response keys.
WORKSPACE_REVISION_KEYS = frozenset({
    "revisionId",
    "workspaceRevision",
    "verifyRevision",
    "workspacePath",
    "changedFiles",
    "lastMutationReceipt",
    "lastMutationSource",
    "externalChangeDetected",
    "externallyChangedPaths",
    "mode",
})

# CONTRACT: coherence token payload on read/status responses (v0.1).
COHERENCE_RESPONSE_KEYS = frozenset({
    "tokenId",
    "workspaceRevision",
    "verifyRevision",
    "anchors",
})

# CONTRACT: read RPCs that issue coherence when taskId is set (v0.1).
COHERENCE_ISSUING_READ_METHODS = frozenset({
    "file.read",
    "file.readBatch",
    "file.readRange",
    "file.readAround",
    "file.stat",
    "workspace.status",
})

# CONTRACT: docs that must stay aligned on coherence (v0.1).
COHERENCE_ALIGNED_DOCS = frozenset({
    "coherence-tokens.md",
    "workspace-drift.md",
    "kernel-rpc.md",
    "error-codes.md",
    "agent-ergonomics.md",
    "runtime-invariants.md",
})

# CONTRACT: coherence-core-v0.1 release gate Makefile targets.
COHERENCE_CORE_V01_TARGETS = frozenset({
    "test-coherence-tokens",
    "coherence-recovery-smoke-fast",
})

# CONTRACT: workspace.snapshot response keys.
WORKSPACE_SNAPSHOT_KEYS = frozenset({
    "revisionId",
    "snapshotId",
    "sinceRevision",
    "revisionDelta",
    "snapshotMode",
    "fileHashes",
    "changedFiles",
    "filesHashed",
    "filesSkipped",
    "complete",
    "partial",
    "truncated",
    "warnings",
    "nextRecommendedCommand",
    "recoveryHint",
    "hashAlgorithm",
    "externalChangeDetected",
    "mode",
})

# CONTRACT: patch.applyBatch success response keys (applied=true).
PATCH_APPLY_BATCH_SUCCESS_KEYS = frozenset({
    "applied",
    "atomic",
    "batchMutationReceipt",
    "complete",
    "partial",
    "warnings",
    "nextRecommendedCommand",
    "recoveryHint",
})

# CONTRACT: Internal method namespaces excluded from tool.registry agent-safe surface.
INTERNAL_METHOD_NAMESPACES = (
    "analysis.",
    "language.",
    "chip.",
    "combo.",
    "recovery.",
    "terminal.run",
    "verify.run",
)

# CONTRACT: patch.applyBatch batchMutationReceipt keys.
BATCH_MUTATION_RECEIPT_KEYS = frozenset({
    "atomic",
    "appliedCount",
    "rolledBack",
    "fileReceipts",
    "rollbackProof",
})

# CONTRACT: operation.status response keys (completed).
OPERATION_STATUS_COMPLETED_KEYS = frozenset({
    "status",
    "idempotencyKey",
    "revisionBefore",
    "revisionAfter",
    "changedFiles",
    "completedAt",
})

# CONTRACT: runtime.diagnostics / memory.status response keys (native runtime journal).
RUNTIME_DIAGNOSTICS_KEYS = frozenset({
    "mode",
    "available",
    "checkpointStatus",
    "maxMemoryBytes",
    "maxBufferedOperations",
    "flushIntervalMs",
    "shardCount",
    "backpressureMode",
    "bufferedOperations",
    "droppedTelemetryCount",
    "mutationAuthority",
    "recordAuthority",
    "currentStateAuthority",
    "notCurrentFileTruth",
    "workspacePath",
    "startup",
    "runtimeRecoveredFromShutdown",
    "complete",
    "partial",
    "warnings",
    "nextRecommendedCommand",
    "recoveryHint",
})

# Back-compat alias for Pass VII contract name.
MEMORY_STATUS_KEYS = RUNTIME_DIAGNOSTICS_KEYS

# CONTRACT: unified operation identity (Pass VIII).
RUNTIME_OPERATION_IDENTITY_KEYS = frozenset({
    "operationId",
    "revisionId",
    "revisionBefore",
    "revisionAfter",
    "idempotencyKey",
    "workflowId",
    "receiptHash",
})

# CONTRACT: runtime.operation / memory.operation record keys.
MEMORY_OPERATION_KEYS = frozenset({
    "operationId",
    "method",
    "paramsHash",
    "status",
    "mode",
    "correlation",
})

# CONTRACT: memory.operation completed optional keys.
MEMORY_OPERATION_COMPLETED_OPTIONAL_KEYS = frozenset({
    "idempotencyKey",
    "startedAt",
    "completedAt",
    "revisionBefore",
    "revisionAfter",
    "receiptHash",
    "receipt",
})

# CONTRACT: memory.replay_cache retained entry keys.
MEMORY_REPLAY_CACHE_KEYS = frozenset({
    "idempotencyKey",
    "method",
    "paramsHash",
    "result",
    "receiptHash",
    "createdAt",
    "expiresAt",
    "mode",
    "retained",
})

# CONTRACT: memory.revision entry keys.
MEMORY_REVISION_KEYS = frozenset({
    "revisionId",
    "changedFiles",
    "mutationSource",
    "receiptHash",
    "timestamp",
    "mode",
})

# CONTRACT: memory.workflow entry keys.
MEMORY_WORKFLOW_KEYS = frozenset({
    "workflowId",
    "agentId",
    "status",
    "startedAt",
    "mode",
})

# CONTRACT: memory.workflow_step entry keys.
MEMORY_WORKFLOW_STEP_KEYS = frozenset({
    "stepId",
    "workflowId",
    "command",
    "status",
    "timestamp",
    "mode",
})

# CONTRACT: memory.verification run keys.
MEMORY_VERIFICATION_KEYS = frozenset({
    "runId",
    "command",
    "suiteName",
    "passedCount",
    "failedCount",
    "durationMs",
    "timestamp",
    "mode",
})

# CONTRACT: Pass XI — journal authority boundary labels (memory/history only, not live file truth).
JOURNAL_AUTHORITY_KEYS = frozenset({
    "recordAuthority",
    "mutationAuthority",
    "currentStateAuthority",
    "notCurrentFileTruth",
})

# CONTRACT: runtime.timeline response keys.
RUNTIME_TIMELINE_KEYS = frozenset({
    "mode",
    "events",
    "limit",
    "offset",
    "sinceRevision",
    "sortOrder",
    "complete",
    "partial",
    "truncated",
    "warnings",
    "nextRecommendedCommand",
    "recoveryHint",
}) | JOURNAL_AUTHORITY_KEYS

# CONTRACT: runtime.timeline event keys.
RUNTIME_TIMELINE_EVENT_KEYS = frozenset({
    "eventId",
    "eventType",
    "timestamp",
    "summary",
    "mode",
    "correlation",
})

# CONTRACT: runtime.* native surfaces (Pass VIII).
RUNTIME_RPC_METHODS = frozenset({
    "runtime.diagnostics",
    "runtime.status",
    "runtime.timeline",
    "runtime.history",
    "workspace.activity",
    "runtime.operation.recent",
    "runtime.warnings.recent",
    "runtime.correlate",
})

# CONTRACT: memory.* RPC method names (frozen durable-store query surface).
MEMORY_RPC_METHODS = frozenset({
    "memory.status",
    "memory.operation.get",
    "memory.operation.list",
    "memory.operation.findByIdempotencyKey",
    "memory.operation.findByRevision",
    "memory.operation.recent",
    "memory.replay.get",
    "memory.revision.get",
    "memory.revision.list",
    "memory.revision.changedFiles",
    "memory.revision.lastMutation",
    "memory.workflow.start",
    "memory.workflow.step",
    "memory.workflow.complete",
    "memory.workflow.fail",
    "memory.workflow.get",
    "memory.workflow.recent",
    "memory.verify.record",
    "memory.verify.latest",
    "memory.verify.history",
})

# CONTRACT: Pass XI — bridge recovery provenance fields.
BRIDGE_RECOVERY_SOURCE_KEYS = frozenset({
    "recoverySource",
    "nextCommandSource",
})

# CONTRACT: Pass XI — safePatch live hash authority (never journal-derived).
SAFE_PATCH_HASH_AUTHORITY = frozenset({
    "live_validate",
    "live_stat",
})

# CONTRACT: BroccoliQ memory safety boundary — memory layer must never expose mutation authority.
MEMORY_SAFETY_BOUNDARY_FORBIDDEN_AUTHORITY = frozenset({
    "patch_validity",
    "stale_content_decision",
    "rollback_success",
    "file_content_truth",
    "symlink_safety",
    "search_determinism",
})

# CONTRACT: patch.validate validation object keys.
PATCH_VALIDATION_KEYS = frozenset({
    "ok",
    "targetFileExists",
    "insideWorkspace",
    "patchAppliesCleanly",
    "changedLineCount",
    "requiresConfirmation",
    "syntaxDanger",
    "rejectedReason",
    "beforeContentHash",
    "patchFingerprint",
    "readSource",
})

# CONTRACT: patch.apply mutation receipt keys.
MUTATION_RECEIPT_KEYS = frozenset({
    "path",
    "beforeContentHash",
    "postContentHash",
    "patchFingerprint",
    "readSourceBefore",
    "applyChannel",
    "atomic",
})

# CONTRACT: file.stat response keys.
FILE_STAT_KEYS = frozenset({
    "path",
    "sizeBytes",
    "lineCount",
    "modified",
    "open",
    "dirty",
    "contentHash",
    "readSource",
    "isSymlink",
    "symlinkTarget",
    "insideWorkspace",
    "pathEscapesWorkspace",
})

# CONTRACT: shell.* shared envelope keys (Pass IX).
SHELL_ENVELOPE_KEYS = frozenset({
    "ok",
    "complete",
    "partial",
    "command",
    "cwdBefore",
    "cwdAfter",
    "workspaceRoot",
    "pathResolved",
    "exitCode",
    "stdout",
    "stderr",
    "truncated",
    "bytesRead",
    "lineCount",
    "warnings",
    "recoveryHint",
    "nextRecommendedCommand",
})

# CONTRACT: shell.rg top-level result keys.
SHELL_RG_RESPONSE_KEYS = SHELL_ENVELOPE_KEYS | frozenset({
    "matches",
    "matchCount",
    "filesSearched",
    "filesSkipped",
    "filesSkippedBinary",
    "filesSkippedSymlink",
    "filesSkippedExcluded",
    "searchMode",
    "sortOrder",
    "hiddenPolicy",
    "symlinkPolicy",
})

# CONTRACT: shell.rg match row keys.
SHELL_RG_MATCH_KEYS = frozenset({
    "path",
    "line",
    "column",
    "preview",
})

# CONTRACT: shell.head/tail/sedRange extended keys.
SHELL_RANGE_RESPONSE_KEYS = SHELL_ENVELOPE_KEYS | frozenset({
    "startLine",
    "endLine",
    "fileLineCount",
    "hasMoreBefore",
    "hasMoreAfter",
})

# CONTRACT: shell.sedRange requested vs actual line keys.
SHELL_SED_RANGE_RESPONSE_KEYS = SHELL_RANGE_RESPONSE_KEYS | frozenset({
    "requestedStartLine",
    "requestedEndLine",
    "actualStartLine",
    "actualEndLine",
})

# CONTRACT: shell.catSmall extended keys.
SHELL_CAT_SMALL_RESPONSE_KEYS = SHELL_ENVELOPE_KEYS | frozenset({
    "partial",
    "fileSizeBytes",
})

# CONTRACT: workspace.grep match row keys.
GREP_MATCH_KEYS = frozenset({
    "resultIndex",
    "path",
    "line",
    "column",
    "matchSpans",
    "matchCountOnLine",
    "preview",
    "lineSha256",
    "contextBefore",
    "contextAfter",
})

# CONTRACT: diff.hunks top-level result keys.
DIFF_HUNKS_RESPONSE_KEYS = frozenset({
    "files",
    "totalFiles",
    "totalHunks",
    "returnedHunks",
    "totalAddedLines",
    "totalRemovedLines",
    "maxHunks",
    "hunkOffset",
    "nextHunkOffset",
    "hasMoreHunks",
    "includeLines",
    "maxLinesPerHunk",
    "truncated",
    "complete",
    "partial",
    "warnings",
    "nextRecommendedCommand",
    "recoveryHint",
    "mode",
    "source",
    "sha256",
})

# CONTRACT: Makefile targets that must exist for agent runtime verification.
REQUIRED_MAKE_TARGETS = frozenset({
    "test-agent-offline",
    "test-rpc-transaction",
    "test-task-health",
    "test-operator-diagnostics",
    "test-runtime-safety",
    "test-grep-diff-tooling",
    "test-runtime-determinism",
    "test-transaction-kernel",
    "test-harness-realism",
    "test-deterministic-retrieval",
    "test-agent-workflow-smoke",
    "test-agent-shell-tooling",
    "test-agent-shell-tooling-fast",
    "test-agent-shell-workflows",
    "test-authority-boundaries",
    "test-cli-agent-failures",
    "test-docs-code-drift",
    "verify-agent-runtime-full",
    "test-partial-success-closure",
    "agent-integration",
    "verify-agent-runtime",
    "release-check-agent-runtime",
    "agent-self-test",
    "control-smoke",
    "test-coherence-tokens",
    "coherence-recovery-smoke-fast",
    "coherence-core-v0.1",
    "validate",
})

# CONTRACT: Live integration suite registry (name → script path).
INTEGRATION_SUITES = {
    "control_smoke": "scripts/control_smoke_test.py",
    "task_server_health": "scripts/test_task_server_health.py",
    "rpc_transaction": "scripts/test_rpc_transaction_health.py",
    "ergonomics": "scripts/test_ergonomics.py",
    "operator_diagnostics": "scripts/test_operator_diagnostics.py",
    "runtime_safety": "scripts/test_runtime_safety.py",
    "grep_diff_tooling": "scripts/test_grep_diff_tooling.py",
    "runtime_determinism": "scripts/test_runtime_determinism.py",
    "transaction_kernel": "scripts/test_transaction_kernel.py",
    "harness_realism": "scripts/test_harness_realism.py",
    "deterministic_retrieval": "scripts/test_deterministic_retrieval.py",
    "agent_workflow_smoke": "scripts/test_agent_workflow_smoke.py",
    "agent_shell_tooling": "scripts/test_agent_shell_tooling.py",
    "agent_shell_workflows": "scripts/test_agent_shell_workflows.py",
    "authority_boundaries": "scripts/test_authority_boundaries.py",
    "cli_agent_failures": "scripts/test_cli_agent_failures.py",
    "docs_code_drift": "scripts/test_docs_code_drift.py",
    "partial_success_closure": "scripts/test_partial_success_closure.py",
}


def validate_search_files_response(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = SEARCH_FILES_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"search.files missing keys: {sorted(missing)}")
    if result.get("searchMode") != "deterministic_path_match":
        errors.append("searchMode must be deterministic_path_match")
    if result.get("sortOrder") != "match_reason_path":
        errors.append("sortOrder must be match_reason_path")
    if result.get("symlinkPolicy") != "skip_never_follow":
        errors.append("symlinkPolicy must be skip_never_follow")
    results = result.get("results")
    if not isinstance(results, list):
        errors.append("results must be list")
    elif results:
        row = results[0]
        missing_row = SEARCH_FILES_RESULT_KEYS - set(row.keys())
        if missing_row:
            errors.append(f"search.files result missing keys: {sorted(missing_row)}")
        if "score" in row:
            errors.append("results must not include score")
    return errors

# CONTRACT: Offline lockdown suites.
OFFLINE_SUITES = {
    "agent_self_test": "scripts/dietcode_agent_client.py",
    "contract_lockdown": "scripts/test_contract_lockdown.py",
    "release_readiness": "scripts/test_release_readiness.py",
}


def validate_summary_line(payload: dict[str, Any]) -> list[str]:
    """Return validation errors for a summary NDJSON object."""
    errors: list[str] = []
    if payload.get("type") != "summary":
        errors.append("type must be 'summary'")
    missing = SUMMARY_SCHEMA_KEYS - set(payload.keys())
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
    if not isinstance(payload.get("failedNames"), list):
        errors.append("failedNames must be a list")
    if payload.get("checks") != payload.get("passed", 0) + payload.get("failed", 0):
        errors.append("checks must equal passed + failed")
    return errors


def validate_check_line(payload: dict[str, Any]) -> list[str]:
    """Return validation errors for a check NDJSON object."""
    errors: list[str] = []
    if payload.get("type") != "check":
        errors.append("type must be 'check'")
    missing = CHECK_LINE_SCHEMA_KEYS - set(payload.keys())
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
    name = payload.get("name")
    if not isinstance(name, str) or not name:
        errors.append("name must be a non-empty string")
    return errors


def assert_rpc_error_diagnostics(error: dict[str, Any], *, expect_request_id: str | None = None) -> None:
    """INVARIANT: Server failures expose stable grep-friendly diagnostic fields."""
    assert isinstance(error.get("string_code"), str) and error["string_code"], error
    if expect_request_id is not None:
        assert error.get("request_id") == expect_request_id, error
    assert isinstance(error.get("category"), str) and error["category"], error
    assert isinstance(error.get("retryable"), bool), error
    assert isinstance(error.get("recovery_hint"), str) and error["recovery_hint"], error


def validate_runtime_diagnostic_line(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if payload.get("type") != "runtime_diagnostic":
        errors.append("type must be 'runtime_diagnostic'")
    missing = RUNTIME_DIAGNOSTIC_LINE_KEYS - set(payload.keys())
    if missing:
        errors.append(f"missing keys: {sorted(missing)}")
    if not isinstance(payload.get("ok"), bool):
        errors.append("ok must be boolean")
    return errors


def validate_grep_match(match: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = GREP_MATCH_KEYS - set(match.keys())
    if missing:
        errors.append(f"match missing keys: {sorted(missing)}")
    if match.get("mode") is not None:
        errors.append("match must not include mode key")
    spans = match.get("matchSpans")
    if not isinstance(spans, list) or not spans:
        errors.append("matchSpans must be a non-empty list")
    else:
        span = spans[0]
        if not isinstance(span, dict):
            errors.append("matchSpans[0] must be object")
        else:
            for key in ("columnStart", "columnEnd", "offset", "length"):
                if key not in span:
                    errors.append(f"matchSpans[0] missing {key}")
    if not isinstance(match.get("resultIndex"), int):
        errors.append("resultIndex must be int")
    if not isinstance(match.get("line"), int) or match.get("line", 0) < 1:
        errors.append("line must be positive int")
    return errors


def validate_partial_success_signals(result: dict[str, Any], *, expect_complete: bool | None = None) -> list[str]:
    errors: list[str] = []
    if "complete" in result and not isinstance(result.get("complete"), bool):
        errors.append("complete must be boolean when present")
    if "partial" in result and not isinstance(result.get("partial"), bool):
        errors.append("partial must be boolean when present")
    if expect_complete is True and result.get("complete") is not True:
        errors.append("complete must be true for fully succeeded read")
    warnings = result.get("warnings")
    if warnings is not None and not isinstance(warnings, list):
        errors.append("warnings must be list when present")
    if result.get("partial") is True:
        if not isinstance(warnings, list) or not warnings:
            errors.append("partial=true requires non-empty warnings list")
    if result.get("partial") is True and result.get("complete") is not True:
        if not result.get("recoveryHint") and not result.get("nextRecommendedCommand"):
            errors.append("incomplete partial result requires recoveryHint or nextRecommendedCommand")
    return errors


def validate_shell_envelope(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = SHELL_ENVELOPE_KEYS - set(result.keys())
    if missing:
        errors.append(f"shell envelope missing keys: {sorted(missing)}")
    if not isinstance(result.get("warnings"), list):
        errors.append("warnings must be list")
    return errors


def validate_shell_rg_response(result: dict[str, Any]) -> list[str]:
    errors = validate_shell_envelope(result)
    missing = SHELL_RG_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"shell.rg missing keys: {sorted(missing)}")
    if result.get("searchMode") not in ("literal", "regex"):
        errors.append("searchMode must be literal or regex")
    if result.get("sortOrder") != "path_line_column":
        errors.append("sortOrder must be path_line_column")
    matches = result.get("matches")
    if not isinstance(matches, list):
        errors.append("matches must be list")
    elif matches:
        missing_row = SHELL_RG_MATCH_KEYS - set(matches[0].keys())
        if missing_row:
            errors.append(f"shell.rg match missing keys: {sorted(missing_row)}")
    errors.extend(validate_partial_success_signals(result))
    return errors


def validate_shell_range_response(result: dict[str, Any]) -> list[str]:
    errors = validate_shell_envelope(result)
    missing = SHELL_RANGE_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"shell range missing keys: {sorted(missing)}")
    errors.extend(validate_partial_success_signals(result))
    return errors


def validate_shell_sed_range_response(result: dict[str, Any]) -> list[str]:
    errors = validate_shell_range_response(result)
    missing = SHELL_SED_RANGE_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"shell.sedRange missing keys: {sorted(missing)}")
    return errors


def validate_shell_cat_small_response(result: dict[str, Any]) -> list[str]:
    errors = validate_shell_envelope(result)
    missing = SHELL_CAT_SMALL_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"shell.catSmall missing keys: {sorted(missing)}")
    errors.extend(validate_partial_success_signals(result))
    return errors


def validate_grep_response(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = GREP_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"grep missing keys: {sorted(missing)}")
    if result.get("mode") != "literal_substring":
        errors.append("mode must be literal_substring")
    matches = result.get("matches")
    if not isinstance(matches, list):
        errors.append("matches must be list")
    elif matches:
        errors.extend(validate_grep_match(matches[0]))
    has_more = result.get("hasMore")
    next_offset = result.get("nextResultOffset")
    if has_more and next_offset is None:
        errors.append("nextResultOffset required when hasMore is true")
    if not has_more and next_offset is not None:
        errors.append("nextResultOffset must be null when hasMore is false")
    if result.get("sortOrder") and result.get("sortOrder") != "path_line_column":
        errors.append("sortOrder must be path_line_column when present")
    if isinstance(matches, list) and matches and result.get("sortOrder") == "path_line_column":
        errors.extend(validate_grep_sort_order(matches))
    errors.extend(validate_partial_success_signals(result))
    return errors


def validate_mutation_receipt(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = MUTATION_RECEIPT_KEYS - set(receipt.keys())
    if missing:
        errors.append(f"mutation receipt missing keys: {sorted(missing)}")
    if receipt.get("atomic") is not True:
        errors.append("mutation receipt atomic must be true")
    return errors


def validate_file_stat(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = FILE_STAT_KEYS - set(result.keys())
    if missing:
        errors.append(f"file.stat missing keys: {sorted(missing)}")
    if not isinstance(result.get("contentHash"), str) or len(result.get("contentHash", "")) != 16:
        errors.append("contentHash must be 16-char stable hash")
    if result.get("readSource") not in ("editor", "disk"):
        errors.append("readSource must be editor or disk")
    if not isinstance(result.get("isSymlink"), bool):
        errors.append("isSymlink must be boolean")
    return errors


def validate_patch_validation(validation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = PATCH_VALIDATION_KEYS - set(validation.keys())
    if missing:
        errors.append(f"patch validation missing keys: {sorted(missing)}")
    if not isinstance(validation.get("ok"), bool):
        errors.append("validation.ok must be boolean")
    if not isinstance(validation.get("syntaxDanger"), bool):
        errors.append("validation.syntaxDanger must be boolean")
    if validation.get("ok") is False and not validation.get("rejectedReason"):
        errors.append("rejectedReason required when validation.ok is false")
    if validation.get("ok") is True:
        for key in ("beforeContentHash", "patchFingerprint", "readSource"):
            if key not in validation:
                errors.append(f"successful validation missing {key}")
    return errors


def validate_search_accounting(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = SEARCH_ACCOUNTING_KEYS - set(result.keys())
    if missing:
        errors.append(f"search accounting missing keys: {sorted(missing)}")
    if result.get("symlinkPolicy") != "skip_never_follow":
        errors.append("symlinkPolicy must be skip_never_follow")
    if result.get("sortOrder") and result.get("sortOrder") != "path_line_column":
        errors.append("sortOrder must be path_line_column when present")
    return errors


def validate_search_text_response(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = SEARCH_TEXT_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"search.text missing keys: {sorted(missing)}")
    if result.get("mode") != "literal_substring":
        errors.append("mode must be literal_substring")
    errors.extend(validate_search_accounting(result))
    return errors


def validate_search_todo_response(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = SEARCH_TODO_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"search.todo missing keys: {sorted(missing)}")
    if result.get("mode") != "literal_marker_scan":
        errors.append("mode must be literal_marker_scan")
    errors.extend(validate_search_accounting(result))
    return errors


def validate_search_literal_response(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = SEARCH_LITERAL_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"search.literal missing keys: {sorted(missing)}")
    if result.get("searchMode") != "literal_substring":
        errors.append("searchMode must be literal_substring")
    if result.get("rankingPolicy") != "none":
        errors.append("rankingPolicy must be none")
    if result.get("scoringDisabled") is not True:
        errors.append("scoringDisabled must be true")
    if result.get("agentSafe") is not True:
        errors.append("agentSafe must be true")
    if result.get("mode") != "literal_substring":
        errors.append("mode must be literal_substring")
    errors.extend(validate_search_accounting(result))
    for row in result.get("results") or []:
        if isinstance(row, dict) and "score" in row:
            errors.append("results must not include score")
            break
    return errors


def validate_search_tokens_response(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = SEARCH_TOKENS_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"search.tokens missing keys: {sorted(missing)}")
    if result.get("searchMode") != "literal_token_conjunctive":
        errors.append("searchMode must be literal_token_conjunctive")
    if result.get("rankingPolicy") != "none":
        errors.append("rankingPolicy must be none")
    if result.get("scoringDisabled") is not True:
        errors.append("scoringDisabled must be true")
    if result.get("agentSafe") is not True:
        errors.append("agentSafe must be true")
    errors.extend(validate_search_accounting(result))
    results = result.get("results")
    if isinstance(results, list) and results:
        row = results[0]
        if row.get("matchReason") != "all_tokens_literal":
            errors.append("matchReason must be all_tokens_literal")
        if "score" in row:
            errors.append("results must not include score")
    return errors


def validate_search_references_response(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = SEARCH_REFERENCES_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"search.references missing keys: {sorted(missing)}")
    if result.get("searchMode") != "symbol_exact":
        errors.append("searchMode must be symbol_exact")
    if result.get("rankingPolicy") != "none":
        errors.append("rankingPolicy must be none")
    if result.get("scoringDisabled") is not True:
        errors.append("scoringDisabled must be true")
    if result.get("agentSafe") is not True:
        errors.append("agentSafe must be true")
    if result.get("sortOrder") != "path_line_column":
        errors.append("sortOrder must be path_line_column")
    results = result.get("results")
    if not isinstance(results, list):
        errors.append("results must be list")
    elif results:
        row = results[0]
        missing_row = SEARCH_REFERENCES_RESULT_KEYS - set(row.keys())
        if missing_row:
            errors.append(f"search.references result missing keys: {sorted(missing_row)}")
        if "score" in row:
            errors.append("results must not include score")
        errors.extend(validate_grep_sort_order(results))
    return errors


def validate_tool_registry_response(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = TOOL_REGISTRY_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"tool.registry missing keys: {sorted(missing)}")
    if result.get("mode") != "tool_registry":
        errors.append("mode must be tool_registry")
    if result.get("rankingPolicy") != "none":
        errors.append("rankingPolicy must be none")
    if result.get("scoringDisabled") is not True:
        errors.append("scoringDisabled must be true")
    tools = result.get("tools")
    if not isinstance(tools, list) or not tools:
        errors.append("tools must be a non-empty list")
    else:
        entry = tools[0]
        missing_entry = TOOL_REGISTRY_ENTRY_KEYS - set(entry.keys())
        if missing_entry:
            errors.append(f"tool.registry entry missing keys: {sorted(missing_entry)}")
    return errors


def validate_tool_capabilities_response(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = TOOL_CAPABILITIES_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"tool.capabilities missing keys: {sorted(missing)}")
    if result.get("mode") != "tool_capabilities":
        errors.append("mode must be tool_capabilities")
    if result.get("semanticSearchDisabled") is not True:
        errors.append("semanticSearchDisabled must be true")
    if result.get("rankingPolicy") != "none":
        errors.append("rankingPolicy must be none")
    if result.get("scoringDisabled") is not True:
        errors.append("scoringDisabled must be true")
    for key in ("agentSafeMethods", "deprecatedMethods", "deterministicSearchMethods", "mutatingMethods"):
        value = result.get(key)
        if not isinstance(value, list):
            errors.append(f"{key} must be list")
        elif value != sorted(value):
            errors.append(f"{key} must be lexicographically sorted")
    deprecated = result.get("deprecatedMethods", [])
    if "search.semantic" not in deprecated:
        errors.append("search.semantic must be in deprecatedMethods")
    deterministic = result.get("deterministicSearchMethods", [])
    for method in ("search.literal", "search.tokens", "search.paths"):
        if method not in deterministic:
            errors.append(f"{method} must be in deterministicSearchMethods")
    internal = result.get("internalNamespaces", [])
    if not isinstance(internal, list):
        errors.append("internalNamespaces must be list")
    else:
        for prefix in INTERNAL_METHOD_NAMESPACES:
            if prefix not in internal:
                errors.append(f"internalNamespaces must include {prefix}")
    return errors


def validate_journal_authority_labels(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = JOURNAL_AUTHORITY_KEYS - set(result.keys())
    if missing:
        errors.append(f"journal authority missing keys: {sorted(missing)}")
    if result.get("recordAuthority") != "runtime_journal":
        errors.append("recordAuthority must be runtime_journal")
    if result.get("mutationAuthority") != "cpp_kernel":
        errors.append("mutationAuthority must be cpp_kernel")
    if result.get("currentStateAuthority") != "workspace_live_read":
        errors.append("currentStateAuthority must be workspace_live_read")
    if result.get("notCurrentFileTruth") is not True:
        errors.append("notCurrentFileTruth must be true for journal/history surfaces")
    return errors


def validate_runtime_diagnostics(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = RUNTIME_DIAGNOSTICS_KEYS - set(result.keys())
    if missing:
        errors.append(f"runtime.diagnostics missing keys: {sorted(missing)}")
    if result.get("mode") != "runtime_diagnostics":
        errors.append("mode must be runtime_diagnostics")
    errors.extend(validate_journal_authority_labels(result))
    errors.extend(validate_partial_success_signals(result))
    return errors


def validate_memory_status(result: dict[str, Any]) -> list[str]:
    return validate_runtime_diagnostics(result)


def validate_runtime_timeline(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = RUNTIME_TIMELINE_KEYS - set(result.keys())
    if missing:
        errors.append(f"runtime.timeline missing keys: {sorted(missing)}")
    if result.get("mode") != "runtime_timeline":
        errors.append("mode must be runtime_timeline")
    if result.get("sortOrder") != "timestamp_desc":
        errors.append("sortOrder must be timestamp_desc")
    errors.extend(validate_journal_authority_labels(result))
    errors.extend(validate_partial_success_signals(result))
    events = result.get("events")
    if isinstance(events, list) and events:
        event_missing = RUNTIME_TIMELINE_EVENT_KEYS - set(events[0].keys())
        if event_missing:
            errors.append(f"runtime.timeline event missing keys: {sorted(event_missing)}")
    return errors


def validate_runtime_operation_identity(correlation: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = RUNTIME_OPERATION_IDENTITY_KEYS - set(correlation.keys())
    if missing:
        errors.append(f"operation identity missing keys: {sorted(missing)}")
    return errors


def validate_memory_operation(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = MEMORY_OPERATION_KEYS - set(result.keys())
    if missing:
        errors.append(f"memory.operation missing keys: {sorted(missing)}")
    if result.get("mode") != "runtime_operation":
        errors.append("mode must be runtime_operation")
    correlation = result.get("correlation")
    if isinstance(correlation, dict):
        errors.extend(validate_runtime_operation_identity(correlation))
    return errors


def validate_memory_revision(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = MEMORY_REVISION_KEYS - set(result.keys())
    if missing:
        errors.append(f"memory.revision missing keys: {sorted(missing)}")
    if result.get("mode") not in ("memory_revision", "memory_revision_last_mutation"):
        errors.append("mode must be memory_revision or memory_revision_last_mutation")
    return errors


def validate_memory_workflow(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = MEMORY_WORKFLOW_KEYS - set(result.keys())
    if missing:
        errors.append(f"memory.workflow missing keys: {sorted(missing)}")
    if result.get("mode") != "memory_workflow":
        errors.append("mode must be memory_workflow")
    return errors


def validate_memory_verification(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = MEMORY_VERIFICATION_KEYS - set(result.keys())
    if missing:
        errors.append(f"memory.verification missing keys: {sorted(missing)}")
    if result.get("mode") != "memory_verification":
        errors.append("mode must be memory_verification")
    return errors


def validate_workspace_revision(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = WORKSPACE_REVISION_KEYS - set(result.keys())
    if missing:
        errors.append(f"workspace.revision missing keys: {sorted(missing)}")
    if result.get("mode") != "workspace_revision":
        errors.append("mode must be workspace_revision")
    if not isinstance(result.get("revisionId"), int) or result["revisionId"] < 1:
        errors.append("revisionId must be positive int")
    return errors


def validate_workspace_snapshot(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = WORKSPACE_SNAPSHOT_KEYS - set(result.keys())
    if missing:
        errors.append(f"workspace.snapshot missing keys: {sorted(missing)}")
    if result.get("mode") != "workspace_snapshot":
        errors.append("mode must be workspace_snapshot")
    if result.get("hashAlgorithm") != "fnv1a_16hex":
        errors.append("hashAlgorithm must be fnv1a_16hex")
    if result.get("snapshotMode") not in ("mutated_only", "tracked_files", "explicit_paths"):
        errors.append("snapshotMode must be mutated_only, tracked_files, or explicit_paths")
    errors.extend(validate_partial_success_signals(result))
    return errors


def validate_patch_apply_batch_success(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if result.get("applied") is not True:
        errors.append("applied must be true")
    missing = PATCH_APPLY_BATCH_SUCCESS_KEYS - set(result.keys())
    if missing:
        errors.append(f"patch.applyBatch success missing keys: {sorted(missing)}")
    if result.get("complete") is not True:
        errors.append("complete must be true on successful batch apply")
    receipt = result.get("batchMutationReceipt")
    if not isinstance(receipt, dict):
        errors.append("batchMutationReceipt must be object")
    else:
        errors.extend(validate_batch_mutation_receipt(receipt))
    if result.get("nextRecommendedCommand") != "workspace.revision" and not result.get("idempotentReplay"):
        errors.append("nextRecommendedCommand must be workspace.revision on fresh batch apply")
    return errors


def validate_batch_mutation_receipt(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = BATCH_MUTATION_RECEIPT_KEYS - set(receipt.keys())
    if missing:
        errors.append(f"batch receipt missing keys: {sorted(missing)}")
    if receipt.get("atomic") is not True:
        errors.append("batch receipt atomic must be true when fully applied")
    file_receipts = receipt.get("fileReceipts")
    if not isinstance(file_receipts, list):
        errors.append("fileReceipts must be list")
    elif file_receipts:
        errors.extend(validate_mutation_receipt(file_receipts[0]))
    return errors


def validate_grep_sort_order(matches: list[dict[str, Any]]) -> list[str]:
    """INVARIANT: matches are sorted path → line → column when sortOrder is path_line_column."""
    errors: list[str] = []
    previous: tuple[str, int, int] | None = None
    for match in matches:
        current = (str(match.get("path", "")), int(match.get("line", 0)), int(match.get("column", 0)))
        if previous and current < previous:
            errors.append(f"grep sort violation: {previous} before {current}")
        previous = current
    return errors


def validate_diff_hunks_response(result: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    missing = DIFF_HUNKS_RESPONSE_KEYS - set(result.keys())
    if missing:
        errors.append(f"diff.hunks missing keys: {sorted(missing)}")
    if result.get("mode") != "literal_unified_diff_hunks":
        errors.append("mode must be literal_unified_diff_hunks")
    files = result.get("files")
    if not isinstance(files, list):
        errors.append("files must be list")
    has_more = result.get("hasMoreHunks")
    next_offset = result.get("nextHunkOffset")
    if has_more and next_offset is None:
        errors.append("nextHunkOffset required when hasMoreHunks is true")
    if not has_more and next_offset is not None:
        errors.append("nextHunkOffset must be null when hasMoreHunks is false")
    errors.extend(validate_partial_success_signals(result))
    return errors


def assert_rpc_envelope(response: dict[str, Any], *, expect_ok: bool) -> None:
    """INVARIANT: Every RPC response is a single terminal envelope."""
    if expect_ok:
        assert response.get("ok") is True, response
        for key in RPC_SUCCESS_ENVELOPE_KEYS:
            assert key in response, f"missing {key} in success envelope"
        assert isinstance(response.get("result"), dict), "result must be object"
    else:
        assert response.get("ok") is False, response
        error = response.get("error", {})
        assert isinstance(error, dict), "error must be object"
        for key in RPC_ERROR_ENVELOPE_KEYS:
            assert key in error, f"missing {key} in error envelope"
        assert isinstance(error.get("string_code"), str) and error["string_code"], "string_code required"
