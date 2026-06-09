# Agent shell tooling

Bounded, deterministic shell-shaped inspection for agents via kernel `shell.*` RPC methods. Use `python3 scripts/dietcode_agent_client.py shell …` — not raw `cat`, `cd`, or unbounded `rg`.

Part of the optional agent-runtime harness ladder; not required for `coherence-core-v0.1`.

Verification:

```bash
make test-agent-shell-tooling-fast      # offline + quick live (assumes server ready)
make test-agent-shell-tooling           # rebuild + restart + offline harness
make test-agent-shell-workflows         # rebuild + restart + workflow A–E
make test-agent-shell-workflows-fast    # workflow A–E only (assumes server ready)
make verify-agent-runtime-full          # includes shell tooling + workflows
```

---

## Principles

| Do | Don't |
|----|-------|
| `shell.pwd` before and after `shell.cd` | Assume cwd persists across tools silently |
| `shell.rg` with line/column + globs | Recursive `grep` or fuzzy search |
| `shell.head` / `shell.tail` / `shell.sedRange` on large files | `cat` unknown or large files |
| `shell.catSmall` only for small known files | `shell.catSmall` on binaries or symlinks |
| Quote paths with spaces | Bare unquoted paths |
| Read-only `sed -n 'start,endp'` via `shell.sedRange` | `sed -i`, substitutions, pipes, chaining |

---

## Shared envelope

Every `shell.*` success returns:

`ok`, `complete`, `partial`, `command`, `cwdBefore`, `cwdAfter`, `workspaceRoot`, `pathResolved`, `exitCode`, `stdout`, `stderr`, `bytesRead`, `lineCount`, `truncated`, `warnings`, `recoveryHint`, `nextRecommendedCommand`

Frozen keys: `scripts/agent_contracts.py` → `SHELL_ENVELOPE_KEYS`.

---

## Methods

### `shell.pwd`

Returns the agent session cwd (defaults to workspace root).

### `shell.cd`

Changes agent session cwd only (not hidden process state). Rejects:

| Code | Meaning |
|------|---------|
| `directory_not_found` | Path does not exist |
| `not_directory` | Path is a file |
| `outside_workspace` | Resolved path leaves workspace |
| `symlink_escape` | Symlink target outside workspace |
| `invalid_path` | Path contains invalid characters |

### `shell.rg`

Runs ripgrep (`--json`) with deterministic defaults:

- `--line-number --column --no-follow --sort path`
- `searchMode`: `literal` (default) or `regex`
- `sortOrder`: `path_line_column`
- `maxResults` capped at 200
- `symlinkPolicy`: `no_follow`

Params: `pattern`, optional `path`, `include[]`, `exclude[]`, `hidden`, `regex`, `maxResults`.

Returns: `matches`, `matchCount`, `filesSearched`, `filesSkipped`, `filesSkippedBinary`, `filesSkippedSymlink`, `filesSkippedExcluded`, `truncated`, `searchMode`, `sortOrder`, `warnings`.

### `shell.head` / `shell.tail`

Defaults: 80 lines, max 300. Binary files, directories, symlinks, and files above 2 MiB are rejected. Returns `startLine`, `endLine`, `hasMoreBefore`, `hasMoreAfter`, `fileLineCount`.

### `shell.sedRange`

Read-only range extraction (controlled file read, not arbitrary `sed` execution). Params: `path`, `startLine`, `endLine` (1-indexed, max 300 lines per call).

Returns: `requestedStartLine`, `requestedEndLine`, `actualStartLine`, `actualEndLine`, `hasMoreBefore`, `hasMoreAfter`.

### `shell.catSmall`

Max 64 KiB / 500 lines. Sets `partial: true` and `recoveryHint: use_shell_head_tail_or_sedRange` when truncated.

---

## Shell error codes

| string_code | Meaning | nextRecommendedCommand |
|-------------|---------|------------------------|
| `shell_timeout` | `shell.rg` exceeded timeout | `shell.rg` |
| `shell_truncated` | Range or result limit exceeded | `shell.sedRange` |
| `shell_binary_file` | Binary file rejected | `file.stat` |
| `shell_file_too_large` | File exceeds 2 MiB read cap | `shell.sedRange` |
| `shell_directory_target` | Path is a directory | `shell.rg` |
| `shell_invalid_range` | Invalid line range | `shell.sedRange` |
| `shell_outside_workspace` | Path escapes workspace | `shell.pwd` |
| `shell_symlink_escape` | Symlink escapes workspace or read blocked | `file.stat` |
| `shell_command_not_allowed` | Unknown shell method | `tool.capabilities` |
| `shell_rg_failed` | ripgrep subprocess failed | `shell.rg` |

See [Error Codes](error-codes.md).

---

## CLI aliases

```bash
dietcode-agent-client shell pwd
dietcode-agent-client shell cd src
dietcode-agent-client shell rg "CONTRACT:" --path scripts/
dietcode-agent-client shell head scripts/fixtures/shell/anchor_target.txt
dietcode-agent-client shell tail logs/runtime.log
dietcode-agent-client shell sed scripts/fixtures/shell/anchor_target.txt 1 5
dietcode-agent-client shell cat-small README.md
```

Python client (same surface):

```bash
python3 scripts/dietcode_agent_client.py shell pwd --compact
python3 scripts/dietcode_agent_client.py shell rg "CONTRACT:" --path scripts/ --compact
```

Use `--pretty` for indented JSON. Partial/truncated results emit a stderr hint unless `--quiet`.

---

## Recommended workflow

1. `shell.pwd` — note cwd
2. `shell.cd` — move inside workspace (optional)
3. `shell.rg` — find anchor with line/column
4. `shell.sedRange` — read context around match
5. `patch.validate` — validate diff before apply

---

## Contracts and fixtures

Frozen keys in `scripts/agent_contracts.py`:

- `SHELL_ENVELOPE_KEYS`
- `SHELL_RG_RESPONSE_KEYS` / `SHELL_RG_MATCH_KEYS`
- `SHELL_RANGE_RESPONSE_KEYS` / `SHELL_SED_RANGE_RESPONSE_KEYS`
- `SHELL_CAT_SMALL_RESPONSE_KEYS`

Fixtures: `scripts/fixtures/shell/`

Harnesses:

- `scripts/test_agent_shell_tooling.py` — offline + quick live
- `scripts/test_agent_shell_workflows.py` — workflows A–E
