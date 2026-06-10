# -*- coding: utf-8 -*-
"""Kernel user-workspace resolution — never treat plugin/kernel trees as project roots."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

SOURCE_HERMES_PROJECT = "hermes_project"
SOURCE_ENV_DIETCODE = "env:DIETCODE_WORKSPACE_ROOT"
SOURCE_EXPLICIT = "explicit"

_VALID_SOURCES = frozenset({SOURCE_HERMES_PROJECT, SOURCE_ENV_DIETCODE, SOURCE_EXPLICIT})
_ENV_DIETCODE_WORKSPACE = "DIETCODE_WORKSPACE_ROOT"


def _plugin_root() -> Path:
    try:
        from plugins.dietcode.paths import get_plugin_root

        return get_plugin_root()
    except ImportError:
        return Path(__file__).resolve().parents[1]


def _kernel_root() -> Path:
    try:
        from plugins.dietcode.paths import kernel_root

        return kernel_root()
    except ImportError:
        return _plugin_root() / "kernel"


def _safe_resolve(path: Path | str) -> Optional[Path]:
    try:
        return Path(path).expanduser().resolve()
    except OSError:
        return None


def _load_kernel_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        raw = load_config()
        if not isinstance(raw, dict):
            return {}
        dietcode = raw.get("dietcode", {})
        if not isinstance(dietcode, dict):
            return {}
        kernel = dietcode.get("kernel", {})
        return kernel if isinstance(kernel, dict) else {}
    except Exception:
        return {}


def _read_scope_env(key: str) -> str:
    try:
        from plugins.dietcode.lib.agent.joyzoning.config import read_scope_env

        return read_scope_env(key)
    except ImportError:
        return os.environ.get(key, "").strip()


def get_workspace_root_source() -> str:
    """Configured ``dietcode.kernel.workspace_root_source`` (default: hermes_project)."""
    cfg = _load_kernel_config()
    raw = str(cfg.get("workspace_root_source") or SOURCE_HERMES_PROJECT).strip()
    if raw in _VALID_SOURCES:
        return raw
    return SOURCE_HERMES_PROJECT


def get_explicit_workspace_root_config() -> str:
    cfg = _load_kernel_config()
    return str(cfg.get("workspace_root") or "").strip()


def is_quarantined_root(path: Path | str) -> bool:
    """True when *path* is inside the plugin install root or kernel subtree."""
    resolved = _safe_resolve(path)
    if resolved is None:
        return False
    plugin = _safe_resolve(_plugin_root())
    kernel = _safe_resolve(_kernel_root())
    return _is_under(resolved, plugin) or _is_under(resolved, kernel)


def _is_under(path: Path, base: Optional[Path]) -> bool:
    if base is None:
        return False
    if path == base:
        return True
    try:
        path.relative_to(base)
        return True
    except ValueError:
        return False


def _resolve_hermes_project_path() -> tuple[Optional[Path], str]:
    """Hermes kanban/dispatcher workspace, then cwd."""
    for key in ("HERMES_KANBAN_WORKSPACE",):
        val = _read_scope_env(key) or os.environ.get(key, "").strip()
        if val:
            resolved = _safe_resolve(val)
            if resolved is not None:
                return resolved, f"hermes_project:{key}"

    try:
        from hermes_cli.config import load_config

        raw = load_config()
        if isinstance(raw, dict):
            kanban = raw.get("kanban", {})
            if isinstance(kanban, dict):
                ws = str(kanban.get("workspace") or kanban.get("workspace_root") or "").strip()
                if ws:
                    resolved = _safe_resolve(ws)
                    if resolved is not None:
                        return resolved, "hermes_project:kanban.workspace"
    except Exception:
        pass

    cwd = _safe_resolve(Path.cwd())
    if cwd is not None:
        if is_quarantined_root(cwd):
            return None, "hermes_project:quarantined_cwd"
        return cwd, "hermes_project:cwd"
    return None, "hermes_project:unresolved"


def _resolve_env_dietcode_path() -> tuple[Optional[Path], str]:
    val = os.environ.get(_ENV_DIETCODE_WORKSPACE, "").strip()
    if not val:
        return None, f"{SOURCE_ENV_DIETCODE}:unset"
    resolved = _safe_resolve(val)
    if resolved is None:
        return None, f"{SOURCE_ENV_DIETCODE}:invalid"
    return resolved, SOURCE_ENV_DIETCODE


def _resolve_explicit_path() -> tuple[Optional[Path], str]:
    raw = get_explicit_workspace_root_config()
    if not raw:
        return None, f"{SOURCE_EXPLICIT}:unset"
    resolved = _safe_resolve(raw)
    if resolved is None:
        return None, f"{SOURCE_EXPLICIT}:invalid"
    return resolved, SOURCE_EXPLICIT


def resolve_workspace_root_path(*, source: Optional[str] = None) -> tuple[Optional[Path], str]:
    """Resolve a candidate workspace path without validation."""
    src = source or get_workspace_root_source()
    if src == SOURCE_HERMES_PROJECT:
        return _resolve_hermes_project_path()
    if src == SOURCE_ENV_DIETCODE:
        return _resolve_env_dietcode_path()
    if src == SOURCE_EXPLICIT:
        return _resolve_explicit_path()
    return None, f"unknown_source:{src}"


def _is_writable_dir(path: Path) -> bool:
    if not path.is_dir():
        return False
    if os.access(path, os.W_OK):
        return True
    probe = path / f".dietcode_write_probe_{os.getpid()}"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False


@dataclass
class WorkspaceValidation:
    ok: bool
    safe_for_mutation: bool
    errors: list[str] = field(default_factory=list)
    checks: dict[str, bool] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "safe_for_mutation": self.safe_for_mutation,
            "errors": list(self.errors),
            "checks": dict(self.checks),
        }


def validate_workspace_root(
    path: Optional[Path | str],
    *,
    plugin_root: Optional[Path] = None,
    kernel_root: Optional[Path] = None,
) -> WorkspaceValidation:
    """Validate a resolved workspace root for kernel mutation (Phase 2 prep)."""
    plugin = _safe_resolve(plugin_root or _plugin_root())
    kernel = _safe_resolve(kernel_root or _kernel_root())
    errors: list[str] = []
    checks: dict[str, bool] = {}

    if path is None:
        return WorkspaceValidation(
            ok=False,
            safe_for_mutation=False,
            errors=["workspace_root unresolved"],
            checks={"resolved": False},
        )

    resolved = _safe_resolve(path)
    if resolved is None:
        return WorkspaceValidation(
            ok=False,
            safe_for_mutation=False,
            errors=["workspace_root path could not be resolved"],
            checks={"resolved": False},
        )

    checks["resolved"] = True
    checks["exists"] = resolved.exists()
    if not checks["exists"]:
        errors.append(f"workspace_root does not exist: {resolved}")

    checks["is_directory"] = resolved.is_dir()
    if checks["exists"] and not checks["is_directory"]:
        errors.append(f"workspace_root is not a directory: {resolved}")

    checks["not_plugin_root"] = plugin is None or not _is_under(resolved, plugin)
    if plugin is not None and _is_under(resolved, plugin):
        errors.append(f"workspace_root must not be inside plugin_root: {resolved}")

    checks["not_kernel_root"] = kernel is None or not _is_under(resolved, kernel)
    if kernel is not None and _is_under(resolved, kernel):
        errors.append("workspace_root must not be inside kernel_root (quarantined subtree)")

    checks["writable"] = _is_writable_dir(resolved) if checks["is_directory"] else False
    if checks["is_directory"] and not checks["writable"]:
        errors.append(f"workspace_root is not writable: {resolved}")

    ok = all(
        checks.get(key, False)
        for key in ("resolved", "exists", "is_directory", "not_plugin_root", "not_kernel_root", "writable")
    )
    return WorkspaceValidation(ok=ok, safe_for_mutation=ok, errors=errors, checks=checks)


@dataclass
class WorkspaceResolution:
    source: str
    resolution_detail: str
    plugin_root: str
    kernel_root: str
    resolved_workspace_root: Optional[str]
    validation: WorkspaceValidation

    @property
    def ok(self) -> bool:
        return self.validation.ok

    @property
    def safe_for_mutation(self) -> bool:
        return self.validation.safe_for_mutation

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "resolution_detail": self.resolution_detail,
            "plugin_root": self.plugin_root,
            "kernel_root": self.kernel_root,
            "resolved_workspace_root": self.resolved_workspace_root,
            "safe_for_mutation": self.safe_for_mutation,
            "ok": self.ok,
            **self.validation.to_dict(),
        }


def resolve_workspace_root(*, source: Optional[str] = None) -> WorkspaceResolution:
    """Resolve and validate the Hermes user workspace for kernel bridge (Phase 2)."""
    src = source or get_workspace_root_source()
    plugin = _safe_resolve(_plugin_root())
    kernel = _safe_resolve(_kernel_root())
    candidate, detail = resolve_workspace_root_path(source=src)
    validation = validate_workspace_root(candidate, plugin_root=plugin, kernel_root=kernel)
    if candidate is None and not validation.errors:
        validation = WorkspaceValidation(
            ok=False,
            safe_for_mutation=False,
            errors=[f"workspace_root_source={src!r} did not resolve ({detail})"],
            checks={"resolved": False},
        )
    return WorkspaceResolution(
        source=src,
        resolution_detail=detail,
        plugin_root=str(plugin) if plugin else str(_plugin_root()),
        kernel_root=str(kernel) if kernel else str(_kernel_root()),
        resolved_workspace_root=str(candidate) if candidate else None,
        validation=validation,
    )


def build_workspace_health() -> dict[str, Any]:
    """Doctor payload for workspace boundary checks."""
    report = resolve_workspace_root()
    payload = report.to_dict()
    if not report.safe_for_mutation and report.resolved_workspace_root:
        if is_quarantined_root(report.resolved_workspace_root):
            payload["hint"] = (
                "Point workspace_root_source at the Hermes project (hermes_project) or set "
                f"env:{_ENV_DIETCODE_WORKSPACE} / dietcode.kernel.workspace_root — never plugin/ or kernel/."
            )
    elif not report.resolved_workspace_root:
        payload["hint"] = (
            "Set HERMES_KANBAN_WORKSPACE, "
            f"{_ENV_DIETCODE_WORKSPACE}, or dietcode.kernel.workspace_root (explicit source)."
        )
    return payload
