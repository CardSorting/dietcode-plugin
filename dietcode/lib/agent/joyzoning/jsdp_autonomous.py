"""Autonomous JSDP harness bootstrap — zero manual config for typical Hermes workers."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from plugins.dietcode.lib.agent.joyzoning.config import read_scope_env
from plugins.dietcode.lib.agent.joyzoning.jsdp_execution_guide import clarity_envelope
from plugins.dietcode.lib.agent.joyzoning.jsdp_harness_client import (
    JsdpHarnessError,
    horizon_export,
    horizon_prompt,
    horizon_status,
    resolve_jz_executable,
    resolve_workspace_root,
    run_jsdp,
)


@dataclass
class BootstrapResult:
    success: bool
    workspace_root: str = ""
    jz_cli: str = ""
    harness_present: bool = False
    initialized: bool = False
    analyzed: bool = False
    goal_used: str = ""
    spec_used: str = ""
    steps: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "workspace_root": self.workspace_root,
            "jz_cli": self.jz_cli,
            "harness_present": self.harness_present,
            "initialized": self.initialized,
            "analyzed": self.analyzed,
            "goal_used": self.goal_used or None,
            "spec_used": self.spec_used or None,
            "steps": self.steps,
            "errors": self.errors,
            "fixes": self.fixes,
        }


def probe_jsdp_available() -> bool:
    """Whether the jsdp tool should be offered (permissive — bootstrap on first use)."""
    if (
        read_scope_env("HERMES_KANBAN_TASK")
        or read_scope_env("HERMES_KANBAN_WORKSPACE")
        or read_scope_env("JOYZONING_WORKSPACE_ROOT")
    ):
        return True
    try:
        probe_jz_cli()
        return True
    except JsdpHarnessError:
        return False


def probe_jz_cli() -> str:
    """Return jz path or raise with actionable message."""
    return resolve_jz_executable()


def _find_project_spec(workspace: Path) -> Optional[str]:
    for rel in ("PROJECT_SPEC.md", "docs/PROJECT_SPEC.md", "project-spec.md"):
        candidate = workspace / rel
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def _default_goal(workspace: Path) -> str:
    spec = _find_project_spec(workspace)
    if spec:
        return f"Deliver the project described in {Path(spec).name}"
    name = workspace.name or "workspace"
    return f"Bounded incremental delivery for {name}"


def _kanban_goal_hint() -> str:
    task_id = read_scope_env("HERMES_KANBAN_TASK")
    if not task_id:
        return ""
    try:
        from hermes_cli.kanban_db import get_task
        task = get_task(task_id)
        if task and getattr(task, "title", None):
            return str(task.title).strip()
    except Exception:
        pass
    return ""


def bootstrap(
    *,
    workspace: Optional[str] = None,
    goal: str = "",
    nodes: int = 3,
) -> BootstrapResult:
    """Ensure workspace, CLI, and ``.jsdp/`` exist before planning or execution."""
    result = BootstrapResult(success=False)
    try:
        root = Path(resolve_workspace_root(workspace))
        result.workspace_root = str(root)
        result.jz_cli = probe_jz_cli()
        result.harness_present = (root / ".jsdp").is_dir()
        result.steps.append(f"workspace={result.workspace_root}")

        run_path = root / ".jsdp" / "run.json"
        if not run_path.is_file():
            init_goal = (goal or "").strip() or _kanban_goal_hint() or _default_goal(root)
            spec = _find_project_spec(root)
            result.goal_used = init_goal
            if spec:
                result.spec_used = spec
                run_jsdp(["init", "--spec", spec], workspace=str(root))
                result.steps.append(f"init --spec {spec}")
            else:
                run_jsdp(["init", init_goal], workspace=str(root))
                result.steps.append("init")
            result.initialized = True
            result.harness_present = True
        else:
            result.steps.append("harness already initialized")

        spec_path = root / ".jsdp" / "project-spec.json"
        needs_analyze = True
        if spec_path.is_file():
            try:
                data = json.loads(spec_path.read_text(encoding="utf-8"))
                needs_analyze = not isinstance(data.get("analysis"), dict)
            except Exception:
                needs_analyze = True
        if needs_analyze:
            run_jsdp(["analyze"], workspace=str(root))
            result.analyzed = True
            result.steps.append("analyze")
        else:
            result.steps.append("analysis present")

        result.success = True
        return result
    except JsdpHarnessError as exc:
        result.errors.append(str(exc))
        result.fixes.extend(_fixes_for_error(str(exc)))
        return result
    except Exception as exc:
        result.errors.append(str(exc))
        return result


def _fixes_for_error(message: str) -> list[str]:
    fixes: list[str] = []
    lower = message.lower()
    if "cli not found" in lower:
        fixes.append(
            "Install JoyZoning and ensure scripts/joyzoning exists, or set JOYZONING_MONOREPO_ROOT."
        )
        fixes.append("JoyZoning desktop auto-setup runs scripts/install-diet-hermes.sh.")
    if "horizon-context" in lower or "horizon export" in lower:
        fixes.append("Call jsdp(action='prepare') before validate/import.")
    if "no jsdp run" in lower:
        fixes.append("Call jsdp(action='prepare') to auto-initialize the harness.")
    return fixes


def session_brief(*, workspace: Optional[str] = None) -> dict[str, Any]:
    """Lightweight snapshot for session start (no init side effects)."""
    from plugins.dietcode.lib.agent.joyzoning.jsdp_execution_guide import determine_phase

    try:
        root = resolve_workspace_root(workspace)
        cli_ok = True
        jz = probe_jz_cli()
        harness_present = (Path(root) / ".jsdp").is_dir()
        horizon = None
        if harness_present:
            try:
                horizon = horizon_status(workspace=root)
            except JsdpHarnessError:
                pass
        guide = determine_phase(
            cli_ok=cli_ok,
            harness_present=harness_present,
            horizon=horizon if isinstance(horizon, dict) else None,
        )
        return clarity_envelope(
            {
                "success": True,
                "workspace_root": root,
                "jz_cli": jz,
                "first_call": guide.get("agent_next_call") or "jsdp(action='start')",
            },
            cli_ok=cli_ok,
            harness_present=harness_present,
            horizon=horizon if isinstance(horizon, dict) else None,
        )
    except JsdpHarnessError as exc:
        return clarity_envelope(
            {"success": False, "error": str(exc)},
            cli_ok=False,
            harness_present=False,
        )


def prepare_planning(
    *,
    workspace: Optional[str] = None,
    goal: str = "",
    nodes: int = 3,
) -> dict[str, Any]:
    """One call: bootstrap → horizon export → prompt; return paths + prompt text."""
    boot = bootstrap(workspace=workspace, goal=goal, nodes=nodes)
    out: dict[str, Any] = {"bootstrap": boot.to_dict(), "success": boot.success}
    if not boot.success:
        return clarity_envelope(
            {**out, "next_action": "jsdp(action='guide') for diagnostics"},
            cli_ok=False,
            harness_present=boot.harness_present,
        )

    n = max(3, min(5, int(nodes)))
    export = horizon_export(nodes=n, workspace=boot.workspace_root)
    prompt = horizon_prompt(nodes=n, workspace=boot.workspace_root)
    out["export"] = export
    out["prompt"] = prompt

    prompt_path = ""
    if isinstance(prompt, dict):
        prompt_path = str(prompt.get("promptPath") or prompt.get("PromptPath") or "")
    if prompt_path and Path(prompt_path).is_file():
        text = Path(prompt_path).read_text(encoding="utf-8", errors="replace")
        if len(text) > 28000:
            text = text[:28000] + "\n…(truncated — read file for full prompt)"
        out["planning_prompt_text"] = text

    ctx_path = ""
    if isinstance(export, dict):
        ctx_path = str(
            export.get("horizonContextPath")
            or export.get("HorizonContextPath")
            or ""
        )
    if ctx_path and Path(ctx_path).is_file():
        try:
            out["horizon_context"] = json.loads(Path(ctx_path).read_text(encoding="utf-8"))
        except Exception:
            out["horizon_context_path"] = ctx_path

    out["success"] = True
    out["next_action"] = (
        "jsdp(action='apply', proposal_json='…') with ≤{n} nodes (JSON only)"
    ).format(n=n)
    out["limits"] = {
        "max_nodes": n,
        "json_only": True,
        "do_not": "full-project planning or import-plan",
    }
    return clarity_envelope(
        out,
        cli_ok=True,
        harness_present=True,
        horizon=out.get("horizon_context") if isinstance(out.get("horizon_context"), dict) else None,
    )


def commit_proposal(
    proposal_json: str,
    *,
    workspace: Optional[str] = None,
    nodes: int = 3,
    skip_dry_run: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Validate, diff, dry-run import, and import a horizon proposal."""
    from plugins.dietcode.lib.agent.joyzoning.jsdp_harness_client import (
        horizon_diff,
        horizon_import,
        horizon_validate,
        write_proposal_temp,
    )

    boot = bootstrap(workspace=workspace, nodes=nodes)
    result: dict[str, Any] = {"bootstrap": boot.to_dict(), "success": False}
    if not boot.success:
        return clarity_envelope(
            result,
            cli_ok=bool(boot.jz_cli),
            harness_present=boot.harness_present,
        )

    # Ensure export context exists for validate
    horizon_export(nodes=max(3, min(5, int(nodes))), workspace=boot.workspace_root)

    path = write_proposal_temp(proposal_json, workspace=boot.workspace_root)
    n = max(3, min(5, int(nodes)))
    validation = horizon_validate(path, nodes=n, workspace=boot.workspace_root)
    result["validate"] = validation

    valid = False
    if isinstance(validation, dict):
        valid = bool(validation.get("valid") or validation.get("Valid"))
    if not valid:
        result["proposal_path"] = path
        result["next_action"] = "Fix validation errors and jsdp(action='apply', proposal_json=…) again"
        return clarity_envelope(
            result,
            cli_ok=True,
            harness_present=True,
        )

    result["diff"] = horizon_diff(path, nodes=n, workspace=boot.workspace_root)
    if not skip_dry_run:
        result["dry_run"] = horizon_import(
            path, dry_run=True, force=force, workspace=boot.workspace_root
        )
    result["import"] = horizon_import(
        path, dry_run=False, force=force, workspace=boot.workspace_root
    )
    imported = result.get("import") or {}
    horizon = None
    try:
        horizon = horizon_status(workspace=boot.workspace_root)
        result["horizon_status"] = horizon
    except JsdpHarnessError:
        pass

    if isinstance(imported, dict) and (imported.get("imported") or imported.get("Imported")):
        result["success"] = True
        result["next_action"] = "jsdp(action='advance') repeatedly; jsdp(action='guide') when unsure"
    else:
        result["next_action"] = "jsdp(action='guide') — import did not complete"
    result["proposal_path"] = path
    return clarity_envelope(
        result,
        cli_ok=True,
        harness_present=True,
        horizon=horizon if isinstance(horizon, dict) else None,
    )


