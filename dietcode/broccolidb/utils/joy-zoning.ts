import * as fs from "fs"
import minimatch from "minimatch"
import * as path from "path"
import * as ts from "typescript"
import { StabilityPolicy } from "../core/policy/StabilityPolicy.js"

export type Layer = "domain" | "core" | "infrastructure" | "plumbing" | "ui"

export enum CommentStyle {
	JSDOC = "jsdoc", // /** [LAYER: TYPE] */
	SLASH = "slash", // // [LAYER: TYPE]
	HASH = "hash", // # [LAYER: TYPE]
	DASH = "dash", // -- [LAYER: TYPE]
	HTML = "html", // <!-- [LAYER: TYPE] -->
}

const STYLE_REGISTRY: Record<string, CommentStyle> = {
	".ts": CommentStyle.JSDOC,
	".tsx": CommentStyle.JSDOC,
	".js": CommentStyle.JSDOC,
	".jsx": CommentStyle.JSDOC,
	".java": CommentStyle.JSDOC,
	".go": CommentStyle.SLASH,
	".rs": CommentStyle.SLASH,
	".proto": CommentStyle.SLASH,
	".grit": CommentStyle.SLASH,
	".cpp": CommentStyle.SLASH,
	".c": CommentStyle.SLASH,
	".h": CommentStyle.SLASH,
	".sh": CommentStyle.HASH,
	".py": CommentStyle.HASH,
	".rb": CommentStyle.HASH,
	".yaml": CommentStyle.HASH,
	".yml": CommentStyle.HASH,
	".env": CommentStyle.HASH,
	".dockerfile": CommentStyle.HASH,
	".sql": CommentStyle.DASH,
	".hs": CommentStyle.DASH,
	".lua": CommentStyle.DASH,
	".md": CommentStyle.HTML,
	".html": CommentStyle.HTML,
	".xml": CommentStyle.HTML,
	".vue": CommentStyle.HTML,
	".svelte": CommentStyle.HTML,
}

const STRICT_BLOCKLIST = [
	".json",
	".json5",
	".lock",
	".sum",
	".bin",
	".exe",
	".iso",
	".png",
	".jpg",
	".jpeg",
	".gif",
	".svg",
	".ico",
	".woff",
	".woff2",
	".ttf",
	".eot",
]

let SPEC_CACHE: any = null
let EXCLUDE_PATTERN_CACHE: any[] | null = null
const PATH_LAYER_CACHE: Map<string, Layer> = new Map()
const PATH_TAG_SUPPORT_CACHE: Map<string, boolean> = new Map()

/**
 * Determines the layer of a given file path based on Joy-Zoning conventions or spider.spec.json.
 * High-Performance: Uses an in-memory session cache to avoid redundant path math.
 * V10: Archetypal Primacy — The [LAYER: TYPE] tag in content overrides the file path.
 */
export function getLayer(filePath: string, content?: string): Layer {
	const normalized = filePath.replace(/\\/g, "/")

	// 1. Archetypal Primacy: Use the explicit tag in the content if available (v10)
	if (content) {
		const tag = parseLayerTag(content)
		if (tag) {
			// Cache this result for this specific file version
			PATH_LAYER_CACHE.set(normalized, tag)
			return tag
		}

		// 2. Archetypal Fallback: Suggest layer based on code patterns (v10)
		const suggestion = suggestLayerForContent(content)
		if (suggestion) {
			// Only trust suggestion if it is a strong signal (not null)
			PATH_LAYER_CACHE.set(normalized, suggestion.layer)
			return suggestion.layer
		}
	}

	if (PATH_LAYER_CACHE.has(normalized)) return PATH_LAYER_CACHE.get(normalized)!

	const layer = getPathLayer(filePath)
	PATH_LAYER_CACHE.set(normalized, layer)
	return layer
}

/**
 * Path-only layer resolution (no content tags or pattern hints).
 * Used for PGA checks in ``validateJoyZoning`` and auto-injected headers.
 */
