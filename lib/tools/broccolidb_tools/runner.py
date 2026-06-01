"""
BroccoliDB Runner — Industrial-grade subprocess execution infrastructure.

All BroccoliDB tools execute TypeScript via `npx tsx`. This module
centralizes that execution with:
  - Structured error categorization (TIMEOUT, MISSING_RUNTIME, etc.)
  - Subprocess timeouts with graduated limits per operation class
  - Output sanitization and JSON extraction from mixed stdout
  - Environment isolation and reproducible cwd management
  - Telemetry hooks for execution duration tracking
"""
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ─── Constants ───
_DEFAULT_TIMEOUT = 60       # 60s for targeted operations
_AUDIT_TIMEOUT = 300        # 5 min for full-repo scans
_BOOTSTRAP_TIMEOUT = 120    # 2 min for bootstrap/warmup operations
_BROCCOLIDB_ROOT = "broccolidb"
_HIVE_SYNC_SCRIPT = "infrastructure/kanban/hive_sync.ts"
_HIVE_DRIFT_SCRIPT = "infrastructure/kanban/hive_drift.ts"
_HIVE_BOARD_INTEL_SCRIPT = "infrastructure/kanban/hive_board_intel.ts"
_HERMES_RPC_SCRIPT = "infrastructure/hermes/hermes_rpc.ts"

# Maximum output size to prevent memory exhaustion from runaway processes
_MAX_OUTPUT_BYTES = 512 * 1024  # 512KB


def resolve_broccolidb_root() -> Optional[str]:
    """Locate broccolidb/ — delegates to ``plugins.dietcode.paths`` when present."""
    try:
        from plugins.dietcode.paths import resolve_broccolidb_root as _plugin_resolve

        return _plugin_resolve()
    except ImportError:
        pass

    rel = Path(_BROCCOLIDB_ROOT)
    if (rel / "package.json").is_file() and (rel / "core").is_dir():
        return str(rel.resolve())
    return None


def resolve_broccolidb_db_path(root: Optional[str] = None) -> Optional[str]:
    """Resolve broccolidb.db path for hive sync (profile/workspace aware)."""
    env_db = os.environ.get("HERMES_BROCCOLIDB_DB", "").strip()
    if env_db:
        return str(Path(env_db).expanduser().resolve())

    try:
        from hermes_cli.config import load_config
        cfg = load_config()
        kanban_cfg = cfg.get("kanban", {}) if isinstance(cfg, dict) else {}
        bdb = kanban_cfg.get("broccolidb", {})
        if isinstance(bdb, dict):
            cfg_db = str(bdb.get("db_path") or "").strip()
            if cfg_db:
                p = Path(cfg_db).expanduser()
                if not p.is_absolute() and root:
                    p = Path(root) / p
                return str(p.resolve())
    except Exception:
        pass

    broot = root or resolve_broccolidb_root()
    if broot:
        ws = os.environ.get("HERMES_KANBAN_WORKSPACE", "").strip()
        if ws:
            ws_db = Path(ws) / "broccolidb.db"
            if ws_db.is_file():
                return str(ws_db.resolve())
        return str((Path(broot).parent / "broccolidb.db").resolve())
    return None


def _broccolidb_root() -> str:
    return resolve_broccolidb_root() or _BROCCOLIDB_ROOT


def check_requirements() -> bool:
    """Check if BroccoliDB is available in the workspace.

    Validates both the package.json and a core module to prevent
    partial installation false-positives.
    """
    root = resolve_broccolidb_root()
    if not root:
        return False
    sync_script = Path(root) / _HIVE_SYNC_SCRIPT
    drift_script = Path(root) / _HIVE_DRIFT_SCRIPT
    intel_script = Path(root) / _HIVE_BOARD_INTEL_SCRIPT
    hermes_rpc = Path(root) / "infrastructure" / "hermes" / "hermes_rpc.ts"
    hermes_handlers = Path(root) / "infrastructure" / "hermes" / "rpc_handlers.ts"
    hermes_oneshot = Path(root) / "infrastructure" / "hermes" / "hermes_oneshot.ts"
    return (
        Path(root, "package.json").is_file()
        and Path(root, "core").is_dir()
        and sync_script.is_file()
        and drift_script.is_file()
        and intel_script.is_file()
        and hermes_rpc.is_file()
        and hermes_handlers.is_file()
        and hermes_oneshot.is_file()
    )


