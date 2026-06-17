"""Production hardening audit — detect non-production antipatterns in plugin sources."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable

from plugins.dietcode.audit import dietcode_plugin_root

_FORBIDDEN_IN_PRODUCTION = re.compile(
    r"\b(mock|stub|simulated|not implemented|TODO implement)\b",
    re.IGNORECASE,
)

_DEAD_CODE_PATTERN = re.compile(
    r"\bif\s+False\b|\braise\s+NotImplementedError\b",
)

_RECOVERY_COMMAND_FILES: frozenset[str] = frozenset({
    "lib/agent/recovery_catalog.py",
    "lib/agent/ergonomics.py",
    "lib/agent/audit/quality_gate.py",
    "lib/agent/audit/completion_gate.py",
})

_ANGLE_BRACKET_PLACEHOLDER = re.compile(r"<[a-z][^>]{0,80}>")

_EXCLUDED_SCAN_FILES: frozenset[str] = frozenset({
    "lib/agent/production_audit.py",
    "scripts/production_hardening_audit.py",
    "scripts/roadmap_audit.py",
})

# Line substrings that legitimately mention forbidden words in production code.
_LINE_ALLOWLIST_SUBSTRINGS: tuple[str, ...] = (
    "bootstrap_placeholder",
    "find_bootstrap_placeholders",
    "BOOTSTRAP_PLACEHOLDER",
    "unfilled bootstrap",
    "bootstrap_complete",
    "placeholder guidance",
    "_TODO_PATTERN",
    "todo_markers",
    "TODO|FIXME",
    "manual — review bootstrap_fill_plan",
    "placeholders =",
    "placeholders})",
    "__mocks__",
    "/mock-data/",
    ".mock.ts",
    ".mock.tsx",
    "declaration stub",
    "unittest.mock",
)

_PRODUCTION_SCAN_REL_PATHS: tuple[str, ...] = (
    "lib",
    "hooks.py",
    "health.py",
    "prompts.py",
    "contracts.py",
    "guard.py",
    "tools_loader.py",
    "slash_commands.py",
    "public.py",
    "install.py",
    "audit.py",
    "scripts",
)

_EXCLUDED_DIR_NAMES: frozenset[str] = frozenset({
    "__pycache__",
    "broccolidb",
    "optional-skills",
    "tests",
})


def _line_allowed(line: str) -> bool:
    lowered = line.lower()
    return any(token in line or token.lower() in lowered for token in _LINE_ALLOWLIST_SUBSTRINGS)


def _iter_production_python_files(root: Path) -> Iterable[Path]:
    for rel in _PRODUCTION_SCAN_REL_PATHS:
        target = root / rel
        if target.is_file() and target.suffix == ".py":
            yield target
            continue
        if not target.is_dir():
            continue
        for path in sorted(target.rglob("*.py")):
            if any(part in _EXCLUDED_DIR_NAMES for part in path.parts):
                continue
            yield path


def scan_production_antipatterns(*, root: Path | None = None) -> list[tuple[str, int, str]]:
    """Return (relative_path, line_no, line_text) for forbidden production language."""
    plugin_root = root or dietcode_plugin_root()
    hits: list[tuple[str, int, str]] = []
    for path in _iter_production_python_files(plugin_root):
        rel = path.relative_to(plugin_root).as_posix()
        if rel in _EXCLUDED_SCAN_FILES:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _line_allowed(stripped):
                continue
            if _FORBIDDEN_IN_PRODUCTION.search(stripped):
                hits.append((rel, i, stripped[:160]))
    return hits


def scan_angle_bracket_placeholders(*, root: Path | None = None) -> list[tuple[str, int, str]]:
    """Flag angle-bracket template placeholders in recovery command builders."""
    plugin_root = root or dietcode_plugin_root()
    hits: list[tuple[str, int, str]] = []
    for rel in sorted(_RECOVERY_COMMAND_FILES):
        path = plugin_root / rel
        if not path.is_file():
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _ANGLE_BRACKET_PLACEHOLDER.search(stripped):
                hits.append((rel, i, stripped[:160]))
    return hits


def scan_dead_code_flags(*, root: Path | None = None) -> list[tuple[str, int, str]]:
    """Return suspicious inactive-branch patterns in production sources."""
    plugin_root = root or dietcode_plugin_root()
    hits: list[tuple[str, int, str]] = []
    for path in _iter_production_python_files(plugin_root):
        rel = path.relative_to(plugin_root).as_posix()
        if rel in _EXCLUDED_SCAN_FILES:
            continue
        for i, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if _DEAD_CODE_PATTERN.search(stripped):
                hits.append((rel, i, stripped[:160]))
    return hits


def run_production_hardening_audit(*, root: Path | None = None) -> dict[str, object]:
    """Structured production audit payload for doctor/CI."""
    antipatterns = scan_production_antipatterns(root=root)
    dead_code = scan_dead_code_flags(root=root)
    placeholders = scan_angle_bracket_placeholders(root=root)
    failures: list[str] = []
    for rel, line_no, text in antipatterns:
        failures.append(f"production language: {rel}:{line_no}: {text}")
    for rel, line_no, text in dead_code:
        failures.append(f"dead code flag: {rel}:{line_no}: {text}")
    for rel, line_no, text in placeholders:
        failures.append(f"angle-bracket placeholder: {rel}:{line_no}: {text}")
    return {
        "ok": not failures,
        "failures": failures,
        "antipattern_count": len(antipatterns),
        "dead_code_count": len(dead_code),
        "placeholder_count": len(placeholders),
        "antipatterns": [
            {"path": rel, "line": line_no, "text": text}
            for rel, line_no, text in antipatterns
        ],
        "dead_code": [
            {"path": rel, "line": line_no, "text": text}
            for rel, line_no, text in dead_code
        ],
        "placeholders": [
            {"path": rel, "line": line_no, "text": text}
            for rel, line_no, text in placeholders
        ],
    }