export function getPathLayer(filePath: string): Layer {
	const normalized = filePath.replace(/\\/g, "/")

	// Try to load spider.spec.json for custom domain/layer mappings (Cached)
	if (SPEC_CACHE === null) {
		try {
			const specPath = path.resolve(process.cwd(), "spider.spec.json")
			if (fs.existsSync(specPath)) {
				SPEC_CACHE = JSON.parse(fs.readFileSync(specPath, "utf-8"))
			} else {
				SPEC_CACHE = {}
			}
		} catch (_e) {
			SPEC_CACHE = {}
		}
	}

	if (SPEC_CACHE?.resources) {
		for (const [_key, resource] of Object.entries(SPEC_CACHE.resources)) {
			const res = resource as { path?: string; domain?: string }
			if (res.path && normalized.includes(res.path)) {
				if (res.domain) {
					const domainToLayer: Record<string, Layer> = {
						ui: "ui",
						api: "infrastructure",
						admin: "infrastructure",
						domain: "domain",
						core: "core",
					}
					return domainToLayer[res.domain] || "infrastructure"
				}
			}
		}
	}

	if (normalized.includes("src/domain/") || normalized.endsWith("/src/domain") || normalized.includes("broccolidb/domain/")) {
		return "domain"
	}
	if (
		normalized.includes("src/infrastructure/") ||
		normalized.endsWith("/src/infrastructure") ||
		normalized.includes("broccolidb/infrastructure/")
	) {
		return "infrastructure"
	}
	if (
		normalized.includes("src/plumbing/") ||
		normalized.endsWith("/src/plumbing") ||
		normalized.includes("src/shared/utils/") ||
		normalized.includes("broccolidb/utils/") ||
		normalized.includes("broccolidb/shared/")
	) {
		return "plumbing"
	}
	if (normalized.includes("src/ui/") || normalized.endsWith("/src/ui") || normalized.includes("webview-ui/")) {
		return "ui"
	}
	if (
		normalized.includes("src/core/") ||
		normalized.endsWith("/src/core") ||
		normalized.includes("broccolidb/core/") ||
		normalized.endsWith("/run_agent.py") ||
		normalized === "run_agent.py" ||
		normalized.includes("agent/")
	) {
		return "core"
	}
	if (
		normalized.includes("src/services/") ||
		normalized.includes("src/integrations/") ||
		normalized.includes("src/generated/") ||
		normalized.includes("src/hosts/") ||
		normalized.includes("src/packages/") ||
		normalized.includes("src/shared/")
	) {
		return "infrastructure"
	}
	if (normalized.includes("src/utils/")) {
		return "plumbing"
	}
	if (
		normalized.endsWith("/cli.py") ||
		normalized === "cli.py" ||
		normalized.includes("herm-tui/") ||
		normalized.includes("broccolidb/cli/")
	) {
		return "ui"
	}
	return "infrastructure"
}

/** Keep in sync with agent/governance_exemptions.py (policy v20+) */
const GOVERNANCE_EXEMPT_BASENAMES = new Set([
	"package.json",
	"package-lock.json",
	"pnpm-lock.yaml",
	"yarn.lock",
	"npm-shrinkwrap.json",
	"bun.lockb",
	"bun.lock",
	"composer.json",
	"composer.lock",
	"cargo.lock",
	"go.sum",
	"go.mod",
	"pyproject.toml",
	"tsconfig.json",
	"jsconfig.json",
	"tsconfig.build.json",
	"vite.config.ts",
	"vitest.config.ts",
	"jest.config.js",
	"schema.prisma",
	"drizzle.config.ts",
	"docker-compose.yml",
	"docker-compose.yaml",
	"readme.md",
	"changelog.md",
	"contributing.md",
	"license",
	"license.md",
	"agents.md",
	"claude.md",
	".gitignore",
	".dockerignore",
	".editorconfig",
	"pnpm-workspace.yaml",
	"lerna.json",
	"nx.json",
	"renovate.json",
	"mise.toml",
	"flake.nix",
	"buf.yaml",
	"turbo.json",
	"cargo.toml",
	"uv.lock",
	"serverless.yml",
	"fly.toml",
	"components.json",
	"bunfig.toml",
	"sbom.json",
	"security.txt",
	".cursorindexingignore",
	"copilot-instructions.md",
])