_TS_DB_PREAMBLE = """\
import { setDbPath } from '../infrastructure/db/Config.js';
const __hermesDb = process.env.HERMES_BROCCOLIDB_DB;
if (__hermesDb) setDbPath(__hermesDb);
"""


_ENV_ALLOWLIST_EXACT = frozenset({
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "TZ",
    "NODE_PATH",
    "NODE_OPTIONS",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "CI",
    "NONINTERACTIVE",
})

_ENV_ALLOWLIST_PREFIXES = (
    "HERMES_",
    "JOYZONING_",
    "TERMINAL_",
    "BROCCOLI",
)


def _get_env(*, extra: Optional[dict[str, str]] = None) -> dict:
    """Build a scoped subprocess environment (allowlist — no full os.environ copy)."""
    import shutil

    env: dict[str, str] = {}
    for key, val in os.environ.items():
        if not val:
            continue
        if key in _ENV_ALLOWLIST_EXACT:
            env[key] = val
        elif any(key.startswith(prefix) for prefix in _ENV_ALLOWLIST_PREFIXES):
            env[key] = val

    if extra:
        env.update({k: v for k, v in extra.items() if v})

    root = resolve_broccolidb_root()
    node = shutil.which("node")
    if node:
        node_dir = str(Path(node).resolve().parent)
        existing = env.get("PATH", "")
        if node_dir not in existing.split(os.pathsep):
            env["PATH"] = f"{node_dir}{os.pathsep}{existing}" if existing else node_dir
    if root:
        env.setdefault("HERMES_BROCCOLIDB_ROOT", root)
    db_path = resolve_broccolidb_db_path(root)
    if db_path:
        env.setdefault("HERMES_BROCCOLIDB_DB", db_path)
    root = _broccolidb_root()
    node_path = os.path.join(os.path.abspath(root), "node_modules")
    if os.path.isdir(node_path):
        existing = env.get("NODE_PATH", "")
        env["NODE_PATH"] = f"{node_path}:{existing}" if existing else node_path
    env["CI"] = "1"
    env["NONINTERACTIVE"] = "1"
    return env


def _truncate_output(text: str, max_bytes: int = _MAX_OUTPUT_BYTES) -> str:
    """Truncate output to prevent memory exhaustion."""
    if len(text) > max_bytes:
        return text[:max_bytes] + f"\n[TRUNCATED: output exceeded {max_bytes} bytes]"
    return text


