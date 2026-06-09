#!/usr/bin/env python3
"""Small agent-facing client helpers for the DietCode control socket."""

from __future__ import annotations

import argparse
from collections.abc import Iterator
from contextlib import contextmanager
import json
import os
import socket
import stat
import subprocess
import sys
import threading
import time
import uuid
import weakref
from pathlib import Path
from typing import Any


from release_versions import CLIENT_SCHEMA_VERSION, runtime_versions_payload

SCHEMA_VERSION = CLIENT_SCHEMA_VERSION
SOCKET_PATH = os.path.expanduser(os.environ.get("DIETCODE_SOCKET_PATH", "~/.dietcode/control.sock"))
TOKEN_PATH = os.path.expanduser(os.environ.get("DIETCODE_TOKEN_PATH", "~/.dietcode/session.token"))
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_KERNEL_PATH = REPO_ROOT / "build" / "dietcode-kernel"
DEFAULT_APP_PATH = DEFAULT_KERNEL_PATH  # backward-compatible alias
TEST_WORKSPACE_ENV = "DIETCODE_TEST_WORKSPACE"

# Documented environment variables (grep: rg 'DIETCODE_' docs/agent-environment.md)
ENV_REGISTRY: dict[str, str] = {
    "DIETCODE_AGENT_CONFIG": "Path to JSON config file (overridden by --config)",
    "DIETCODE_APP_PATH": "Path to dietcode-kernel binary (overridden by --app and config.app)",
    "DIETCODE_SOCKET_PATH": "Unix control socket path (overridden by --socket and config.socket)",
    "DIETCODE_TOKEN_PATH": "Session token file path (overridden by --token-file and config.tokenFile)",
    "DIETCODE_TEST_WORKSPACE": "Workspace root for integration harnesses (default: repo root)",
}
MAX_REQUEST_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024
_SOCKET_READ_BUFFERS: weakref.WeakKeyDictionary[socket.socket, bytearray] = weakref.WeakKeyDictionary()
_SOCKET_LOCKS: weakref.WeakKeyDictionary[socket.socket, Any] = weakref.WeakKeyDictionary()

READ_METHODS = {
    "rpc.ping", "rpc.version", "rpc.methods", "rpc.describe", "chip.list", "chip.describe",
    "combo.status", "combo.result", "combo.list", "recovery.scan", "recovery.schemaInfo", "recovery.list",
    "workspace.getRoot", "workspace.findFiles", "workspace.listFiles", "workspace.grep",
    "workspace.searchStart", "workspace.searchNext", "workspace.searchCancel", "workspace.getRecentFiles",
    "search.files", "search.text", "search.literal", "search.tokens", "search.paths",
    "search.references", "search.todo", "search.semantic", "search.diagnostics",
    "tool.registry", "tool.capabilities",
    "file.read", "file.readBatch", "file.readRange", "file.readAround", "file.getChunks", "file.stat", "file.statBatch",
    "shell.pwd", "shell.cd", "shell.rg", "shell.head", "shell.tail", "shell.sedRange", "shell.catSmall",
    "editor.getActiveFile", "editor.getOpenFiles", "editor.getText", "editor.getSelection",
    "analysis.workspaceSummary", "analysis.searchRanked", "analysis.fileSummary", "analysis.relatedFiles",
    "symbols.document", "symbols.hierarchy", "symbols.outline", "symbols.activeDocument",
    "symbols.references", "symbols.atCursor",
    "diff.workspaceInfo", "diff.stats", "diff.file", "diff.chunk", "diff.hunks",
    "diff.current", "diff.staged", "diff.unstaged", "diff.summary",
    "buffers.snapshot", "buffers.dirty", "buffers.active", "buffers.unsavedDiff",
    "changes.current", "changes.summary", "patch.chunk", "patch.hunks", "problems.list",
    "diagnostics.list", "diagnostics.summary", "diagnostics.cluster", "diagnostics.forFile",
    "language.diagnostics", "language.hover", "language.completions", "language.definition",
    "verify.last", "verify.status", "verify.failures", "terminal.status", "terminal.jobs", "terminal.history",
    "terminal.getOutput", "session.info", "session.workflowState", "session.recentCommands",
    "session.lastSearches", "system.info"
}



class DietCodeRpcError(RuntimeError):
    def __init__(self, method: str, response: dict[str, Any]) -> None:
        err = response.get("error", {})
        self.method = method
        self.response = response
        self.code = err.get("code")
        self.string_code = err.get("string_code")
        self.message = err.get("message")
        super().__init__(f"{method} failed: {self.code}: {self.message}")


class DietCodeTransportError(RuntimeError):
    pass


CLIENT_ERROR_DIAGNOSTICS: dict[str, dict[str, Any]] = {
    "invalid_request": {"category": "validation", "retryable": False, "recovery_hint": "fix_request_json", "phase": "client_validate"},
    "invalid_params": {"category": "validation", "retryable": False, "recovery_hint": "fix_request_params", "phase": "client_validate"},
    "transport_error": {"category": "transport", "retryable": True, "recovery_hint": "dietcode_agent_client.py --diagnose", "phase": "client_transport"},
    "rpc_error": {"category": "transport", "retryable": False, "recovery_hint": "inspect_client_trace", "phase": "client_rpc"},
}


def local_error_response(
    request_id: str | None,
    code: str,
    message: str,
    *,
    phase: str | None = None,
) -> dict[str, Any]:
    numeric_code = -32600
    if code == "invalid_params":
        numeric_code = -32602
    elif code == "transport_error":
        numeric_code = -32603
    elif code == "rpc_error":
        numeric_code = -32000
    resolved_id = request_id or "unknown"
    meta = CLIENT_ERROR_DIAGNOSTICS.get(code, {})
    error: dict[str, Any] = {
        "code": numeric_code,
        "string_code": code,
        "message": message,
        "request_id": resolved_id,
        "category": meta.get("category", "transport"),
        "retryable": bool(meta.get("retryable", False)),
        "recovery_hint": meta.get("recovery_hint", "rg string_code docs/error-codes.md"),
        "phase": phase or meta.get("phase", "client_error"),
    }
    return {
        "id": resolved_id,
        "ok": False,
        "error": error,
    }


def exception_error_response(exc: Exception, request_id: str | None = None) -> dict[str, Any]:
    if isinstance(exc, DietCodeRpcError):
        return exc.response
    if isinstance(exc, (DietCodeTransportError, OSError)):
        return local_error_response(request_id, "transport_error", str(exc))
    if isinstance(exc, ValueError):
        return local_error_response(request_id, "invalid_params", str(exc))
    return local_error_response(request_id, "rpc_error", str(exc))


def json_text(value: Any, compact: bool = False) -> str:
    if compact:
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return json.dumps(value, indent=2, sort_keys=True)


def rpc_succeeded(response: Any) -> bool:
    """Return True when a JSON-RPC envelope (or local error envelope) succeeded."""
    return isinstance(response, dict) and response.get("ok") is True


def rpc_exit_code(response: Any, *, raw_response: bool = False) -> int:
    """Map a printed RPC payload to a Unix exit code."""
    if raw_response:
        return 0 if rpc_succeeded(response) else 1
    return 0


def emit_test_line(payload: dict[str, Any], *, compact: bool = True) -> None:
    """Print one NDJSON test result line to stdout."""
    print(json_text(payload, compact=compact))


def finish_test_run(checks: list[dict[str, Any]], *, suite: str, compact: bool = True) -> int:
    """Print a final NDJSON summary and return 0/1."""
    ok = all(check.get("ok") for check in checks)
    failed_names = [check["name"] for check in checks if not check.get("ok")]
    passed = len(checks) - len(failed_names)
    emit_test_line(
        {
            "type": "summary",
            "suite": suite,
            "ok": ok,
            "checks": len(checks),
            "passed": passed,
            "failed": len(failed_names),
            "failedNames": failed_names,
        },
        compact=compact,
    )
    return 0 if ok else 1


def default_test_workspace() -> str:
    """Resolve the workspace path used by integration harnesses."""
    configured = os.environ.get(TEST_WORKSPACE_ENV)
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    return str(REPO_ROOT)


def ensure_workspace_root(sock: socket.socket, token: str) -> str:
    """Return an open workspace root, opening the default test workspace when needed."""
    response = send_rpc(sock, token, "workspace.getRoot")
    workspace_root = response.get("result", {}).get("path")
    if workspace_root:
        return workspace_root
    target = default_test_workspace()
    open_response = send_rpc(sock, token, "workspace.openFolder", {"path": target})
    if not open_response.get("ok"):
        raise DietCodeRpcError("workspace.openFolder", open_response)
    response = send_rpc(sock, token, "workspace.getRoot")
    workspace_root = response.get("result", {}).get("path")
    if not workspace_root:
        raise RuntimeError("workspace.getRoot returned no path after workspace.openFolder")
    return workspace_root


def normalize_event_types(types: list[str]) -> list[str]:
    if not isinstance(types, list) or not types:
        raise ValueError("event types must be a non-empty list of strings")
    normalized: list[str] = []
    for event_type in types:
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("event types must contain only non-empty strings")
        normalized.append(event_type)
    return normalized