const GOVERNANCE_EXEMPT_EXTENSIONS = new Set([
	...STRICT_BLOCKLIST,
	".md",
	".mdx",
	".mdc",
	".markdown",
	".rst",
	".dbml",
	".txt",
	".adoc",
	".sql",
	".sqlite",
	".sqlite3",
	".db",
	".prisma",
	".toml",
	".yaml",
	".yml",
	".ini",
	".cfg",
	".conf",
	".properties",
	".csv",
	".graphql",
	".gql",
	".proto",
	".map",
	".min.js",
	".min.css",
	".zip",
	".gz",
	".wasm",
	".xml",
	".plist",
	".info",
	".lcov",
	".html",
	".htm",
	".css",
	".scss",
	".vue",
	".svelte",
	".py",
	".go",
	".rs",
	".java",
	".rb",
	".sh",
	".tf",
	".tfvars",
	".hcl",
	".po",
	".tex",
	".bib",
	".sty",
	".bst",
	".cls",
	".eikon",
	".service",
	".astro",
	".feature",
	".rego",
	".nim",
	".zig",
	".dart",
	".sln",
	".csproj",
	".webp",
	".avif",
])

const GOVERNANCE_EXEMPT_PATH_MARKERS = [
	"/migrations/",
	"/migration/",
	"/migrate/",
	"/prisma/",
	"/drizzle/",
	"/typeorm/",
	"/sequelize/",
	"/knex/",
	"/alembic/",
	"/liquibase/",
	"/flyway/",
	"/supabase/",
	"/orm/",
	"/database/",
	"/databases/",
	"/db/migrations/",
	"/db/schema/",
	"/database/schema/",
	"/entities/",
	"/seeders/",
	"/seeds/",
	"/fixtures/",
	"/__fixtures__/",
	"/testdata/",
	"/snapshots/",
	"/__snapshots__/",
	"/docs/",
	"/documentation/",
	"/reports/",
	"/website/",
	"/generated/",
	"/__generated__/",
	"/vendor/",
	"/node_modules/",
	"/.venv/",
	"/venv/",
	"/.git/",
	"/.github/",
	"/dist/",
	"/build/",
	"/coverage/",
	"/.next/",
	"/.nuxt/",
	"/public/",
	"/static/",
	"/locales/",
	"/openapi/",
	"/swagger/",
	"/.storybook/",
	"/.cursor/",
	"/.vscode/",
	"/sql/",
	"/atlas/",
	"/.turbo/",
	"/.changeset/",
	"/proto/",
	"/mocks/",
	"/__mocks__/",
	"/test-utils/",
	"/optional-skills/",
	"/grafana/",
	"/prometheus/",
]

const GOVERNANCE_EXEMPT_BASENAME_SUFFIXES = [
	".d.ts",
	".config.ts",
	".config.js",
	".config.mjs",
	".config.cjs",
	".config.json",
	".test.ts",
	".test.tsx",
	".test.js",
	".test.jsx",
	".spec.ts",
	".spec.tsx",
	".stories.ts",
	".stories.tsx",
	".mock.ts",
	".bench.ts",
	".e2e.ts",
	".e2e.tsx",
	".integration.ts",
	".smoke.ts",
	".contract.ts",
	".config.mts",
	".config.mjs",
	".bench.ts",
	".test.mjs",
	".test.cjs",
]

const GOVERNANCE_COMPOUND_SUFFIXES = [
	".min.js",
	".min.css",
	".min.ts",
	".bundle.js",
	".tar.gz",
	".tar.bz2",
	".test.ts.snap",
]

const GOVERNANCE_EXEMPT_SEGMENT_PREFIXES = [
	"node_modules/",
	".git/",
	".venv/",
	"venv/",
	"dist/",
	"build/",
	"coverage/",
	".husky/",
	".cursor/",
	".idea/",
	".github/",
	".gitlab/",
	".circleci/",
	"out/",
	"target/",
	".cache/",
	".turbo/",
	"temp/",
	"logs/",
	"mocks/",
	"__mocks__/",
	"stubs/",
	"test-utils/",
	"proto/",
	".changeset/",
	"docs/",
	"migrations/",
	"prisma/",
	"fixtures/",
	"generated/",
	"e2e/",
	"cypress/",
	"playwright/",
	".storybook/",
	"terraform/",
	"optional-skills/",
	".broccolidb/",
	"paste_store/",
]

function isCompoundExemptPath(normalized: string): boolean {
	return GOVERNANCE_COMPOUND_SUFFIXES.some((s) => normalized.endsWith(s))
}

function isEnvFileBasename(basename: string): boolean {
	const lower = basename.toLowerCase()
	if (lower.startsWith(".env")) return true
	if (lower === ".envrc" || lower === "envrc") return true
	if (lower.startsWith("env.") && /\.(local|example|sample|development|production|test)$/.test(lower)) return true
	return false
}

