"""
BroccoliDB native RPC gateway — persistent tsx worker for hot read/write paths.

Centralizes BroccoliDB/BroccoliQ operations that previously spawned a fresh
``npx tsx`` subprocess per call. Falls back to ``hermes_oneshot.ts`` when the
worker is unavailable or ``HERMES_BROCCOLIDB_RPC=0``.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import select
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from plugins.dietcode.lib.tools.broccolidb_tools.db_native import (
    RPC_METHODS,
    RPC_VERSION,
    _HERMES_ONESHOT_SCRIPT,
    _HERMES_RPC_SCRIPT,
)  # RPC_METHODS synced with rpc_handlers.ts
from plugins.dietcode.lib.tools.broccolidb_tools.runner import (
    _DEFAULT_TIMEOUT,
    _extract_json,
    _get_env,
    _make_result,
    resolve_broccolidb_root,
)

logger = logging.getLogger(__name__)

_READY_TIMEOUT = 15  # ready line is immediate; DB warm happens on first RPC
_FIRST_RPC_EXTRA_TIMEOUT = 180  # first call may run schema self-heal

_gateway_lock = threading.Lock()
_gateway_instance: Optional["BroccoliDbGateway"] = None


def rpc_available() -> bool:
    """True when native Hermes RPC modules exist and RPC is not disabled."""
    if os.environ.get("HERMES_BROCCOLIDB_RPC", "1").strip().lower() in ("0", "false", "no"):
        return False
    root = resolve_broccolidb_root()
    if not root:
        return False
    rpc_dir = Path(root) / "infrastructure" / "hermes"
    return (
        (rpc_dir / "hermes_rpc.ts").is_file()
        and (rpc_dir / "rpc_handlers.ts").is_file()
        and (rpc_dir / "hermes_oneshot.ts").is_file()
    )


def _tsx_bin(root: str) -> list[str]:
    """Return tsx executable prefix (local bin preferred over npx)."""
    local_tsx = Path(root) / "node_modules" / ".bin" / "tsx"
    if local_tsx.is_file():
        return [str(local_tsx)]
    return ["npx", "-y", "tsx"]


def _pin_node_on_path(env: dict[str, str]) -> None:
    """Ensure subprocess uses the same Node as ``which node`` (native ABI match)."""
    node = shutil.which("node")
    if not node:
        return
    node_dir = str(Path(node).resolve().parent)
    existing = env.get("PATH", "")
    if node_dir not in existing.split(os.pathsep):
        env["PATH"] = f"{node_dir}{os.pathsep}{existing}" if existing else node_dir


def _is_fatal_worker_error(message: str) -> bool:
    """Errors where retrying the worker cannot help (native module / ABI)."""
    lower = message.lower()
    return (
        "node_module_version" in lower
        or "better_sqlite3" in lower
        or "was compiled against a different node" in lower
        or "invalid elf header" in lower
    )


def _attach_stderr_drainer(proc: subprocess.Popen[str]) -> None:
    """Prevent stderr pipe fill from deadlocking the worker during long schema work."""

    def _drain() -> None:
        if not proc.stderr:
            return
        try:
            for line in proc.stderr:
                text = line.rstrip()
                if text:
                    logger.debug("[BroccoliDB worker] %s", text)
        except Exception:
            pass

    threading.Thread(
        target=_drain,
        daemon=True,
        name="broccolidb-rpc-stderr",
    ).start()


def run_oneshot_rpc(
    method: str,
    params: Optional[dict[str, Any]] = None,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    """Cold path: single dispatch via hermes_oneshot.ts (no persistent worker)."""
    if method not in RPC_METHODS:
        return _make_result(
            False,
            error=f"unsupported RPC method: {method}",
            error_code="UNKNOWN_METHOD",
        )
    root = resolve_broccolidb_root()
    if not root:
        return _make_result(False, error="BroccoliDB root not found", error_code="BROCCOLIDB_NOT_FOUND")
    script = Path(root) / _HERMES_ONESHOT_SCRIPT
    if not script.is_file():
        return _make_result(False, error="hermes_oneshot.ts missing", error_code="ONESHOT_MISSING")

    cmd = _tsx_bin(root) + [_HERMES_ONESHOT_SCRIPT, method, json.dumps(params or {}, ensure_ascii=False)]
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_get_env(),
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
                error=_truncate(error_text) or f"exit {result.returncode}",
                error_code=f"ONESHOT_EXIT_{result.returncode}",
                duration_ms=duration_ms,
            )
        stdout = result.stdout.strip()
        parsed = _extract_json(stdout)
        if parsed:
            parsed = dict(parsed)
            parsed.setdefault("success", True)
            parsed["oneshot"] = True
            if duration_ms:
                parsed.setdefault("duration_ms", duration_ms)
            return json.dumps(parsed, ensure_ascii=False)
        return _make_result(True, output=_truncate(stdout), duration_ms=duration_ms, oneshot=True)
    except subprocess.TimeoutExpired:
        duration_ms = int((time.monotonic() - start) * 1000)
        return _make_result(
            False,
            error=f"oneshot timed out after {timeout}s",
            error_code="TIMEOUT",
            duration_ms=duration_ms,
        )
    except FileNotFoundError:
        return _make_result(False, error="npx/tsx not found", error_code="MISSING_RUNTIME")
    except Exception as exc:
        logger.exception("[BroccoliDB] oneshot failed: %s", method)
        return _make_result(False, error=str(exc), error_code="ONESHOT_ERROR")


def _truncate(text: str, max_bytes: int = 512 * 1024) -> str:
    if len(text) > max_bytes:
        return text[:max_bytes] + f"\n[TRUNCATED: {max_bytes} bytes]"
    return text


class BroccoliDbGateway:
    """Persistent newline-delimited JSON RPC to broccolidb/infrastructure/hermes/hermes_rpc.ts."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._next_id = 0
        self._ready = False
        self._warmed = False
        self._last_used = 0.0

    def invoke(
        self,
        method: str,
        params: Optional[dict[str, Any]] = None,
        *,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> str:
        if method not in RPC_METHODS:
            return _make_result(
                False,
                error=f"unsupported RPC method: {method}",
                error_code="UNKNOWN_METHOD",
            )
        if not rpc_available():
            return run_oneshot_rpc(method, params, timeout=timeout)

        self._maybe_recycle_idle()
        start = time.monotonic()
        effective_timeout = (
            max(timeout, _FIRST_RPC_EXTRA_TIMEOUT) if not self._warmed else timeout
        )
        try:
            raw_line = self._rpc_call(method, params or {}, timeout=effective_timeout)
        except Exception as exc:
            err_text = str(exc)
            if _is_fatal_worker_error(err_text):
                logger.warning(
                    "[BroccoliDB] RPC worker native module error — use oneshot fallback. "
                    "Fix: cd broccolidb && npm rebuild better-sqlite3"
                )
                return run_oneshot_rpc(method, params, timeout=timeout)
            logger.warning("[BroccoliDB] RPC failed (%s), retrying once", exc)
            try:
                raw_line = self._rpc_call(
                    method,
                    params or {},
                    timeout=effective_timeout,
                    force_restart=True,
                )
            except Exception as retry_exc:
                logger.warning("[BroccoliDB] RPC retry failed: %s", retry_exc)
                return run_oneshot_rpc(method, params, timeout=timeout)

        self._last_used = time.monotonic()
        self._warmed = True
        return self._format_rpc_response(raw_line, duration_ms=int((time.monotonic() - start) * 1000))

    def invoke_batch(
        self,
        calls: list[tuple[str, dict[str, Any]]],
        *,
        timeout: int = _DEFAULT_TIMEOUT,
    ) -> str:
        if not calls:
            return _make_result(True, results=[], rpc=True)
        return self.invoke(
            "batch",
            {"calls": [{"method": m, "params": p or {}} for m, p in calls]},
            timeout=timeout,
        )

    def shutdown(self) -> None:
        with self._lock:
            self._terminate_process()

    def _maybe_recycle_idle(self) -> None:
        idle_sec = os.environ.get("HERMES_BROCCOLIDB_RPC_IDLE_SEC", "").strip()
        if not idle_sec:
            return
        try:
            limit = float(idle_sec)
        except ValueError:
            return
        if limit <= 0 or self._last_used <= 0:
            return
        if (time.monotonic() - self._last_used) <= limit:
            return
        with self._lock:
            if self._last_used > 0 and (time.monotonic() - self._last_used) > limit:
                self._terminate_process()

    def _rpc_call(
        self,
        method: str,
        params: dict[str, Any],
        *,
        timeout: int,
        force_restart: bool = False,
    ) -> str:
        with self._lock:
            if force_restart:
                self._terminate_process()
            self._ensure_process()
            assert self._process is not None and self._process.stdin and self._process.stdout
            self._next_id += 1
            req_id = self._next_id
            payload = {"id": req_id, "method": method, "params": params}
            self._process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
            self._process.stdin.flush()
            return self._read_response_line(self._process, timeout=timeout, expect_id=req_id)

    def _ensure_process(self) -> None:
        if self._process is not None and self._process.poll() is None and self._ready:
            return
        self._terminate_process()
        root = resolve_broccolidb_root()
        if not root:
            raise RuntimeError("BroccoliDB root not found")
        if not (Path(root) / _HERMES_RPC_SCRIPT).is_file():
            raise RuntimeError(f"missing RPC script: {_HERMES_RPC_SCRIPT}")

        env = _get_env()
        _pin_node_on_path(env)
        if os.environ.get("HERMES_BROCCOLIDB_PRELOAD_AGENT", "").strip() in ("1", "true", "yes"):
            env["HERMES_BROCCOLIDB_PRELOAD_AGENT"] = "1"
        self._process = subprocess.Popen(
            _tsx_bin(root) + [_HERMES_RPC_SCRIPT],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=env,
            cwd=root,
        )
        _attach_stderr_drainer(self._process)
        self._next_id = 0
        self._ready = False
        ready_line = self._read_response_line(self._process, timeout=_READY_TIMEOUT, expect_id=None)
        ready = _extract_json(ready_line) or {}
        if not ready.get("ready"):
            err = ready_line
            self._terminate_process()
            raise RuntimeError(f"RPC worker failed ready handshake: {err}")
        self._ready = True

    def _terminate_process(self) -> None:
        proc = self._process
        self._process = None
        self._ready = False
        self._warmed = False
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except OSError:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
                proc.wait(timeout=1)
            except Exception:
                pass

    @staticmethod
    def _read_response_line(
        proc: subprocess.Popen[str],
        *,
        timeout: int,
        expect_id: Optional[int],
    ) -> str:
        assert proc.stdout is not None
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if proc.poll() is not None:
                err = (proc.stderr.read() if proc.stderr else "") or f"exit {proc.returncode}"
                raise RuntimeError(f"RPC worker exited: {err}")
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            line: str = ""
            try:
                # Prefer select-based polling so the timeout is real (readline() can block).
                rlist, _, _ = select.select([proc.stdout], [], [], min(0.1, remaining))
                if not rlist:
                    continue
                line = proc.stdout.readline()
            except (TypeError, ValueError, OSError):
                # Test doubles / mocked streams may not support fileno/select; fall back.
                line = proc.stdout.readline()
            if not line:
                continue
            stripped = line.strip()
            if not stripped:
                continue
            parsed = _extract_json(stripped)
            if expect_id is None:
                if parsed and parsed.get("ready"):
                    return stripped
                continue
            if not parsed:
                continue
            if parsed.get("ready"):
                continue
            if parsed.get("id") != expect_id:
                continue
            return stripped
        raise TimeoutError(f"RPC timed out after {timeout}s")

    @staticmethod
    def _format_rpc_response(raw_line: str, *, duration_ms: int) -> str:
        parsed = _extract_json(raw_line)
        if not parsed:
            return _make_result(
                False,
                error="invalid RPC response",
                error_code="RPC_PARSE_ERROR",
                duration_ms=duration_ms,
            )
        if not parsed.get("ok"):
            return _make_result(
                False,
                error=str(parsed.get("error") or "RPC error"),
                error_code=str(parsed.get("error_code") or "RPC_ERROR"),
                duration_ms=duration_ms,
            )
        result = parsed.get("result")
        if isinstance(result, dict):
            result = dict(result)
            result.setdefault("success", True)
            if duration_ms:
                result.setdefault("duration_ms", duration_ms)
            result.setdefault("rpc", True)
            result.setdefault("rpc_version", RPC_VERSION)
            return json.dumps(result, ensure_ascii=False)
        return _make_result(True, output=raw_line, duration_ms=duration_ms, rpc=True)


def get_gateway() -> BroccoliDbGateway:
    global _gateway_instance
    with _gateway_lock:
        if _gateway_instance is None:
            _gateway_instance = BroccoliDbGateway()
        return _gateway_instance


def run_db_rpc(
    method: str,
    params: Optional[dict[str, Any]] = None,
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    return get_gateway().invoke(method, params or {}, timeout=timeout)


def run_db_rpc_batch(
    calls: list[tuple[str, dict[str, Any]]],
    *,
    timeout: int = _DEFAULT_TIMEOUT,
) -> str:
    return get_gateway().invoke_batch(calls, timeout=timeout)


def shutdown_gateway() -> None:
    global _gateway_instance
    with _gateway_lock:
        if _gateway_instance is not None:
            _gateway_instance.shutdown()
            _gateway_instance = None


atexit.register(shutdown_gateway)
