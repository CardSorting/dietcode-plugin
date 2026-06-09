#!/usr/bin/env python3
"""Shared coherence token helpers for governed Python agents and smoke harnesses."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable

from agent_contracts import COHERENCE_RESPONSE_KEYS
from dietcode_agent_client import send_rpc

EmitFn = Callable[..., None]


def iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def emit_task_coherence_event(event_type: str, task_id: str, **payload: Any) -> None:
    """Write NDJSON task events when DIETCODE_TASK_EVENT_LOG is configured."""
    log_path = os.environ.get("DIETCODE_TASK_EVENT_LOG", "").strip()
    if not log_path:
        return
    record = {
        "type": event_type,
        "taskId": task_id,
        "timestamp": iso_now(),
        "source": os.environ.get("DIETCODE_COHERENCE_EVENT_SOURCE", "dietcode_coherence"),
        **payload,
    }
    path = os.path.expanduser(log_path)
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def assert_coherence_shape(coherence: dict[str, Any]) -> None:
    missing = COHERENCE_RESPONSE_KEYS - set(coherence.keys())
    if missing:
        raise AssertionError(f"coherence missing keys: {sorted(missing)}")


def read_with_coherence(sock, token: str, path: str, task_id: str) -> dict[str, Any]:
    response = send_rpc(sock, token, "file.read", {"path": path, "taskId": task_id})
    if not response.get("ok"):
        raise RuntimeError(f"file.read failed: {response}")
    coherence = (response.get("result") or {}).get("coherence")
    if not isinstance(coherence, dict):
        raise RuntimeError("file.read with taskId did not return coherence token")
    assert_coherence_shape(coherence)
    return response["result"]


def build_line_replacement_patch(rel_path: str, *, search: str, replace: str) -> str:
    return (
        f"--- {rel_path}\n"
        f"+++ {rel_path}\n"
        "@@ -1,1 +1,1 @@\n"
        f"-{search}\n"
        f"+{replace}\n"
    )


def build_line_replacement_patch_for_content(
    rel_path: str,
    content: str,
    *,
    search: str,
    replace: str,
) -> str:
    lines = content.splitlines()
    idx = next((i for i, line in enumerate(lines) if line.strip() == search.strip()), -1)
    if idx < 0:
        match = re.match(r"^(\w+)\s*=", search.strip())
        if match:
            name = match.group(1)
            pattern = re.compile(rf"^{re.escape(name)}\s*=")
            idx = next((i for i, line in enumerate(lines) if pattern.search(line.strip())), -1)
    if idx < 0:
        raise RuntimeError(f"search line not found in {rel_path}: {search!r}")
    line_no = idx + 1
    return (
        f"--- {rel_path}\n"
        f"+++ {rel_path}\n"
        f"@@ -{line_no},1 +{line_no},1 @@\n"
        f"-{lines[idx]}\n"
        f"+{replace}\n"
    )


def build_value_assignment_patch(
    rel_path: str,
    *,
    from_value: int,
    to_value: int,
    header_line: str = ' """Coherence recovery smoke probe."""',
) -> str:
    return (
        f"--- {rel_path}\n"
        f"+++ {rel_path}\n"
        "@@ -1,3 +1,3 @@\n"
        f"-{header_line}\n"
        " \n"
        f"-VALUE = {from_value}\n"
        f"+{header_line}\n"
        " \n"
        f"+VALUE = {to_value}\n"
    )


def parse_coherence_mismatch(error: dict[str, Any]) -> dict[str, Any]:
    coherence = error.get("coherence") if isinstance(error.get("coherence"), dict) else {}
    changed = error.get("changedPaths") or coherence.get("changedPaths") or []
    return {
        "reason": error.get("reason") or coherence.get("reason") or "unknown",
        "changedPaths": [p for p in changed if isinstance(p, str) and p],
        "requiredAction": error.get("requiredAction") or coherence.get("requiredAction") or "refresh_context",
        "currentWorkspaceRevision": error.get("currentWorkspaceRevision") or coherence.get("currentWorkspaceRevision"),
    }


def resolve_kernel_approval(
    sock,
    token: str,
    response: dict[str, Any],
    task_id: str,
    *,
    resolved_by: str = "dietcode_coherence",
    emit: EmitFn | None = None,
) -> dict[str, Any]:
    result = response.get("result") or {}
    if not result.get("approvalRequired"):
        return response

    approval = result.get("approval") or {}
    approval_id = approval.get("approvalId")
    if not approval_id:
        raise RuntimeError(f"approvalRequired without approvalId: {response}")

    if emit:
        emit("approval.required", task_id, approvalId=approval_id)
    else:
        emit_task_coherence_event("approval.required", task_id, approvalId=approval_id)

    resolved = send_rpc(
        sock,
        token,
        "approval.resolve",
        {
            "approvalId": approval_id,
            "decision": "approved",
            "reason": "governed task auto-approve",
            "resolvedBy": resolved_by,
        },
    )
    if not resolved.get("ok"):
        return resolved

    if emit:
        emit("approval.resolved", task_id, approvalId=approval_id, decision="approved")
    else:
        emit_task_coherence_event("approval.resolved", task_id, approvalId=approval_id, decision="approved")

    resolution = (resolved.get("result") or {}).get("resolution") or {}
    if resolution.get("executionErrorCode"):
        return {
            "ok": False,
            "error": {
                "string_code": resolution.get("executionErrorCode"),
                "message": resolution.get("executionError") or "approved mutation failed",
            },
        }
    exec_result = resolution.get("executionResult")
    if exec_result:
        return {"ok": True, "result": exec_result}
    return resolved


def _complete_after_workspace_drift(
    sock,
    token: str,
    response: dict[str, Any],
    method: str,
    params: dict[str, Any],
) -> dict[str, Any]:
    result = response.get("result") or {}
    if not result.get("workspaceDriftRequired"):
        return response

    refreshed = send_rpc(sock, token, "workspace.refreshAnchor", {})
    if not refreshed.get("ok"):
        return refreshed
    status = refreshed.get("result") or {}
    retry_params = dict(params)
    if status.get("contextRefreshId") is not None:
        retry_params["contextRefreshId"] = status["contextRefreshId"]
    return send_rpc(sock, token, method, retry_params)


def apply_patch_with_coherence(
    sock,
    token: str,
    *,
    task_id: str,
    path: str,
    patch: str,
    coherence: dict[str, Any],
    expect_before_hash: str,
    emit: EmitFn | None = None,
    resolved_by: str = "dietcode_coherence",
    resolve_approval: bool = True,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "path": path,
        "patch": patch,
        "confirm": True,
        "expectBeforeHash": expect_before_hash,
        "taskId": task_id,
    }
    if coherence.get("tokenId"):
        params["coherenceTokenId"] = coherence["tokenId"]
    if coherence.get("workspaceRevision") is not None:
        params["expectedWorkspaceRevision"] = coherence["workspaceRevision"]

    applied = send_rpc(sock, token, "patch.apply", params)
    if not applied.get("ok"):
        return applied
    applied = _complete_after_workspace_drift(sock, token, applied, "patch.apply", params)
    if not applied.get("ok"):
        return applied
    result = applied.get("result") or {}
    if not resolve_approval and result.get("approvalRequired"):
        return applied
    return resolve_kernel_approval(sock, token, applied, task_id, resolved_by=resolved_by, emit=emit)


def current_int_assignment(text: str, name: str = "VALUE") -> int:
    match = re.search(rf"^{re.escape(name)}\s*=\s*(\d+)\s*$", text, re.MULTILINE)
    if not match:
        raise RuntimeError(f"{name} assignment not found in: {text!r}")
    return int(match.group(1))


def recover_and_apply_patch(
    sock,
    token: str,
    *,
    task_id: str,
    path: str,
    stale_patch: str,
    stale_coherence: dict[str, Any],
    build_patch_from_content: Callable[[str], str],
    emit: EmitFn | None = None,
    resolved_by: str = "dietcode_coherence",
    stale_expect_before_hash: str | None = None,
) -> dict[str, Any]:
    if stale_expect_before_hash:
        expect_before_hash = stale_expect_before_hash
    else:
        validated = send_rpc(sock, token, "patch.validate", {"path": path, "patch": stale_patch})
        if not validated.get("ok"):
            raise RuntimeError(f"patch.validate failed: {validated}")
        expect_before_hash = validated["result"]["validation"]["beforeContentHash"]

    blocked = apply_patch_with_coherence(
        sock,
        token,
        task_id=task_id,
        path=path,
        patch=stale_patch,
        coherence=stale_coherence,
        expect_before_hash=expect_before_hash,
        emit=emit,
        resolved_by=resolved_by,
    )
    if blocked.get("ok"):
        return blocked

    err = blocked.get("error") or {}
    if err.get("string_code") != "coherence_mismatch":
        return blocked

    detail = parse_coherence_mismatch(err)
    if emit:
        emit("context.stale", task_id, path=path, reason=detail["reason"], changedPaths=detail["changedPaths"])
    else:
        emit_task_coherence_event(
            "context.stale",
            task_id,
            path=path,
            reason=detail["reason"],
            changedPaths=detail["changedPaths"],
        )

    fresh = read_with_coherence(sock, token, path, task_id)
    if emit:
        emit("context.refreshed", task_id, path=path, tokenId=fresh["coherence"]["tokenId"])
    else:
        emit_task_coherence_event("context.refreshed", task_id, path=path, tokenId=fresh["coherence"]["tokenId"])

    recovery_patch = build_patch_from_content(fresh["text"])
    if emit:
        emit("coherence.retry", task_id, path=path, attempt=1)
    else:
        emit_task_coherence_event("coherence.retry", task_id, path=path, attempt=1)

    send_rpc(sock, token, "workspace.refreshAnchor", {})
    revalidated = send_rpc(sock, token, "patch.validate", {"path": path, "patch": recovery_patch})
    if not revalidated.get("ok"):
        raise RuntimeError(f"recovery patch.validate failed: {revalidated}")

    retry = apply_patch_with_coherence(
        sock,
        token,
        task_id=task_id,
        path=path,
        patch=recovery_patch,
        coherence=fresh["coherence"],
        expect_before_hash=revalidated["result"]["validation"]["beforeContentHash"],
        emit=emit,
        resolved_by=resolved_by,
    )
    if not retry.get("ok"):
        err2 = retry.get("error") or {}
        if err2.get("string_code") == "coherence_mismatch":
            detail2 = parse_coherence_mismatch(err2)
            if emit:
                emit("coherence.operator_required", task_id, path=path, reason=detail2["reason"])
            else:
                emit_task_coherence_event(
                    "coherence.operator_required",
                    task_id,
                    path=path,
                    reason=detail2["reason"],
                )
        return retry
    return retry
