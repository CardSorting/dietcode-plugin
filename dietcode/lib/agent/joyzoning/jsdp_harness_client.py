"""JoyZoning JSDP convergence harness client — rolling horizon via ``jz jsdp``.

Hermes agents call this module; JoyZoning owns ``.jsdp/`` state and validation.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Optional

from plugins.dietcode.lib.agent.joyzoning.config import get_joyzoning_config, read_scope_env


class JsdpHarnessError(Exception):
    """Harness CLI or configuration failure."""


def resolve_workspace_root(explicit: Optional[str] = None) -> str:
    """Resolve canonical project workspace for ``jz jsdp`` (must contain or init ``.jsdp``)."""
    if explicit and str(explicit).strip():
        return str(Path(explicit).expanduser().resolve())

    for key in (
        "JOYZONING_WORKSPACE_ROOT",
        "HERMES_KANBAN_WORKSPACE",
    ):
        val = read_scope_env(key) or os.environ.get(key, "").strip()
        if val:
            return str(Path(val).expanduser().resolve())

    cfg = get_joyzoning_config()
    if cfg.jsdp_workspace_root:
        return str(Path(cfg.jsdp_workspace_root).expanduser().resolve())

    seeds: list[Path] = []
    ws = os.environ.get("HERMES_KANBAN_WORKSPACE", "").strip()
    if ws:
        seeds.append(Path(ws))
    seeds.append(Path.cwd())

    seen: set[str] = set()
    for seed in seeds:
        try:
            resolved = seed.resolve()
        except OSError:
            continue
        for parent in [resolved, *resolved.parents]:
            key = str(parent)
            if key in seen:
                continue
            seen.add(key)
            if (parent / ".jsdp").is_dir() or (parent / "JoyZoning.sln").is_file():
                return key

    return str(Path.cwd().resolve())


def resolve_jz_executable() -> str:
    """Locate ``jz`` / ``joyzoning`` CLI."""
    cfg = get_joyzoning_config()
    if cfg.jsdp_jz_cli:
        candidate = Path(cfg.jsdp_jz_cli).expanduser()
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())

    for key in ("JOYZONING_JZ_CLI", "JZ_CLI"):
        val = os.environ.get(key, "").strip()
        if val and Path(val).expanduser().is_file():
            return str(Path(val).expanduser().resolve())

    monorepo = os.environ.get("JOYZONING_MONOREPO_ROOT", "").strip()
    if monorepo:
        for name in ("scripts/joyzoning", "jz"):
            script = Path(monorepo) / name
            if script.is_file():
                return str(script.resolve())

    for seed in [Path.cwd(), *Path.cwd().parents]:
        if (seed / "JoyZoning.sln").is_file():
            script = seed / "scripts" / "joyzoning"
            if script.is_file():
                return str(script.resolve())
        if (seed / "scripts" / "joyzoning").is_file():
            return str((seed / "scripts" / "joyzoning").resolve())

    for name in ("jz", "joyzoning"):
        found = _which(name)
        if found:
            return found

    raise JsdpHarnessError(
        "JoyZoning CLI not found. Set joyzoning.jsdp.harness.jz_cli, JOYZONING_JZ_CLI, "
        "JOYZONING_MONOREPO_ROOT, or install jz on PATH."
    )


def _jsdp_subprocess_env(workspace: str) -> dict[str, str]:
    """Scoped env for jz subprocess — no full os.environ inheritance."""
    env: dict[str, str] = {}
    for key in ("PATH", "HOME", "USER", "LANG", "LC_ALL", "TZ"):
        val = os.environ.get(key, "").strip()
        if val:
            env[key] = val
    for key, val in os.environ.items():
        if key.startswith(("HERMES_", "JOYZONING_", "JZ_")) and val:
            env[key] = val
    env["JOYZONING_WORKSPACE_ROOT"] = workspace
    return env


def _which(name: str) -> Optional[str]:
    path = os.environ.get("PATH", "")
    for part in path.split(os.pathsep):
        candidate = Path(part) / name
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate.resolve())
    return None


def run_jsdp(
    subcommand: list[str],
    *,
    workspace: Optional[str] = None,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Run ``jz jsdp … --json`` and return parsed envelope."""
    root = resolve_workspace_root(workspace)
    jz = resolve_jz_executable()
    cmd = [jz, "jsdp", *subcommand, "--json"]
    env = _jsdp_subprocess_env(root)

    try:
        proc = subprocess.run(
            cmd,
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise JsdpHarnessError(f"jz jsdp timed out after {timeout}s: {' '.join(subcommand)}") from exc
    except OSError as exc:
        raise JsdpHarnessError(f"Failed to run {jz}: {exc}") from exc

    stdout = (proc.stdout or "").strip()
    stderr = (proc.stderr or "").strip()

    if not stdout:
        detail = stderr or f"exit {proc.returncode}"
        raise JsdpHarnessError(f"jz jsdp {' '.join(subcommand)} produced no JSON output: {detail}")

    try:
        data = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise JsdpHarnessError(
            f"jz jsdp returned non-JSON (exit {proc.returncode}): {stdout[:500]}"
        ) from exc

    if isinstance(data, dict):
        data.setdefault("exit_code", proc.returncode)
        data.setdefault("workspace_root", root)
        if stderr and "stderr" not in data:
            data["stderr"] = stderr
        if proc.returncode != 0 and data.get("ok") is not False:
            data["ok"] = False
        return data

    return {
        "ok": proc.returncode == 0,
        "exit_code": proc.returncode,
        "workspace_root": root,
        "data": data,
        "stderr": stderr or None,
    }


def horizon_export(*, nodes: int = 3, workspace: Optional[str] = None) -> dict[str, Any]:
    n = max(3, min(5, int(nodes)))
    return run_jsdp(["horizon", "export", "--nodes", str(n)], workspace=workspace)


def horizon_prompt(*, nodes: int = 3, workspace: Optional[str] = None) -> dict[str, Any]:
    n = max(3, min(5, int(nodes)))
    return run_jsdp(["horizon", "prompt", "--nodes", str(n)], workspace=workspace)


def horizon_validate(
    proposal_path: str,
    *,
    nodes: Optional[int] = None,
    workspace: Optional[str] = None,
) -> dict[str, Any]:
    args = ["horizon", "validate", proposal_path]
    if nodes is not None:
        args.extend(["--nodes", str(max(3, min(5, int(nodes))))])
    return run_jsdp(args, workspace=workspace)


def horizon_diff(
    proposal_path: str,
    *,
    nodes: Optional[int] = None,
    workspace: Optional[str] = None,
) -> dict[str, Any]:
    args = ["horizon", "diff", proposal_path]
    if nodes is not None:
        args.extend(["--nodes", str(max(3, min(5, int(nodes))))])
    return run_jsdp(args, workspace=workspace)


def horizon_import(
    proposal_path: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    workspace: Optional[str] = None,
) -> dict[str, Any]:
    args = ["horizon", "import", proposal_path]
    if dry_run:
        args.append("--dry-run")
    if force:
        args.append("--force")
    return run_jsdp(args, workspace=workspace)


def horizon_status(*, workspace: Optional[str] = None) -> dict[str, Any]:
    return run_jsdp(["horizon", "status"], workspace=workspace)


def harness_doctor(*, workspace: Optional[str] = None) -> dict[str, Any]:
    return run_jsdp(["doctor"], workspace=workspace)


def harness_next(*, workspace: Optional[str] = None) -> dict[str, Any]:
    return run_jsdp(["next"], workspace=workspace)


def harness_verify(*, workspace: Optional[str] = None) -> dict[str, Any]:
    return run_jsdp(["verify"], workspace=workspace)


def harness_continue(*, workspace: Optional[str] = None) -> dict[str, Any]:
    return run_jsdp(["continue"], workspace=workspace)


def write_proposal_temp(proposal_json: str, *, workspace: Optional[str] = None) -> str:
    """Write agent-produced horizon JSON to workspace ``.jsdp/state/horizon-agent-proposal.json``."""
    root = Path(resolve_workspace_root(workspace))
    state = root / ".jsdp" / "state"
    state.mkdir(parents=True, exist_ok=True)
    path = state / "horizon-agent-proposal.json"
    try:
        parsed = json.loads(proposal_json)
    except json.JSONDecodeError as exc:
        raise JsdpHarnessError(f"proposal_json is not valid JSON: {exc}") from exc
    path.write_text(json.dumps(parsed, indent=2) + "\n", encoding="utf-8")
    return str(path)


def rolling_horizon_operational_hint(workspace: Optional[str] = None) -> dict[str, Any]:
    """Lightweight hint for ``joyzoning(action='context')`` without running export."""
    root = resolve_workspace_root(workspace)
    jsdp_dir = Path(root) / ".jsdp"
    return {
        "harness_present": jsdp_dir.is_dir(),
        "workspace_root": root,
        "recommended_tool": "jsdp",
        "strategy": "rolling_horizon_autonomous",
        "max_nodes_per_cycle": 5,
        "workflow": [
            "jsdp(action='prepare')",
            "Agent writes horizon JSON (≤5 nodes)",
            "jsdp(action='commit', proposal_json=…)",
            "jsdp(action='step') until re-plan",
        ],
    }