def _extract_json(text: str) -> Optional[dict]:
    """Extract the last valid JSON object from mixed stdout.

    TypeScript processes may emit warnings/logs before JSON output.
    This extracts the last JSON object/array from the output stream.
    """
    if not text.strip():
        return None
    # Try parsing the full output first
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass
    # Find the last JSON object by scanning for { ... } from the end
    for match in reversed(list(re.finditer(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', text, re.DOTALL))):
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            continue
    return None


def _make_result(success: bool, output: str = "", error: str = "",
                 error_code: str = "", duration_ms: int = 0, **extra) -> str:
    """Build a standardized JSON result string.

    All tool outputs follow this contract so the agent can reliably
    parse success/failure regardless of which tool was called.
    """
    result = {"success": success}
    if output:
        result["output"] = _truncate_output(output)
    if error:
        result["error"] = error
    if error_code:
        result["error_code"] = error_code
    if duration_ms > 0:
        result["duration_ms"] = duration_ms
    result.update(extra)
    return json.dumps(result, ensure_ascii=False)


def run_cli(
    args: list,
    timeout: int = _DEFAULT_TIMEOUT,
    *,
    extra_env: Optional[dict[str, str]] = None,
) -> str:
    """Execute a BroccoliDB CLI command and return structured JSON.

    Args:
        args: CLI arguments (e.g. ["audit"], ["status"])
        timeout: Max seconds before killing the subprocess

    Returns:
        JSON string with {success, output, error?, error_code?, duration_ms}
    """
    root = _broccolidb_root()
    cmd = ["npx", "-y", "tsx", f"{root}/cli/index.ts"] + args
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_get_env(extra=extra_env),
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        if result.returncode != 0:
            return _make_result(
                False,
                error=result.stderr.strip() or result.stdout.strip() or f"Exit code {result.returncode}",
                error_code=f"EXIT_{result.returncode}",
                duration_ms=duration_ms,
            )
        return _make_result(True, output=result.stdout.strip(), duration_ms=duration_ms)
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning("[BroccoliDB] CLI timed out after %ds: %s", timeout, " ".join(args))
        return _make_result(
            False,
            error=f"Operation timed out after {timeout}s. Try a more focused query or increase scope.",
            error_code="TIMEOUT",
            duration_ms=duration_ms,
        )
    except FileNotFoundError:
        return _make_result(
            False,
            error="npx/tsx not found. Ensure Node.js 18+ and tsx are installed.",
            error_code="MISSING_RUNTIME",
        )
    except OSError as e:
        return _make_result(False, error=f"OS error: {e}", error_code="OS_ERROR")
    except Exception as e:
        logger.exception("[BroccoliDB] Unexpected error running CLI")
        return _make_result(False, error=str(e), error_code="SUBPROCESS_ERROR")


def run_ts_script(
    script_content: str,
    timeout: int = _DEFAULT_TIMEOUT,
    *,
    db_preamble: bool = True,
) -> str:
    """Execute an inline TypeScript script inside the BroccoliDB context.

    Writes a temp file in broccolidb/scratch/, executes via tsx with
    cwd=broccolidb, then cleans up. Extracts JSON from mixed output.

    Returns:
        JSON string (extracted from output) or error JSON
    """
    root = _broccolidb_root()
    scratch_dir = os.path.join(root, "scratch")
    os.makedirs(scratch_dir, exist_ok=True)

    if db_preamble and "setDbPath" not in script_content:
        script_content = _TS_DB_PREAMBLE + "\n" + script_content

    temp_path = None
    start = time.monotonic()
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".ts", dir=scratch_dir, delete=False, mode="w"
        ) as f:
            f.write(script_content)
            temp_path = f.name

        rel_path = os.path.relpath(temp_path, root)
        result = subprocess.run(
            ["npx", "-y", "tsx", rel_path],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_get_env(),
            cwd=root,
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        if result.returncode != 0:
            # Try extracting structured error from stderr/stdout
            error_text = result.stderr.strip() or result.stdout.strip()
            parsed = _extract_json(error_text)
            if parsed:
                parsed["duration_ms"] = duration_ms
                return json.dumps(parsed, ensure_ascii=False)
            return _make_result(
                False,
                error=_truncate_output(error_text) or f"Exit code {result.returncode}",
                error_code=f"SCRIPT_EXIT_{result.returncode}",
                duration_ms=duration_ms,
            )

        # Extract JSON from potentially mixed output (logs + JSON)
        stdout = result.stdout.strip()
        parsed = _extract_json(stdout)
        if parsed:
            if "duration_ms" not in parsed:
                parsed["duration_ms"] = duration_ms
            return json.dumps(parsed, ensure_ascii=False)
        # Fallback: return raw output
        return _make_result(True, output=_truncate_output(stdout), duration_ms=duration_ms)

    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - start) * 1000)
        logger.warning("[BroccoliDB] TS script timed out after %ds", timeout)
        return _make_result(
            False,
            error=f"Script timed out after {timeout}s. The operation may be too heavy for this codebase size.",
            error_code="TIMEOUT",
            duration_ms=duration_ms,
        )
    except FileNotFoundError:
        return _make_result(False, error="npx/tsx not found.", error_code="MISSING_RUNTIME")
    except Exception as e:
        logger.exception("[BroccoliDB] Unexpected error in TS script")
        return _make_result(False, error=str(e), error_code="SCRIPT_ERROR")
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


def run_cli_interactive(
    args: list,
    stdin_input: str = "n\n",
    timeout: int = _DEFAULT_TIMEOUT,
    *,
    extra_env: Optional[dict[str, str]] = None,
) -> str:
    """Execute a BroccoliDB CLI command that requires stdin interaction.

    Args:
        args: CLI arguments
        stdin_input: String to pipe to stdin (bypasses interactive prompts)
        timeout: Max seconds

    Returns:
        JSON string with {success, output, error?}
    """
    root = _broccolidb_root()
    cmd = ["npx", "-y", "tsx", f"{root}/cli/index.ts"] + args
    start = time.monotonic()
    process = None
    try:
        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=_get_env(extra=extra_env),
        )
        stdout, stderr = process.communicate(input=stdin_input, timeout=timeout)
        duration_ms = int((time.monotonic() - start) * 1000)
        return _make_result(
            success=process.returncode == 0,
            output=stdout.strip(),
            error=stderr.strip() if stderr.strip() else "",
            duration_ms=duration_ms,
        )
    except subprocess.TimeoutExpired:
        if process:
            process.kill()
            process.wait()
        duration_ms = int((time.monotonic() - start) * 1000)
        return _make_result(
            False,
            error=f"Interactive command timed out after {timeout}s",
            error_code="TIMEOUT",
            duration_ms=duration_ms,
        )
    except Exception as e:
        return _make_result(False, error=str(e), error_code="INTERACTIVE_ERROR")