def autonomous_step(*, workspace: Optional[str] = None) -> dict[str, Any]:
    """Run the next harness command based on current DAG state (no guessing by the agent)."""
    boot = bootstrap(workspace=workspace)
    out: dict[str, Any] = {"bootstrap": boot.to_dict(), "success": False}
    if not boot.success:
        return clarity_envelope(
            out,
            cli_ok=bool(boot.jz_cli),
            harness_present=boot.harness_present,
        )

    hstatus = horizon_status(workspace=boot.workspace_root)
    out["horizon_status"] = hstatus
    suggested = ""
    if isinstance(hstatus, dict):
        suggested = str(hstatus.get("suggestedAction") or hstatus.get("SuggestedAction") or "")

    failed = []
    if isinstance(hstatus, dict):
        failed = list(hstatus.get("failedNodeIds") or hstatus.get("FailedNodeIds") or [])

    if failed:
        out["ran"] = "continue"
        out["result"] = run_jsdp(["continue"], workspace=boot.workspace_root)
        out["success"] = True
        out["next_action"] = "Repair failed node, then jsdp(action='advance')"
        return clarity_envelope(
            out, cli_ok=True, harness_present=True, horizon=hstatus
        )

    if "continue" in suggested.lower() or "repair" in suggested.lower():
        out["ran"] = "continue"
        out["result"] = run_jsdp(["continue"], workspace=boot.workspace_root)
        out["success"] = True
        out["next_action"] = "jsdp(action='advance') after repair"
        return clarity_envelope(
            out, cli_ok=True, harness_present=True, horizon=hstatus
        )

    if "export" in suggested.lower() and "re-export" in suggested.lower():
        out["ran"] = "none"
        out["next_action"] = "jsdp(action='start') — context stale"
        return clarity_envelope(
            out, cli_ok=True, harness_present=True, horizon=hstatus
        )

    if "next" in suggested.lower():
        out["ran"] = "next"
        out["result"] = run_jsdp(["next"], workspace=boot.workspace_root)
        out["success"] = True
        out["next_action"] = "Implement node prompt, then jsdp(action='advance')"
        return clarity_envelope(
            out, cli_ok=True, harness_present=True, horizon=hstatus
        )

    verify_result = run_jsdp(["verify"], workspace=boot.workspace_root)
    out["ran"] = "verify"
    out["result"] = verify_result
    if isinstance(verify_result, dict) and verify_result.get("passed") is True:
        out["success"] = True
        out["next_action"] = "jsdp(action='advance') or jsdp(action='start') for next horizon"
        return clarity_envelope(
            out, cli_ok=True, harness_present=True, horizon=hstatus
        )

    out["ran"] = "next"
    out["result"] = run_jsdp(["next"], workspace=boot.workspace_root)
    out["success"] = True
    out["next_action"] = "Work the returned node prompt, then jsdp(action='advance')"
    return clarity_envelope(
        out,
        cli_ok=True,
        harness_present=True,
        horizon=hstatus if isinstance(hstatus, dict) else None,
    )


