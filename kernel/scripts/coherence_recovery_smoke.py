#!/usr/bin/env python3
"""Prove coherence recovery: stale patch blocked, re-read, safe retry, verify passes."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
FIXTURES = _SCRIPT_DIR / "fixtures" / "coherence_recovery"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from agent_test_support import CheckRecorder, add_output_args, output_compact  # noqa: E402
from dietcode_agent_client import connect, ensure_workspace_root, load_token, send_rpc  # noqa: E402
from dietcode_coherence import (  # noqa: E402
    build_line_replacement_patch_for_content,
    current_int_assignment,
    read_with_coherence,
    recover_and_apply_patch,
)


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_event(event_type: str, task_id: str, **payload: Any) -> None:
    record = {
        "type": event_type,
        "taskId": task_id,
        "timestamp": _iso_now(),
        "source": "coherence-recovery-smoke",
        **payload,
    }
    print(json.dumps(record, ensure_ascii=False), flush=True)


def _value_patch(rel_path: str, content: str, from_value: int, to_value: int) -> str:
    return build_line_replacement_patch_for_content(
        rel_path,
        content,
        search=f"VALUE = {from_value}",
        replace=f"VALUE = {to_value}",
    )


def run_recovery_smoke() -> None:
    task_id = f"task_coherence_recovery_{uuid.uuid4().hex[:8]}"
    probe_name = f".dietcode/coherence_recovery_{uuid.uuid4().hex[:8]}/probe.py"

    sock = connect(timeout=120.0)
    token = load_token()
    workspace_root = Path(ensure_workspace_root(sock, token))
    probe_abs = workspace_root / probe_name
    probe_abs.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FIXTURES / "probe.py", probe_abs)
    shutil.copyfile(FIXTURES / "verify.sh", probe_abs.parent / "verify.sh")
    (probe_abs.parent / "verify.sh").chmod(0o755)

    emit_event("task.started", task_id, path=probe_name, workspace=str(workspace_root))

    initial = read_with_coherence(sock, token, probe_name, task_id)
    initial_text = initial["text"]
    stale_coherence = initial["coherence"]
    if current_int_assignment(initial_text) != 1:
        raise RuntimeError(f"expected VALUE=1 after fixture copy, got: {initial_text!r}")
    emit_event("context.read", task_id, action="file.read", path=probe_name, value=1)

    stale_patch = _value_patch(probe_name, initial_text, 1, 2)
    validated_stale = send_rpc(
        sock, token, "patch.validate", {"path": probe_name, "patch": stale_patch}
    )
    if not validated_stale.get("ok"):
        raise RuntimeError(f"stale patch.validate failed: {validated_stale}")

    probe_abs.write_text(initial_text.replace("VALUE = 1", "VALUE = 3"), encoding="utf-8")
    emit_event("workspace.external_change", task_id, path=probe_name, value=3)

    applied = recover_and_apply_patch(
        sock,
        token,
        task_id=task_id,
        path=probe_name,
        stale_patch=stale_patch,
        stale_coherence=stale_coherence,
        stale_expect_before_hash=validated_stale["result"]["validation"]["beforeContentHash"],
        build_patch_from_content=lambda text: _value_patch(
            probe_name,
            text,
            current_int_assignment(text),
            2,
        ),
        emit=emit_event,
        resolved_by="coherence-recovery-smoke",
    )
    if not applied.get("ok"):
        raise RuntimeError(f"recovery patch.apply failed: {applied}")
    result = applied.get("result") or {}
    if not (result.get("patched") or result.get("applied") or result.get("complete")):
        raise RuntimeError(f"recovery patch did not apply: {result}")

    if current_int_assignment(probe_abs.read_text(encoding="utf-8")) != 2:
        raise RuntimeError("probe.py was not updated to VALUE = 2")
    emit_event("mutation.applied", task_id, path=probe_name, changedPaths=[probe_name])

    verify_cwd = str(probe_abs.parent.relative_to(workspace_root))
    verify = send_rpc(
        sock,
        token,
        "verify.run",
        {"command": "./verify.sh", "cwd": verify_cwd, "taskId": task_id},
    )
    if not verify.get("ok"):
        raise RuntimeError(f"verify.run failed: {verify}")
    if not verify["result"].get("passed"):
        raise RuntimeError(f"verify.run did not pass: {verify}")
    emit_event("verify.completed", task_id, command="./verify.sh", passed=True)
    emit_event("task.completed", task_id, exitCode=0)


def main() -> int:
    parser = argparse.ArgumentParser(description="Coherence recovery vertical smoke.")
    add_output_args(parser)
    args = parser.parse_args()
    recorder = CheckRecorder(compact=output_compact(args), verbose=args.verbose)
    recorder.run("coherence.recovery_smoke", run_recovery_smoke)
    return recorder.finish("coherence_recovery_smoke")


if __name__ == "__main__":
    raise SystemExit(main())
