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

_LINT_MARKERS: tuple[tuple[str, str], ...] = (
    ("biome.json", "Biome"),
    ("eslint.config.js", "ESLint"),
    ("eslint.config.mjs", "ESLint"),
    ("eslint.config.ts", "ESLint"),
    (".eslintrc.json", "ESLint"),
    (".eslintrc.cjs", "ESLint"),
    ("ruff.toml", "Ruff"),
    (".prettierrc", "Prettier"),
    (".prettierrc.json", "Prettier"),
    ("mise.toml", "mise"),
    (".editorconfig", "EditorConfig"),
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

_FP_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}


def invalidate_fingerprint_cache(workspace: str | Path) -> None:
    _FP_CACHE.pop(str(Path(workspace).expanduser().resolve()), None)


def _fingerprint_cache_token(root: Path) -> float:
    token = 0.0
    for rel in (
        "README.md",
        "package.json",
        "pyproject.toml",
        "plugin.yaml",
        "Cargo.toml",
        "go.mod",
        "Makefile",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "catalog-info.yaml",
        ".cursorrules",
        "DIRECTIONS.md",
        ".nvmrc",
        ".node-version",
        ".python-version",
        ".tool-versions",
        ".github/CODEOWNERS",
        "CODEOWNERS",
        "renovate.json",
        ".github/dependabot.yml",
        "docker-compose.yml",
        "pnpm-workspace.yaml",
        "turbo.json",
        "SECURITY.md",
        "compose.yml",
        ".pre-commit-config.yaml",
        "biome.json",
        "eslint.config.js",
        "ruff.toml",
        "mise.toml",
    ):
        path = root / rel
        if path.is_file():
            try:
                token = max(token, path.stat().st_mtime)
            except OSError:
                continue
    wf_dir = root / ".github" / "workflows"
    if wf_dir.is_dir():
        for path in wf_dir.glob("*.yml"):
            try:
                token = max(token, path.stat().st_mtime)
            except OSError:
                continue
        for path in wf_dir.glob("*.yaml"):
            try:
                token = max(token, path.stat().st_mtime)
            except OSError:
                continue
    return token


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


def _package_scripts(root: Path) -> list[str]:
    scripts: list[str] = []
    data = _package_json(root)
    pkg_scripts = data.get("scripts")
    if isinstance(pkg_scripts, dict):
        for name in ("dev", "start", "build", "test", "lint"):
            if name in pkg_scripts and name not in scripts:
                scripts.append(name)
        for name in sorted(pkg_scripts):
            if name not in scripts and len(scripts) < 6:
                scripts.append(name)

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = _read_text(pyproject)
        for match in re.finditer(r'^\s*["\']([^"\']+)["\']\s*=', text, re.MULTILINE):
            name = match.group(1)
            if name not in scripts and len(scripts) < 8:
                scripts.append(name)
    return scripts[:8]


def _license_label(root: Path) -> Optional[str]:
    data = _package_json(root)
    lic = str(data.get("license") or "").strip()
    if lic:
        return lic[:80]
    for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"):
        if (root / name).is_file():
            return name
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        match = re.search(r'^\s*license\s*=\s*["\'{]([^"\'}]+)', _read_text(pyproject), re.MULTILINE)
        if match:
            return match.group(1).strip()[:80]
    return None


def _git_remote_summary(root: Path) -> Optional[str]:
    if not (root / ".git").is_dir():
        return None
    try:
        import subprocess

        proc = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=3.0,
        )
        if proc.returncode == 0 and (proc.stdout or "").strip():
            url = proc.stdout.strip()
            if url.startswith("git@"):
                host = url.split("@", 1)[-1].split(":", 1)[0]
                repo = url.split(":")[-1].replace(".git", "")
                return f"{host}/{repo}"[:120]
            return url.replace("https://", "").replace("http://", "").rstrip(".git")[:120]
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


def _docs_roots(root: Path) -> list[str]:
    found: list[str] = []
    for rel in ("docs", "doc", "documentation", "wiki"):
        if (root / rel).is_dir() and rel not in found:
            found.append(rel)
    for name in ("CONTRIBUTING.md", "docs/architecture.md", "ARCHITECTURE.md"):
        if (root / name).is_file() and name not in found:
            found.append(name)
    return found[:6]


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


