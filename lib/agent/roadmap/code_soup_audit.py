"""Programmatic code soup and centralization heuristics."""
from __future__ import annotations

import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from plugins.dietcode.lib.agent.roadmap.workspace_scan import HeavyScanResult

_ENTRY_PATTERNS = (
    re.compile(r"if\s+__name__\s*==\s*['\"]__main__['\"]"),
    re.compile(r"def\s+main\s*\("),
    re.compile(r"register_command\s*\("),
    re.compile(r"registry\.register\s*\("),
)

_HOOK_MARKERS = (
    "register_hook(",
    "ctx.register_hook(",
    "register_all_hooks",
)

_CONFIG_NAMES = (
    "package.json",
    "plugin.yaml",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "config.yaml",
    "tsconfig.json",
)


def _find_duplicate_basenames(files: list[tuple[str, str]]) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    paths_by_name: dict[str, list[str]] = {}
    for rel, _ in files:
        name = Path(rel).name
        counts[name] += 1
        paths_by_name.setdefault(name, []).append(rel)
    dupes = []
    for name, count in counts.most_common():
        if count < 2:
            break
        if name in {"__init__.py", "index.ts", "types.ts", "config.py", "config.ts"}:
            continue
        dupes.append({
            "basename": name,
            "count": count,
            "paths": paths_by_name[name][:6],
        })
    return dupes[:8]


def _find_entry_surfaces(files: list[tuple[str, str]], *, limit: int = 250) -> list[dict[str, str]]:
    hits: list[dict[str, str]] = []
    for rel, text in files[:limit]:
        for pattern in _ENTRY_PATTERNS:
            if pattern.search(text):
                hits.append({"path": rel, "signal": pattern.pattern[:40]})
                break
        if len(hits) >= 20:
            break
    return hits


def _find_hook_surfaces(files: list[tuple[str, str]], *, limit: int = 200) -> list[str]:
    found: list[str] = []
    for rel, text in files[:limit]:
        if any(marker in text for marker in _HOOK_MARKERS):
            found.append(rel)
    return found[:12]


def _find_config_sources(root: Path) -> list[str]:
    return [name for name in _CONFIG_NAMES if (root / name).is_file()]


def _find_parallel_commands(files: list[tuple[str, str]], *, limit: int = 150) -> list[str]:
    commands: list[str] = []
    for _, text in files[:limit]:
        for match in re.finditer(r'register_command\s*\(\s*["\']([^"\']+)["\']', text):
            commands.append(match.group(1))
        for match in re.finditer(r'ctx\.register_command\s*\(\s*["\']([^"\']+)["\']', text):
            commands.append(match.group(1))
    tallies = Counter(commands)
    return [cmd for cmd, n in tallies.items() if n > 1]


def assess_code_soup(
    workspace: str | Path,
    *,
    heavy_scan: Optional["HeavyScanResult"] = None,
) -> dict[str, Any]:
    """Run filesystem heuristics aligned with the skill's code soup detection."""
    root = Path(workspace).expanduser().resolve()
    if heavy_scan is None:
        from plugins.dietcode.lib.agent.roadmap.workspace_scan import get_heavy_scan

        heavy_scan = get_heavy_scan(root)

    files = heavy_scan.source_files
    duplicate_basenames = _find_duplicate_basenames(files)
    entry_surfaces = _find_entry_surfaces(files)
    hook_surfaces = _find_hook_surfaces(files)
    config_sources = _find_config_sources(root)
    parallel_commands = _find_parallel_commands(files)

    signals: list[dict[str, str]] = []
    if len(entry_surfaces) > 12:
        signals.append({
            "code": "many_entry_surfaces",
            "detail": f"{len(entry_surfaces)} files expose CLI/tool entry points",
        })
    if len(hook_surfaces) > 3:
        signals.append({
            "code": "multiple_hook_registrars",
            "detail": f"Hook registration spread across {len(hook_surfaces)} files",
        })
    if len(config_sources) > 3:
        signals.append({
            "code": "multiple_config_sources",
            "detail": f"Config files present: {', '.join(config_sources)}",
        })
    if duplicate_basenames:
        signals.append({
            "code": "duplicate_basenames",
            "detail": f"{len(duplicate_basenames)} duplicate source basenames",
        })
    if parallel_commands:
        signals.append({
            "code": "duplicate_command_registration",
            "detail": f"Commands registered more than once: {', '.join(parallel_commands[:5])}",
        })

    risk = "Low"
    if len(signals) >= 3:
        risk = "High"
    elif signals:
        risk = "Medium"

    recommendation = "Document the canonical mutation, inspection, and command surfaces in section 1."
    if duplicate_basenames:
        recommendation = (
            f"Converge duplicate modules ({duplicate_basenames[0]['basename']}) "
            "or document which path is canonical."
        )
    elif len(hook_surfaces) > 3:
        recommendation = "Centralize hook registration behind one composed registrar."
    elif len(entry_surfaces) > 12:
        recommendation = "Collapse operator entry points into one command surface where possible."

    return {
        "overall_risk": risk,
        "signals": signals,
        "duplicate_basenames": duplicate_basenames,
        "entry_surface_count": len(entry_surfaces),
        "entry_surfaces_sample": entry_surfaces[:8],
        "hook_registrar_files": hook_surfaces,
        "config_sources": config_sources,
        "parallel_command_names": parallel_commands,
        "centralization_recommendation": recommendation,
    }
