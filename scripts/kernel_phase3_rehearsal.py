#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Phase 3A integration rehearsal — disposable workspace, real kernel gate."""
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


def _patch_kernel_config(enabled: bool = True, mutations: bool = True, policy: str = "warn") -> None:
    """Merge rehearsal bridge settings into kernel config loader."""
    import plugins.dietcode.lib.kernel_workspace as kw

    original = kw._load_kernel_config

    def merged() -> dict:
        base = dict(original())
        bridge = dict(base.get("bridge") or {})
        bridge["enabled"] = enabled
        bridge["mutations_enabled"] = mutations
        bridge["raw_write_policy"] = policy
        base["bridge"] = bridge
        base["mutations_enabled"] = mutations
        base["raw_write_policy"] = policy
        return base

    kw._load_kernel_config = merged  # type: ignore[method-assign]
    import plugins.dietcode.lib.agent.kernel_bridge_client as kbc

    kbc._PREFLIGHT_CACHE = None


def _fail(msg: str) -> None:
    print(f"REHEARSAL FAIL: {msg}", file=sys.stderr)
    sys.exit(1)


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _kernel_scripts_on_path() -> None:
    scripts = PLUGIN_ROOT / "kernel" / "scripts"
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))


def _open_workspace_with_approval(ws_path: str) -> None:
    """Open disposable workspace on kernel and auto-resolve approval (autonomy 3)."""
    from plugins.dietcode.lib.agent import kernel_bridge_client as kbc

    _kernel_scripts_on_path()
    from dietcode_coherence import resolve_kernel_approval

    resolved_ws = str(Path(ws_path).resolve())
    with kbc._kernel_rpc_session() as (client, sock, token, _cfg):
        opened = client.send_rpc(sock, token, "workspace.openFolder", {"path": resolved_ws})
        approved = resolve_kernel_approval(
            sock, token, opened, "", resolved_by="phase3_rehearsal"
        )
        if not approved.get("ok"):
            _fail(f"workspace open/approval failed: {approved}")
        verify = client.send_rpc(sock, token, "workspace.getRoot", {})
        root = (verify.get("result") or {}).get("path")
        if not root or Path(str(root)).resolve() != Path(resolved_ws).resolve():
            _fail(f"workspace root mismatch after open: {root!r} != {resolved_ws!r}")


def _kernel_patch_resolved(ws: Path, **patch_kwargs: object) -> dict:
    """Run dietcode_kernel patch and auto-resolve kernel approval when required."""
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
                sock, token, rpc, "", resolved_by="phase3_rehearsal"
            )
        if not approved.get("ok"):
            _fail(f"patch approval failed: {approved}")
        exec_result = approved.get("result") or {}
        parsed["kernel"] = exec_result

    receipt = (parsed.get("kernel") or {}).get("mutationReceipt")
    if not receipt:
        _fail(f"kernel patch missing mutationReceipt: {parsed}")
    return parsed


def _resolve_rehearsal_workspace() -> Path:
    """Use kernel's open workspace when available (avoids openFolder drift/approval churn)."""
    from plugins.dietcode.lib.agent import kernel_bridge_client as kbc

    try:
        with kbc._kernel_rpc_session() as (client, sock, token, _cfg):
            root_resp = client.send_rpc(sock, token, "workspace.getRoot", {})
            kernel_ws = (root_resp.get("result") or {}).get("path")
            if kernel_ws:
                return Path(str(kernel_ws))
    except Exception:
        pass
    ws = Path(tempfile.gettempdir()) / "dietcode-phase3-rehearsal"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


