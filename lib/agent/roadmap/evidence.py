"""Gather project evidence for roadmap checkpoint passes."""
from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from plugins.dietcode.lib.agent.roadmap.code_soup_audit import assess_code_soup
from plugins.dietcode.lib.agent.roadmap.schema import HEALTH_STATUSES, REQUIRED_SECTIONS, SOUP_RISK_LEVELS

_README_CANDIDATES = ("README.md", "docs/README.md", "readme.md")
_ARCH_DOC_CANDIDATES = (
    "docs/architecture.md",
    "ARCHITECTURE.md",
    "docs/design.md",
    "docs/overview.md",
    "CONTRIBUTING.md",
)
_CONFIG_CANDIDATES = (
    "package.json",
    "plugin.yaml",
    "pyproject.toml",
    "Cargo.toml",
    "go.mod",
    "CHANGELOG.md",
)

_GIT_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def invalidate_git_cache(workspace: str | Path) -> None:
    prefix = str(Path(workspace).expanduser().resolve()) + ":"
    for key in list(_GIT_CACHE):
        if key.startswith(prefix):
            _GIT_CACHE.pop(key, None)

@dataclass
class RoadmapParse:
    exists: bool = False
    path: str = ""
    size_bytes: int = 0
    sections_present: list[str] = field(default_factory=list)
    sections_missing: list[str] = field(default_factory=list)
    health_status: Optional[str] = None
    code_soup_risk: Optional[str] = None
    recent_checkpoint_date: Optional[str] = None
    center_of_gravity_excerpt: str = ""
    now_item_count: int = 0
    next_item_count: int = 0
    discovery_item_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "exists": self.exists,
            "path": self.path or None,
            "size_bytes": self.size_bytes,
            "sections_present": self.sections_present,
            "sections_missing": self.sections_missing,
            "health_status": self.health_status,
            "code_soup_risk": self.code_soup_risk,
            "recent_checkpoint_date": self.recent_checkpoint_date,
            "center_of_gravity_excerpt": self.center_of_gravity_excerpt or None,
            "now_item_count": self.now_item_count,
            "next_item_count": self.next_item_count,
            "discovery_item_count": self.discovery_item_count,
        }


def _git_timeout() -> float:
    try:
        from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config
        return get_roadmap_config().git_timeout_seconds
    except Exception:
        return 5.0


def _run_git(workspace: Path, *args: str) -> Optional[str]:
    if not (workspace / ".git").exists():
        return None
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=workspace,
            capture_output=True,
            text=True,
            timeout=_git_timeout(),
        )
        if proc.returncode != 0:
            return None
        return (proc.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return None


def git_commits_since(workspace: str | Path, since_date: str) -> list[str]:
    """Return one-line commit subjects since an ISO date (YYYY-MM-DD)."""
    root = Path(workspace).expanduser().resolve()
    if not since_date or not (root / ".git").exists():
        return []
    raw = _run_git(root, "log", "--oneline", f"--since={since_date.strip()}")
    return raw.splitlines() if raw else []


def _git_recent_changes(workspace: Path, *, light: bool = False) -> dict[str, Any]:
    key = f"{workspace}:{'light' if light else 'full'}"
    now = time.monotonic()
    cached = _GIT_CACHE.get(key)
    if cached is not None and (now - cached[0]) <= _git_timeout():
        return cached[1]

    commits = _run_git(workspace, "log", "--oneline", "-12")
    if light:
        result = {
            "available": True,
            "recent_commits": commits.splitlines() if commits else [],
            "status_short": [],
            "diff_stat_recent": [],
            "changed_files_recent": [],
        }
        _GIT_CACHE[key] = (now, result)
        return result

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=3) as pool:
        status_f = pool.submit(_run_git, workspace, "status", "--short")
        diff_f = pool.submit(_run_git, workspace, "diff", "--stat", "HEAD~5..HEAD")
        changed_f = pool.submit(_run_git, workspace, "diff", "--name-only", "HEAD~3..HEAD")
        status = status_f.result()
        diff_stat = diff_f.result()
        changed_files = changed_f.result()

    if diff_stat is None:
        diff_stat = _run_git(workspace, "log", "--stat", "--oneline", "-5")
    if changed_files is None:
        changed_files = _run_git(workspace, "diff", "--name-only")
    result = {
        "available": True,
        "recent_commits": commits.splitlines() if commits else [],
        "status_short": status.splitlines() if status else [],
        "diff_stat_recent": diff_stat.splitlines() if diff_stat else [],
        "changed_files_recent": changed_files.splitlines() if changed_files else [],
    }
    _GIT_CACHE[key] = (now, result)
    return result


def _read_excerpt(path: Path, limit: int = 2500) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "\n…"


def _unique_existing_paths(root: Path, relatives: tuple[str, ...]) -> list[dict[str, str]]:
    seen: set[str] = set()
    results: list[dict[str, str]] = []
    for rel in relatives:
        path = (root / rel).resolve()
        key = str(path)
        if key in seen or not path.is_file():
            continue
        seen.add(key)
        results.append({"path": rel, "excerpt": _read_excerpt(path)})
    return results