# ─── TypeScript Bootstrap Templates ───
#
# Two templates for different execution contexts:
#   1. _TS_STANDALONE — Direct SpiderEngine/JoyZoning access (no DB needed)
#   2. _TS_CONTEXT    — Full AgentContext with services (needs DB)

_TS_STANDALONE = """\
import * as path from 'path';
import * as fs from 'fs';

async function run() {
  const cwd = process.cwd();
  try {
    %BODY%
  } catch (err) {
    console.log(JSON.stringify({
      success: false,
      error: err instanceof Error ? err.message : String(err),
      error_code: 'RUNTIME_ERROR',
    }));
  }
  process.exit(0);
}
run();
"""

_TS_CONTEXT = """\
import { setDbPath } from './infrastructure/db/Config.js';
import { Connection } from './core/connection.js';
import { AgentContext } from './core/agent-context.js';
import { Workspace } from './core/workspace.js';

const __hermesDb = process.env.HERMES_BROCCOLIDB_DB;
if (__hermesDb) setDbPath(__hermesDb);

async function run() {
  try {
    const conn = new Connection();
    const pool = conn.getPool();
    const userId = 'local-user';
    const workspaceId = 'local-workspace';
    const workspace = new Workspace(pool, userId, workspaceId);
    await workspace.init();
    const context = new AgentContext(workspace, pool, userId);

    %BODY%

    await context.flush();
  } catch (err) {
    console.log(JSON.stringify({
      success: false,
      error: err instanceof Error ? err.message : String(err),
      error_code: 'CONTEXT_ERROR',
    }));
  }
  process.exit(0);
}
run();
"""


def _run_kanban_ts_module(
    script_rel: str,
    env_var: str,
    payload: dict[str, Any],
    *,
    timeout: int = _DEFAULT_TIMEOUT,
    missing_code: str,
    not_found_code: str = "BROCCOLIDB_NOT_FOUND",
) -> str:
    """Execute a kanban infrastructure TypeScript module with a JSON env payload."""
    root = resolve_broccolidb_root()
    if not root:
        return _make_result(
            False,
            skipped=True,
            reason="broccolidb package not found",
            error_code=not_found_code,
        )

    script_path = Path(root) / script_rel
    if not script_path.is_file():
        return _make_result(
            False,
            error=f"missing module: {script_rel}",
            error_code=missing_code,
        )

    env = _get_env()
    env[env_var] = json.dumps(payload, ensure_ascii=False)
    db_path = resolve_broccolidb_db_path(root)
    if db_path:
        env["HERMES_BROCCOLIDB_DB"] = db_path

    start = time.monotonic()
    try:
        result = subprocess.run(
            ["npx", "-y", "tsx", script_rel],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=root,
        )
        duration_ms = int((time.monotonic() - start) * 1000)
        if result.returncode != 0:
            error_text = result.stderr.strip() or result.stdout.strip()
            parsed = _extract_json(error_text)
            if parsed:
                parsed["duration_ms"] = duration_ms
                return json.dumps(parsed, ensure_ascii=False)
            return _make_result(
                False,
                error=_truncate_output(error_text) or f"Exit code {result.returncode}",
                error_code=f"{missing_code}_EXIT",
                duration_ms=duration_ms,
            )

        stdout = result.stdout.strip()
        parsed = _extract_json(stdout)
        if parsed:
            if "duration_ms" not in parsed:
                parsed["duration_ms"] = duration_ms
            return json.dumps(parsed, ensure_ascii=False)
        return _make_result(True, output=_truncate_output(stdout), duration_ms=duration_ms)
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - start) * 1000)
        return _make_result(
            False,
            error=f"Operation timed out after {timeout}s",
            error_code="TIMEOUT",
            duration_ms=duration_ms,
        )
    except FileNotFoundError:
        return _make_result(False, error="npx/tsx not found.", error_code="MISSING_RUNTIME")
    except Exception as e:
        logger.exception("[BroccoliDB] Kanban module failed: %s", script_rel)
        return _make_result(False, error=str(e), error_code=missing_code)