function isMakefileVariant(basename: string): boolean {
	const lower = basename.toLowerCase()
	if (["makefile", "gnumakefile", "makefile.win", "makefile.am"].includes(lower)) return true
	return lower.startsWith("makefile.") || lower.startsWith("gnumakefile.")
}

function isReleaseDocBasename(basename: string): boolean {
	const lower = basename.toLowerCase()
	return (lower.startsWith("release_") || lower.startsWith("release-")) && lower.endsWith(".md")
}

function isRepoRootSkillsTree(normalized: string): boolean {
	return normalized.startsWith("skills/")
}

const GOVERNANCE_SOURCE_EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx"])

export function normalizeGovernancePath(filePath: string): string {
	return filePath.replace(/\\/g, "/").trim()
}

function isLockfileBasename(basename: string): boolean {
	const lower = basename.toLowerCase()
	if (lower.endsWith(".lock") || lower.endsWith("-lock.json")) return true
	if (["bun.lockb", "bun.lock", "pnpm-lock.yaml", "yarn.lock", "uv.lock"].includes(lower)) return true
	if (lower.endsWith(".lockb") || lower.endsWith(".lock.yaml")) return true
	return false
}

function isEditorRcBasename(basename: string): boolean {
	const lower = basename.toLowerCase()
	if (lower.startsWith(".") && lower.endsWith("rc")) return true
	if (lower.endsWith("rc.json") || lower.endsWith("rc.yaml") || lower.endsWith("rc.yml")) return true
	return false
}

function isRepoRootTmpDir(normalized: string): boolean {
	return normalized.startsWith("tmp/")
}

/** Ephemeral Hermes scratch only — not all of ``/tmp`` or pytest temps under ``/private/tmp/``. */
function isHermesScratchTemp(normalized: string): boolean {
	return normalized.startsWith("/tmp/hermes") || normalized.includes("/tmp/hermes-")
}

export function isGovernanceArtifactPath(filePath: string): boolean {
	if (!filePath || !String(filePath).trim()) return true
	const normalized = normalizeGovernancePath(filePath).toLowerCase()
	const basename = path.basename(normalized)
	if (GOVERNANCE_EXEMPT_BASENAMES.has(basename)) return true
	if (isLockfileBasename(basename) || isEditorRcBasename(basename)) return true
	if (isEnvFileBasename(basename) || isMakefileVariant(basename) || isReleaseDocBasename(basename)) return true
	if (isCompoundExemptPath(normalized)) return true
	if (isRepoRootTmpDir(normalized) || isHermesScratchTemp(normalized)) return true
	for (const suffix of GOVERNANCE_EXEMPT_BASENAME_SUFFIXES) {
		if (basename.endsWith(suffix)) return true
	}
	const ext = path.extname(filePath).toLowerCase()
	if (GOVERNANCE_EXEMPT_EXTENSIONS.has(ext)) return true
	if (basename === "dockerfile" || basename.startsWith("dockerfile.")) return true
	if (GOVERNANCE_EXEMPT_PATH_MARKERS.some((marker) => normalized.includes(marker))) return true
	if (isRepoRootSkillsTree(normalized)) return true
	for (const seg of GOVERNANCE_EXEMPT_SEGMENT_PREFIXES) {
		if (seg === "skills/") continue
		if (normalized.startsWith(seg) || normalized.includes(`/${seg}`)) return true
	}
	return false
}

export function isGovernanceSubject(filePath: string, content?: string): boolean {
	if (isGovernanceArtifactPath(filePath)) return false
	const ext = path.extname(filePath).toLowerCase()
	if (!GOVERNANCE_SOURCE_EXTENSIONS.has(ext)) return false
	return isLayerTagSupported(filePath, content)
}

/**
 * Determines if a file supports architectural [LAYER: TYPE] tags.
 * Only source files that support JSDoc-style comments are included.
 */