def _count_section_items(content: str, section_title: str) -> int:
    match = re.search(
        rf"^##\s+{re.escape(section_title)}\s*$([\s\S]*?)(?=^##\s+|\Z)",
        content,
        re.MULTILINE,
    )
    if not match:
        return 0
    return len(re.findall(r"^###\s+\d+\.\s+", match.group(1), re.MULTILINE))


def parse_roadmap(content: str, *, path: str = "") -> RoadmapParse:
    """Extract roadmap structure signals from markdown content."""
    result = RoadmapParse(
        exists=bool(content.strip()),
        path=path,
        size_bytes=len(content.encode("utf-8")),
    )
    if not content.strip():
        result.sections_missing = list(REQUIRED_SECTIONS)
        return result

    for section in REQUIRED_SECTIONS:
        if re.search(rf"^##\s+{re.escape(section)}\s*$", content, re.MULTILINE):
            result.sections_present.append(section)
        else:
            result.sections_missing.append(section)

    health_match = re.search(
        r"##\s+2\.\s+Roadmap Health.*?\*\*Status:\*\*\s*([A-Za-z]+)",
        content,
        re.DOTALL,
    )
    if health_match:
        candidate = health_match.group(1).strip()
        for status in HEALTH_STATUSES:
            if status.lower() == candidate.lower():
                result.health_status = status
                break

    soup_match = re.search(
        r"\*\*Overall Code Soup Risk:\*\*\s*(Low|Medium|High)",
        content,
        re.IGNORECASE,
    )
    if soup_match:
        label = soup_match.group(1).strip().title()
        if label in SOUP_RISK_LEVELS:
            result.code_soup_risk = label

    checkpoint_match = re.search(
        r"##\s+11\.\s+Recent Checkpoint.*?\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})",
        content,
        re.DOTALL,
    )
    if checkpoint_match:
        result.recent_checkpoint_date = checkpoint_match.group(1)

    cog_match = re.search(
        r"##\s+1\.\s+Project Center of Gravity(.*?)(?=\n##\s+|\Z)",
        content,
        re.DOTALL,
    )
    if cog_match:
        excerpt = cog_match.group(1).strip()
        if len(excerpt) > 800:
            excerpt = excerpt[:800] + "…"
        result.center_of_gravity_excerpt = excerpt

    result.now_item_count = _count_section_items(content, "4. Now")
    result.next_item_count = _count_section_items(content, "5. Next")
    result.discovery_item_count = _count_section_items(content, "7. Discovery")
    return result


_DOC_CACHE: dict[str, tuple[float, tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]]] = {}


def _doc_cache_token(root: Path) -> float:
    token = 0.0
    for rel in (*_README_CANDIDATES, *_ARCH_DOC_CANDIDATES, *_CONFIG_CANDIDATES):
        path = root / rel
        if path.is_file():
            try:
                token = max(token, path.stat().st_mtime)
            except OSError:
                continue
    return token


def invalidate_doc_cache(workspace: str | Path) -> None:
    _DOC_CACHE.pop(str(Path(workspace).expanduser().resolve()), None)


def _load_doc_excerpts(root: Path) -> tuple[list[dict[str, str]], list[dict[str, str]], list[dict[str, str]]]:
    key = str(root)
    token = _doc_cache_token(root)
    cached = _DOC_CACHE.get(key)
    if cached is not None and cached[0] == token:
        return cached[1]

    readmes = _unique_existing_paths(root, _README_CANDIDATES)
    arch = _unique_existing_paths(root, _ARCH_DOC_CANDIDATES)
    configs = _unique_existing_paths(root, _CONFIG_CANDIDATES)
    result = (readmes, arch, configs)
    _DOC_CACHE[key] = (token, result)
    return result


