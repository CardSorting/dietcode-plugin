"""Single-pass workspace filesystem scan — shared by evidence and code soup."""
from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

_SKIP_DIRS = frozenset({
    ".git", "node_modules", "dist", "build", ".venv", "venv", "__pycache__",
    "broccolidb/node_modules", ".cursor", ".hermes",
})

_SOURCE_SUFFIXES = frozenset({".py", ".ts", ".js", ".mm", ".cpp", ".go", ".rs"})
_TODO_SUFFIXES = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".md", ".yaml", ".yml",
})
_TODO_PATTERN = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b[:\s]*(.*)", re.IGNORECASE)

_SOURCE_LIMIT = 400
_SOURCE_MAX_BYTES = 300_000
_TODO_LIMIT = 40
_TODO_MAX_BYTES = 200_000
_TEST_LIMIT = 200

_HEAVY_CACHE: dict[str, tuple[float, "HeavyScanResult"]] = {}


@dataclass
class HeavyScanResult:
    """One workspace walk — source texts, TODO markers, test count."""

    workspace: str
    source_files: list[tuple[str, str]] = field(default_factory=list)
    todo_markers: list[dict[str, str]] = field(default_factory=list)
    test_file_count: int = 0


def _heavy_scan_ttl() -> float:
    try:
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config

        return float(get_roadmap_config().heavy_scan_cache_ttl_seconds)
    except Exception:
        return 60.0


def invalidate_heavy_scan(workspace: str | Path) -> None:
    key = str(Path(workspace).expanduser().resolve())
    _HEAVY_CACHE.pop(key, None)


def get_heavy_scan(workspace: str | Path) -> HeavyScanResult:
    """Return cached or freshly scanned heavy workspace signals."""
    root = Path(workspace).expanduser().resolve()
    key = str(root)
    now = time.monotonic()
    cached = _HEAVY_CACHE.get(key)
    if cached is not None and (now - cached[0]) <= _heavy_scan_ttl():
        return cached[1]

    result = _scan_workspace(root)
    _HEAVY_CACHE[key] = (now, result)
    return result


def _scan_file(
    root: Path,
    path: Path,
    *,
    source_files: list[tuple[str, str]],
    todo_markers: list[dict[str, str]],
    test_file_count: int,
) -> int:
    suffix = path.suffix.lower()
    name_lower = path.name.lower()
    rel = str(path.relative_to(root))

    if test_file_count < _TEST_LIMIT:
        if (name_lower.startswith("test_") and suffix == ".py") or name_lower.endswith(
            (".test.ts", ".test.js")
        ):
            test_file_count += 1

    need_todo = len(todo_markers) < _TODO_LIMIT and suffix in _TODO_SUFFIXES
    need_source = len(source_files) < _SOURCE_LIMIT and suffix in _SOURCE_SUFFIXES
    if not need_todo and not need_source:
        return test_file_count

    try:
        size = path.stat().st_size
    except OSError:
        return test_file_count

    if need_todo and size > _TODO_MAX_BYTES:
        need_todo = False
    if need_source and size > _SOURCE_MAX_BYTES:
        need_source = False
    if not need_todo and not need_source:
        return test_file_count

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return test_file_count

    if need_todo:
        for lineno, line in enumerate(text.splitlines(), 1):
            match = _TODO_PATTERN.search(line)
            if match:
                todo_markers.append({
                    "file": rel,
                    "line": str(lineno),
                    "marker": match.group(1).upper(),
                    "text": match.group(2).strip()[:120],
                })
                if len(todo_markers) >= _TODO_LIMIT:
                    break

    if need_source:
        source_files.append((rel, text))

    return test_file_count


def _scan_workspace(root: Path) -> HeavyScanResult:
    source_files: list[tuple[str, str]] = []
    todo_markers: list[dict[str, str]] = []
    test_file_count = 0

    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        dirnames[:] = [name for name in dirnames if name not in _SKIP_DIRS]
        base = Path(dirpath)
        for name in filenames:
            if len(source_files) >= _SOURCE_LIMIT and len(todo_markers) >= _TODO_LIMIT:
                if test_file_count >= _TEST_LIMIT:
                    return HeavyScanResult(
                        workspace=str(root),
                        source_files=source_files,
                        todo_markers=todo_markers,
                        test_file_count=test_file_count,
                    )
            test_file_count = _scan_file(
                root,
                base / name,
                source_files=source_files,
                todo_markers=todo_markers,
                test_file_count=test_file_count,
            )

    return HeavyScanResult(
        workspace=str(root),
        source_files=source_files,
        todo_markers=todo_markers,
        test_file_count=test_file_count,
    )