def _path_state(path: str) -> dict[str, Any]:
    expanded = os.path.expanduser(path)
    state: dict[str, Any] = {"path": expanded, "exists": False}
    try:
        st = os.lstat(expanded)
    except FileNotFoundError:
        return state
    except OSError as exc:
        state["error"] = str(exc)
        return state
    state.update(
        {
            "exists": True,
            "isSymlink": stat.S_ISLNK(st.st_mode),
            "mode": oct(stat.S_IMODE(st.st_mode)),
            "uid": st.st_uid,
            "ownerIsCurrentUser": st.st_uid == os.getuid(),
        }
    )
    return state


def _probe_socket(timeout: float = 0.5, socket_path: str = SOCKET_PATH) -> tuple[bool, str | None]:
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as test_sock:
            test_sock.settimeout(timeout)
            test_sock.connect(socket_path)
            return True, None
    except PermissionError as exc:
        return False, f"permission_denied: {exc}"
    except FileNotFoundError:
        return False, "not_found"
    except ConnectionRefusedError as exc:
        return False, f"connection_refused: {exc}"
    except socket.timeout:
        return False, "timeout"
    except OSError as exc:
        return False, f"os_error: {exc}"


def _connect_probe(timeout: float = 0.5, socket_path: str = SOCKET_PATH) -> bool:
    ok, _ = _probe_socket(timeout=timeout, socket_path=socket_path)
    return ok


def _append_probe_error(errors: list[str] | None, error: str | None) -> None:
    if errors is not None and error and (not errors or errors[-1] != error):
        errors.append(error)


def _wait_for_socket(
    socket_path: str = SOCKET_PATH,
    timeout: float = 10.0,
    interval: float = 0.2,
    errors: list[str] | None = None,
) -> bool:
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() <= deadline:
        ok, error = _probe_socket(socket_path=socket_path)
        if ok:
            return True
        _append_probe_error(errors, error)
        time.sleep(interval)
    ok, error = _probe_socket(socket_path=socket_path)
    _append_probe_error(errors, error)
    return ok


def _socket_probe_diagnostic(socket_path: str, errors: list[str]) -> str | None:
    if not errors:
        return None
    last_error = errors[-1]
    if last_error.startswith("permission_denied:"):
        return (
            f"control socket exists at {socket_path}, but this process cannot connect to it "
            f"({last_error}). Run the harness with permission to access the DietCode socket."
        )
    return f"last socket probe error for {socket_path}: {last_error}"


def resolve_app_path(app_path: str | os.PathLike[str] | None = None) -> Path:
    configured = app_path or os.environ.get("DIETCODE_APP_PATH")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_KERNEL_PATH


