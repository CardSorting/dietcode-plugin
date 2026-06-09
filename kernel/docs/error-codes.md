# RPC Error Codes

Stable `string_code` values returned in JSON-RPC error envelopes (`ok: false`). Grep this file or the server mapping when debugging agent failures.

Recovery hints and quarantined surfaces: [runtime-invariants.md](runtime-invariants.md), [agent-tooling.md](agent-tooling.md).

**Canonical mapping:** `src/platform/macos/control/MacControlServer.mm` (`sendError:code:message:clientFd:`)

**Client mirror:** `scripts/dietcode_agent_client.py` (`local_error_response`, `exception_error_response`)

---

## Error taxonomy

| Category | Numeric range | Retry? | Examples |
|----------|---------------|--------|----------|
| Transport | -32600..-32603, client-local | Sometimes | `invalid_request`, `transport_error`, `internal_error` |
| Validation | -32602, 413 | No — fix params | `invalid_params`, `request_too_large`, `too_many_results` |
| Resource | 404, 409 | No | `not_found`, `already_exists`, `method_not_found` |
| Domain | 4001–4008 | Case-by-case | `outside_workspace`, `task_not_active`, `patch_failed`, `semantic_disabled` |
| Serialization | -32603 | No — inspect payload | `response_serialization_failed`, `response_too_large` |
| Recovery | -32603, 404 | Manual | `rollback_failed`, `backup_corrupt` |

**Envelope contract:** every RPC returns exactly one terminal object with `id`, `ok`, and either `result` (success) or `error` with `code`, `string_code`, `message` (failure).

**Diagnostic fields (failure only, optional but stable):** `request_id`, `category`, `retryable`, `phase`, `queue`, `recovery_hint`. See [troubleshooting.md](troubleshooting.md).

```bash
rg 'assert_envelope_shape|REQUIRED_ERROR_KEYS' scripts/test_rpc_transaction_health.py
```

---

## Grep anchors

```bash
# All server string_code assignments
rg 'errorCodeOut.*=.*@"|outErrCode = @"' src/platform/macos/control

# Numeric code mapping table
rg 'stringCode isEqualToString' src/platform/macos/control/MacControlServer.mm

# Contract tests that assert string_code values
rg 'string_code' scripts/test_*.py
```

---

## JSON-RPC transport codes

| string_code | numeric `code` | Meaning |
|-------------|----------------|---------|
| `invalid_request` | -32600 | Malformed frame or unsupported request shape |
| `method_not_found` | -32601 | Unknown RPC method |
| `invalid_params` | -32602 | Params failed validation |
| `internal_error` | -32603 | Unhandled server failure |

## Response serialization

| string_code | numeric `code` | Meaning |
|-------------|----------------|---------|
| `response_serialization_failed` | -32603 | Server could not JSON-encode a success payload |

## Client-local codes (no live server)

| string_code | numeric `code` | Meaning |
|-------------|----------------|---------|
| `invalid_json` | -32600 | Batch line is not valid JSON |
| `transport_error` | -32603 | Socket connect/read/write failure |
| `rpc_error` | -32000 | Unclassified client-side failure |

## Local safety / concurrency codes

| string_code | numeric `code` | Meaning |
|-------------|----------------|---------|
| `connection_limit_exceeded` | 429 | Active connection cap (`kMaxActiveConnections`) |
| `too_many_pending` | 429 | Per-connection in-flight request cap |
| `malformed_request_flood` | 429 | Too many malformed lines on one connection |
| `nested_call_timeout` | 429 | Nested executor exceeded `kMaxNestedCallWaitSeconds` |

## Socket safety codes (startup / audit)

| string_code | Meaning |
|-------------|---------|
| `socket_symlink` | Socket or `~/.dietcode` is a symlink |
| `socket_wrong_owner` | Path owned by another user |
| `socket_unsafe_permissions` | Unexpected file mode (expect `0600` socket, `0700` dir) |
| `socket_unsafe_type` | Path is not the expected file type |
| `socket_unsafe_path` | Invalid or empty socket path |