def extend_evidence(
    base: dict[str, Any],
    *,
    tier: str,
    context_hint: str = "",
    user_request: str = "",
) -> dict[str, Any]:
    """Extend cached lighter-tier evidence without re-parsing ROADMAP or re-running git."""
    current = (base.get("evidence_tier") or "light").strip().lower()
    target = (tier or "full").strip().lower()
    rank = {"light": 0, "standard": 1, "full": 2}
    if rank.get(target, 2) <= rank.get(current, 0):
        updated = dict(base)
        if context_hint.strip():
            updated["context_hint"] = context_hint.strip()
        if user_request.strip():
            updated["user_request"] = user_request.strip()
        return updated

    root = Path(base.get("workspace") or ".").expanduser().resolve()
    evidence = dict(base)
    evidence["evidence_tier"] = target
    evidence["gathered_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if context_hint.strip():
        evidence["context_hint"] = context_hint.strip()
    if user_request.strip():
        evidence["user_request"] = user_request.strip()

    if target in {"standard", "full"} and not evidence.get("readmes"):
        readmes, arch, configs = _load_doc_excerpts(root)
        evidence["readmes"] = readmes
        evidence["architecture_docs"] = arch
        evidence["configs"] = configs
        parsed = evidence.get("roadmap") or {}
        evidence["uncertainty"] = _uncertainty_notes(
            RoadmapParse(
                exists=bool(parsed.get("exists")),
                sections_missing=parsed.get("sections_missing") or [],
                health_status=parsed.get("health_status"),
                now_item_count=int(parsed.get("now_item_count") or 0),
            ),
            readmes,
            evidence.get("git") or {},
        )

    if target == "full":
        from plugins.dietcode.lib.agent.roadmap.workspace_scan import get_heavy_scan

        heavy = get_heavy_scan(root)
        evidence["todo_markers"] = heavy.todo_markers
        evidence["test_file_count"] = heavy.test_file_count
        if not evidence.get("code_soup_audit"):
            evidence["code_soup_audit"] = assess_code_soup(root, heavy_scan=heavy)

    return evidence


def gather_evidence(
    workspace: str | Path,
    *,
    context_hint: str = "",
    user_request: str = "",
    include_code_soup: bool = True,
    tier: str = "full",
    roadmap_text: Optional[str] = None,
) -> dict[str, Any]:
    """Collect inspectable project signals before a roadmap pass.

    Tiers (fast → thorough):
    - light: ROADMAP parse + git log only (gate/guide/session)
    - standard: + README/arch/config excerpts, no TODO scan or code soup
    - full: + TODO scan + code soup audit (checkpoint passes)
    """
    root = Path(workspace).expanduser().resolve()
    roadmap_path = root / "ROADMAP.md"
    core = None
    if roadmap_text is None:
        from plugins.dietcode.lib.agent.roadmap.roadmap_core import read_roadmap_core

        core = read_roadmap_core(root)
        roadmap_text = core.text
    elif not roadmap_text and roadmap_path.is_file():
        try:
            roadmap_text = roadmap_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            roadmap_text = ""

    t = (tier or "full").strip().lower()
    if t not in {"light", "standard", "full"}:
        t = "full" if include_code_soup else "standard"
    light = t == "light"
    do_soup = t == "full" and include_code_soup
    do_todos = t == "full"

    if core is not None:
        parsed_dict = core.parsed
    else:
        parsed_dict = parse_roadmap(roadmap_text, path=str(roadmap_path)).to_dict()

    git_info = (
        _git_recent_changes(root, light=light)
        if (root / ".git").exists()
        else {"available": False, "recent_commits": [], "status_short": [], "diff_stat_recent": [], "changed_files_recent": []}
    )

    readmes: list[dict[str, str]] = []
    arch_docs: list[dict[str, str]] = []
    configs: list[dict[str, str]] = []
    if not light:
        readmes, arch_docs, configs = _load_doc_excerpts(root)
    parsed = RoadmapParse(
        exists=bool(parsed_dict.get("exists")),
        sections_missing=parsed_dict.get("sections_missing") or [],
        health_status=parsed_dict.get("health_status"),
        now_item_count=int(parsed_dict.get("now_item_count") or 0),
    )
    evidence: dict[str, Any] = {
        "workspace": str(root),
        "gathered_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "evidence_tier": t,
        "context_hint": context_hint.strip() or None,
        "user_request": user_request.strip() or None,
        "roadmap": parsed_dict,
        "readmes": readmes,
        "architecture_docs": arch_docs,
        "configs": configs,
        "git": git_info,
        "todo_markers": [],
        "test_file_count": 0,
        "uncertainty": _uncertainty_notes(parsed, readmes, git_info),
        "_roadmap_text": roadmap_text or None,
    }

    try:
        from plugins.dietcode.lib.agent.roadmap.project_fingerprint import build_project_fingerprint

        evidence["project_fingerprint"] = build_project_fingerprint(root)
    except Exception:
        evidence["project_fingerprint"] = {"steering_identity": root.name}

    if do_todos or do_soup:
        from plugins.dietcode.lib.agent.roadmap.workspace_scan import get_heavy_scan

        heavy = get_heavy_scan(root)
        if do_todos:
            evidence["todo_markers"] = heavy.todo_markers
            evidence["test_file_count"] = heavy.test_file_count
        if do_soup:
            evidence["code_soup_audit"] = assess_code_soup(root, heavy_scan=heavy)

    return evidence


def _uncertainty_notes(
    parsed: RoadmapParse,
    readmes: list[dict[str, str]],
    git_info: dict[str, Any],
) -> list[str]:
    notes: list[str] = []
    if not parsed.exists:
        notes.append("ROADMAP.md not found — first pass will create it from evidence.")
    elif parsed.sections_missing:
        notes.append(f"ROADMAP.md missing sections: {', '.join(parsed.sections_missing[:4])}")
    if not readmes:
        notes.append("No README found — center of gravity may need explicit user input.")
    if not git_info.get("available"):
        notes.append("Git history unavailable — recent change signals limited.")
    if parsed.exists and not parsed.health_status:
        notes.append("Roadmap health status not parsed — verify section 2 format.")
    if parsed.now_item_count > 5:
        notes.append(f"Now section overloaded ({parsed.now_item_count} items) — demote to Next or Archive.")
    return notes