def _agent_rules_excerpt(root: Path) -> Optional[str]:
    for rel in ("AGENTS.md", "CLAUDE.md", "docs/AGENTS.md"):
        path = root / rel
        if not path.is_file():
            continue
        lines = [
            ln.strip()
            for ln in _read_text(path, limit=2500).splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        for line in lines:
            if len(line) >= 20:
                return line[:200]
        if lines:
            return lines[0][:200]
    return None


def _contributing_excerpt(root: Path) -> Optional[str]:
    path = root / "CONTRIBUTING.md"
    if not path.is_file():
        return None
    for line in _read_text(path, limit=2000).splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and len(stripped) >= 20:
            return stripped[:200]
    return None


def _agent_rules_files(root: Path) -> list[str]:
    found: list[str] = []
    for rel in (
        "AGENTS.md",
        "CLAUDE.md",
        "DIRECTIONS.md",
        ".cursorrules",
        "docs/AGENTS.md",
        "catalog-info.yaml",
    ):
        path = root / rel
        if path.is_file() and rel not in found:
            found.append(rel)
    rules_dir = root / ".cursor" / "rules"
    if rules_dir.is_dir():
        for path in sorted(list(rules_dir.glob("*.md")) + list(rules_dir.glob("*.mdc")))[:5]:
            rel = f".cursor/rules/{path.name}"
            if rel not in found:
                found.append(rel)
        if not any(p.suffix in {".md", ".mdc"} for p in rules_dir.iterdir() if p.is_file()):
            if ".cursor/rules" not in found:
                found.append(".cursor/rules")
    return found[:8]


def _compose_services(root: Path) -> list[str]:
    for name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        path = root / name
        if not path.is_file():
            continue
        services: list[str] = []
        in_services = False
        for line in _read_text(path, limit=4000).splitlines():
            if re.match(r"^\s*services:\s*$", line):
                in_services = True
                continue
            if not in_services:
                continue
            match = re.match(r"^\s{2}([\w-]+):\s*$", line)
            if match:
                services.append(match.group(1))
            elif line.strip() and not line.startswith(" "):
                break
        return services[:6]
    return []


def _ci_workflow_names(root: Path) -> list[str]:
    wf_dir = root / ".github" / "workflows"
    if not wf_dir.is_dir():
        return []
    names: list[str] = []
    for path in sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml"))):
        if path.stem not in names:
            names.append(path.stem)
        if len(names) >= 6:
            break
    return names


def _governance_files(root: Path) -> list[str]:
    found: list[str] = []
    for rel in ("SECURITY.md", "CODE_OF_CONDUCT.md", ".editorconfig", "CHANGELOG.md"):
        if (root / rel).is_file() and rel not in found:
            found.append(rel)
    if (root / "docs" / "adr").is_dir():
        found.append("docs/adr")
    return found[:6]


def _workspace_packages(root: Path) -> list[str]:
    packages: list[str] = []
    pnpm_ws = root / "pnpm-workspace.yaml"
    if pnpm_ws.is_file():
        for line in _read_text(pnpm_ws, limit=2000).splitlines():
            match = re.match(r'^\s*-\s*["\']?([^"\']+)["\']?', line)
            if match:
                name = match.group(1).strip()
                if name and name not in packages:
                    packages.append(name[:60])
    data = _package_json(root)
    workspaces = data.get("workspaces")
    if isinstance(workspaces, list):
        for item in workspaces:
            if len(packages) >= 8:
                break
            name = str(item).strip()
            if name and name not in packages:
                packages.append(name[:60])
    elif isinstance(workspaces, dict):
        for item in workspaces.get("packages") or []:
            if len(packages) >= 8:
                break
            name = str(item).strip()
            if name and name not in packages:
                packages.append(name[:60])
    return packages[:8]


def _catalog_metadata(root: Path) -> dict[str, Optional[str]]:
    catalog = root / "catalog-info.yaml"
    if not catalog.is_file():
        return {}
    text = _read_text(catalog, limit=4000)
    meta: dict[str, Optional[str]] = {}
    name = re.search(r"^\s*name:\s*(.+)$", text, re.MULTILINE)
    if name:
        meta["catalog_name"] = name.group(1).strip().strip("'\"")[:120]
    desc = re.search(r"^\s*description:\s*(.+)$", text, re.MULTILINE)
    if desc:
        meta["catalog_description"] = desc.group(1).strip().strip("'\"")[:200]
    return meta


def _runtime_versions(root: Path) -> dict[str, str]:
    versions: dict[str, str] = {}
    for rel, label in (
        (".nvmrc", "node"),
        (".node-version", "node"),
        (".python-version", "python"),
        (".tool-versions", "asdf"),
    ):
        path = root / rel
        if not path.is_file():
            continue
        line = _read_text(path, limit=64).strip().splitlines()
        if line:
            versions[label] = line[0][:32]
    return versions


def _issue_templates(root: Path) -> list[str]:
    found: list[str] = []
    tpl_dir = root / ".github" / "ISSUE_TEMPLATE"
    if tpl_dir.is_dir():
        for path in sorted(tpl_dir.glob("*.md"))[:4]:
            rel = f".github/ISSUE_TEMPLATE/{path.name}"
            if rel not in found:
                found.append(rel)
        for path in sorted(tpl_dir.glob("*.yaml"))[:2]:
            rel = f".github/ISSUE_TEMPLATE/{path.name}"
            if rel not in found:
                found.append(rel)
    for rel in (
        ".github/pull_request_template.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "pull_request_template.md",
    ):
        if (root / rel).is_file() and rel not in found:
            found.append(rel)
    return found[:6]


def _dependency_automation(root: Path) -> list[str]:
    found: list[str] = []
    if (root / "renovate.json").is_file() or (root / ".github" / "renovate.json").is_file():
        found.append("Renovate")
    if (root / ".github" / "dependabot.yml").is_file() or (root / ".github" / "dependabot.yaml").is_file():
        found.append("Dependabot")
    return found


def _verification_commands(
    root: Path,
    *,
    entry_points: list[str],
    makefile_targets: list[str],
    test_frameworks: list[str],
) -> list[str]:
    """Industry-standard verify commands inferred from Makefile, package scripts, and test markers."""
    cmds: list[str] = []
    for target in ("verify", "test", "lint", "check", "ci"):
        if target in makefile_targets:
            cmds.append(f"make {target}")
            break

    scripts = _package_json(root).get("scripts")
    if isinstance(scripts, dict):
        for name in ("verify", "test", "lint", "ci", "check"):
            if name in scripts:
                cmd = f"npm run {name}" if (root / "package.json").is_file() else name
                if cmd not in cmds:
                    cmds.append(cmd)
                break

    if not cmds:
        if "pytest" in test_frameworks:
            cmds.append("pytest")
        elif any(t in test_frameworks for t in ("Jest", "Vitest")):
            cmds.append("npm test")
        elif (root / "go.mod").is_file():
            cmds.append("go test ./...")
        elif (root / "Cargo.toml").is_file():
            cmds.append("cargo test")
        elif entry_points:
            first = entry_points[0]
            if first in ("test", "verify", "lint", "check"):
                cmds.append(f"npm run {first}" if (root / "package.json").is_file() else first)

    return cmds[:4]


def _makefile_targets(root: Path) -> list[str]:
    makefile = root / "Makefile"
    if not makefile.is_file():
        return []
    targets: list[str] = []
    for line in _read_text(makefile, limit=4000).splitlines():
        stripped = line.strip()
        if stripped.startswith(".PHONY:"):
            for token in stripped.split(":", 1)[-1].split():
                name = token.strip()
                if name and name not in targets:
                    targets.append(name)
    for name in ("help", "test", "lint", "build", "deploy", "verify"):
        if name not in targets and re.search(rf"^{re.escape(name)}\s*:", _read_text(makefile, limit=4000), re.MULTILINE):
            targets.append(name)
    return targets[:8]


def build_project_fingerprint(workspace: str | Path) -> dict[str, Any]:
    """Return compact project identity signals for steering surfaces."""
    root = Path(workspace).expanduser().resolve()
    key = str(root)
    token = _fingerprint_cache_token(root)
    cached = _FP_CACHE.get(key)
    if cached is not None and cached[0] == token:
        return dict(cached[1])

    result = _build_project_fingerprint(root)
    _FP_CACHE[key] = (token, result)
    return dict(result)


def _build_project_fingerprint(root: Path) -> dict[str, Any]:
    package = _package_name(root)
    readme_title = _readme_title(root)
    tagline = _readme_tagline(root)
    description = _package_description(root)
    frameworks = _detect_frameworks(root)
    primary_lang = _primary_language(root)
    ci_systems = _detect_markers(root, _CI_MARKERS, dir_ok=True)
    test_frameworks = _detect_markers(root, _TEST_MARKERS)
    quality_tools = _detect_markers(root, _LINT_MARKERS)
    monorepo_tools = _detect_markers(root, _MONOREPO_MARKERS)
    package_managers = _detect_markers(root, _PACKAGE_MANAGER_MARKERS)
    has_docker = (root / "Dockerfile").is_file() or (root / "docker-compose.yml").is_file()
    has_tests = bool(test_frameworks) or (root / "tests").is_dir() or (root / "test").is_dir()
    archetype = _detect_archetype(root, frameworks=frameworks, monorepo_tools=monorepo_tools)
    entry_points = _package_scripts(root)
    license_label = _license_label(root)
    git_remote = _git_remote_summary(root)
    docs_roots = _docs_roots(root)
    agent_rules = _agent_rules_files(root)
    makefile_targets = _makefile_targets(root)
    runtime_versions = _runtime_versions(root)
    dependency_automation = _dependency_automation(root)
    compose_services = _compose_services(root)
    governance_files = _governance_files(root)
    workspace_packages = _workspace_packages(root)
    ci_workflow_names = _ci_workflow_names(root)
    issue_templates = _issue_templates(root)
    has_pre_commit = (root / ".pre-commit-config.yaml").is_file()
    has_codeowners = (root / ".github" / "CODEOWNERS").is_file() or (root / "CODEOWNERS").is_file()
    verification_commands = _verification_commands(
        root,
        entry_points=entry_points,
        makefile_targets=makefile_targets,
        test_frameworks=test_frameworks,
    )
    has_backstage = (root / "catalog-info.yaml").is_file()
    catalog_meta = _catalog_metadata(root) if has_backstage else {}

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

    purpose_hint = tagline or description or catalog_meta.get("catalog_description") or ""
    runtime_hint = ""
    if archetype == "hermes-plugin":
        runtime_hint = f"Hermes plugin workspace — ROADMAP.md at {root.name} root beside plugin.yaml"
    elif archetype == "web-app":
        runtime_hint = f"Web application root at {root.name} — deploy/runtime config in repo manifests"
    elif has_docker:
        if compose_services:
            runtime_hint = f"Containerized runtime — services: {', '.join(compose_services[:4])}"
        else:
            runtime_hint = "Containerized runtime — Docker/Docker Compose manifests define operational center"
    elif frameworks:
        runtime_hint = f"Primary stack: {', '.join(frameworks[:3])} — operational truth in repo config and entrypoints"

    operators_hint = description or _agent_rules_excerpt(root) or _contributing_excerpt(root) or ""
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
        "quality_tools": quality_tools or None,
        "monorepo_tools": monorepo_tools,
        "package_managers": package_managers,
        "has_ci": bool(ci_systems),
        "has_tests": has_tests,
        "has_docker": has_docker,
        "purpose_hint": purpose_hint or None,
        "runtime_center_hint": runtime_hint or None,
        "operators_hint": operators_hint or None,
        "entry_points": entry_points,
        "license": license_label,
        "git_remote": git_remote,
        "docs_roots": docs_roots,
        "agent_rules_files": agent_rules,
        "makefile_targets": makefile_targets,
        "verification_commands": verification_commands,
        "runtime_versions": runtime_versions or None,
        "dependency_automation": dependency_automation or None,
        "has_codeowners": has_codeowners,
        "compose_services": compose_services or None,
        "governance_files": governance_files or None,
        "workspace_packages": workspace_packages or None,
        "ci_workflow_names": ci_workflow_names or None,
        "issue_templates": issue_templates or None,
        "has_pre_commit": has_pre_commit,
        "has_backstage_catalog": has_backstage,
        "catalog_name": catalog_meta.get("catalog_name"),
        "catalog_description": catalog_meta.get("catalog_description"),
    }
