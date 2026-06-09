#!/usr/bin/env python3
"""Live kernel checks for coherence token v0.1."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from agent_contracts import COHERENCE_RESPONSE_KEYS, WORKSPACE_REVISION_KEYS  # noqa: E402
from dietcode_agent_client import connect, ensure_workspace_root, load_token, send_rpc  # noqa: E402
from agent_test_support import CheckRecorder, add_output_args, output_compact  # noqa: E402


def _assert_coherence_shape(coherence: dict) -> None:
    missing = COHERENCE_RESPONSE_KEYS - set(coherence.keys())
    assert not missing, f"coherence missing keys: {sorted(missing)}"


def test_workspace_revision_keys(sock, token: str) -> None:
    rev = send_rpc(sock, token, "workspace.revision", {})
    assert rev.get("ok"), rev
    result = rev["result"]
    missing = WORKSPACE_REVISION_KEYS - set(result.keys())
    assert not missing, f"workspace.revision missing keys: {sorted(missing)}"


def test_read_issues_coherence(sock, token: str, rel_path: str, task_id: str) -> dict:
    read = send_rpc(sock, token, "file.read", {"path": rel_path, "taskId": task_id})
    assert read.get("ok"), read
    coherence = read["result"].get("coherence")
    assert isinstance(coherence, dict), "file.read with taskId must return coherence"
    _assert_coherence_shape(coherence)
    assert str(coherence["tokenId"]).startswith("coh_")
    assert rel_path in coherence.get("anchors", {})
    return coherence


def test_read_batch_issues_coherence(sock, token: str, rel_paths: list[str], task_id: str) -> dict:
    read = send_rpc(sock, token, "file.readBatch", {"paths": rel_paths, "taskId": task_id})
    assert read.get("ok"), read
    coherence = read["result"].get("coherence")
    assert isinstance(coherence, dict), "file.readBatch with taskId must return top-level coherence"
    _assert_coherence_shape(coherence)
    assert str(coherence["tokenId"]).startswith("coh_")
    anchors = coherence.get("anchors") or {}
    for rel_path in rel_paths:
        assert rel_path in anchors, f"missing anchor for {rel_path}"
    results = read["result"].get("results") or {}
    for rel_path in rel_paths:
        row = results.get(rel_path) or {}
        assert row.get("ok") is True, f"expected successful read for {rel_path}: {row}"
    return coherence


def test_stale_token_rejected(sock, token: str, rel_path: str, task_id: str) -> None:
    coherence = test_read_issues_coherence(sock, token, rel_path, task_id)
    patch = (
        f"--- {rel_path}\n"
        f"+++ {rel_path}\n"
        "@@ -1,1 +1,1 @@\n"
        "-hello\n"
        "+world\n"
    )
    validated = send_rpc(sock, token, "patch.validate", {"path": rel_path, "patch": patch})
    assert validated.get("ok"), validated

    stale = send_rpc(
        sock,
        token,
        "patch.apply",
        {
            "path": rel_path,
            "patch": patch,
            "confirm": True,
            "expectBeforeHash": validated["result"]["validation"]["beforeContentHash"],
            "taskId": task_id,
            "coherenceTokenId": coherence["tokenId"],
            "expectedWorkspaceRevision": int(coherence["workspaceRevision"]) - 1,
        },
    )
    assert not stale.get("ok"), "expected coherence_mismatch for stale revision"
    err = stale.get("error") or {}
    assert err.get("string_code") == "coherence_mismatch", err
    assert err.get("reason") == "workspace_changed", err


def test_missing_token_with_task_id(sock, token: str, rel_path: str, task_id: str) -> None:
    send_rpc(sock, token, "file.read", {"path": rel_path, "taskId": task_id})
    patch = (
        f"--- {rel_path}\n"
        f"+++ {rel_path}\n"
        "@@ -1,1 +1,1 @@\n"
        "-hello\n"
        "+world\n"
    )
    validated = send_rpc(sock, token, "patch.validate", {"path": rel_path, "patch": patch})
    assert validated.get("ok"), validated
    blocked = send_rpc(
        sock,
        token,
        "patch.apply",
        {
            "path": rel_path,
            "patch": patch,
            "confirm": True,
            "expectBeforeHash": validated["result"]["validation"]["beforeContentHash"],
            "taskId": task_id,
        },
    )
    assert not blocked.get("ok"), blocked
    assert (blocked.get("error") or {}).get("string_code") == "coherence_mismatch"


def main() -> int:
    parser = argparse.ArgumentParser(description="Coherence token kernel checks.")
    add_output_args(parser)
    args = parser.parse_args()
    recorder = CheckRecorder(compact=output_compact(args), verbose=args.verbose)

    sock = connect()
    token = load_token()
    workspace_root = Path(ensure_workspace_root(sock, token))
    rel_path = f".dietcode/coherence_probe_{uuid.uuid4().hex[:8]}.txt"
    rel_path_b = f".dietcode/coherence_probe_{uuid.uuid4().hex[:8]}.txt"
    probe = workspace_root / rel_path
    probe_b = workspace_root / rel_path_b
    probe.parent.mkdir(parents=True, exist_ok=True)
    probe.write_text("hello\n", encoding="utf-8")
    probe_b.write_text("world\n", encoding="utf-8")
    task_id = f"task_coherence_{uuid.uuid4().hex[:8]}"

    try:
        recorder.run("coherence.revision_keys", lambda: test_workspace_revision_keys(sock, token))
        recorder.run(
            "coherence.read_issues_token",
            lambda: test_read_issues_coherence(sock, token, rel_path, task_id),
        )
        recorder.run(
            "coherence.read_batch_issues_token",
            lambda: test_read_batch_issues_coherence(sock, token, [rel_path, rel_path_b], task_id),
        )
        recorder.run(
            "coherence.stale_revision_rejected",
            lambda: test_stale_token_rejected(sock, token, rel_path, task_id),
        )
        recorder.run(
            "coherence.missing_token_rejected",
            lambda: test_missing_token_with_task_id(sock, token, rel_path, task_id),
        )
    finally:
        if probe.exists():
            probe.unlink()
        if probe_b.exists():
            probe_b.unlink()

    return recorder.finish("coherence_tokens")


if __name__ == "__main__":
    raise SystemExit(main())
