#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 5 end-to-end: patch → verify → journal → convergence (no auto-complete)."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import types
import uuid
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def _bootstrap() -> None:
    if str(PLUGIN_ROOT) not in sys.path:
        sys.path.insert(0, str(PLUGIN_ROOT))
    bootstrap_path = PLUGIN_ROOT / "_bootstrap.py"
    spec = importlib.util.spec_from_file_location("dietcode_bootstrap", bootstrap_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    loaded_name = "hermes_plugins.dietcode"
    loaded = types.ModuleType(loaded_name)
    loaded.__path__ = [str(PLUGIN_ROOT)]  # type: ignore[attr-defined]
    sys.modules[loaded_name] = loaded
    mod.ensure_namespace(loaded_name)


def _patch_kernel_config(*, mutations: bool = True, policy: str = "warn") -> None:
    import plugins.dietcode.lib.kernel_workspace as kw

    original = kw._load_kernel_config

    def merged() -> dict:
        base = dict(original())
        bridge = dict(base.get("bridge") or {})
        bridge["enabled"] = True
        bridge["mutations_enabled"] = mutations
        bridge["raw_write_policy"] = policy
        base["bridge"] = bridge
        return base

    kw._load_kernel_config = merged  # type: ignore[method-assign]
    import plugins.dietcode.lib.agent.kernel_bridge_client as kbc

    kbc._PREFLIGHT_CACHE = None


def _fail(msg: str) -> None:
    print(f"E2E FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _kernel_scripts_on_path() -> None:
    scripts = PLUGIN_ROOT / "kernel" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


def _resolve_workspace() -> Path:
    from plugins.dietcode.lib.agent import kernel_bridge_client as kbc

    try:
        with kbc._kernel_rpc_session() as (client, sock, token, _cfg):
            root_resp = client.send_rpc(sock, token, "workspace.getRoot", {})
            kernel_ws = (root_resp.get("result") or {}).get("path")
            if kernel_ws:
                return Path(str(kernel_ws))
    except Exception:
        pass
    ws = Path(tempfile.gettempdir()) / "dietcode-kernel-bridge-e2e"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def _kernel_patch_resolved(ws: Path, **patch_kwargs: object) -> dict:
    from plugins.dietcode.lib.tools import kernel_bridge_tools
    from plugins.dietcode.lib.agent import kernel_bridge_client as kbc

    _kernel_scripts_on_path()
    from dietcode_coherence import resolve_kernel_approval

    raw = kernel_bridge_tools.dietcode_kernel("patch", workspace=str(ws), **patch_kwargs)
    parsed = json.loads(raw)
    if not parsed.get("ok"):
        _fail(f"dietcode_kernel patch failed: {raw[:500]}")

    kernel_body = parsed.get("kernel") or {}
    if kernel_body.get("approvalRequired"):
        rpc = parsed.get("rpc") or {}
        with kbc._kernel_rpc_session() as (_client, sock, token, _cfg):
            approved = resolve_kernel_approval(
                sock, token, rpc, "", resolved_by="kernel_bridge_e2e"
            )
        if not approved.get("ok"):
            _fail(f"patch approval failed: {approved}")
        parsed["kernel"] = approved.get("result") or {}

    if not (parsed.get("kernel") or {}).get("mutationReceipt"):
        _fail(f"kernel patch missing mutationReceipt: {parsed}")
    return parsed


def _kernel_verify_resolved(ws: Path, command: str = "./verify.sh") -> dict:
    from plugins.dietcode.lib.tools import kernel_bridge_tools

    raw = kernel_bridge_tools.dietcode_kernel(
        "verify",
        workspace=str(ws),
        command=command,
    )
    parsed = json.loads(raw)
    if not parsed.get("ok"):
        _fail(f"dietcode_kernel verify failed: {raw[:500]}")
    if not parsed.get("verify_ran"):
        _fail(f"verify did not run: {parsed}")
    return parsed


def main() -> None:
    _bootstrap()
    ws = _resolve_workspace()
    target = ws / "e2e.txt"
    verify_sh = ws / "verify.sh"
    target.write_text("e2e-start\n", encoding="utf-8")
    verify_sh.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    verify_sh.chmod(0o755)

    scope_id = f"e2e-scope-{uuid.uuid4().hex[:8]}"
    os.environ["HERMES_KANBAN_WORKSPACE"] = str(ws)
    os.environ["JOYZONING_SCOPE_ID"] = scope_id
    os.environ.pop("HERMES_KANBAN_TASK", None)
    os.environ.pop("DIETCODE_TASK_ID", None)
    os.environ.pop("DIETCODE_KERNEL_RAW_WRITE_BLOCK", None)

    _patch_kernel_config(mutations=True, policy="warn")

    from plugins.dietcode.lib.kernel_health import build_kernel_bridge_status_summary
    from plugins.dietcode.lib.agent.kernel_bridge_client import build_patch_gate_state
    from plugins.dietcode.lib.agent import kernel_receipt_journal as krj
    from plugins.dietcode.lib.agent import kernel_verify_journal as kvj
    from plugins.dietcode.lib.tools.convergence_tools import convergence_status

    print(f"E2E workspace: {ws}")
    print("--- Step 1: operator status ---")

    summary = build_kernel_bridge_status_summary(probe_runtime=True)
    gate = build_patch_gate_state()
    print(json.dumps({k: summary.get(k) for k in (
        "bridge_enabled", "mutations_enabled", "raw_write_policy", "env_fuse_present",
        "workspace_safe", "patch_allowed", "verify_allowlist_count",
    )}, indent=2))

    if not summary.get("workspace_safe"):
        _fail(f"workspace not safe: {summary}")
    if not gate.get("patch_allowed"):
        _fail(
            "patch gate closed — start kernel agent server "
            "(make -C kernel restart-agent-server-fast) and retry"
        )
    _ok("status summary: workspace_safe + patch_allowed")

    print("--- Step 2: kernel patch + receipt journal ---")
    krj.reset_journal_dedup_cache()
    kvj.reset_verify_journal_dedup_cache()

    from plugins.dietcode.lib.agent import kernel_bridge_client as kbc

    with kbc._kernel_rpc_session() as (client, sock, token, _cfg):
        refreshed = client.send_rpc(sock, token, "workspace.refreshAnchor", {})
        if not refreshed.get("ok"):
            _fail(f"workspace.refreshAnchor failed: {refreshed}")

    patch_result = _kernel_patch_resolved(
        ws,
        path="e2e.txt",
        line_search="e2e-start",
        line_replace="e2e-patched",
    )
    patch_journal = krj.journal_kernel_patch(
        tool_name="dietcode_kernel",
        args={"action": "patch"},
        result=patch_result,
    )
    if not patch_journal.get("journaled"):
        _fail(f"patch journal failed: {patch_journal}")
    _ok(f"patch journaled (mutation_id={patch_journal.get('mutation_id')})")

    print("--- Step 3: kernel verify + verification journal ---")
    verify_result = _kernel_verify_resolved(ws, command="./verify.sh")
    verify_journal = kvj.journal_kernel_verify(
        tool_name="dietcode_kernel",
        args={"action": "verify"},
        result=verify_result,
    )
    if not verify_journal.get("journaled"):
        _fail(f"verify journal failed: {verify_journal}")
    _ok(f"verify journaled (passed={verify_result.get('passed')})")

    print("--- Step 4: convergence gate (no auto-complete) ---")
    conv_raw = convergence_status(scope_id=scope_id)
    conv = json.loads(conv_raw)
    if conv.get("kanban_complete_allowed"):
        _fail(f"kanban_complete_allowed unexpectedly true: {conv}")
    _ok(f"kanban_complete blocked: {conv.get('kanban_complete_block_reason')!r}")

    if target.read_text(encoding="utf-8").strip() != "e2e-patched":
        _fail(f"unexpected file content: {target.read_text()!r}")
    _ok("file on disk matches kernel patch")

    print("--- E2E PASS ---")


if __name__ == "__main__":
    main()