export function isLayerTagSupported(filePath: string, content?: string): boolean {
	const normalized = filePath.replace(/\\/g, "/")
	if (!content && PATH_TAG_SUPPORT_CACHE.has(normalized)) return PATH_TAG_SUPPORT_CACHE.get(normalized)!
	if (isGovernanceArtifactPath(filePath)) return false
	const ext = path.extname(filePath).toLowerCase()
	if (filePath.toLowerCase().endsWith(".d.ts") || STRICT_BLOCKLIST.includes(ext)) return false
	if ([".md", ".mdx", ".rst"].includes(ext)) return false

	const policy = StabilityPolicy.getInstance(process.cwd())
	const config = policy.getGlobalConfig()
	const supportedExtensions = config.supportedLayerTags
	const excludePaths = config.excludePaths || []

	// 1. Path-based Glob Exclusion (Optimized with Cached Matchers)
	if (EXCLUDE_PATTERN_CACHE === null) {
		EXCLUDE_PATTERN_CACHE = excludePaths.map((p) => (f: string) => minimatch(f, p, { dot: true }))
	}

	for (const matcher of EXCLUDE_PATTERN_CACHE) {
		if (matcher(filePath) || matcher(path.relative(process.cwd(), filePath))) {
			return false
		}
	}

	// 2. Extension Check
	const style = STYLE_REGISTRY[ext]
	const isExtSupported = supportedExtensions && supportedExtensions.length > 0 ? supportedExtensions.includes(ext) : !!style

	if (!isExtSupported || !style) return false

	// 3. Content-based Protection (if content is provided)
	if (content) {
		// Empty check
		if (content.trim().length === 0) return false

		// Binary check (search for null bytes in first 1KB)
		const sample = content.slice(0, 1024)
		if (sample.includes("\0")) return false

		// Generated check
		const generatedMarkers = [
			"@" + "generated",
			"Code " + "generated by",
			"DO " + "NOT EDIT",
			"Automatically " + "generated"
		]
		if (generatedMarkers.some((marker) => content.slice(0, 5000).includes(marker))) {
			return false
		}
	}

	if (!content) PATH_TAG_SUPPORT_CACHE.set(normalized, true)
	return true
}

/**
 * Generates the appropriate layer comment for the given file and layer.
 * Detects shebangs and respects language-specific comment syntax.
 * Now performs in-place replacement if a tag already exists.
 */
export function generateLayerComment(filePath: string, layer: string, content?: string): string | null {
	if (!isLayerTagSupported(filePath, content)) return null

	const ext = path.extname(filePath).toLowerCase()
	const style = STYLE_REGISTRY[ext]
	if (!style) return null

	const tag = layer.toUpperCase()
	const label = `[LAYER: ${tag}]`
	let comment = ""

	switch (style) {
		case CommentStyle.JSDOC:
			comment = `/**\n * ${label}\n */\n`
			break
		case CommentStyle.SLASH:
			comment = `// ${label}\n\n`
			break
		case CommentStyle.HASH:
			comment = `# ${label}\n\n`
			break
		case CommentStyle.DASH:
			comment = `-- ${label}\n\n`
			break
		case CommentStyle.HTML:
			comment = `<!-- ${label} -->\n\n`
			break
	}

	if (content) {
		// 1. In-place Replacement Strategy
		const tagRegex = /\[LAYER:\s*(DOMAIN|CORE|INFRASTRUCTURE|PLUMBING|UI|UTILS)\]/i
		const existingMatch = content.slice(0, 10000).match(tagRegex)

		if (existingMatch) {
			// Find the line containing the tag and replace Just the tag part
			if (style === CommentStyle.JSDOC && !content.includes(`* ${label}`)) {
				// Check if we are inside a JSDoc block already
				const index = content.search(tagRegex)
				const prefix = content.slice(0, index)
				const lastOpen = prefix.lastIndexOf("/**")
				const lastClose = prefix.lastIndexOf("*/")

				if (lastOpen > lastClose) {
					// We are inside a JSDoc block, just ensure the asterisk prefix is handled correctly
					// If the line already starts with an asterisk, we don't add another one
					const lineStart = prefix.lastIndexOf("\n")
					const lineContent = prefix.slice(lineStart + 1)
					if (lineContent.trim().startsWith("*")) {
						return content.replace(tagRegex, label)
					}
					return content.replace(tagRegex, `* ${label}`)
				}
				// Not in a JSDoc block, wrap it
				return content.replace(tagRegex, `/**\n * ${label}\n */`)
			}
			return content.replace(tagRegex, label)
		}

		// 2. Structural Header Detection (Shebang + Frontmatter)
		let injectionIndex = 0

		// Check for Shebang (must be at the very start)
		if (content.startsWith("#!")) {
			const firstLineEnd = content.indexOf("\n")
			if (firstLineEnd !== -1) {
				injectionIndex = firstLineEnd + 1
			}
		}

		// Check for YAML Frontmatter (starts after Shebang if exists, or at 0)
		const remainingFromIndex = content.slice(injectionIndex)
		const frontmatterMatch = remainingFromIndex.match(/^---\n([\s\S]*?)\n---\n?/)
		if (frontmatterMatch) {
			injectionIndex += frontmatterMatch[0].length
		}

		if (injectionIndex > 0) {
			const header = content.slice(0, injectionIndex)
			const body = content.slice(injectionIndex)
			return `${header}${comment}${body}`
		}

		return `${comment}${content}`
	}

	return comment
}