def run_hive_sync(payload: dict[str, Any], timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Execute Kanban-to-hive sync (native RPC when available)."""
    from plugins.dietcode.lib.tools.broccolidb_tools.db_gateway import rpc_available, run_db_rpc

    if rpc_available():
        return run_db_rpc("hive_sync", payload, timeout=timeout)
    return _run_kanban_ts_module(
        _HIVE_SYNC_SCRIPT,
        "KANBAN_HIVE_SYNC_PAYLOAD",
        payload,
        timeout=timeout,
        missing_code="SYNC_MODULE_MISSING",
    )


def run_hive_drift(payload: dict[str, Any], timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Fetch hive_tasks statuses for kanban drift detection."""
    from plugins.dietcode.lib.tools.broccolidb_tools.db_gateway import rpc_available, run_db_rpc

    if rpc_available():
        return run_db_rpc("hive_drift", payload, timeout=timeout)
    return _run_kanban_ts_module(
        _HIVE_DRIFT_SCRIPT,
        "KANBAN_HIVE_DRIFT_PAYLOAD",
        payload,
        timeout=timeout,
        missing_code="DRIFT_MODULE_MISSING",
    )


def run_hive_board_intel(payload: dict[str, Any], timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Fetch bounded BroccoliQ queue/hive metrics for orchestrator board intel."""
    from plugins.dietcode.lib.tools.broccolidb_tools.db_gateway import rpc_available, run_db_rpc

    if rpc_available():
        return run_db_rpc("hive_board_intel", payload, timeout=timeout)
    return _run_kanban_ts_module(
        _HIVE_BOARD_INTEL_SCRIPT,
        "KANBAN_HIVE_BOARD_INTEL_PAYLOAD",
        payload,
        timeout=timeout,
        missing_code="BOARD_INTEL_MODULE_MISSING",
    )


def run_standalone_script(body: str, timeout: int = _DEFAULT_TIMEOUT) -> str:
    """Execute a TypeScript snippet with direct SpiderEngine/JoyZoning access.

    Use this for operations that don't need the full AgentContext (DB, services).
    Faster startup since it skips DB initialization.
    """
    script = _TS_STANDALONE.replace("%BODY%", body)
    return run_ts_script(script, timeout=timeout, db_preamble=False)


def run_agent_context_script(body: str, timeout: int = _BOOTSTRAP_TIMEOUT) -> str:
    """Execute a TypeScript snippet within a fully bootstrapped AgentContext.

    Prefer ``run_agent_rpc`` for known graph ops (persistent worker). This path
    is for one-off scripts (e.g. structural heal) when RPC cannot map the body.
    """
    script = _TS_CONTEXT.replace("%BODY%", body)
    return run_ts_script(script, timeout=timeout)


def run_db_rpc(
    method: str,
    params: Optional[dict[str, Any]] = None,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    """Native BroccoliDB/BroccoliQ RPC (persistent worker when available).

    Prefer this over inline ``run_ts_script`` for hot read/write paths — see
    ``rpc_handlers.ts`` for the canonical method list.
    """
    from plugins.dietcode.lib.tools.broccolidb_tools.db_gateway import run_db_rpc as _rpc

    return _rpc(method, params, timeout=timeout)


def run_db_rpc_batch(
    calls: list[tuple[str, dict[str, Any]]],
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    """Batch multiple native RPC calls in one worker round-trip."""
    from plugins.dietcode.lib.tools.broccolidb_tools.db_gateway import run_db_rpc_batch as _batch

    return _batch(calls, timeout=timeout)