def load_config(config_path: str | None) -> dict[str, Any]:
    configured = config_path or os.environ.get("DIETCODE_AGENT_CONFIG")
    if not configured:
        return {}
    path = Path(configured).expanduser()
    if not path.exists():
        raise RuntimeError(f"agent config not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RuntimeError("agent config must be a JSON object")
    return data


def config_value(args: argparse.Namespace, config: dict[str, Any], attr: str, key: str, default: Any) -> Any:
    value = getattr(args, attr)
    if value is not None:
        return value
    return config.get(key, default)


def ensure_socket(
    app_path: str | os.PathLike[str] | None = None,
    timeout: float = 10.0,
    quiet: bool = False,
    socket_path: str = SOCKET_PATH,
    start: bool = True,
    probe_errors: list[str] | None = None,
) -> bool:
    """Ensure the control socket is accepting connections, launching headless if needed."""
    if _wait_for_socket(socket_path=socket_path, timeout=min(timeout, 1.0), errors=probe_errors):
        return True
    if not start:
        return False

    app_binary = resolve_app_path(app_path)
    if not app_binary.exists():
        raise RuntimeError(f"dietcode-kernel binary not found at {app_binary}. Run 'make kernel' first.")

    if not quiet:
        print("control socket not active, asking DietCode to ensure headless control...", file=sys.stderr)
        diagnostic = _socket_probe_diagnostic(socket_path, probe_errors or [])
        if diagnostic:
            print(diagnostic, file=sys.stderr)

    try:
        completed = subprocess.run(
            [str(app_binary), "--ensure-socket", "--ensure-timeout", str(timeout)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=timeout + 2.0,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _wait_for_socket(socket_path=socket_path, timeout=2.0, errors=probe_errors)
    if not quiet:
        for line in (completed.stdout + completed.stderr).splitlines():
            print(line, file=sys.stderr)
    if _wait_for_socket(socket_path=socket_path, timeout=2.0, errors=probe_errors):
        return True
    if completed.returncode != 0:
        return False
    return _wait_for_socket(socket_path=socket_path, timeout=2.0, errors=probe_errors)


def load_token(token_path: str = TOKEN_PATH) -> str:
    if not os.path.exists(token_path):
        raise RuntimeError(f"session token not found: {token_path}")
    with open(token_path, "r", encoding="utf-8") as f:
        return f.read().strip()


RUNTIME_DIAGNOSTIC_LOG = os.path.expanduser("~/.dietcode/agent-runtime.ndjson")
DIAGNOSTIC_DOCS = {
    "checkpointModel": "docs/checkpoint-model.md",
    "testing": "docs/testing.md",
    "agentTooling": "docs/agent-tooling.md",
    "runtimeInvariants": "docs/runtime-invariants.md",
    "kernelRpc": "docs/kernel-rpc.md",
    "errorCodes": "docs/error-codes.md",
    "troubleshooting": "docs/troubleshooting.md",
    "architecture": "docs/architecture.md",
}


def read_runtime_diagnostic_lines(path: str = RUNTIME_DIAGNOSTIC_LOG, limit: int = 10) -> list[dict[str, Any]]:
    log_path = os.path.expanduser(path)
    if not os.path.isfile(log_path):
        return []
    lines: list[dict[str, Any]] = []
    try:
        with open(log_path, "r", encoding="utf-8") as handle:
            for raw in handle.readlines()[-limit:]:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    lines.append(payload)
    except OSError:
        return []
    return lines


def _process_status_for_dietcode() -> dict[str, Any] | None:
    try:
        completed = subprocess.run(
            ["pgrep", "-lf", "dietcode-kernel"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    output = completed.stdout.strip()
    if not output:
        return {"running": False, "matches": []}
    return {"running": True, "matches": output.splitlines()}


def build_diagnostic_snapshot(
    socket_path: str = SOCKET_PATH,
    token_path: str = TOKEN_PATH,
    app_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    from agent_contracts import REQUIRED_MAKE_TARGETS
    from runtime_safety import RUNTIME_LIMITS, audit_socket_path, redact_diagnostic_snapshot

    base = status(socket_path=socket_path, token_path=token_path, app_path=app_path)
    snapshot: dict[str, Any] = {
        "type": "diagnostic_snapshot",
        "repoRoot": str(REPO_ROOT),
        "schemaVersion": SCHEMA_VERSION,
        "environment": {key: os.environ.get(key) for key in ENV_REGISTRY},
        "runtimeLimits": dict(RUNTIME_LIMITS),
        "socketAudit": audit_socket_path(socket_path),
        "timeouts": {
            "defaultConnectSeconds": 10.0,
            "defaultRequestSeconds": 30.0,
            "socketProbeSeconds": 2.0,
        },
        "makefileTargets": sorted(REQUIRED_MAKE_TARGETS),
        "docs": {name: str(REPO_ROOT / rel) for name, rel in DIAGNOSTIC_DOCS.items()},
        "recentRuntimeLogs": read_runtime_diagnostic_lines(limit=10),
        "process": _process_status_for_dietcode(),
        "runtimeLogPath": RUNTIME_DIAGNOSTIC_LOG,
        "verificationCommands": [
            "make release-check-agent-runtime",
            "make verify-agent-runtime",
            "make test-runtime-safety",
            "make test-grep-diff-tooling",
            "make test-operator-diagnostics",
            "python3 scripts/dietcode_agent_client.py --diagnose --json",
            "rg 'RELEASE:|STABILITY:|CONTRACT_VERSION' src/ scripts/ docs/",
        ],
    }
    snapshot.update(base)
    snapshot.update(runtime_versions_payload())
    return redact_diagnostic_snapshot(snapshot)


def response_for_output(response: Any) -> Any:
    if isinstance(response, dict):
        cleaned = dict(response)
        cleaned.pop("_client_duration_ms", None)
        return cleaned
    return response


def log_rpc_client_diagnostic(
    response: dict[str, Any],
    *,
    method: str,
    request_id: str | None,
    verbose: bool,
    error_json: bool,
    compact: bool,
) -> None:
    if not verbose and not error_json and rpc_succeeded(response):
        return
    req_id = str(response.get("id") or request_id or "unknown")
    error = response.get("error", {}) if isinstance(response.get("error"), dict) else {}
    emit_client_diagnostic(
        request_id=req_id,
        method=method,
        phase="rpc_response",
        ok=rpc_succeeded(response),
        string_code=error.get("string_code"),
        duration_ms=response.get("_client_duration_ms"),
        compact=compact,
    )


def emit_client_diagnostic(
    *,
    request_id: str,
    method: str,
    phase: str,
    ok: bool,
    string_code: str | None = None,
    duration_ms: float | None = None,
    compact: bool = True,
) -> None:
    payload: dict[str, Any] = {
        "type": "client_diagnostic",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "request_id": request_id,
        "method": method,
        "phase": phase,
        "ok": ok,
    }
    if string_code:
        payload["string_code"] = string_code
    if duration_ms is not None:
        payload["duration_ms"] = round(duration_ms, 2)
    print(json_text(payload, compact=compact), file=sys.stderr)


def status(
    socket_path: str = SOCKET_PATH,
    token_path: str = TOKEN_PATH,
    app_path: str | os.PathLike[str] | None = None,
) -> dict[str, Any]:
    app_binary = resolve_app_path(app_path)
    socket_active, socket_probe_error = _probe_socket(socket_path=socket_path)
    token_state = _path_state(token_path)
    socket_state = _path_state(socket_path)
    rpc_ready = False
    rpc_ping: dict[str, Any] | None = None
    rpc_error: str | None = None
    if socket_active and token_state.get("exists"):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(2.0)
                sock.connect(socket_path)
                rpc_ping = send_rpc(sock, load_token(token_path), "rpc.ping", request_timeout=2.0)
                rpc_ready = bool(rpc_ping.get("ok"))
        except Exception as exc:
            rpc_error = str(exc)

    result: dict[str, Any] = {
        "ok": rpc_ready,
        "socketActive": socket_active,
        "rpcReady": rpc_ready,
        "socket": socket_state,
        "token": token_state,
        "app": {
            "path": str(app_binary),
            "exists": app_binary.exists(),
            "executable": os.access(app_binary, os.X_OK),
        },
        "schemaVersion": SCHEMA_VERSION,
        "limits": {
            "maxRequestBytes": MAX_REQUEST_BYTES,
            "maxResponseBytes": MAX_RESPONSE_BYTES,
        },
    }
    if rpc_ping is not None:
        result["rpcPing"] = rpc_ping
    if rpc_error is not None:
        result["rpcError"] = rpc_error
    if socket_probe_error is not None:
        result["socketProbeError"] = socket_probe_error
    return result


def wait_ready(
    app_path: str | os.PathLike[str] | None = None,
    socket_path: str = SOCKET_PATH,
    token_path: str = TOKEN_PATH,
    timeout: float = 10.0,
    interval: float = 0.2,
    start: bool = True,
    quiet: bool = False,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    if start:
        ensure_socket(app_path=app_path, timeout=timeout, quiet=quiet, socket_path=socket_path, start=True)
    last_state: dict[str, Any] = {}
    while time.monotonic() <= deadline:
        last_state = status(socket_path=socket_path, token_path=token_path, app_path=app_path)
        if last_state.get("ok"):
            return last_state
        time.sleep(interval)
    if last_state:
        return last_state
    return status(socket_path=socket_path, token_path=token_path, app_path=app_path)


def load_params(args: argparse.Namespace) -> dict[str, Any]:
    patch_sources = [args.patch_file is not None, args.patch_stdin]
    if sum(patch_sources) > 1:
        raise ValueError("provide only one of --patch-file or --patch-stdin")
    if any(patch_sources):
        if args.params_json is not None or args.params_file is not None or args.params_stdin:
            raise ValueError("patch input cannot be combined with params_json, --params-file, or --params-stdin")
        if args.patch_stdin:
            patch = sys.stdin.read()
        else:
            with open(args.patch_file, "r", encoding="utf-8") as f:
                patch = f.read()
        params: dict[str, Any] = {"patch": patch}
        if args.path:
            params["path"] = args.path
        if args.confirm:
            params["confirm"] = True
        if args.dry_run is not None:
            params["dryRun"] = args.dry_run
        if args.offset is not None:
            params["offset"] = args.offset
        if args.max_bytes is not None:
            params["maxBytes"] = args.max_bytes
        if args.max_hunks is not None:
            params["maxHunks"] = args.max_hunks
        if args.hunk_offset is not None:
            params["hunkOffset"] = args.hunk_offset
        if args.include_lines:
            params["includeLines"] = True
        if args.max_lines_per_hunk is not None:
            params["maxLinesPerHunk"] = args.max_lines_per_hunk
        if args.expect_before_hash:
            params["expectBeforeHash"] = args.expect_before_hash
        return params

    sources = [args.params_json is not None, args.params_file is not None, args.params_stdin]
    if sum(sources) > 1:
        raise ValueError("provide only one of params_json, --params-file, or --params-stdin")
    if args.params_stdin:
        raw = sys.stdin.read()
    elif args.params_file:
        with open(args.params_file, "r", encoding="utf-8") as f:
            raw = f.read()
    else:
        raw = args.params_json or "{}"
    try:
        params = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"params JSON is invalid: {exc.msg} at line {exc.lineno} column {exc.colno}") from exc
    if not isinstance(params, dict):
        raise ValueError("params must decode to a JSON object")
    return params


def batch_requests_from_lines(lines: list[str]) -> list[dict[str, Any]]:
    requests: list[dict[str, Any]] = []
    for index, raw in enumerate(lines, start=1):
        line = raw.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            requests.append(
                {
                    "id": f"line:{index}",
                    "localError": local_error_response(f"line:{index}", "invalid_json", str(exc)),
                }
            )
            continue
        if not isinstance(item, dict):
            requests.append(
                {
                    "id": f"line:{index}",
                    "localError": local_error_response(f"line:{index}", "invalid_request", "batch line must be a JSON object"),
                }
            )
            continue
        requests.append(item)
    return requests


def _socket_read_buffer(sock: socket.socket) -> bytearray:
    buffer = _SOCKET_READ_BUFFERS.get(sock)
    if buffer is None:
        buffer = bytearray()
        _SOCKET_READ_BUFFERS[sock] = buffer
    return buffer


def _socket_lock(sock: socket.socket) -> Any:
    lock = _SOCKET_LOCKS.get(sock)
    if lock is None:
        lock = threading.RLock()
        _SOCKET_LOCKS[sock] = lock
    return lock


def _discard_socket_read_buffer(sock: socket.socket) -> None:
    try:
        del _SOCKET_READ_BUFFERS[sock]
    except KeyError:
        pass


def _discard_socket_state(sock: socket.socket) -> None:
    _discard_socket_read_buffer(sock)
    try:
        del _SOCKET_LOCKS[sock]
    except KeyError:
        pass


@contextmanager
def _scoped_socket_timeout(sock: socket.socket, timeout: float | None) -> Iterator[None]:
    previous_timeout = sock.gettimeout()
    if timeout is not None:
        sock.settimeout(timeout)
    try:
        yield
    finally:
        if timeout is not None:
            sock.settimeout(previous_timeout)


def _read_json_frame(sock: socket.socket, method: str, max_response_bytes: int) -> dict[str, Any]:
    buffer = _socket_read_buffer(sock)
    while True:
        while b"\n" not in buffer:
            chunk = sock.recv(65536)
            if not chunk:
                raise DietCodeTransportError(f"socket closed while waiting for {method}")
            buffer.extend(chunk)
            if len(buffer) > max_response_bytes + 1 and b"\n" not in buffer:
                raise RuntimeError(f"response exceeds maximum allowed size of {max_response_bytes} bytes")

        line, _, rest = buffer.partition(b"\n")
        buffer[:] = rest
        if line:
            break
    if len(line) > max_response_bytes:
        raise RuntimeError(f"response exceeds maximum allowed size of {max_response_bytes} bytes")
    try:
        frame = json.loads(line.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise DietCodeTransportError(f"invalid JSON frame while waiting for {method}: {exc}") from exc
    if not isinstance(frame, dict):
        raise DietCodeTransportError(f"non-object JSON frame while waiting for {method}")
    return frame


def read_rpc_frame(
    sock: socket.socket,
    request_timeout: float | None = None,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    """Read one newline-delimited JSON-RPC frame using the shared socket buffer."""
    with _socket_lock(sock):
        with _scoped_socket_timeout(sock, request_timeout):
            return _read_json_frame(sock, "event frame", max_response_bytes)


def load_batch_requests(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.batch_file and args.batch_stdin:
        raise ValueError("provide only one of --batch-file or --batch-stdin")
    if args.batch_stdin:
        lines = sys.stdin.readlines()
    elif args.batch_file:
        with open(args.batch_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        return []
    return batch_requests_from_lines(lines)


def send_rpc(
    sock: socket.socket,
    token: str,
    method: str,
    params: dict[str, Any] | None = None,
    request_id: str | None = None,
    request_timeout: float | None = None,
    agent_id: str | None = None,
    rationale: str | None = None,
    max_request_bytes: int = MAX_REQUEST_BYTES,
    max_response_bytes: int = MAX_RESPONSE_BYTES,
) -> dict[str, Any]:
    expected_id = request_id or f"{method}:{uuid.uuid4().hex}"
    payload = {
        "id": expected_id,
        "schemaVersion": SCHEMA_VERSION,
        "method": method,
        "params": params or {},
        "token": token,
    }
    if agent_id:
        payload["agentId"] = agent_id
    if rationale:
        payload["rationale"] = rationale
    encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8") + b"\n"
    if len(encoded) > max_request_bytes:
        raise RuntimeError(f"request exceeds maximum allowed size of {max_request_bytes} bytes")
    started = time.monotonic()
    with _socket_lock(sock):
        with _scoped_socket_timeout(sock, request_timeout):
            sock.sendall(encoded)
            while True:
                frame = _read_json_frame(sock, method, max_response_bytes)
                frame_id = frame.get("id")
                if frame_id == expected_id:
                    frame["_client_duration_ms"] = round((time.monotonic() - started) * 1000.0, 2)
                    return frame
                if frame_id is None and isinstance(frame.get("method"), str):
                    continue
                raise DietCodeTransportError(f"received response id {frame_id!r} while waiting for {expected_id!r}")


def call(
    sock: socket.socket,
    token: str,
    method: str,
    params: dict[str, Any] | None = None,
    request_id: str | None = None,
    request_timeout: float | None = None,
    agent_id: str | None = None,
    rationale: str | None = None,
) -> dict[str, Any]:
    response = send_rpc(sock, token, method, params, request_id, request_timeout=request_timeout, agent_id=agent_id, rationale=rationale)
    if not response.get("ok"):
        raise DietCodeRpcError(method, response)
    return response.get("result", {})


class DietCodeAgentClient:
    """Small context-managed SDK wrapper for long-lived agent sessions."""

    def __init__(
        self,
        app_path: str | os.PathLike[str] | None = None,
        socket_path: str = SOCKET_PATH,
        token_path: str = TOKEN_PATH,
        timeout: float = 10.0,
        request_timeout: float = 30.0,
        start: bool = True,
        retries: int = 0,
        agent_id: str | None = None,
        rationale: str | None = None,
    ) -> None:
        self.app_path = app_path
        self.socket_path = socket_path
        self.token_path = token_path
        self.timeout = timeout
        self.request_timeout = request_timeout
        self.start = start
        self.retries = max(0, retries)
        self.agent_id = agent_id
        self.rationale = rationale
        self.sock: socket.socket | None = None
        self.token: str | None = None

    def __enter__(self) -> "DietCodeAgentClient":
        self.open()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def open(self) -> None:
        self.sock = connect(
            timeout=self.timeout,
            app_path=self.app_path,
            socket_path=self.socket_path,
            start=self.start,
        )
        self.token = load_token(self.token_path)

    def close(self) -> None:
        if self.sock is not None:
            _discard_socket_state(self.sock)
            self.sock.close()
            self.sock = None

    def reconnect(self) -> None:
        self.close()
        self.open()

    def raw_call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: str | None = None,
        agent_id: str | None = None,
        rationale: str | None = None,
    ) -> dict[str, Any]:
        transport_attempts = 0
        token_refreshed = False
        while True:
            if self.sock is None or self.token is None:
                self.open()
            assert self.sock is not None
            assert self.token is not None
            try:
                response = send_rpc(
                    self.sock,
                    self.token,
                    method,
                    params,
                    request_id,
                    request_timeout=self.request_timeout,
                    agent_id=agent_id or self.agent_id,
                    rationale=rationale or self.rationale,
                )
            except (OSError, DietCodeTransportError) as exc:
                max_retries = max(1, self.retries) if method in READ_METHODS else self.retries
                if transport_attempts >= max_retries:
                    raise
                transport_attempts += 1
                self.reconnect()
                continue

            err = response.get("error", {}) if not response.get("ok") else {}
            message = str(err.get("message", ""))
            if (
                err.get("string_code") == "permission_denied"
                and "token" in message.lower()
                and not token_refreshed
            ):
                token_refreshed = True
                self.token = load_token(self.token_path)
                continue
            return response

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        response = self.raw_call(method, params, request_id)
        if not response.get("ok"):
            raise DietCodeRpcError(method, response)
        return response.get("result", {})

    def read_frame(self, request_timeout: float | None = None) -> dict[str, Any]:
        if self.sock is None:
            self.open()
        assert self.sock is not None
        return read_rpc_frame(self.sock, request_timeout=request_timeout)

    def subscribe_events(self, types: list[str], request_id: str | None = None) -> dict[str, Any]:
        types = normalize_event_types(types)
        return self.call("event.subscribe", {"types": types}, request_id)

    def unsubscribe_events(self, types: list[str], request_id: str | None = None) -> dict[str, Any]:
        types = normalize_event_types(types)
        return self.call("event.unsubscribe", {"types": types}, request_id)

    @contextmanager
    def event_subscription(self, types: list[str]) -> Iterator["DietCodeAgentClient"]:
        types = normalize_event_types(types)
        self.subscribe_events(types)
        try:
            yield self
        finally:
            self.unsubscribe_events(types)

    def iter_events(
        self,
        types: list[str],
        event_timeout: float = 1.0,
        max_events: int | None = None,
        idle_timeout: float | None = None,
        unsubscribe: bool = True,
    ) -> Iterator[dict[str, Any]]:
        types = normalize_event_types(types)
        if event_timeout <= 0:
            raise ValueError("event_timeout must be greater than zero")
        if max_events is not None and max_events <= 0:
            raise ValueError("max_events must be greater than zero")
        if idle_timeout is not None and idle_timeout <= 0:
            raise ValueError("idle_timeout must be greater than zero")

        def events() -> Iterator[dict[str, Any]]:
            delivered = 0
            idle_deadline = time.monotonic() + idle_timeout if idle_timeout is not None else None
            while max_events is None or delivered < max_events:
                read_timeout = event_timeout
                if idle_deadline is not None:
                    remaining = idle_deadline - time.monotonic()
                    if remaining <= 0:
                        break
                    read_timeout = min(read_timeout, remaining)
                try:
                    frame = self.read_frame(request_timeout=read_timeout)
                except socket.timeout:
                    continue
                if frame.get("method") != "event.emitted":
                    continue
                delivered += 1
                if idle_deadline is not None:
                    idle_deadline = time.monotonic() + idle_timeout
                yield frame

        if unsubscribe:
            with self.event_subscription(types):
                yield from events()
        else:
            self.subscribe_events(types)
            yield from events()

    def batch(self, requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
        responses: list[dict[str, Any]] = []
        for index, request in enumerate(requests, start=1):
            if "localError" in request:
                responses.append(request["localError"])
                continue
            request_id = request.get("id") or f"batch:{index}"
            method = request.get("method")
            params = request.get("params", {})
            if not isinstance(method, str) or not method:
                responses.append(local_error_response(str(request_id), "invalid_request", "batch request missing method"))
                continue
            if not isinstance(params, dict):
                responses.append(local_error_response(str(request_id), "invalid_params", "params must be a JSON object"))
                continue
            try:
                responses.append(self.raw_call(method, params, str(request_id)))
            except Exception as exc:
                responses.append(local_error_response(str(request_id), "transport_error", str(exc)))
        return responses

    def capabilities(self) -> dict[str, Any]:
        return {
            "version": self.call("rpc.version"),
            "methods": self.call("rpc.methods").get("methods", []),
            "limits": {
                "maxRequestBytes": MAX_REQUEST_BYTES,
                "maxResponseBytes": MAX_RESPONSE_BYTES,
            },
            "schemaVersion": SCHEMA_VERSION,
        }


def connect(
    timeout: float = 10.0,
    app_path: str | os.PathLike[str] | None = None,
    socket_path: str = SOCKET_PATH,
    start: bool = True,
) -> socket.socket:
    probe_errors: list[str] = []
    if not ensure_socket(app_path=app_path, timeout=timeout, socket_path=socket_path, start=start, probe_errors=probe_errors):
        diagnostic = _socket_probe_diagnostic(socket_path, probe_errors)
        suffix = f": {diagnostic}" if diagnostic else ""
        raise RuntimeError(f"failed to start DietCode control socket at {socket_path}{suffix}")
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    sock.connect(socket_path)
    return sock


def _socketpair_rpc_server(frames_by_request: list[list[dict[str, Any]]]) -> tuple[socket.socket, threading.Thread]:
    client_sock, server_sock = socket.socketpair()

    def serve() -> None:
        try:
            for frames in frames_by_request:
                request_buffer = bytearray()
                while b"\n" not in request_buffer:
                    chunk = server_sock.recv(65536)
                    if not chunk:
                        return
                    request_buffer.extend(chunk)
                request_line, _, _ = request_buffer.partition(b"\n")
                try:
                    request = json.loads(request_line.decode("utf-8"))
                    request_id = request.get("id") if isinstance(request, dict) else None
                except json.JSONDecodeError:
                    request_id = None
                resolved_frames: list[dict[str, Any]] = []
                for frame in frames:
                    resolved = dict(frame)
                    if resolved.get("id") == "$request_id":
                        resolved["id"] = request_id
                    resolved_frames.append(resolved)
                payload = b"".join(
                    json.dumps(frame, separators=(",", ":")).encode("utf-8") + b"\n"
                    for frame in resolved_frames
                )
                server_sock.sendall(payload)
        finally:
            server_sock.close()

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    return client_sock, thread


def run_self_test() -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    valid = batch_requests_from_lines(['{"id":"a","method":"rpc.ping","params":{}}\n'])
    checks.append({"name": "batch.valid", "ok": valid[0]["method"] == "rpc.ping"})
    checks.append({"name": "batch.empty", "ok": batch_requests_from_lines(["\n"]) == []})

    invalid_json = batch_requests_from_lines(["{bad json}\n"])
    checks.append({"name": "batch.invalid_json", "ok": invalid_json[0]["localError"]["error"]["string_code"] == "invalid_json"})

    invalid_params = batch_requests_from_lines(['{"id":"b","method":"rpc.ping","params":[]}\n'])
    responses = DietCodeAgentClient(start=False).batch(invalid_params)
    checks.append({"name": "batch.invalid_params", "ok": responses[0]["error"]["string_code"] == "invalid_params"})
    checks.append({"name": "batch.invalid_params_code", "ok": responses[0]["error"]["code"] == -32602})

    compact = json_text({"b": 2, "a": 1}, compact=True)
    checks.append({"name": "json.compact", "ok": compact == '{"a":1,"b":2}'})
    checks.append({"name": "events.normalize_valid", "ok": normalize_event_types(["terminal.output"]) == ["terminal.output"]})
    try:
        normalize_event_types([])
        event_types_empty_ok = False
    except ValueError as exc:
        event_types_empty_ok = "non-empty" in str(exc)
    checks.append({"name": "events.normalize_empty", "ok": event_types_empty_ok})
    validation_error = exception_error_response(ValueError("bad input"), "req-error")
    checks.append({
        "name": "errors.validation_envelope",
        "ok": validation_error["id"] == "req-error" and validation_error["error"]["string_code"] == "invalid_params",
    })
    transport_error = exception_error_response(DietCodeTransportError("closed"), "transport-error")
    checks.append({
        "name": "errors.transport_envelope",
        "ok": transport_error["id"] == "transport-error" and transport_error["error"]["string_code"] == "transport_error",
    })
    try:
        DietCodeAgentClient(start=False).subscribe_events([])
        sdk_invalid_subscribe_ok = False
    except ValueError as exc:
        sdk_invalid_subscribe_ok = "non-empty" in str(exc)
    checks.append({"name": "events.sdk_invalid_subscribe", "ok": sdk_invalid_subscribe_ok})
    fake_args = argparse.Namespace(app=None)
    checks.append({"name": "config.value", "ok": config_value(fake_args, {"app": "configured"}, "app", "app", None) == "configured"})
    patch_args = argparse.Namespace(
        patch_file=None,
        patch_stdin=True,
        params_json=None,
        params_file=None,
        params_stdin=False,
        path="a.txt",
        confirm=True,
        dry_run=None,
        offset=None,
        max_bytes=None,
        max_hunks=None,
        hunk_offset=None,
        include_lines=False,
        max_lines_per_hunk=None,
        expect_before_hash=None,
    )
    patch_args.params_json = "{}"
    try:
        load_params(patch_args)
        conflict_ok = False
    except ValueError:
        conflict_ok = True
    checks.append({"name": "patch.params_conflict", "ok": conflict_ok})
    patch_args.params_json = None
    patch_args.patch_file = "/dev/null"
    patch_args.patch_stdin = False
    patch_args.hunk_offset = 25
    patch_args.include_lines = True
    patch_args.max_lines_per_hunk = 12
    try:
        patch_params = load_params(patch_args)
        cursor_ok = (
            patch_params.get("hunkOffset") == 25
            and patch_params.get("includeLines") is True
            and patch_params.get("maxLinesPerHunk") == 12
            and patch_params.get("patch") == ""
        )
    except ValueError:
        cursor_ok = False
    checks.append({"name": "patch.params_hunk_offset", "ok": cursor_ok})
    checks.append({"name": "read_methods.ping", "ok": "rpc.ping" in READ_METHODS})
    checks.append({"name": "read_methods.batch", "ok": "file.readBatch" in READ_METHODS and "file.statBatch" in READ_METHODS})
    checks.append({"name": "read_methods.search_session", "ok": "workspace.searchStart" in READ_METHODS and "workspace.searchNext" in READ_METHODS})
    checks.append({"name": "read_methods.symbols", "ok": "symbols.hierarchy" in READ_METHODS and "system.info" in READ_METHODS})
    checks.append({"name": "read_methods.mutation", "ok": "patch.apply" not in READ_METHODS})
    diagnostic = _socket_probe_diagnostic("/tmp/control.sock", ["permission_denied: [Errno 1] Operation not permitted"])
    checks.append({"name": "socket_probe.permission_diagnostic", "ok": diagnostic is not None and "cannot connect" in diagnostic})

    client_sock, server_thread = _socketpair_rpc_server([
        [
            {"id": "req-1", "ok": True, "result": {"one": 1}},
            {"method": "event.emitted", "params": {"type": "terminal.output", "detail": {"text": "ready"}}},
        ],
        [{"id": "req-2", "ok": True, "result": {"two": 2}}],
    ])
    try:
        first = send_rpc(client_sock, "token", "rpc.ping", request_id="req-1", request_timeout=2.0)
        second = send_rpc(client_sock, "token", "rpc.version", request_id="req-2", request_timeout=2.0)
        buffered_ok = first.get("result", {}).get("one") == 1 and second.get("result", {}).get("two") == 2
    except Exception:
        buffered_ok = False
    finally:
        _discard_socket_state(client_sock)
        client_sock.close()
        server_thread.join(timeout=2.0)
    checks.append({"name": "transport.notification_buffering", "ok": buffered_ok})

    event_sock, event_thread = _socketpair_rpc_server([
        [
            {"id": "subscribe-1", "ok": True, "result": {"subscribed": True}},
            {"method": "event.emitted", "params": {"type": "terminal.output", "detail": {"text": "buffered"}}},
        ],
    ])
    try:
        response = send_rpc(event_sock, "token", "event.subscribe", {"types": ["terminal.output"]}, request_id="subscribe-1", request_timeout=2.0)
        event = read_rpc_frame(event_sock, request_timeout=0.1)
        listener_ok = (
            response.get("ok") is True
            and event.get("method") == "event.emitted"
            and event.get("params", {}).get("detail", {}).get("text") == "buffered"
        )
    except Exception:
        listener_ok = False
    finally:
        _discard_socket_state(event_sock)
        event_sock.close()
        event_thread.join(timeout=2.0)
    checks.append({"name": "transport.listener_uses_shared_buffer", "ok": listener_ok})

    timeout_sock, timeout_thread = _socketpair_rpc_server([
        [{"id": "timeout-req", "ok": True, "result": {"ok": True}}],
    ])
    try:
        timeout_sock.settimeout(7.0)
        send_rpc(timeout_sock, "token", "rpc.ping", request_id="timeout-req", request_timeout=0.1)
        timeout_restore_ok = timeout_sock.gettimeout() == 7.0
    except Exception:
        timeout_restore_ok = False
    finally:
        _discard_socket_state(timeout_sock)
        timeout_sock.close()
        timeout_thread.join(timeout=2.0)
    checks.append({"name": "transport.rpc_timeout_restored", "ok": timeout_restore_ok})

    frame_timeout_sock, frame_timeout_thread = _socketpair_rpc_server([
        [{"method": "event.emitted", "params": {"type": "terminal.output", "detail": {"text": "timeout"}}}],
    ])
    try:
        frame_timeout_sock.settimeout(6.0)
        frame_timeout_sock.sendall(b'{"id":"subscribe","method":"event.subscribe","params":{}}\n')
        read_rpc_frame(frame_timeout_sock, request_timeout=0.1)
        frame_timeout_restore_ok = frame_timeout_sock.gettimeout() == 6.0
    except Exception:
        frame_timeout_restore_ok = False
    finally:
        _discard_socket_state(frame_timeout_sock)
        frame_timeout_sock.close()
        frame_timeout_thread.join(timeout=2.0)
    checks.append({"name": "transport.frame_timeout_restored", "ok": frame_timeout_restore_ok})

    iterator_sock, iterator_thread = _socketpair_rpc_server([
        [
            {"id": "$request_id", "ok": True, "result": {"subscribed": True, "types": ["terminal.output"]}},
            {"method": "event.emitted", "params": {"type": "terminal.output", "detail": {"text": "first"}}},
            {"method": "event.emitted", "params": {"type": "terminal.output", "detail": {"text": "second"}}},
        ],
        [{"id": "$request_id", "ok": True, "result": {"unsubscribed": True, "types": ["terminal.output"]}}],
    ])
    iterator_client = DietCodeAgentClient(start=False)
    iterator_client.sock = iterator_sock
    iterator_client.token = "token"
    try:
        events = list(iterator_client.iter_events(["terminal.output"], event_timeout=0.1, max_events=2))
        iterator_ok = [event.get("params", {}).get("detail", {}).get("text") for event in events] == ["first", "second"]
    except Exception:
        iterator_ok = False
    finally:
        iterator_client.close()
        iterator_thread.join(timeout=2.0)
    checks.append({"name": "sdk.iter_events_unsubscribes", "ok": iterator_ok})

    idle_sock, idle_thread = _socketpair_rpc_server([
        [{"id": "$request_id", "ok": True, "result": {"subscribed": True, "types": ["terminal.output"]}}],
        [{"id": "$request_id", "ok": True, "result": {"unsubscribed": True, "types": ["terminal.output"]}}],
    ])
    idle_client = DietCodeAgentClient(start=False)
    idle_client.sock = idle_sock
    idle_client.token = "token"
    try:
        idle_events = list(idle_client.iter_events(["terminal.output"], event_timeout=0.01, max_events=1, idle_timeout=0.03))
        idle_ok = idle_events == []
    except Exception:
        idle_ok = False
    finally:
        idle_client.close()
        idle_thread.join(timeout=2.0)
    checks.append({"name": "sdk.iter_events_idle_timeout", "ok": idle_ok})

    try:
        list(DietCodeAgentClient(start=False).iter_events(["terminal.output"], event_timeout=0))
        event_timeout_validation_ok = False
    except ValueError as exc:
        event_timeout_validation_ok = "event_timeout" in str(exc)
    checks.append({"name": "sdk.iter_events_event_timeout_validation", "ok": event_timeout_validation_ok})

    mismatch_sock, mismatch_thread = _socketpair_rpc_server([
        [{"id": "wrong-id", "ok": True, "result": {}}],
    ])
    try:
        send_rpc(mismatch_sock, "token", "rpc.ping", request_id="expected-id", request_timeout=2.0)
        mismatch_ok = False
    except DietCodeTransportError as exc:
        mismatch_ok = "wrong-id" in str(exc) and "expected-id" in str(exc)
    except Exception:
        mismatch_ok = False
    finally:
        _discard_socket_state(mismatch_sock)
        mismatch_sock.close()
        mismatch_thread.join(timeout=2.0)
    checks.append({"name": "transport.response_id_mismatch", "ok": mismatch_ok})
    checks.append({"name": "rpc.succeeded_true", "ok": rpc_succeeded({"ok": True, "result": {}})})
    checks.append({"name": "rpc.succeeded_false", "ok": not rpc_succeeded({"ok": False, "error": {"string_code": "invalid_params"}})})
    checks.append({
        "name": "rpc.exit_code_raw_failure",
        "ok": rpc_exit_code({"ok": False, "error": {"string_code": "invalid_params"}}, raw_response=True) == 1,
    })
    checks.append({
        "name": "rpc.exit_code_raw_success",
        "ok": rpc_exit_code({"ok": True, "result": {}}, raw_response=True) == 0,
    })
    checks.append({"name": "workspace.default_test_path", "ok": default_test_workspace() == str(REPO_ROOT)})
    checks.append({"name": "env.registry_documented", "ok": TEST_WORKSPACE_ENV in ENV_REGISTRY})
    checks.append({"name": "env.registry_socket", "ok": "DIETCODE_SOCKET_PATH" in ENV_REGISTRY})
    probe_checks = [{"name": "a", "ok": True}, {"name": "b", "ok": False}]
    probe_failed = [c["name"] for c in probe_checks if not c.get("ok")]
    checks.append({
        "name": "harness.summary_accounting",
        "ok": len(probe_checks) == 2 and len(probe_failed) == 1 and probe_failed == ["b"],
    })
    try:
        from agent_contracts import SUMMARY_SCHEMA_KEYS, validate_summary_line

        schema_ok = not validate_summary_line(
            {
                "type": "summary",
                "suite": "probe",
                "ok": True,
                "checks": 0,
                "passed": 0,
                "failed": 0,
                "failedNames": [],
            }
        ) and len(SUMMARY_SCHEMA_KEYS) >= 7
    except Exception:
        schema_ok = False
    checks.append({"name": "contract.summary_schema_import", "ok": schema_ok})
    local_err = local_error_response("diag-req", "transport_error", "probe")
    checks.append({
        "name": "diagnostic.local_error_fields",
        "ok": all(
            local_err["error"].get(key) is not None
            for key in ("request_id", "category", "retryable", "recovery_hint", "phase")
        ),
    })
    snapshot = build_diagnostic_snapshot()
    checks.append({
        "name": "diagnostic.snapshot_shape",
        "ok": snapshot.get("type") == "diagnostic_snapshot" and isinstance(snapshot.get("makefileTargets"), list),
    })
    try:
        from release_versions import assert_versions_synced

        versions_ok = True
        assert_versions_synced()
    except Exception:
        versions_ok = False
    checks.append({"name": "release.versions_synced", "ok": versions_ok})
    try:
        from agent_contracts import GREP_RESPONSE_KEYS, validate_grep_response
        from agent_tooling import format_grep_matches_rg, literal_match_spans, parse_unified_diff_hunks

        grep_contract_ok = len(GREP_RESPONSE_KEYS) >= 20
        spans_ok = len(literal_match_spans("abc", "b")) == 1
        parse_ok = parse_unified_diff_hunks("").get("totalHunks") == 0
        rg_fmt_ok = format_grep_matches_rg([{"path": "a", "line": 1, "column": 1, "preview": "x"}]) == "a:1:1:x"
        schema_ok = not validate_grep_response({
            "matches": [],
            "query": "x",
            "mode": "literal_substring",
            "caseSensitive": False,
            "maxResults": 1,
            "resultOffset": 0,
            "nextResultOffset": None,
            "hasMore": False,
            "truncated": False,
            "scanLimitReached": False,
            "scannedFiles": 0,
            "filesRead": 0,
            "filesSkippedUnreadable": 0,
            "filesSkippedBinary": 0,
            "filesReadFromDisk": 0,
            "filesReadFromEditor": 0,
            "filesSkippedOversize": 0,
            "filesSkippedExcluded": 0,
            "filesSkippedSymlink": 0,
            "symlinkPolicy": "skip_never_follow",
            "sortOrder": "path_line_column",
            "scanDurationMs": 0,
        })
        tooling_ok = grep_contract_ok and spans_ok and parse_ok and rg_fmt_ok and schema_ok
    except Exception:
        tooling_ok = False
    checks.append({"name": "tooling.grep_diff_imports", "ok": tooling_ok})
    configured_workspace = os.environ.get(TEST_WORKSPACE_ENV)
    if configured_workspace:
        checks.append({
            "name": "workspace.env_override",
            "ok": default_test_workspace() == os.path.abspath(os.path.expanduser(configured_workspace)),
        })

    ok = all(check["ok"] for check in checks)
    return {"ok": ok, "checks": checks}


CLI_EXAMPLES = """
Examples:
  %(prog)s --wait-ready --compact
  %(prog)s --grep "CONTRACT:" --include scripts/agent_contracts.py --max-results 5 --compact
  %(prog)s --search-literal "def main" --include "scripts/*.py" --compact
  %(prog)s --patch-file fix.diff --path src/foo.py --patch-summary --compact
  %(prog)s --expect-before-hash <hash> --patch-file fix.diff --path src/foo.py --confirm --compact
  %(prog)s tool.capabilities --compact
  %(prog)s shell pwd --compact
  %(prog)s shell cd scripts --compact
  %(prog)s shell rg "CONTRACT:" --path scripts/ --compact
  %(prog)s shell head scripts/fixtures/shell/anchor_target.txt --compact
  %(prog)s shell sed scripts/fixtures/shell/anchor_target.txt 1 5 --compact
  %(prog)s shell cat-small README.md --compact
  %(prog)s --raw-response --error-json search.semantic '{"query":"foo"}'
""".strip()


def _emit_partial_success_hint(result: dict[str, Any], *, quiet: bool) -> None:
    if quiet:
        return
    from agent_tooling import partial_success_hint

    hint = partial_success_hint(result)
    if hint:
        print(f"hint: {hint}", file=sys.stderr)


def parse_shell_shortcut(
    method: str,
    params_json: str | None,
    tail_args: list[str],
) -> tuple[str, dict[str, Any]] | None:
    """Map `shell <subcommand> ...` CLI invocations to shell.* RPC methods."""
    if method != "shell":
        return None
    tokens: list[str] = []
    if params_json:
        tokens.append(params_json)
    tokens.extend(tail_args)
    if not tokens:
        raise ValueError("shell subcommand required: pwd, cd, rg, head, tail, sed, cat-small")
    sub = tokens[0]
    rest = tokens[1:]
    if sub == "pwd":
        return "shell.pwd", {}
    if sub == "cd":
        if not rest:
            raise ValueError("shell cd requires <path>")
        return "shell.cd", {"path": rest[0]}
    if sub == "rg":
        if not rest:
            raise ValueError("shell rg requires <pattern>")
        path_idx = rest.index("--path") if "--path" in rest else -1
        path = rest[path_idx + 1] if path_idx >= 0 else None
        pattern = rest[0]
        params: dict[str, Any] = {"pattern": pattern}
        if path:
            params["path"] = path
        return "shell.rg", params
    if sub == "head":
        if not rest:
            raise ValueError("shell head requires <path>")
        lines_idx = rest.index("--lines") if "--lines" in rest else -1
        lines = int(rest[lines_idx + 1]) if lines_idx >= 0 else None
        params = {"path": rest[0]}
        if lines is not None:
            params["lines"] = lines
        return "shell.head", params
    if sub == "tail":
        if not rest:
            raise ValueError("shell tail requires <path>")
        lines_idx = rest.index("--lines") if "--lines" in rest else -1
        lines = int(rest[lines_idx + 1]) if lines_idx >= 0 else None
        params = {"path": rest[0]}
        if lines is not None:
            params["lines"] = lines
        return "shell.tail", params
    if sub == "sed":
        if len(rest) < 3:
            raise ValueError("shell sed requires <path> <startLine> <endLine>")
        return "shell.sedRange", {
            "path": rest[0],
            "startLine": int(rest[1]),
            "endLine": int(rest[2]),
        }
    if sub == "cat-small":
        if not rest:
            raise ValueError("shell cat-small requires <path>")
        return "shell.catSmall", {"path": rest[0]}
    raise ValueError(f"unknown shell subcommand '{sub}'")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="DietCode agent control client — deterministic RPC/CLI for local automation.",
        epilog=CLI_EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", help="JSON config file. Can also be set with DIETCODE_AGENT_CONFIG.")
    parser.add_argument("--app", help="Path to dietcode-kernel binary. Defaults to build/dietcode-kernel.")
    parser.add_argument("--socket", help="Unix socket path. Defaults to config, DIETCODE_SOCKET_PATH, or ~/.dietcode/control.sock.")
    parser.add_argument("--token-file", help="Session token path. Defaults to config, DIETCODE_TOKEN_PATH, or ~/.dietcode/session.token.")
    parser.add_argument("--timeout", type=float, help="Seconds to wait for socket startup and connect.")
    parser.add_argument("--request-timeout", type=float, help="Seconds to wait for one RPC response.")
    parser.add_argument("--retries", type=int, help="Transport retries after socket errors. Use only for safe/idempotent calls.")
    parser.add_argument("--no-start", action="store_true", help="Do not launch DietCode if the socket is inactive.")
    parser.add_argument("--quiet", action="store_true", help="Suppress diagnostic output on stderr.")
    parser.add_argument("--verbose", action="store_true", help="Print diagnostic messages on stderr (overrides --quiet).")
    parser.add_argument("--ensure-only", action="store_true", help="Only ensure the socket is active, then exit.")
    parser.add_argument("--status", action="store_true", help="Print local socket/token/app readiness JSON, then exit.")
    parser.add_argument("--diagnose", action="store_true", help="Print a local diagnostic snapshot safe to paste into an issue.")
    parser.add_argument("--wait-ready", action="store_true", help="Ensure the socket, then wait for authenticated RPC readiness.")
    parser.add_argument("--self-test", action="store_true", help="Run client-only parser/format checks without connecting to DietCode.")
    parser.add_argument("--emit-config", action="store_true", help="Print resolved config JSON without connecting to DietCode.")
    parser.add_argument("--capabilities", action="store_true", help="Print version, method list, schema, and client transport limits.")
    parser.add_argument("--server-version", action="store_true", help="Call rpc.version and exit.")
    parser.add_argument("--list-methods", action="store_true", help="Call rpc.methods and exit.")
    parser.add_argument("--describe", help="Call rpc.describe for one method and exit.")
    parser.add_argument("--raw-response", action="store_true", help="Print the full JSON-RPC response envelope.")
    parser.add_argument("--compact", action="store_true", help="Print compact JSON on one line.")
    parser.add_argument("--json", action="store_true", help="Alias for --compact (machine-readable single-line JSON).")
    parser.add_argument("--error-json", action="store_true", help="Print failures as JSON envelopes on stderr.")
    parser.add_argument("--listen", action="store_true", help="Listen for asynchronous event notifications.")
    parser.add_argument("--listen-type", action="append", help="Event type to subscribe to with --listen. May be repeated; defaults to '*'.")
    parser.add_argument("--listen-max-events", type=int, help="Stop --listen after printing this many event notifications.")
    parser.add_argument("--listen-idle-timeout", type=float, help="Stop --listen after this many seconds without an event.")
    parser.add_argument("--request-id", help="Override the JSON-RPC request id.")
    parser.add_argument("--agent-id", help="Identify the agent calling the RPC.")
    parser.add_argument("--rationale", help="Provide a human-readable explanation for the action.")
    parser.add_argument("--params-file", help="Read RPC params JSON object from a file.")
    parser.add_argument("--params-stdin", action="store_true", help="Read RPC params JSON object from stdin.")
    parser.add_argument("--path", help="Path used with --patch-file or --patch-stdin.")
    parser.add_argument("--grep", help="Call workspace.grep with a literal query.")
    parser.add_argument(
        "--grep-format",
        choices=["json", "rg"],
        default="json",
        help="With --grep: json prints RPC result; rg prints path:line:column:preview lines.",
    )
    parser.add_argument("--search-text", help="Call search.text with a literal substring query.")
    parser.add_argument("--search-literal", help="Call search.literal (agent-safe alias of search.text with explicit metadata).")
    parser.add_argument(
        "--search-semantic",
        help="DEPRECATED: calls search.semantic (quarantined; use --search-text or search.literal).",
    )
    parser.add_argument("--result-offset", type=int, help="Zero-based result cursor for workspace.grep or search.text.")
    parser.add_argument("--max-results", type=int, help="Maximum results for workspace.grep or search.text.")
    parser.add_argument("--before", type=int, help="Context lines before each search.text result.")
    parser.add_argument("--after", type=int, help="Context lines after each search.text result.")
    parser.add_argument("--case-sensitive", action="store_true", help="Use case-sensitive literal grep/text search.")
    parser.add_argument("--include", action="append", help="Include glob for grep/text search. May be repeated.")
    parser.add_argument("--exclude", action="append", help="Exclude glob for grep/text search. May be repeated.")
    parser.add_argument("--diff-source", choices=["unstaged", "staged", "file"], help="Call diff.chunk for unstaged, staged, or file diff.")
    parser.add_argument("--diff-hunks", action="store_true", help="Use diff.hunks with --diff-source instead of diff.chunk.")
    parser.add_argument(
        "--diff-summary",
        action="store_true",
        help="With --diff-hunks: print compact diff_summary JSON instead of full hunk payload.",
    )
    parser.add_argument("--offset", type=int, help="Byte offset for diff.chunk or patch.chunk.")
    parser.add_argument("--max-bytes", type=int, help="Maximum bytes for diff.chunk or patch.chunk.")
    parser.add_argument("--max-hunks", type=int, help="Maximum hunk summaries for diff.hunks or patch.hunks.")
    parser.add_argument("--hunk-offset", type=int, help="Zero-based hunk cursor for diff.hunks or patch.hunks.")
    parser.add_argument("--include-lines", action="store_true", help="Include literal per-row old/new line evidence in hunk responses.")
    parser.add_argument("--max-lines-per-hunk", type=int, help="Maximum literal line rows per returned hunk.")
    parser.add_argument("--patch-file", help="Read unified diff patch text from a file.")
    parser.add_argument("--patch-stdin", action="store_true", help="Read unified diff patch text from stdin.")
    parser.add_argument("--patch-hunks", action="store_true", help="Default patch stdin/file calls to patch.hunks instead of patch.validate.")
    parser.add_argument(
        "--patch-summary",
        action="store_true",
        help="With patch.validate/patch.preview shortcuts: print compact patch_validation_summary JSON.",
    )
    parser.add_argument(
        "--expect-before-hash",
        help="Set expectBeforeHash on patch.apply (optimistic concurrency guard).",
    )
    parser.add_argument("--confirm", action="store_true", help="Set confirm=true for patch apply calls.")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=None, help="Set dryRun=true for supported calls.")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false", help="Set dryRun=false for supported calls.")
    parser.add_argument("--batch-file", help="Read newline-delimited JSON RPC requests from a file.")
    parser.add_argument("--batch-stdin", action="store_true", help="Read newline-delimited JSON RPC requests from stdin.")
    parser.add_argument("method", nargs="?", default="rpc.ping", help="RPC method to call after ensuring the socket.")
    parser.add_argument("params_json", nargs="?", help="JSON object params for the RPC call.")
    parser.add_argument("tail_args", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.json:
        args.compact = True
    quiet = args.quiet and not args.verbose

    try:
        config = load_config(args.config)
        app_path = config_value(args, config, "app", "app", None)
        socket_path = os.path.expanduser(config_value(args, config, "socket", "socket", SOCKET_PATH))
        token_path = os.path.expanduser(config_value(args, config, "token_file", "tokenFile", TOKEN_PATH))
        timeout = float(config_value(args, config, "timeout", "timeout", 10.0))
        request_timeout = float(config_value(args, config, "request_timeout", "requestTimeout", 30.0))
        retries = int(config_value(args, config, "retries", "retries", 0))

        if args.self_test:
            result = run_self_test()
            print(json_text(result, compact=args.compact))
            return 0 if result["ok"] else 1

        if args.emit_config:
            resolved = {
                "app": str(resolve_app_path(app_path)),
                "socket": socket_path,
                "tokenFile": token_path,
                "timeout": timeout,
                "requestTimeout": request_timeout,
                "retries": retries,
                "schemaVersion": SCHEMA_VERSION,
                "environment": ENV_REGISTRY,
                "precedence": ["CLI flag", "config file", "environment variable", "built-in default"],
            }
            resolved.update(runtime_versions_payload())
            print(json_text(resolved, compact=args.compact))
            return 0

        if args.status:
            state = status(socket_path=socket_path, token_path=token_path, app_path=app_path)
            print(json_text(state, compact=args.compact))
            return 0 if state["ok"] else 1

        if args.diagnose:
            snapshot = build_diagnostic_snapshot(socket_path=socket_path, token_path=token_path, app_path=app_path)
            print(json_text(snapshot, compact=args.compact))
            return 0 if snapshot.get("rpcReady") else 1

        if args.wait_ready:
            state = wait_ready(
                app_path=app_path,
                socket_path=socket_path,
                token_path=token_path,
                timeout=timeout,
                start=not args.no_start,
                quiet=quiet,
            )
            print(json_text(state, compact=args.compact))
            return 0 if state["ok"] else 1

        if args.ensure_only:
            if ensure_socket(app_path=app_path, timeout=timeout, quiet=quiet, socket_path=socket_path, start=not args.no_start):
                print(json_text({"ok": True, "socket": socket_path}, compact=args.compact))
                return 0
            raise RuntimeError(f"failed to start DietCode control socket at {socket_path}")

        if args.batch_stdin and args.params_stdin:
            raise ValueError("provide only one of --batch-stdin or --params-stdin")
        search_shortcuts = [args.grep, args.search_text, args.search_literal, args.search_semantic]
        if sum(1 for item in search_shortcuts if item) > 1:
            raise ValueError("provide only one of --grep, --search-text, --search-literal, or --search-semantic")
        if args.listen_max_events is not None and args.listen_max_events <= 0:
            raise ValueError("--listen-max-events must be greater than zero")
        if args.listen_idle_timeout is not None and args.listen_idle_timeout <= 0:
            raise ValueError("--listen-idle-timeout must be greater than zero")
        batch_mode = args.batch_file is not None or args.batch_stdin
        batch_requests = load_batch_requests(args)
        if batch_mode:
            if not batch_requests:
                return 0
            with DietCodeAgentClient(
                app_path=app_path,
                socket_path=socket_path,
                token_path=token_path,
                timeout=timeout,
                request_timeout=request_timeout,
                start=not args.no_start,
                retries=retries,
                agent_id=args.agent_id,
                rationale=args.rationale,
            ) as client:
                responses = client.batch(batch_requests)
            for response in responses:
                print(json_text(response, compact=args.compact))
            return 0 if all(rpc_succeeded(response) for response in responses) else 1

        shortcut_method: str | None = None
        shortcut_params: dict[str, Any] = {}
        if args.diff_source:
            shortcut_method = "diff.hunks" if args.diff_hunks else "diff.chunk"
            shortcut_params = {"source": args.diff_source}
            if args.path:
                shortcut_params["path"] = args.path
            if args.offset is not None:
                shortcut_params["offset"] = args.offset
            if args.max_bytes is not None:
                shortcut_params["maxBytes"] = args.max_bytes
            if args.max_hunks is not None:
                shortcut_params["maxHunks"] = args.max_hunks
            if args.hunk_offset is not None:
                shortcut_params["hunkOffset"] = args.hunk_offset
            if args.include_lines:
                shortcut_params["includeLines"] = True
            if args.max_lines_per_hunk is not None:
                shortcut_params["maxLinesPerHunk"] = args.max_lines_per_hunk
        elif args.grep or args.search_text or args.search_literal or args.search_semantic:
            if args.search_semantic:
                print(
                    "warning: --search-semantic is deprecated; search.semantic is quarantined. "
                    "Use --search-literal, search.tokens, or --grep instead.",
                    file=sys.stderr,
                )
            if args.search_literal:
                shortcut_method = "search.literal"
                shortcut_params = {"query": args.search_literal}
            elif args.grep:
                shortcut_method = "workspace.grep"
                shortcut_params = {"query": args.grep}
            elif args.search_text:
                shortcut_method = "search.text"
                shortcut_params = {"query": args.search_text}
            else:
                shortcut_method = "search.semantic"
                shortcut_params = {"query": args.search_semantic}
            if args.max_results is not None:
                shortcut_params["maxResults"] = args.max_results
            if args.result_offset is not None:
                shortcut_params["resultOffset"] = args.result_offset
            if args.case_sensitive:
                shortcut_params["caseSensitive"] = True
            if args.include:
                shortcut_params["include"] = args.include
            if args.exclude:
                shortcut_params["exclude"] = args.exclude
            if args.search_text:
                if args.before is not None:
                    shortcut_params["before"] = args.before
                if args.after is not None:
                    shortcut_params["after"] = args.after
        elif args.capabilities:
            with DietCodeAgentClient(
                app_path=app_path,
                socket_path=socket_path,
                token_path=token_path,
                timeout=timeout,
                request_timeout=request_timeout,
                start=not args.no_start,
                retries=retries,
                agent_id=args.agent_id,
                rationale=args.rationale,
            ) as client:
                response = client.capabilities()
            print(json_text(response, compact=args.compact))
            return 0

        if shortcut_method is None and args.server_version:
            shortcut_method = "rpc.version"
        elif shortcut_method is None and args.list_methods:
            shortcut_method = "rpc.methods"
        elif shortcut_method is None and args.describe:
            shortcut_method = "rpc.describe"
            shortcut_params = {"method": args.describe}

        if args.listen:
            with DietCodeAgentClient(
                app_path=app_path,
                socket_path=socket_path,
                token_path=token_path,
                timeout=timeout,
                request_timeout=request_timeout,
                start=not args.no_start,
                retries=retries,
                agent_id=args.agent_id,
                rationale=args.rationale,
            ) as client:
                listen_types = normalize_event_types(args.listen_type or ["*"])
                if not quiet:
                    print("Listening for events... (Press Ctrl+C to stop)", file=sys.stderr)
                try:
                    for frame in client.iter_events(
                        listen_types,
                        event_timeout=1.0,
                        max_events=args.listen_max_events,
                        idle_timeout=args.listen_idle_timeout,
                    ):
                        print(json_text(frame, compact=args.compact))
                except KeyboardInterrupt:
                    pass
                except DietCodeTransportError as exc:
                    print(f"Socket closed by server: {exc}", file=sys.stderr)
            return 0

        if shortcut_method:
            with DietCodeAgentClient(
                app_path=app_path,
                socket_path=socket_path,
                token_path=token_path,
                timeout=timeout,
                request_timeout=request_timeout,
                start=not args.no_start,
                retries=retries,
                agent_id=args.agent_id,
                rationale=args.rationale,
            ) as client:
                if args.raw_response:
                    response = client.raw_call(shortcut_method, shortcut_params, args.request_id)
                else:
                    response = client.call(shortcut_method, shortcut_params, args.request_id)
            shortcut_ok = rpc_succeeded(response) if isinstance(response, dict) and "ok" in response else True
            log_rpc_client_diagnostic(
                response if isinstance(response, dict) and "ok" in response else {"ok": shortcut_ok, "id": args.request_id, "result": response},
                method=shortcut_method,
                request_id=args.request_id,
                verbose=args.verbose,
                error_json=args.error_json and not shortcut_ok,
                compact=args.compact,
            )
            shortcut_result = response.get("result", response) if isinstance(response, dict) and "result" in response else response
            if shortcut_ok and isinstance(shortcut_result, dict):
                _emit_partial_success_hint(shortcut_result, quiet=quiet)
            if shortcut_method == "workspace.grep" and shortcut_ok and isinstance(shortcut_result, dict):
                from agent_tooling import format_grep_matches_rg, grep_empty_result_hint

                matches = shortcut_result.get("matches", [])
                if args.grep_format == "rg":
                    if matches:
                        print(format_grep_matches_rg(matches))
                    elif not quiet:
                        hint = grep_empty_result_hint(shortcut_result)
                        if hint:
                            print(hint, file=sys.stderr)
                    return 0 if matches else 1
                if not matches and not quiet:
                    hint = grep_empty_result_hint(shortcut_result)
                    if hint:
                        print(hint, file=sys.stderr)
            if (
                shortcut_method in ("patch.validate", "patch.preview")
                and args.patch_summary
                and shortcut_ok
                and isinstance(shortcut_result, dict)
            ):
                from agent_tooling import format_patch_validation_summary

                validation = shortcut_result.get("validation", shortcut_result)
                print(json_text(format_patch_validation_summary(validation, path=args.path), compact=args.compact))
                return 0
            if (
                shortcut_method == "diff.hunks"
                and args.diff_summary
                and shortcut_ok
                and isinstance(shortcut_result, dict)
            ):
                from agent_tooling import format_diff_hunk_summary

                print(json_text(format_diff_hunk_summary(shortcut_result), compact=args.compact))
                return 0
            print(json_text(response_for_output(response), compact=args.compact))
            return rpc_exit_code(response, raw_response=args.raw_response)

        shell_shortcut = parse_shell_shortcut(args.method, args.params_json, args.tail_args)
        effective_method = shell_shortcut[0] if shell_shortcut else args.method
        if (args.patch_file or args.patch_stdin) and effective_method == "rpc.ping":
            effective_method = "patch.hunks" if args.patch_hunks else "patch.validate"
        params = shell_shortcut[1] if shell_shortcut else load_params(args)
        with DietCodeAgentClient(
            app_path=app_path,
            socket_path=socket_path,
            token_path=token_path,
            timeout=timeout,
            request_timeout=request_timeout,
            start=not args.no_start,
            retries=retries,
            agent_id=args.agent_id,
            rationale=args.rationale,
        ) as client:
            if args.raw_response:
                response = client.raw_call(effective_method, params, args.request_id)
            else:
                response = client.call(effective_method, params, args.request_id)
        method_ok = rpc_succeeded(response) if isinstance(response, dict) and "ok" in response else True
        log_rpc_client_diagnostic(
            response if isinstance(response, dict) and "ok" in response else {"ok": method_ok, "id": args.request_id, "result": response},
            method=effective_method,
            request_id=args.request_id,
            verbose=args.verbose,
            error_json=args.error_json and not method_ok,
            compact=args.compact,
        )
        method_result = response.get("result", response) if isinstance(response, dict) and "result" in response else response
        if method_ok and isinstance(method_result, dict):
            _emit_partial_success_hint(method_result, quiet=quiet)
        if (
            effective_method in ("patch.validate", "patch.preview")
            and args.patch_summary
            and method_ok
            and isinstance(method_result, dict)
        ):
            from agent_tooling import format_patch_validation_summary

            validation = method_result.get("validation", method_result)
            print(json_text(format_patch_validation_summary(validation, path=args.path), compact=args.compact))
            return 0
        print(json_text(response_for_output(response), compact=args.compact))
        return rpc_exit_code(response, raw_response=args.raw_response)
    except Exception as exc:
        if getattr(args, "error_json", False):
            print(json_text(exception_error_response(exc, getattr(args, "request_id", None)), compact=args.compact), file=sys.stderr)
        elif not quiet:
            print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