/**
 * Validates architectural smells in the given content.
 * Layer-aware: strict checks apply only to domain/infrastructure.
 */
export function validateSmells(filePath: string, content: string): string[] {
	const errors: string[] = []
	const layer = getLayer(filePath)

	// Multiple classes in a single file — only enforced in domain for large files
	if (layer === "domain") {
		const classCount = (content.match(/class\s+/g) || []).length
		const totalLines = content.split("\n").length
		// V215: Relaxed to allow multiple classes unless the file is getting massive (> 500 lines)
		if (classCount > 3 || (classCount > 1 && totalLines > 500)) {
			errors.push(
				`${path.basename(filePath)}: Multiple classes in a single file — consider splitting for better domain isolation.`,
			)
		}
	}

	// Discouraged 'any' type — domain and infrastructure only (core is exempt)
	if (layer === "domain" || layer === "infrastructure") {
		if (content.includes(": any") || content.includes("<any>")) {
			// Surface as an architectural smell rather than a strict error
			errors.push(`${path.basename(filePath)}: Architectural smell — 'any' type detected.`)
		}
	}

	return errors
}

/**
 * Validates layering constraints using AST analysis.
 */
export function validateLayering(filePath: string, content: string): string[] {
	const errors: string[] = []
	const layer = getLayer(filePath)
	const ext = path.extname(filePath).toLowerCase()

	if (ext === ".py") {
		// Python Layering Validation (Regex-based for performance)
		const importRegex = /^(?:from\s+([\w.]+)\s+import|import\s+([\w.]+))/gm
		let match
		while ((match = importRegex.exec(content)) !== null) {
			const spec = match[1] || match[2]
			if (!spec) continue

			if (spec.startsWith(".")) {
				const dots = spec.match(/^\.+/)?.[0] || ""
				const depth = dots.length
				const remaining = spec.slice(depth)
				let dir = path.dirname(filePath)
				for (let i = 1; i < depth; i++) dir = path.dirname(dir)
				const absoluteImportPath = path.resolve(dir, remaining.replace(/\./g, "/"))
				const importedLayer = getLayer(absoluteImportPath)
				if (isLayerViolation(layer, importedLayer)) {
					errors.push(`${layer} layer in ${path.basename(filePath)} cannot import from ${importedLayer} (${spec}).`)
				}
			} else {
				const parts = spec.split(".")
				const internalPackages = ["agent", "tools", "gateway", "broccolidb", "hermes_cli", "plugins"]
				if (internalPackages.includes(parts[0])) {
					const projectPath = path.resolve(process.cwd(), parts.join("/"))
					const importedLayer = getLayer(projectPath)
					if (isLayerViolation(layer, importedLayer)) {
						errors.push(`${layer} layer in ${path.basename(filePath)} cannot import from ${importedLayer} (${spec}).`)
					}
				}
			}
		}
		if (layer === "domain") {
			const forbiddenTerms = ["requests.", "urllib.", "os.system", "subprocess.", "open("]
			for (const term of forbiddenTerms) {
				if (content.includes(term)) {
					errors.push(`Architectural Violation: Forbidden call '${term}' in Domain layer file ${path.basename(filePath)}.`)
				}
			}
		}
		return errors
	}

	const sourceFile = ts.createSourceFile(filePath, content, ts.ScriptTarget.Latest, true)
	const visit = (node: ts.Node) => {
		if (ts.isImportDeclaration(node)) {
			const moduleSpecifier = node.moduleSpecifier
			if (ts.isStringLiteral(moduleSpecifier)) {
				const spec = moduleSpecifier.text
				let absoluteImportPath: string | null = null
				if (spec.startsWith(".")) {
					absoluteImportPath = path.resolve(path.dirname(filePath), spec)
				} else if (spec.startsWith("@")) {
					const root = process.cwd()
					const aliasMap: Record<string, string> = {
						"@/": "src/",
						"@api/": "src/core/api/",
						"@core/": "src/core/",
						"@hosts/": "src/hosts/",
						"@integrations/": "src/integrations/",
						"@packages/": "src/packages/",
						"@services/": "src/services/",
						"@shared/": "src/shared/",
						"@utils/": "src/utils/",
					}
					aliasMap["@" + "generated/"] = "src/generated/"
					for (const [alias, relDir] of Object.entries(aliasMap)) {
						if (spec.startsWith(alias)) {
							const suffix = spec.slice(alias.length)
							absoluteImportPath = path.resolve(root, relDir, suffix)
							break
						}
					}
				}

				if (absoluteImportPath) {
					if (!fs.existsSync(absoluteImportPath)) {
						for (const e of [".ts", ".tsx", ".js", ".jsx"]) {
							if (fs.existsSync(absoluteImportPath + e)) {
								absoluteImportPath = absoluteImportPath + e
								break
							}
						}
					}
					const importedLayer = getLayer(absoluteImportPath)
					if (isLayerViolation(layer, importedLayer)) {
						errors.push(`${layer} layer in ${path.basename(filePath)} cannot import from ${importedLayer} (${spec}).`)
					}
				}
			}
		}
		if (layer === "domain" && ts.isCallExpression(node)) {
			const text = node.expression.getText(sourceFile)
			const forbiddenTerms = ["fetch", "fs.", "child_process", "axios", "http."]
			if (forbiddenTerms.some((term) => text.includes(term))) {
				errors.push(`Architectural Violation: Forbidden call '${text}' in Domain layer file ${path.basename(filePath)}.`)
			}
		}
		ts.forEachChild(node, visit)
	}
	visit(sourceFile)
	return errors
}

