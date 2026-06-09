#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 7C — live kernel cockpit smoke checks (no mutation required)."""
from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

_PLUGIN_ROOT = Path(__file__).resolve().parents[1]
if str(_PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(_PLUGIN_ROOT))


def _bootstrap() -> None:
    import importlib.util
    import types

    bootstrap_path = _PLUGIN_ROOT / "_bootstrap.py"
    spec = importlib.util.spec_from_file_location("dietcode_bootstrap", bootstrap_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    loaded_name = "hermes_plugins.dietcode"
    loaded = types.ModuleType(loaded_name)
    loaded.__path__ = [str(_PLUGIN_ROOT)]  # type: ignore[attr-defined]
    sys.modules[loaded_name] = loaded
    mod.ensure_namespace(loaded_name)


_bootstrap()

from plugins.dietcode.lib.agent import kernel_cockpit as cockpit  # noqa: E402
from plugins.dietcode.lib.agent import kernel_progress as progress  # noqa: E402
from plugins.dietcode.lib.agent import kernel_progress_ux as ux  # noqa: E402


_TOKEN_LEAK_PATTERNS = (
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{8,}", re.I),
    re.compile(r"session\.token['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9._-]{8,}", re.I),
    re.compile(r"token['\"]?\s*[:=]\s*['\"][A-Za-z0-9._-]{16,}['\"]", re.I),
)


def _assert_no_token_leak(text: str) -> None:
    for pattern in _TOKEN_LEAK_PATTERNS:
        if pattern.search(text):
            raise AssertionError(f"possible token leakage matched: {pattern.pattern}")


def main() -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        session = Path(tmp) / "session"
        session.mkdir(parents=True)
        os.environ["DIETCODE_SESSION_DIR"] = str(session)

        tracker = progress.start_operation(action="patch", path="src/foo.py", workspace_root="/tmp/project")
        events = []
        log_path = session / "kernel-progress.jsonl"
        if log_path.is_file():
            events = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]

        if not events or events[0].get("phase") != progress.PHASE_OPERATION_ACCEPTED:
            failures.append("ack not emitted as first JSONL event")
        current = progress.read_progress_current()
        if not current.get("ok"):
            failures.append("current snapshot not written")

        snap = current.get("current") or {}
        watch = ux.compact_watch_line(snap)
        if not watch or "next:" not in watch:
            failures.append("watch line did not render with next action")
        _assert_no_token_leak(watch)

        cockpit_text = cockpit.format_cockpit_report()
        if "Kernel cockpit" not in cockpit_text:
            failures.append("cockpit report empty")
        for required in ("Patch gate", "Raw write", "Next action", "Workspace"):
            if required not in cockpit_text:
                failures.append(f"cockpit missing section: {required}")
        _assert_no_token_leak(cockpit_text)

        tracker.emit(progress.PHASE_PATCH_VALIDATE, path="src/foo.py")
        tracker.finish(ok=True)
        progress.flush_progress_writes(force=True)

        perf_text = ux.format_ux_perf_report(last_operations=5)
        if "UX budgets" not in perf_text:
            failures.append("perf --ux missing budget fields")
        if "Time to acknowledgement" not in perf_text:
            failures.append("perf --ux missing acknowledgement line")
        _assert_no_token_leak(perf_text)

        payload = ux.build_ux_perf_report(last_operations=5)
        if payload.get("operations"):
            op = payload["operations"][0]
            if "ux_budgets" not in op:
                failures.append("ux_budgets missing on operation metrics")

        state = cockpit.normalize_operation_state(phase=progress.PHASE_PATCH_VALIDATE)
        if state != cockpit.STATE_VALIDATING:
            failures.append(f"expected validating state, got {state}")

    if failures:
        print("kernel_cockpit_smoke: FAIL")
        for item in failures:
            print(f"  - {item}")
        return 1

    print("kernel_cockpit_smoke: OK")
    print("  ack emitted")
    print("  current snapshot written")
    print("  watch line renders")
    print("  cockpit renders")
    print("  perf --ux budget fields present")
    print("  no token leakage detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