def operational_status(*, workspace: Optional[str] = None) -> dict[str, Any]:
    """Diagnostics + recommended next action — safe to call anytime."""
    result: dict[str, Any] = {"success": True}
    try:
        root = resolve_workspace_root(workspace)
        jz = probe_jz_cli()
        result["workspace_root"] = root
        result["jz_cli"] = jz
        result["harness_present"] = Path(root).joinpath(".jsdp").is_dir()
        result["kanban_task"] = read_scope_env("HERMES_KANBAN_TASK") or None
    except JsdpHarnessError as exc:
        return clarity_envelope(
            {
                "success": False,
                "error": str(exc),
                "fixes": _fixes_for_error(str(exc)),
            },
            cli_ok=False,
            harness_present=False,
        )

    horizon = None
    if result["harness_present"]:
        try:
            horizon = horizon_status(workspace=root)
            result["horizon"] = horizon
        except JsdpHarnessError as exc:
            result["horizon_error"] = str(exc)

    return clarity_envelope(
        {
            **result,
            "tool_actions": {
                "start": "begin session — init .jsdp/ + planning context (alias: prepare)",
                "apply": "commit horizon JSON to DAG (alias: commit)",
                "advance": "run next harness step automatically (alias: step)",
                "guide": "this view — phase + next call (alias: status)",
            },
        },
        cli_ok=True,
        harness_present=result["harness_present"],
        horizon=horizon if isinstance(horizon, dict) else None,
    )
