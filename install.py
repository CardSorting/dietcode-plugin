# -*- coding: utf-8 -*-
"""Seamless Hermes integration — config defaults and BroccoliDB runtime setup."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PLUGIN_NAME = "dietcode"
_MARKER = ".dietcode-integrated"


def plugin_root() -> Path:
    return Path(__file__).resolve().parent


def broccolidb_root() -> Path:
    return plugin_root() / "broccolidb"


def kernel_root() -> Path:
    """Deprecated — macOS kernel subtree removed; kept for import compatibility."""
    return get_plugin_root() / ".removed-kernel"


def _integration_marker() -> Path:
    try:
        from hermes_constants import get_hermes_home

        return get_hermes_home() / "plugins" / _PLUGIN_NAME / _MARKER
    except Exception:
        return Path.home() / ".hermes" / "plugins" / _PLUGIN_NAME / _MARKER


def broccolidb_runtime_ready() -> bool:
    root = broccolidb_root()
    if not (root / "package.json").is_file():
        return False
    nm = root / "node_modules"
    return nm.is_dir() and any(nm.iterdir())


def ensure_broccolidb_runtime(*, auto_npm: bool = False, timeout: int = 300) -> dict[str, Any]:
    """Ensure node_modules exists; optionally run ``npm ci``."""
    root = broccolidb_root()
    if not (root / "package.json").is_file():
        return {"ok": False, "error": "broccolidb/package.json missing from plugin bundle"}

    if broccolidb_runtime_ready():
        return {"ok": True, "root": str(root), "action": "ready"}

    if not auto_npm or not shutil.which("npm"):
        return {
            "ok": False,
            "root": str(root),
            "action": "npm_ci_required",
            "hint": f"cd {root} && npm ci",
        }

    try:
        proc = subprocess.run(
            ["npm", "ci"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "CI": "1"},
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:500]
            return {"ok": False, "action": "npm_ci_failed", "error": err or f"exit {proc.returncode}"}
        return {"ok": True, "root": str(root), "action": "npm_ci"}
    except subprocess.TimeoutExpired:
        return {"ok": False, "action": "npm_ci_timeout", "error": f"npm ci exceeded {timeout}s"}
    except OSError as exc:
        return {"ok": False, "action": "npm_ci_error", "error": str(exc)}


def apply_seamless_defaults(*, save: bool = True) -> dict[str, Any]:
    """Merge DietCode-friendly defaults into the active Hermes config."""
    try:
        from hermes_cli.config import load_config, save_config
    except ImportError:
        return {"ok": False, "error": "hermes_cli not available"}

    config = load_config()
    changed: list[str] = []

    plugins_cfg = config.setdefault("plugins", {})
    if not isinstance(plugins_cfg, dict):
        plugins_cfg = {}
        config["plugins"] = plugins_cfg

    enabled = plugins_cfg.get("enabled")
    if enabled is None:
        enabled = []
    if not isinstance(enabled, list):
        enabled = []
    enabled_set = set(enabled)
    if _PLUGIN_NAME not in enabled_set:
        enabled_set.add(_PLUGIN_NAME)
        plugins_cfg["enabled"] = sorted(enabled_set)
        changed.append("plugins.enabled")

    disabled = plugins_cfg.get("disabled") or []
    if isinstance(disabled, list) and _PLUGIN_NAME in disabled:
        disabled = [x for x in disabled if x != _PLUGIN_NAME]
        plugins_cfg["disabled"] = disabled
        changed.append("plugins.disabled")

    toolsets = config.get("toolsets")
    if toolsets is None:
        toolsets = ["hermes-cli"]
    if not isinstance(toolsets, list):
        toolsets = ["hermes-cli"]
    toolsets_changed = False
    for toolset_name in (_PLUGIN_NAME, "roadmap"):
        if toolset_name not in toolsets:
            toolsets = list(toolsets) + [toolset_name]
            toolsets_changed = True
    if toolsets_changed:
        config["toolsets"] = toolsets
        changed.append("toolsets")

    jz = config.setdefault("joyzoning", {})
    if isinstance(jz, dict):
        gov = jz.setdefault("governance", {})
        if isinstance(gov, dict) and "enabled" not in gov:
            gov["enabled"] = True
            changed.append("joyzoning.governance.enabled")

    dietcode = config.setdefault("dietcode", {})
    if isinstance(dietcode, dict):
        ws_cfg = dietcode.setdefault("workspace", {})
        if isinstance(ws_cfg, dict) and "workspace_root_source" not in ws_cfg:
            ws_cfg["workspace_root_source"] = "hermes_project"
            changed.append("dietcode.workspace.workspace_root_source")
        # Back-compat: also seed legacy kernel.workspace_root_source when absent.
        kernel_cfg = dietcode.setdefault("kernel", {})
        if isinstance(kernel_cfg, dict) and "workspace_root_source" not in kernel_cfg:
            kernel_cfg["workspace_root_source"] = "hermes_project"
            changed.append("dietcode.kernel.workspace_root_source")

        roadmap_cfg = dietcode.setdefault("roadmap", {})
        if isinstance(roadmap_cfg, dict):
            if "enabled" not in roadmap_cfg:
                roadmap_cfg["enabled"] = True
                changed.append("dietcode.roadmap.enabled")
            if "auto_install_skills" not in roadmap_cfg:
                roadmap_cfg["auto_install_skills"] = True
                changed.append("dietcode.roadmap.auto_install_skills")
            if "nudge_on_roadmap_write" not in roadmap_cfg:
                roadmap_cfg["nudge_on_roadmap_write"] = True
                changed.append("dietcode.roadmap.nudge_on_roadmap_write")
            if "progress_enabled" not in roadmap_cfg:
                roadmap_cfg["progress_enabled"] = True
                changed.append("dietcode.roadmap.progress_enabled")
            if "stale_checkpoint_days" not in roadmap_cfg:
                roadmap_cfg["stale_checkpoint_days"] = 7
                changed.append("dietcode.roadmap.stale_checkpoint_days")
            if "warn_on_stale_before_complete" not in roadmap_cfg:
                roadmap_cfg["warn_on_stale_before_complete"] = True
                changed.append("dietcode.roadmap.warn_on_stale_before_complete")
            if "block_kanban_on_invalid_schema" not in roadmap_cfg:
                roadmap_cfg["block_kanban_on_invalid_schema"] = False
                changed.append("dietcode.roadmap.block_kanban_on_invalid_schema")
            if "block_kanban_on_validation_pending" not in roadmap_cfg:
                roadmap_cfg["block_kanban_on_validation_pending"] = True
                changed.append("dietcode.roadmap.block_kanban_on_validation_pending")
            if "evidence_cache_ttl_seconds" not in roadmap_cfg:
                roadmap_cfg["evidence_cache_ttl_seconds"] = 15
                changed.append("dietcode.roadmap.evidence_cache_ttl_seconds")
            if "git_timeout_seconds" not in roadmap_cfg:
                roadmap_cfg["git_timeout_seconds"] = 5
                changed.append("dietcode.roadmap.git_timeout_seconds")
            if "heavy_scan_cache_ttl_seconds" not in roadmap_cfg:
                roadmap_cfg["heavy_scan_cache_ttl_seconds"] = 60
                changed.append("dietcode.roadmap.heavy_scan_cache_ttl_seconds")

    if save and changed:
        save_config(config)
        logger.info("DietCode: applied seamless defaults (%s)", ", ".join(changed))

    try:
        _integration_marker().write_text("ok\n", encoding="utf-8")
    except OSError:
        pass

    return {"ok": True, "changed": changed, "saved": bool(save and changed)}


def ensure_kernel_built(*, auto_build: bool = False, timeout: int = 600) -> dict[str, Any]:
    """Deprecated — native mutation replaced macOS kernel bridge."""
    return {"ok": True, "action": "removed", "hint": "kernel subtree removed; use dietcode_kernel native tool"}


def run_install_wizard(*, auto_npm: bool = True, auto_kernel: bool = False) -> dict[str, Any]:
    """CLI / drag-and-drop installer — config + optional npm ci."""
    cfg = apply_seamless_defaults(save=True)
    runtime = ensure_broccolidb_runtime(auto_npm=auto_npm)
    ok = bool(cfg.get("ok", True)) and bool(runtime.get("ok", True))
    return {"ok": ok, "config": cfg, "broccolidb": runtime}


_SYNC_EXCLUDES = (
    ".git",
    ".DS_Store",
    "broccolidb/node_modules",
    "__pycache__",
)


def hermes_home() -> Path:
    raw = os.environ.get("HERMES_HOME", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return Path.home() / ".hermes"


def hermes_venv_root() -> Path:
    custom = os.environ.get("HERMES_VENV", "").strip()
    if custom:
        return Path(custom).expanduser().resolve()
    return hermes_home() / "hermes-agent" / "venv"


def plugin_install_dest() -> Path:
    return hermes_home() / "plugins" / _PLUGIN_NAME


def _editable_hermes_src(*, venv: Path) -> Path | None:
    pip = venv / "bin" / "pip"
    if not pip.is_file():
        return None
    try:
        proc = subprocess.run(
            [str(pip), "show", "hermes-agent"],
            capture_output=True,
            text=True,
            timeout=30,
            env={k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}},
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    for line in proc.stdout.splitlines():
        if line.startswith("Editable project location:"):
            loc = line.split(":", 1)[1].strip()
            if loc:
                path = Path(loc).expanduser().resolve()
                if path.is_dir():
                    return path
    return None


def resolve_hermes_src(explicit: str | Path | None = None) -> Path:
    """Locate the Hermes agent checkout for editable reinstall."""
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not (path / "pyproject.toml").is_file():
            raise FileNotFoundError(f"Hermes source not found (missing pyproject.toml): {path}")
        return path

    env = os.environ.get("HERMES_SRC", "").strip()
    if env:
        return resolve_hermes_src(env)

    venv = hermes_venv_root()
    detected = _editable_hermes_src(venv=venv)
    if detected is not None:
        return detected

    candidates = [
        Path.home() / "Downloads" / "hermes-agent-main 2",
        Path.home() / "Downloads" / "hermes-agent-main",
        hermes_home() / "hermes-agent",
    ]
    for candidate in candidates:
        if (candidate / "pyproject.toml").is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "Could not locate Hermes source. Set HERMES_SRC or pass --hermes-src /path/to/hermes-agent"
    )


def _rsync_plugin(src: Path, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("rsync"):
        cmd = ["rsync", "-a", "--delete"]
        for item in _SYNC_EXCLUDES:
            cmd.extend(["--exclude", item])
        cmd.extend([f"{src}/", f"{dest}/"])
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "").strip()[:500]
            return {"ok": False, "action": "rsync", "error": err or f"exit {proc.returncode}"}
        return {"ok": True, "action": "rsync", "dest": str(dest)}

    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(
        src,
        dest,
        ignore=shutil.ignore_patterns(*_SYNC_EXCLUDES, "*.pyc"),
    )
    return {"ok": True, "action": "copytree", "dest": str(dest)}


def sync_plugin_to_hermes(
    *,
    src: Path | None = None,
    dest: Path | None = None,
    hermes_src: Path | None = None,
    sync_bundled_copy: bool = True,
) -> dict[str, Any]:
    """Copy this plugin tree into ~/.hermes/plugins/dietcode (and optional bundled path)."""
    root = (src or plugin_root()).resolve()
    target = (dest or plugin_install_dest()).resolve()
    results: dict[str, Any] = {"ok": True, "src": str(root), "destinations": []}

    primary = _rsync_plugin(root, target)
    results["destinations"].append({"path": str(target), **primary})
    if not primary.get("ok"):
        results["ok"] = False

    if sync_bundled_copy and hermes_src is not None:
        bundled = Path(hermes_src) / "plugins" / "dietcode-plugin"
        if bundled.resolve() != target:
            bundled_sync = _rsync_plugin(root, bundled)
            results["destinations"].append({"path": str(bundled), **bundled_sync})
            if not bundled_sync.get("ok"):
                results["ok"] = False

    return results


def reinstall_hermes_editable(*, hermes_src: Path, venv: Path | None = None) -> dict[str, Any]:
    """pip install -e the Hermes checkout into the active Hermes venv."""
    venv = venv or hermes_venv_root()
    pip = venv / "bin" / "pip"
    if not pip.is_file():
        return {"ok": False, "error": f"pip not found in Hermes venv: {pip}"}

    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    try:
        proc = subprocess.run(
            [str(pip), "install", "-e", str(hermes_src)],
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "pip install timed out after 600s"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()[:800]
        return {"ok": False, "error": err or f"pip exit {proc.returncode}"}

    return {"ok": True, "hermes_src": str(hermes_src), "venv": str(venv)}


def enable_dietcode_plugin(*, hermes_bin: str | None = None) -> dict[str, Any]:
    """Ensure dietcode is enabled in Hermes plugin registry."""
    cmd = hermes_bin or shutil.which("hermes") or str(hermes_venv_root() / "bin" / "hermes")
    if not Path(cmd).exists() and not shutil.which(cmd):
        return {"ok": False, "error": f"hermes CLI not found: {cmd}"}

    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    try:
        proc = subprocess.run(
            [cmd, "plugins", "enable", _PLUGIN_NAME],
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"ok": False, "error": str(exc)}

    out = (proc.stdout or proc.stderr or "").strip()
    already = "already enabled" in out.lower()
    if proc.returncode != 0 and not already:
        return {"ok": False, "error": out or f"exit {proc.returncode}"}
    return {"ok": True, "message": out or "enabled", "already_enabled": already}


def verify_hermes_deployment(
    *,
    plugin_dest: Path | None = None,
    venv: Path | None = None,
    run_tests: bool = True,
) -> dict[str, Any]:
    """Run roadmap smoke, audit, and unit tests against the installed plugin copy."""
    dest = (plugin_dest or plugin_install_dest()).resolve()
    python = (venv or hermes_venv_root()) / "bin" / "python"
    if not python.is_file():
        return {"ok": False, "error": f"python not found: {python}"}

    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}
    checks: list[dict[str, Any]] = []

    def _run(label: str, args: list[str], *, timeout: int = 120) -> None:
        try:
            proc = subprocess.run(
                args,
                cwd=dest,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )
            checks.append({
                "name": label,
                "ok": proc.returncode == 0,
                "exit_code": proc.returncode,
                "output_tail": (proc.stdout or proc.stderr or "").strip()[-400:],
            })
        except (OSError, subprocess.TimeoutExpired) as exc:
            checks.append({"name": label, "ok": False, "error": str(exc)})

    _run("roadmap_smoke", [str(python), "scripts/roadmap_smoke.py"])
    _run("roadmap_audit", [str(python), "scripts/roadmap_audit.py"])
    _run("roadmap_operator_smoke", [str(python), "scripts/roadmap_operator_smoke.py"])
    if run_tests:
        _run(
            "roadmap_tests",
            [str(python), "-m", "unittest", "tests.test_roadmap_checkpoint", "-q"],
            timeout=180,
        )

    ok = all(c.get("ok") for c in checks)
    return {"ok": ok, "checks": checks}


def ensure_hermes_root_deploy_script(hermes_src: Path) -> dict[str, Any]:
    """Install scripts/hermes_deploy.sh into the Hermes checkout (repo-root entrypoint)."""
    template = plugin_root() / "scripts" / "hermes_root_deploy.sh"
    dest = Path(hermes_src) / "scripts" / "hermes_deploy.sh"
    if not template.is_file():
        return {"ok": False, "error": f"template missing: {template}"}

    dest.parent.mkdir(parents=True, exist_ok=True)
    content = template.read_text(encoding="utf-8")
    if dest.is_file() and dest.read_text(encoding="utf-8") == content:
        return {"ok": True, "path": str(dest), "action": "unchanged"}

    dest.write_text(content, encoding="utf-8")
    dest.chmod(dest.stat().st_mode | 0o111)
    return {"ok": True, "path": str(dest), "action": "installed"}


def deploy_to_hermes(
    *,
    hermes_src: str | Path | None = None,
    plugin_src: str | Path | None = None,
    sync_bundled_copy: bool = True,
    reinstall_hermes: bool = True,
    auto_npm: bool = True,
    auto_kernel: bool = False,
    enable_plugin: bool = True,
    verify: bool = True,
    run_tests: bool = True,
) -> dict[str, Any]:
    """Full loop: sync plugin → reinstall Hermes → install.py → enable → verify."""
    src_root = Path(plugin_src or plugin_root()).resolve()
    hermes_path = resolve_hermes_src(hermes_src)
    venv = hermes_venv_root()
    dest = plugin_install_dest()

    report: dict[str, Any] = {
        "ok": True,
        "plugin_src": str(src_root),
        "hermes_src": str(hermes_path),
        "plugin_dest": str(dest),
        "hermes_venv": str(venv),
    }

    root_script = ensure_hermes_root_deploy_script(hermes_path)
    report["hermes_root_script"] = root_script
    if not root_script.get("ok"):
        report["ok"] = False
        return report

    sync = sync_plugin_to_hermes(
        src=src_root,
        dest=dest,
        hermes_src=hermes_path,
        sync_bundled_copy=sync_bundled_copy,
    )
    report["sync"] = sync
    if not sync.get("ok"):
        report["ok"] = False
        return report

    if reinstall_hermes:
        reinstall = reinstall_hermes_editable(hermes_src=hermes_path, venv=venv)
        report["hermes_reinstall"] = reinstall
        if not reinstall.get("ok"):
            report["ok"] = False
            return report

    python = venv / "bin" / "python"
    if not python.is_file():
        report["ok"] = False
        report["install"] = {"ok": False, "error": f"python not found: {python}"}
        return report

    # Run install wizard in-process using the synced plugin tree on sys.path.
    import sys

    dest_str = str(dest)
    if dest_str not in sys.path:
        sys.path.insert(0, dest_str)
    try:
        import importlib.util

        spec = importlib.util.spec_from_file_location("dietcode_install", dest / "install.py")
        if spec is None or spec.loader is None:
            raise ImportError("could not load install.py from plugin dest")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        install_result = mod.run_install_wizard(auto_npm=auto_npm, auto_kernel=auto_kernel)
        report["install"] = install_result
        if not install_result.get("ok"):
            report["ok"] = False
            return report
    except Exception as exc:
        report["install"] = {"ok": False, "error": str(exc)}
        report["ok"] = False
        return report

    if enable_plugin:
        enabled = enable_dietcode_plugin()
        report["enable_plugin"] = enabled
        if not enabled.get("ok"):
            report["ok"] = False
            return report

    if verify:
        verification = verify_hermes_deployment(
            plugin_dest=dest,
            venv=venv,
            run_tests=run_tests,
        )
        report["verify"] = verification
        if not verification.get("ok"):
            report["ok"] = False

    return report


if __name__ == "__main__":
    import argparse
    import json
    import sys

    parser = argparse.ArgumentParser(description="DietCode Hermes installer / deploy")
    parser.add_argument("--deploy-hermes", action="store_true", help="Sync plugin, reinstall Hermes, enable, verify")
    parser.add_argument("--hermes-src", default="", help="Path to hermes-agent checkout (or set HERMES_SRC)")
    parser.add_argument("--plugin-src", default="", help="Path to dietcode-plugin source (default: this repo)")
    parser.add_argument("--skip-hermes-reinstall", action="store_true")
    parser.add_argument("--skip-bundled-sync", action="store_true", help="Do not sync into hermes-src/plugins/dietcode-plugin")
    parser.add_argument("--skip-npm", action="store_true")
    parser.add_argument("--skip-verify", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--build-kernel", action="store_true")
    parser.add_argument("--no-enable", action="store_true", help="Skip hermes plugins enable dietcode")
    args = parser.parse_args()

    if args.deploy_hermes:
        result = deploy_to_hermes(
            hermes_src=args.hermes_src or None,
            plugin_src=args.plugin_src or None,
            sync_bundled_copy=not args.skip_bundled_sync,
            reinstall_hermes=not args.skip_hermes_reinstall,
            auto_npm=not args.skip_npm,
            auto_kernel=args.build_kernel,
            enable_plugin=not args.no_enable,
            verify=not args.skip_verify,
            run_tests=not args.skip_tests,
        )
    else:
        result = run_install_wizard(
            auto_npm=not args.skip_npm,
            auto_kernel=args.build_kernel,
        )

    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result.get("ok") else 1)
