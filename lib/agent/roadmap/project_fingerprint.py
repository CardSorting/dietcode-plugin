"""Project fingerprint — compact per-repo identity for agent steering."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Optional

_FRAMEWORK_MARKERS: tuple[tuple[str, str], ...] = (
    ("next.config.js", "Next.js"),
    ("next.config.ts", "Next.js"),
    ("nuxt.config.ts", "Nuxt"),
    ("vite.config.ts", "Vite"),
    ("manage.py", "Django"),
    ("pyproject.toml", "Python"),
    ("Cargo.toml", "Rust"),
    ("go.mod", "Go"),
    ("plugin.yaml", "Hermes plugin"),
    ("docker-compose.yml", "Docker"),
    ("Dockerfile", "Docker"),
)

_LANG_EXTENSIONS: tuple[tuple[str, str], ...] = (
    (".py", "Python"),
    (".ts", "TypeScript"),
    (".tsx", "TypeScript"),
    (".js", "JavaScript"),
    (".jsx", "JavaScript"),
    (".rs", "Rust"),
    (".go", "Go"),
    (".java", "Java"),
    (".rb", "Ruby"),
)

_CI_MARKERS: tuple[tuple[str, str], ...] = (
    (".github/workflows", "GitHub Actions"),
    (".gitlab-ci.yml", "GitLab CI"),
    (".circleci/config.yml", "CircleCI"),
    ("Jenkinsfile", "Jenkins"),
    (".travis.yml", "Travis CI"),
    ("azure-pipelines.yml", "Azure Pipelines"),
    (".buildkite/pipeline.yml", "Buildkite"),
)

_TEST_MARKERS: tuple[tuple[str, str], ...] = (
    ("pytest.ini", "pytest"),
    ("conftest.py", "pytest"),
    ("jest.config.js", "Jest"),
    ("jest.config.ts", "Jest"),
    ("vitest.config.ts", "Vitest"),
    ("playwright.config.ts", "Playwright"),
    ("cypress.config.ts", "Cypress"),
    ("Cargo.toml", "cargo test"),
)

_MONOREPO_MARKERS: tuple[tuple[str, str], ...] = (
    ("turbo.json", "Turborepo"),
    ("nx.json", "Nx"),
    ("lerna.json", "Lerna"),
    ("pnpm-workspace.yaml", "pnpm workspace"),
)

_PACKAGE_MANAGER_MARKERS: tuple[tuple[str, str], ...] = (
    ("pnpm-lock.yaml", "pnpm"),
    ("yarn.lock", "Yarn"),
    ("bun.lockb", "Bun"),
    ("package-lock.json", "npm"),
    ("poetry.lock", "Poetry"),
    ("uv.lock", "uv"),
    ("Pipfile", "Pipenv"),
    ("requirements.txt", "pip"),
)


def _read_text(path: Path, *, limit: int = 8000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")[:limit]
    except OSError:
        return ""


def _package_json(root: Path) -> dict[str, Any]:
    pkg = root / "package.json"
    if not pkg.is_file():
        return {}
    try:
        data = json.loads(_read_text(pkg))
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _package_name(root: Path) -> Optional[str]:
    data = _package_json(root)
    name = str(data.get("name") or "").strip()
    if name:
        return name

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = _read_text(pyproject)
        match = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if match:
            return match.group(1).strip()

    cargo = root / "Cargo.toml"
    if cargo.is_file():
        text = _read_text(cargo)
        match = re.search(r'^\s*name\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if match:
            return match.group(1).strip()

    go_mod = root / "go.mod"
    if go_mod.is_file():
        text = _read_text(go_mod)
        match = re.search(r"^module\s+(\S+)", text, re.MULTILINE)
        if match:
            return Path(match.group(1)).name or match.group(1)

    return root.name or None


def _package_description(root: Path) -> Optional[str]:
    data = _package_json(root)
    desc = str(data.get("description") or "").strip()
    if desc:
        return desc[:400]

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = _read_text(pyproject)
        match = re.search(r'^\s*description\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if match:
            return match.group(1).strip()[:400]

    cargo = root / "Cargo.toml"
    if cargo.is_file():
        text = _read_text(cargo)
        match = re.search(r'^\s*description\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
        if match:
            return match.group(1).strip()[:400]

    return None


def _readme_title(root: Path) -> Optional[str]:
    for name in ("README.md", "readme.md", "docs/README.md"):
        path = root / name
        if not path.is_file():
            continue
        for line in _read_text(path, limit=4000).splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                title = stripped.lstrip("#").strip()
                if title:
                    return title[:200]
    return None


def _readme_tagline(root: Path) -> Optional[str]:
    """First substantive paragraph after the README title."""
    for name in ("README.md", "readme.md", "docs/README.md"):
        path = root / name
        if not path.is_file():
            continue
        past_title = False
        for line in _read_text(path, limit=6000).splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#"):
                past_title = True
                continue
            if stripped.startswith(("![", "[!", "<", "---", "```", "|", "- ", "* ", ">")):
                continue
            if past_title or not stripped.startswith("#"):
                return stripped[:400]
    return None


def _detect_markers(root: Path, markers: tuple[tuple[str, str], ...], *, dir_ok: bool = False) -> list[str]:
    found: list[str] = []
    for rel, label in markers:
        path = root / rel
        if dir_ok and path.is_dir() and label not in found:
            found.append(label)
        elif path.is_file() and label not in found:
            found.append(label)
    return found[:6]


def _detect_frameworks(root: Path) -> list[str]:
    found = _detect_markers(root, _FRAMEWORK_MARKERS)
    if (root / "app" / "layout.tsx").is_file() and "Next.js" not in found:
        found.append("Next.js App Router")
    return found[:5]


def _primary_language(root: Path) -> Optional[str]:
    counts: dict[str, int] = {}
    scanned = 0
    skip_dirs = frozenset({".git", "node_modules", ".venv", "venv", "dist", "build", "__pycache__"})
    for path in root.rglob("*"):
        if scanned >= 400:
            break
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        suffix = path.suffix.lower()
        for ext, lang in _LANG_EXTENSIONS:
            if suffix == ext:
                counts[lang] = counts.get(lang, 0) + 1
                scanned += 1
                break
    if not counts:
        return None
    return max(counts, key=counts.get)


def _detect_archetype(
    root: Path,
    *,
    frameworks: list[str],
    monorepo_tools: list[str],
) -> str:
    if (root / "plugin.yaml").is_file():
        return "hermes-plugin"
    if monorepo_tools:
        return "monorepo"
    if any(f in frameworks for f in ("Next.js", "Next.js App Router", "Nuxt", "Vite")):
        if (root / "app").is_dir() or (root / "pages").is_dir() or (root / "src" / "routes").is_dir():
            return "web-app"
    data = _package_json(root)
    if data.get("bin") or (root / "cmd").is_dir():
        return "cli-tool"
    if data.get("private") is True and (root / "src").is_dir():
        return "application"
    if (root / "lib").is_dir() or (root / "src").is_dir():
        pyproject = root / "pyproject.toml"
        if pyproject.is_file() and re.search(r"\[project\.scripts\]", _read_text(pyproject)):
            return "cli-tool"
    if data.get("main") or (root / "src" / "index.ts").is_file():
        return "library"
    return "project"


def _steering_brief(
    *,
    display_name: str,
    tagline: Optional[str],
    stack_parts: list[str],
    archetype: str,
    ci_systems: list[str],
    test_frameworks: list[str],
) -> str:
    bits: list[str] = [display_name]
    if tagline and tagline.lower() not in display_name.lower():
        bits.append(tagline[:120])
    elif stack_parts:
        bits.append(", ".join(stack_parts[:3]))
    meta: list[str] = []
    if archetype and archetype != "project":
        meta.append(archetype.replace("-", " "))
    if test_frameworks:
        meta.append(test_frameworks[0])
    if ci_systems:
        meta.append(ci_systems[0])
    if meta:
        bits.append(" · ".join(meta))
    return " — ".join(bits) if len(bits) > 1 else bits[0]


def build_project_fingerprint(workspace: str | Path) -> dict[str, Any]:
    """Return compact project identity signals for steering surfaces."""
    root = Path(workspace).expanduser().resolve()
    package = _package_name(root)
    readme_title = _readme_title(root)
    tagline = _readme_tagline(root)
    description = _package_description(root)
    frameworks = _detect_frameworks(root)
    primary_lang = _primary_language(root)
    ci_systems = _detect_markers(root, _CI_MARKERS, dir_ok=True)
    test_frameworks = _detect_markers(root, _TEST_MARKERS)
    monorepo_tools = _detect_markers(root, _MONOREPO_MARKERS)
    package_managers = _detect_markers(root, _PACKAGE_MANAGER_MARKERS)
    has_docker = (root / "Dockerfile").is_file() or (root / "docker-compose.yml").is_file()
    has_tests = bool(test_frameworks) or (root / "tests").is_dir() or (root / "test").is_dir()
    archetype = _detect_archetype(root, frameworks=frameworks, monorepo_tools=monorepo_tools)

    display_name = readme_title or package or root.name
    stack_parts: list[str] = []
    if primary_lang:
        stack_parts.append(primary_lang)
    stack_parts.extend(f for f in frameworks if f not in stack_parts)
    if package_managers and package_managers[0] not in stack_parts:
        stack_parts.append(package_managers[0])

    summary = display_name
    if stack_parts:
        summary = f"{display_name} ({', '.join(stack_parts[:4])})"

    purpose_hint = tagline or description or ""
    runtime_hint = ""
    if archetype == "hermes-plugin":
        runtime_hint = f"Hermes plugin workspace — ROADMAP.md at {root.name} root beside plugin.yaml"
    elif archetype == "web-app":
        runtime_hint = f"Web application root at {root.name} — deploy/runtime config in repo manifests"
    elif has_docker:
        runtime_hint = "Containerized runtime — Docker/Docker Compose manifests define operational center"
    elif frameworks:
        runtime_hint = f"Primary stack: {', '.join(frameworks[:3])} — operational truth in repo config and entrypoints"

    operators_hint = description or ""
    if not operators_hint and archetype == "hermes-plugin":
        operators_hint = "Hermes operators and agent-assisted developers extending the plugin surface"

    return {
        "project_name": display_name,
        "package_name": package,
        "readme_title": readme_title,
        "readme_tagline": tagline,
        "package_description": description,
        "primary_language": primary_lang,
        "frameworks": frameworks,
        "stack_summary": ", ".join(stack_parts) if stack_parts else None,
        "steering_identity": summary,
        "steering_brief": _steering_brief(
            display_name=display_name,
            tagline=tagline or description,
            stack_parts=stack_parts,
            archetype=archetype,
            ci_systems=ci_systems,
            test_frameworks=test_frameworks,
        ),
        "project_archetype": archetype,
        "ci_systems": ci_systems,
        "test_frameworks": test_frameworks,
        "monorepo_tools": monorepo_tools,
        "package_managers": package_managers,
        "has_ci": bool(ci_systems),
        "has_tests": has_tests,
        "has_docker": has_docker,
        "purpose_hint": purpose_hint or None,
        "runtime_center_hint": runtime_hint or None,
        "operators_hint": operators_hint or None,
    }
