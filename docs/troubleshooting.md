# Troubleshooting

Common DietCode integration issues and fixes.

---

## Plugin not loading

**Symptom:** `hermes plugins list` shows dietcode disabled or "not enabled in config".

**Fixes:**

1. Confirm directory: `ls ~/.hermes/plugins/dietcode/plugin.yaml`
2. Check `plugins.disabled` does not contain `dietcode`
3. Restart Hermes after copy
4. Run `python3 ~/.hermes/plugins/dietcode/install.py`
5. Manual enable: `hermes plugins enable dietcode`

**Symptom:** Import errors in plugin error column.

**Fixes:**

- Ensure full `dietcode/` tree copied (not just `__init__.py`)
- Python ≥ 3.10
- `pyyaml` available (bundled with Hermes; pip package installs it explicitly)

---

## plugins.dietcode ImportError (drag-and-drop)

**Symptom:** `No module named 'plugins.dietcode'`

**Cause:** Bootstrap did not run — usually corrupted or partial copy.

**Fix:**

1. Verify `_bootstrap.py` exists beside `__init__.py`
2. Ensure `__init__.py` calls `_run_namespace_bootstrap()` at top
3. Re-copy from package: `./scripts/install-to-hermes.sh`

---

## BroccoliDB rpc_available: false

**Symptom:** `/dietcode doctor` shows RPC unavailable.

**Checklist:**

```bash
# 1. Node deps installed?
ls ~/.hermes/plugins/dietcode/broccolidb/node_modules/.bin/tsx

# 2. Install if missing
cd ~/.hermes/plugins/dietcode/broccolidb && npm ci

# 3. Manual RPC smoke test
export HERMES_BROCCOLIDB_DB=/tmp/test.db
echo '{"id":1,"method":"rpc_health","params":{}}' | \
  node_modules/.bin/tsx infrastructure/hermes/hermes_rpc.ts
```

**Other causes:**

- Wrong `HERMES_BROCCOLIDB_ROOT` pointing to invalid directory
- Node version mismatch — run `npm rebuild better-sqlite3`
- Stale RPC worker — restart Hermes session

---

## node_modules_installed: false

**Fix:**

```bash
cd ~/.hermes/plugins/dietcode/broccolidb && npm ci
```

Or re-run install script without skip:

```bash
DIETCODE_SKIP_NPM= ./scripts/install-to-hermes.sh
```

---

## Tools missing from registry

**Symptom:** `/dietcode tools` shows `registry_missing: [...]`

**Fixes:**

1. Confirm `dietcode` in `toolsets` in config.yaml
2. `/dietcode doctor` — check `modules_failed` for import tracebacks
3. Restart Hermes (tool load is cached in `tools_loader._CACHED_REPORT`)
4. Fix underlying import error in failed module

---

## Governance not blocking writes

**Symptom:** Layer violations pass silently.

**Checks:**

1. `/dietcode doctor` → `governance_hook_active: true`
2. Config: `joyzoning.governance.enabled: true`
3. Plugin not disabled
4. File may be exempt (`.md`, docs path, `extra_exempt_paths`)
5. `layer_tags_required: false` uses light mode — only import-depth rules in `auto` mode

---

## kanban_complete blocked

**Symptom:** Pre-tool hook prevents task completion.

**Expected** when `joyzoning.enabled: true` and convergence not reached.

**Fix (agent workflow):**

1. `convergence_status` — check state
2. Complete mutation lifecycle through `request_review`
3. Operator approves → `convergence_mark_converged`
4. Retry `kanban_complete`

**Disable gate** (not recommended for production workers):

```yaml
joyzoning:
  convergence:
    review_before_complete: false
```

Or disable full lifecycle: `joyzoning.enabled: false`

---

## Slash commands fail with TS errors

**Symptom:** `/joyzoning status` returns RPC or tsx errors.

**Fixes:**

1. BroccoliDB RPC healthy (`/dietcode broccolidb`)
2. Run from workspace with valid TS/JS sources for SpiderEngine
3. Check stderr in Hermes logs for schema self-heal messages

---

## Profile confusion

**Symptom:** Plugin works in CLI but not gateway (or vice versa).

Each profile has separate `HERMES_HOME`. Install plugin and config per profile:

```bash
HERMES_HOME=~/.hermes/profiles/work ./scripts/install-to-hermes.sh
```

---

## pip vs drag-and-drop conflict

**Symptom:** Double registration or wrong `plugins.dietcode` path.

**Guidance:** Use one install method per environment.

- Drag-and-drop → `~/.hermes/plugins/dietcode/`
- Pip → entry point + optional copy of broccolidb tree

If both exist, Hermes discovery order may pick unexpected manifest.

---

## Getting detailed diagnostics

```bash
# Hermes logs
hermes logs --level DEBUG

# JSON doctor output (gateway/api)
/dietcode doctor

# Install wizard JSON
python3 ~/.hermes/plugins/dietcode/install.py
```

Report issues with:

- `/dietcode doctor` output (redact paths if needed)
- `hermes plugins list` line for dietcode
- Node version: `node --version`
- Hermes version / fork identity