function isLayerViolation(layer: Layer, importedLayer: Layer): boolean {
	if (layer === "domain") return importedLayer === "infrastructure" || importedLayer === "ui"
	if (layer === "core") return importedLayer === "ui"
	if (layer === "infrastructure") return importedLayer === "ui"
	if (layer === "ui") return false // UI (CLI) can import from Infrastructure/Core/Domain/Plumbing
	if (layer === "plumbing") return ["domain", "core", "infrastructure", "ui"].includes(importedLayer)
	return false
}

/**
 * Parses the [LAYER: TYPE] tag from the file content.
 * Follows the Header Rule: tag must be within the first 10,000 characters.
 */
export function parseLayerTag(content: string): Layer | null {
	const header = content.slice(0, 10000)
	const match = header.match(/\[LAYER:\s*(DOMAIN|CORE|INFRASTRUCTURE|PLUMBING|UI|UTILS)\]/i)
	if (!match) return null

	const tag = match[1].toLowerCase()
	if (tag === "utils") return "plumbing"
	return tag as Layer
}

/**
 * Validates the vertical depth of relative imports.
 * Limit: 3 levels of relative depth (../../..).
 */
export function validateImportDepth(filePath: string, content: string): string[] {
	const errors: string[] = []
	const lines = content.split("\n")

	for (let i = 0; i < lines.length; i++) {
		const line = lines[i]
		if (line.includes('from "') || line.includes("from '")) {
			const match = line.match(/["'](\.\.\/)+[^"']*["']/)
			if (match) {
				const depth = (match[0].match(/\.\.\//g) || []).length
				if (depth > 3) {
					errors.push(
						`${path.basename(filePath)}:${i + 1}: Excessive relative navigation (${depth} levels) — use @ aliases or flatten structure.`,
					)
				}
			}
		}
	}

	return errors
}

/**
 * Full Joy-Zoning validation for a file.
 */
export function validateJoyZoning(
	filePath: string,
	content: string,
): { success: boolean; errors: string[]; skipped?: boolean } {
	if (!isGovernanceSubject(filePath, content)) {
		return { success: true, errors: [], skipped: true }
	}

	const allErrors: string[] = []

	// 1. Tag Locality & PGA (Principle of Geographic Alignment)
	const tag = parseLayerTag(content)
	const pathLayer = getPathLayer(filePath)

	if (!tag) {
		if (isLayerTagSupported(filePath)) {
			allErrors.push(`${path.basename(filePath)}: Missing mandatory [LAYER: TYPE] header tag.`)
		}
	} else if (tag !== pathLayer) {
		allErrors.push(
			`${path.basename(filePath)}: Geographic Misalignment — Tag [LAYER: ${tag.toUpperCase()}] does not match path layer '${pathLayer}'.`,
		)
	}

	// 2. Import Depth
	const depthErrors = validateImportDepth(filePath, content)
	allErrors.push(...depthErrors)

	// 3. Smells & Layering
	const smellErrors = validateSmells(filePath, content)
	const layeringErrors = validateLayering(filePath, content)
	allErrors.push(...smellErrors, ...layeringErrors)

	return {
		success: allErrors.length === 0,
		errors: allErrors,
	}
}

/** Single-file gate used by governance hooks and CLI check commands. */
export function checkSingleFile(filePath: string): {
	valid: boolean
	layer: Layer
	errors: string[]
} {
	if (!fs.existsSync(filePath)) {
		return { valid: true, layer: getLayer(filePath), errors: [] }
	}
	const content = fs.readFileSync(filePath, "utf-8")
	const layer = getLayer(filePath, content)
	if (!isGovernanceSubject(filePath, content)) {
		return { valid: true, layer, errors: [] }
	}
	const result = validateJoyZoning(filePath, content)
	return { valid: result.success, layer, errors: result.errors }
}

/**
 * Analyzes code content and suggests which architectural layer best fits.
 * Returns the suggested layer and the reasoning behind the suggestion.
 * PRODUCTION HARDENING: Context-aware detection for reactive and orchestration patterns.
 */
export function suggestLayerForContent(content: string): { layer: Layer; reason: string } | null {
	// 1. UI Patterns
	if (/import\s+.*from\s+["']react/i.test(content) || /jsx|tsx|component|render/i.test(content)) {
		return { layer: "ui", reason: "Contains React/JSX patterns — belongs in the UI layer." }
	}

	// 2. Infrastructure Patterns (I/O, Adapters, Storage)
	if (
		/import\s+.*from\s+["'](?:fs|http|https|net|child_process|pg|mysql|redis|axios|sqlite|mongodb)/i.test(content) ||
		/class\s+.*Adapter|class\s+.*Repository|class\s+.*Client/i.test(content)
	) {
		return { layer: "infrastructure", reason: "Contains I/O, storage, or external service adapter patterns." }
	}

	// 3. Core Patterns (Orchestration, Events, State Management)
	// PRODUCTION HARDENING: Explicitly recognize Reactive and Message-passing primitives as Core signals.
	if (
		/EventEmitter|Observable|Subject|BehaviorSubject|ReplaySubject|Subscription|Redux|Store|Dispatch|Effect/i.test(content) ||
		/class\s+.*Service|class\s+.*Manager|class\s+.*Orchestrator|class\s+.*Broker/i.test(content) ||
		/import\s+.*from\s+["'](?:rxjs|@ngrx|@reduxjs|events)/i.test(content)
	) {
		return { layer: "core", reason: "Contains orchestration, event-driven, or state management patterns." }
	}

	// 4. Domain Patterns (DDD - Value Objects, Entities)
	// PRODUCTION HARDENING: Recognize ValueObject, Entity, and AggregateRoot as strong Domain signals.
	if (
		/ValueObject|Entity|AggregateRoot|Specification|DomainEvent/i.test(content) ||
		/class\s+.*(?:Entity|Service|Factory|Repository|VO)/.test(content)
	) {
		// Only suggest Domain if it doesn't look like Infrastructure (Repository Impls usually in Infra)
		if (!/import\s+.*from\s+["'](?:fs|http|pg|mysql|redis|axios|sqlite|mongodb)/i.test(content)) {
			return {
				layer: "domain",
				reason: "Contains Domain-Driven Design (DDD) patterns (ValueObject, Entity, AggregateRoot) — belongs in the Domain layer.",
			}
		}
	}

	// 5. Plumbing Patterns (Pure utilities, stateless)
	if (
		!/class\s+/.test(content) &&
		/export\s+(?:function|const)\s+/.test(content) &&
		!/import\s+.*from\s+["']@(?:core|infrastructure|services|api)/.test(content)
	) {
		return { layer: "plumbing", reason: "Stateless utility functions with no high-level layer dependencies." }
	}

	return null // can't confidently suggest
}

/**
 * Extracts a target file path from various common tool parameter names.
 */
export function getTargetPath(params: Record<string, unknown>): string | null {
	if (!params) return null
	const rawPath = params.path || params.file_path || params.target_file || params.absolutePath
	if (typeof rawPath !== "string") return null
	return rawPath
}