def main() -> None:
    _bootstrap()
    ws = _resolve_rehearsal_workspace()
    target = ws / "hello.txt"
    target.write_text("hello\n", encoding="utf-8")

    os.environ["HERMES_KANBAN_WORKSPACE"] = str(ws)
    os.environ["HERMES_KANBAN_TASK"] = f"rehearsal_{uuid.uuid4().hex[:8]}"
    os.environ["JOYZONING_SCOPE_ID"] = f"rehearsal-scope-{uuid.uuid4().hex[:8]}"
    os.environ.pop("DIETCODE_KERNEL_RAW_WRITE_BLOCK", None)

    _patch_kernel_config(mutations=True, policy="warn")

    from plugins.dietcode.lib.kernel_health import build_kernel_health
    from plugins.dietcode.lib.agent.kernel_bridge_client import build_patch_gate_state
    from plugins.dietcode.lib.agent.kernel_raw_write_router import build_raw_write_router_health
    from plugins.dietcode.lib.runtime import kernel_hooks
    from plugins.dietcode.lib.agent import kernel_receipt_journal as krj
    from plugins.dietcode.lib.tools import kernel_bridge_tools

    print(f"Rehearsal workspace: {ws}")
    print("--- Step 3: doctor gates ---")

    health = build_kernel_health()
    ws_info = health.get("workspace") or {}
    gate = build_patch_gate_state()
    router = build_raw_write_router_health(probe_runtime=True)

    print(json.dumps({
        "safe_for_mutation": ws_info.get("safe_for_mutation"),
        "patch_allowed": gate.get("patch_allowed"),
        "would_warn_on_raw_write": router.get("would_warn_on_raw_write"),
        "socket_reachable": health.get("socket_reachable"),
        "token_readable": health.get("token_readable"),
    }, indent=2))

    if not ws_info.get("safe_for_mutation"):
        _fail(f"workspace not safe: {ws_info}")
    if not gate.get("patch_allowed"):
        _fail(f"patch gate closed: {gate}")
    if not router.get("would_warn_on_raw_write"):
        _fail(f"would_warn_on_raw_write false: {router}")
    _ok("doctor gates: safe_for_mutation, patch_allowed, would_warn_on_raw_write")

    print("--- Step 4: raw patch + warning ---")
    krj.reset_journal_dedup_cache()
    krj.clear_raw_write_warning_stash() if hasattr(krj, "clear_raw_write_warning_stash") else None
    from plugins.dietcode.lib.agent import kernel_raw_write_router as router_mod

    router_mod.clear_raw_write_warning_stash()

    patch_args = {
        "path": "hello.txt",
        "old_string": "hello",
        "new_string": "hello world",
    }
    pre = kernel_hooks._pre_tool_call(tool_name="patch", args=patch_args)
    if not pre or pre.get("action") != "warn":
        _fail(f"pre_tool_call expected warn, got: {pre}")

    target.write_text("hello world\n", encoding="utf-8")
    raw_result = json.dumps({"ok": True, "path": "hello.txt"})
    transformed = kernel_hooks.on_kernel_raw_write_transform(
        tool_name="patch",
        args=patch_args,
        result=raw_result,
    )
    if not transformed:
        _fail("transform did not merge raw write warning")
    parsed_raw = json.loads(transformed)
    if not parsed_raw.get("_kernel_raw_write_warning"):
        _fail(f"missing _kernel_raw_write_warning: {parsed_raw}")
    if parsed_raw.get("_kernel_raw_write_warning", {}).get("string_code") != "kernel_raw_write_warn":
        _fail("wrong warning string_code")
    _ok("raw patch succeeded with _kernel_raw_write_warning")

    print("--- Step 5: dietcode_kernel patch + journal ---")
    krj.reset_journal_dedup_cache()

    from plugins.dietcode.lib.agent import kernel_bridge_client as kbc

    with kbc._kernel_rpc_session() as (client, sock, token, _cfg):
        refreshed = client.send_rpc(sock, token, "workspace.refreshAnchor", {})
        if not refreshed.get("ok"):
            _fail(f"workspace.refreshAnchor failed: {refreshed}")

    # Avoid coherence task binding for disposable rehearsal workspace.
    os.environ.pop("HERMES_KANBAN_TASK", None)
    os.environ.pop("DIETCODE_TASK_ID", None)

    kernel_parsed = _kernel_patch_resolved(
        ws,
        path="hello.txt",
        line_search="hello world",
        line_replace="hello kernel",
    )

    journal_report = krj.journal_kernel_patch(
        tool_name="dietcode_kernel",
        args={"action": "patch"},
        result=kernel_parsed,
    )
    if not journal_report.get("journaled"):
        _fail(f"journal failed: {journal_report}")

    dup = krj.journal_kernel_patch(
        tool_name="dietcode_kernel",
        args={"action": "patch"},
        result=kernel_parsed,
    )
    if not dup.get("deduplicated"):
        _fail(f"expected deduplicated journal, got: {dup}")

    transformed_kernel = kernel_hooks.on_kernel_journal_transform(
        tool_name="dietcode_kernel",
        args={"action": "patch"},
        result=json.dumps(kernel_parsed),
    )
    _ok(f"kernel patch ok + receipt + journal (dedup={dup.get('deduplicated')})")

    if target.read_text(encoding="utf-8").strip() != "hello kernel":
        _fail(f"file content unexpected: {target.read_text()!r}")
    _ok(f"file on disk: {target.read_text().strip()!r}")

    print("--- REHEARSAL PASS ---")


if __name__ == "__main__":
    main()