See [Runtime Invariants](runtime-invariants.md) and [Troubleshooting](troubleshooting.md).

## Size and limit codes

| string_code | numeric `code` | Meaning |
|-------------|----------------|---------|
| `request_too_large` | 413 | Request frame exceeds 1 MB |
| `response_too_large` | 413 | Response would exceed 4 MB |
| `too_many_results` | 413 | Result page limit exceeded |
| `file_too_large` | 413 | File exceeds read limit |

## Resource codes

| string_code | numeric `code` | Meaning |
|-------------|----------------|---------|
| `not_found` | 404 | File, task, combo, or backup not found |
| `already_exists` | 409 | Create would overwrite an existing resource |

## Domain codes (4001–4007)

| string_code | numeric `code` | Typical source |
|-------------|----------------|----------------|
| `outside_workspace` | 4001 | Path escapes workspace root |
| `outside_scope` | 4001 | Task step outside allowed scope |
| `lock_conflict` | 4002 | File lock held by another operation |
| `dirty_buffer_conflict` | 4002 | Unsaved editor buffer conflicts with patch |
| `budget_exceeded` | 4003 | Task/combo budget limit hit |
| `verification_failed` | 4004 | Post-change verification failed |
| `verify_failed` | 4004 | Alias of verification failure |
| `patch_failed` | 4004 | Patch could not be applied |
| `stale_content` | 4004 | Target file changed since validation (`expectBeforeHash` mismatch). **Next:** `patch.validate` |
| `coherence_mismatch` | 4004 | Task coherence token stale — observed state no longer matches workspace. **Next:** re-read with `taskId`, retry with fresh token |
| `symlink_target` | 4004 | Patch attempted through symlink path. **Next:** `file.stat` on real path |
| `rollback_conflict` | 4005 | Rollback state mismatch |
| `rollback_failed` | 4005 | Rollback operation failed |
| `permission_denied` | 4006 | Socket or sandbox permission denied |
| `task_not_active` | 4007 | Task already completed or cancelled |
| `semantic_disabled` | 4008 | `search.semantic` quarantined in deterministic agent mode |
| `ranked_search_disabled` | 4008 | `analysis.searchRanked` quarantined (probabilistic scoring removed) |

**Recovery:** use `search.literal`, `search.tokens`, `workspace.grep`, or `search.references`. Each error includes `recovery_hint` and `nextRecommendedCommand` in the envelope.

| string_code | recovery_hint | nextRecommendedCommand |
|-------------|---------------|------------------------|
| `stale_content` | `revalidate_patch_with_patch.validate` | `patch.validate` |
| `coherence_mismatch` | `refresh_context_and_retry_mutation` | `file.read` |
| `symlink_target` | `use_non_symlink_target_path` | `file.stat` |
| `semantic_disabled` | `use_search_literal_or_search_tokens` | `search.literal` |
| `ranked_search_disabled` | `use_workspace_grep_or_search_literal` | `workspace.grep` |
| `patch_failed` | `run_patch_preview_or_patch_validate` | `patch.validate` |
| `nested_call_timeout` | `reduce_concurrency_or_retry_later` | `operation.status` |

## Shell wrapper codes (Pass IX)

| string_code | Meaning | recovery_hint | nextRecommendedCommand |
|-------------|---------|---------------|------------------------|
| `shell_timeout` | `shell.rg` subprocess timed out | `narrow_search_or_retry_later` | `shell.rg` |
| `shell_truncated` | Result or range limit exceeded | `narrow_range_or_paginate` | `shell.sedRange` |
| `shell_binary_file` | Binary file rejected for text read | `use_file_stat_or_skip_binary` | `file.stat` |
| `shell_file_too_large` | File exceeds shell read cap (2 MiB) | `use_shell_head_tail_or_sedRange` | `shell.sedRange` |
| `shell_directory_target` | Path is a directory | `use_shell_cd_or_shell_rg` | `shell.rg` |
| `shell_invalid_range` | Invalid `startLine`/`endLine` | `verify_line_bounds_with_shell_sedRange` | `shell.sedRange` |
| `shell_outside_workspace` | Resolved path leaves workspace | `use_workspace_relative_path` | `shell.pwd` |
| `shell_symlink_escape` | Symlink escapes workspace or read blocked | `use_non_symlink_target_path` | `file.stat` |
| `shell_command_not_allowed` | Unknown `shell.*` method | `use_documented_shell_methods` | `tool.capabilities` |
| `shell_rg_failed` | ripgrep subprocess failed | `verify_pattern_and_path` | `shell.rg` |

`shell.cd` uses domain codes: `directory_not_found`, `not_directory`, `outside_workspace`, `symlink_escape`, `invalid_path`.

Docs: [Agent Shell Tooling](agent-shell-tooling.md).

```bash
python3 scripts/dietcode_agent_client.py --raw-response --compact search.semantic '{"query":"foo"}'
python3 scripts/dietcode_agent_client.py tool.capabilities
```

## Recovery and backup codes

| string_code | numeric `code` | Typical source |
|-------------|----------------|----------------|
| `backup_workspace_mismatch` | -32603 | Backup belongs to a different workspace |
| `backup_manifest_invalid` | -32603 | Backup manifest failed validation |
| `backup_manifest_missing` | -32603 | Expected manifest not present |
| `backup_corrupt` | -32603 | Backup file integrity check failed |
| `backup_not_found` | 404 | Backup id does not exist |
| `rollback_target_escaped` | -32603 | Rollback path outside workspace |
| `rollback_postimage_mismatch` | -32603 | Post-rollback file hash mismatch |
| `rollback_preimage_mismatch` | -32603 | Pre-rollback file hash mismatch |
| `invalid_state` | -32603 | Recovery store in unexpected state |
| `confirmation_required` | -32603 | Destructive action needs `confirm: true` |
| `delete_failed` | -32603 | Backup deletion failed |

## Chip codes

| string_code | numeric `code` | Typical source |
|-------------|----------------|----------------|
| `unknown_chip` | -32603 | `chip.describe` for unregistered chip |

## Patch and git codes

| string_code | numeric `code` | Typical source |
|-------------|----------------|----------------|
| `invalid_range` | -32602 | Editor range out of bounds |
| `git_failed` | -32603 | Git subprocess or operation failed |

---

## Inspect failures from the CLI

```bash
# Structured stderr envelope on failure
python3 scripts/dietcode_agent_client.py --error-json --compact event.subscribe '{}' 1>/dev/null

# Full server envelope (exit 1 when ok:false)
python3 scripts/dietcode_agent_client.py --raw-response --compact event.subscribe '{}'; echo "exit=$?"

# Offline client checks (no socket)
make agent-self-test
python3 scripts/dietcode_agent_client.py --self-test --compact | python3 -m json.tool
```

## Recovery workflow

1. Read `string_code` and `message` from the error envelope.
2. Grep this file and `src/platform/macos/control` for the code.
3. Re-run the failing RPC with `--raw-response --compact` to capture the full envelope.
4. For mutation failures, check `recovery.list` / `combo.status` before retrying.
5. For path errors, verify `workspace.getRoot` and re-run with `DIETCODE_TEST_WORKSPACE` set when using integration scripts.
6. For `stale_content`, re-run `patch.validate` and apply with fresh `expectBeforeHash` from validation.
7. For `semantic_disabled` / `ranked_search_disabled`, switch to `search.literal` or `workspace.grep` per `nextRecommendedCommand`.

## Related docs

- [kernel-rpc.md](kernel-rpc.md)
- [runtime-invariants.md](runtime-invariants.md)
- [agent-tooling.md](agent-tooling.md)
- [troubleshooting.md](troubleshooting.md)
