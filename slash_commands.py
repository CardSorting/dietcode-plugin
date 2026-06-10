# -*- coding: utf-8 -*-
"""DietCode slash commands — JoyZoning, BroccoliDB, and BroccoliQ consoles."""
from __future__ import annotations

import json
import shlex
from typing import Any, Dict, List, Optional

from plugins.dietcode.lib.agent.governance_exemptions import (
    governance_skip_reason,
    run_governance_validation_gate,
)
from plugins.dietcode.lib.tools.broccolidb_tools.runner import (
    run_agent_context_script,
    run_standalone_script,
)


def _validate_slash_file_path(raw: str) -> str | None:
    """Reject paths unsafe to embed in generated TypeScript snippets."""
    path = (raw or "").strip()
    if not path:
        return "path is required"
    if "\n" in path or "\r" in path or "\0" in path or "`" in path:
        return "path contains invalid characters"
    if ".." in path.replace("\\", "/"):
        return "path must not contain '..'"
    return None


def run_joyzoning_gate(files: List[str]) -> Dict[str, Any]:
    """Run JoyZoning policy checks on governable source files only."""
    return run_governance_validation_gate(files)


# ---------------------------------------------------------------------------
# Slash Command Handlers
# ---------------------------------------------------------------------------

_JZ_HELP = """\
/joyzoning — codebase layering compliance engine

Subcommands:
  status / audit             Run full structural composition audit of the codebase
  check <file>               Verify layer tags and imports for a specific file
  suggest <file>             Determine optimal layer assignment for a file
  refactor <file>            Generate dependency inversion refactoring specifications
"""

def _handle_joyzoning(raw_args: str) -> Optional[str]:
    """Handle /joyzoning slash command."""
    argv = shlex.split(raw_args.strip())
    if not argv or argv[0] in ("help", "-h", "--help"):
        return _JZ_HELP

    sub = argv[0].lower()

    if sub in ("status", "audit"):
        body = """
        const jz = await import('../utils/joy-zoning.js');
        const { SpiderEngine } = await import('../core/policy/SpiderEngine.js');
        
        const spider = new SpiderEngine(process.cwd());
        await spider.warmUp();

        const totalFiles = spider.nodes.size;
        const layerCounts = { domain: 0, core: 0, infrastructure: 0, plumbing: 0, ui: 0 };
        let tagsFound = 0;
        let cycleCount = 0;
        let violationCount = 0;
        const violations = [];

        // Count layers
        for (const [path, node] of spider.nodes.entries()) {
            const layer = node.layer || jz.getLayer(node.path);
            if (layerCounts[layer] !== undefined) {
                layerCounts[layer]++;
            }
            if (node.hasTag) tagsFound++;
        }

        // Cycle verification
        const visited = new Set();
        const pathStack = [];
        function dfs(nodePath) {
            if (pathStack.includes(nodePath)) {
                cycleCount++;
                return;
            }
            if (visited.has(nodePath)) return;
            visited.add(nodePath);
            pathStack.push(nodePath);
            const node = spider.nodes.get(nodePath);
            if (node) {
                for (const imp of node.imports) {
                    const resolved = node.resolvedImports.get(imp.specifier);
                    if (resolved) dfs(resolved);
                }
            }
            pathStack.pop();
        }
        for (const nodePath of spider.nodes.keys()) {
            dfs(nodePath);
        }

        // Enforce forbidden dependencies
        const FORBIDDEN = {
            'domain': ['infrastructure', 'ui'],
            'core': ['infrastructure', 'ui'],
        };
        for (const [nodePath, node] of spider.nodes.entries()) {
            const sourceLayer = node.layer || jz.getLayer(node.path);
            const forbidden = FORBIDDEN[sourceLayer];
            if (!forbidden) continue;

            for (const imp of node.imports) {
                const resolved = node.resolvedImports.get(imp.specifier);
                if (!resolved) continue;
                const targetNode = spider.nodes.get(resolved);
                if (!targetNode) continue;
                const targetLayer = targetNode.layer || jz.getLayer(targetNode.path);

                if (forbidden.includes(targetLayer)) {
                    violations.push({
                        file: node.path,
                        sourceLayer,
                        target: resolved,
                        targetLayer,
                        importSpec: imp.specifier,
                    });
                    violationCount++;
                }
            }
        }

        console.log(JSON.stringify({
            totalFiles,
            layerCounts,
            tagsFound,
            cycleCount,
            violationCount,
            violations: violations.slice(0, 10),
        }));
        """
        try:
            res_str = run_standalone_script(body)
            data = json.loads(res_str)
            if "error" in data:
                return f"❌ Error auditing codebase: {data['error']}"

            # Format composition
            lc = data.get("layerCounts", {})
            comp_lines = [f"  • {k.capitalize()}: {v} files" for k, v in lc.items()]
            
            # Format violations
            v_lines = []
            for v in data.get("violations", []):
                v_lines.append(f"  🚨 {v['file']} [{v['sourceLayer']}] imports {v['target']} [{v['targetLayer']}]")

            status_report = (
                "==============================================================\n"
                "🧅 JOYZONING COGNITIVE ARCHITECTURE AUDIT\n"
                "==============================================================\n"
                f"📊 Codebase Size : {data.get('totalFiles', 0)} files monitored\n"
                f"🏷️ Tag Saturation : {data.get('tagsFound', 0)} files tagged\n"
                f"🔄 Circular Deps : {data.get('cycleCount', 0)} cycles verified\n"
                f"🛡️ Policy Leaks  : {data.get('violationCount', 0)} violations active\n\n"
                "📦 Composition:\n" + "\n".join(comp_lines) + "\n\n"
            )
            if v_lines:
                status_report += "📂 Top Violations:\n" + "\n".join(v_lines)
            else:
                status_report += "🎉 Workspace is fully compliant! Layer structures are clean."
            status_report += "\n=============================================================="
            return status_report
        except Exception as e:
            return f"❌ Subprocess failed: {e}"

    if sub == "check":
        if len(argv) < 2:
            return "Usage: /joyzoning check <file>"
        target = argv[1]
        bad = _validate_slash_file_path(target)
        if bad:
            return f"❌ Invalid path: {bad}"
        skip = governance_skip_reason(target)
        if skip:
            return (
                f"ℹ️ '{target}' is exempt from layer governance ({skip}). "
                "JoyZoning does not require [LAYER: TYPE] tags on docs, manifests, "
                "migrations, or other non-source artifacts."
            )
        gate = run_joyzoning_gate([target])
        if gate.get("success", True):
            return f"✅ File '{target}' is fully compliant with JoyZoning policies!"
        
        errors = []
        for item in gate.get("singleResults", []):
            errors.extend(item.get("errors", []))
        return f"🚨 Governance violations found in '{target}':\n" + "\n".join(f"  - {e}" for e in errors)

    if sub == "suggest":
        if len(argv) < 2:
            return "Usage: /joyzoning suggest <file>"
        target = argv[1]
        bad = _validate_slash_file_path(target)
        if bad:
            return f"❌ Invalid path: {bad}"
        skip = governance_skip_reason(target)
        if skip:
            return (
                f"ℹ️ '{target}' is exempt from layer assignment ({skip}). "
                "No [LAYER: TYPE] tag is required."
            )
        body = f"""
        const jz = await import('../utils/joy-zoning.js');
        const layer = jz.getLayer({json.dumps(target)});
        console.log(JSON.stringify({{ layer }}));
        """
        try:
            res_str = run_standalone_script(body)
            data = json.loads(res_str)
            return f"💡 Suggestion: '{target}' belongs in the **{data.get('layer', 'unknown')}** layer."
        except Exception as e:
            return f"❌ Suggestion calculation failed: {e}"

    if sub == "refactor":
        if len(argv) < 2:
            return "Usage: /joyzoning refactor <file>"
        target = argv[1]
        bad = _validate_slash_file_path(target)
        if bad:
            return f"❌ Invalid path: {bad}"
        skip = governance_skip_reason(target)
        if skip:
            return (
                f"ℹ️ '{target}' is exempt from layer refactoring ({skip}). "
                "Governance applies to application source under src/, not manifests or docs."
            )
        body = f"""
        const {{ SpiderEngine }} = await import('../core/policy/SpiderEngine.js');
        const spider = new SpiderEngine(process.cwd());
        await spider.warmUp();
        const node = spider.nodes.get({json.dumps(target)});
        if (!node) {{
            console.log(JSON.stringify({{ error: 'File not indexed or not found' }}));
            process.exit(0);
        }}
        console.log(JSON.stringify({{
            imports: node.imports,
            resolved: Array.from(node.resolvedImports.entries()),
        }}));
        """
        try:
            res_str = run_standalone_script(body)
            data = json.loads(res_str)
            if "error" in data:
                return f"❌ Refactoring scan failed: {data['error']}"

            imports = data.get("imports", [])
            resolved = dict(data.get("resolved", []))
            
            refactor_lines = [
                f"🔧 Refactoring Blueprint for '{target}':",
                "  1. Introduce interfaces in the `domain` or `core` layers.",
                "  2. Inject actual service implementations from `infrastructure` using Dependency Injection.",
                "\n🔍 Detected Imports & Resolutions:"
            ]
            for imp in imports:
                res_path = resolved.get(imp.get("specifier", ""))
                refactor_lines.append(f"  • `{imp.get('specifier')}` -> resolved to `{res_path or 'unresolved'}`")
            
            return "\n".join(refactor_lines)
        except Exception as e:
            return f"❌ Refactor calculation failed: {e}"

    return f"Unknown subcommand: {sub}\n\n{_JZ_HELP}"


_BDB_HELP = """\
/broccolidb — epistemic cognitive database console

Subcommands:
  status                     Show connection status, node, edge and metadata metrics
  query <term>               Perform keyword/semantic search across knowledge graph
  audit                      Perform skeptical Git sovereign connectivity audit
  heal                       Prune unreliable or untrustworthy knowledge items
"""

def _handle_broccolidb(raw_args: str) -> Optional[str]:
    """Handle /broccolidb slash command."""
    argv = shlex.split(raw_args.strip())
    if not argv or argv[0] in ("help", "-h", "--help"):
        return _BDB_HELP

    sub = argv[0].lower()

    if sub == "status":
        body = """
        const db = await pool.ensureDb();
        const nodesRes = await db.selectFrom('knowledge').select(eb => eb.fn.countAll().as('count')).executeTakeFirst();
        const edgesRes = await db.selectFrom('knowledge_edges').select(eb => eb.fn.countAll().as('count')).executeTakeFirst();
        const workspacesRes = await db.selectFrom('workspaces').select(eb => eb.fn.countAll().as('count')).executeTakeFirst();
        
        console.log(JSON.stringify({
            nodes: nodesRes ? Number(nodesRes.count) : 0,
            edges: edgesRes ? Number(edgesRes.count) : 0,
            workspaces: workspacesRes ? Number(workspacesRes.count) : 0,
        }));
        """
        try:
            res_str = run_agent_context_script(body)
            data = json.loads(res_str)
            if "error" in data:
                return f"❌ BroccoliDB Connection Error: {data['error']}"

            status_report = (
                "==============================================================\n"
                "🥦 BROCCOLIDB COGNITIVE KNOWLEDGE METRICS\n"
                "==============================================================\n"
                "🟢 Connection : Active & Healthy\n"
                f"📁 Workspaces : {data.get('workspaces', 0)} initialized\n"
                f"🧠 Knowledge  : {data.get('nodes', 0)} nodes indexed\n"
                f"🔗 Relations  : {data.get('edges', 0)} edges mapped\n"
                "=============================================================="
            )
            return status_report
        except Exception as e:
            return f"❌ Context runner failed: {e}"

    if sub == "query":
        if len(argv) < 2:
            return "Usage: /broccolidb query <term>"
        query_term = " ".join(argv[1:])
        body = f"""
        const results = await context.searchKnowledge({json.dumps(query_term)}, [], 10);
        console.log(JSON.stringify({{
            results: results.map(r => ({{
                id: r.id,
                type: r.type,
                content: r.content,
                confidence: r.confidence,
            }})),
        }}));
        """
        try:
            res_str = run_agent_context_script(body)
            data = json.loads(res_str)
            if "error" in data:
                return f"❌ Search failed: {data['error']}"

            results = data.get("results", [])
            if not results:
                return f"🔍 Search for '{query_term}' returned 0 matches."

            lines = [f"🔍 Top results for '{query_term}':"]
            for i, r in enumerate(results, 1):
                lines.append(f"  {i}. [{r['type']}] {r['id']} (confidence: {r.get('confidence', 0.0):.2f})")
                content_truncated = r['content'][:120].replace('\n', ' ')
                lines.append(f"     \"{content_truncated}...\"")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Search error: {e}"

    if sub == "audit":
        body = """
        const db = await pool.ensureDb();
        const nodes = await db.selectFrom('knowledge').select(['id', 'type', 'content', 'confidence']).execute();
        const unreliable = [];

        for (const node of nodes) {
            const check = await context.reasoningService.verifySovereignty(node.id);
            if (!check.isValid) {
                unreliable.push({
                    id: node.id,
                    type: node.type,
                    content: node.content,
                    confidence: node.confidence,
                    metrics: check.metrics,
                });
            }
        }

        console.log(JSON.stringify({
            unreliable,
        }));
        """
        try:
            res_str = run_agent_context_script(body)
            data = json.loads(res_str)
            if "error" in data:
                return f"❌ Skeptical Audit Error: {data['error']}"

            unreliable = data.get("unreliable", [])
            if not unreliable:
                return "🎉 Epistemic audit complete. 100% of knowledge nodes have full Git sovereign validity!"

            lines = [
                "==============================================================\n"
                "🧐 BROCCOLIDB SKEPTICAL AUDIT REPORT\n"
                "==============================================================\n"
                f"🚨 Untrustworthy nodes found: {len(unreliable)}\n\n"
                "🔍 Top Unreliable Nodes (Discounted due to commit age or churn):"
            ]
            for i, r in enumerate(unreliable[:5], 1):
                m = r.get("metrics", {})
                lines.append(
                    f"  {i}. [{r['type']}] {r['id']}\n"
                    f"     - Probability: {m.get('finalProb', 0.0):.2f} (Threshold: {m.get('adaptiveThreshold', 0.0):.2f})\n"
                    f"     - Commit Distance: {m.get('commitDistance', 0)} commits back | Churn: {m.get('churn', 0.0):.2f}\n"
                    f"     - Summary: \"{r['content'][:80]}...\""
                )
            lines.append("==============================================================")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ Audit run failed: {e}"

    if sub == "heal":
        body = """
        const db = await pool.ensureDb();
        const nodes = await db.selectFrom('knowledge').select(['id']).execute();
        let pruned = 0;

        for (const node of nodes) {
            const check = await context.reasoningService.verifySovereignty(node.id);
            if (!check.isValid) {
                await db.deleteFrom('knowledge').where('id', '=', node.id).execute();
                await db.deleteFrom('knowledge_edges').where('sourceId', '=', node.id).execute();
                await db.deleteFrom('knowledge_edges').where('targetId', '=', node.id).execute();
                pruned++;
            }
        }

        console.log(JSON.stringify({
            pruned,
        }));
        """
        try:
            res_str = run_agent_context_script(body)
            data = json.loads(res_str)
            if "error" in data:
                return f"❌ Healing failed: {data['error']}"

            return f"🩹 Epistemic Retraction Complete: Successfully pruned {data.get('pruned', 0)} untrustworthy nodes from the graph!"
        except Exception as e:
            return f"❌ Healing execution error: {e}"

    return f"Unknown subcommand: {sub}\n\n{_BDB_HELP}"


_BQ_HELP = """\
/broccoliq — BroccoliQ sharded queue & hive infrastructure console

Subcommands:
  queue                      Job counts by status across all shards
  shards                     List active database shards and health
  integrity                  Run one-shot IntegrityWorker audit
"""


def _handle_broccoliq(raw_args: str) -> Optional[str]:
    """Handle /broccoliq slash command for sharded queue infrastructure."""
    argv = shlex.split(raw_args.strip())
    if not argv or argv[0] in ("help", "-h", "--help"):
        return _BQ_HELP

    sub = argv[0].lower()

    if sub == "queue":
        body = """
        import { getDb, getActiveShards } from './infrastructure/db/Config.js';
        const shards = getActiveShards().length ? getActiveShards() : ['main'];
        const byStatus = {};
        let total = 0;
        for (const shardId of shards) {
          const db = await getDb(shardId);
          const rows = await db.selectFrom('queue_jobs').select(['status']).execute();
          for (const row of rows) {
            byStatus[row.status] = (byStatus[row.status] ?? 0) + 1;
            total += 1;
          }
        }
        console.log(JSON.stringify({ total, byStatus, shards }));
        """
        try:
            data = json.loads(run_standalone_script(body))
            if "error" in data:
                return f"❌ BroccoliQ queue error: {data['error']}"
            lines = [
                "==============================================================",
                "📬 BROCCOLIQ SHARDED QUEUE STATUS",
                "==============================================================",
                f"🧩 Shards   : {', '.join(data.get('shards', ['main']))}",
                f"📊 Total    : {data.get('total', 0)} jobs",
            ]
            for status, count in sorted((data.get("byStatus") or {}).items()):
                lines.append(f"   • {status}: {count}")
            lines.append("==============================================================")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ BroccoliQ queue failed: {e}"

    if sub == "shards":
        body = """
        import { getActiveShards, getDb } from './infrastructure/db/Config.js';
        const listed = getActiveShards().length ? getActiveShards() : ['main'];
        const detail = [];
        for (const shardId of listed) {
          try {
            const db = await getDb(shardId);
            await db.selectFrom('queue_settings').selectAll().limit(1).execute();
            detail.push({ shardId, healthy: true });
          } catch (e) {
            detail.push({ shardId, healthy: false, error: String(e) });
          }
        }
        console.log(JSON.stringify({ shards: detail }));
        """
        try:
            data = json.loads(run_standalone_script(body))
            lines = ["🧩 BroccoliQ shards:"]
            for s in data.get("shards", []):
                icon = "🟢" if s.get("healthy") else "🔴"
                err = f" — {s['error']}" if s.get("error") else ""
                lines.append(f"  {icon} {s.get('shardId', '?')}{err}")
            return "\n".join(lines)
        except Exception as e:
            return f"❌ BroccoliQ shard status failed: {e}"

    if sub == "integrity":
        body = """
        import { IntegrityWorker } from './infrastructure/db/IntegrityWorker.js';
        import { getActiveShards } from './infrastructure/db/Config.js';
        const worker = new IntegrityWorker(600000);
        await worker.runAudit();
        console.log(JSON.stringify({
          ok: true,
          shards: getActiveShards().length ? getActiveShards() : ['main'],
        }));
        """
        try:
            data = json.loads(run_standalone_script(body, timeout=120))
            if not data.get("ok"):
                return f"❌ Integrity audit failed: {data.get('error', data)}"
            return (
                "🛡️ BroccoliQ IntegrityWorker audit complete.\n"
                f"Shards checked: {', '.join(data.get('shards', ['main']))}"
            )
        except Exception as e:
            return f"❌ Integrity audit failed: {e}"

    return f"Unknown subcommand: {sub}\n\n{_BQ_HELP}"


_ROADMAP_HELP = """\
/roadmap — auto-rolling roadmap checkpoint console

Subcommands:
  cockpit                One-screen operator summary (health, schema, code soup, next action)
  doctor                 Install skill + production health checks
  status                 Parse ROADMAP.md health and schema completeness
  evidence               Gather read-only project signals for a checkpoint pass
  checkpoint [context]   Full checkpoint briefing (evidence + update algorithm)
  validate               Schema validation for ROADMAP.md
  template               Bootstrap skeleton for first-pass ROADMAP.md
  guide                  Phase, health, and recommended next agent call
  progress [--timeline]  Roadmap tool activity (current + optional timeline)
  progress --current     Full progress + gate snapshot JSON
  progress --tail        JSON tail of roadmap-progress.jsonl
  watch                  Compact live summary of last roadmap action
  last-error             Last roadmap failure or validation issue
  explain-stale          Why checkpoint may be stale vs git activity
  explain-gate           Closed schema/freshness gates (kernel explain-gate analogue)
"""

def _handle_roadmap(raw_args: str) -> Optional[str]:
    """Handle /roadmap slash command."""
    argv = shlex.split(raw_args.strip())
    if not argv or argv[0] in ("help", "-h", "--help"):
        return _ROADMAP_HELP

    sub = argv[0].lower()
    context = " ".join(argv[1:]).strip()

    try:
        from plugins.dietcode.lib.agent.roadmap.cockpit import format_cockpit_report
        from plugins.dietcode.lib.agent.roadmap.config import RoadmapWorkspaceError, resolve_workspace_root
        from plugins.dietcode.lib.agent.roadmap import evidence as evidence_mod
        from plugins.dietcode.lib.agent.roadmap.doctor import run_checks
        from plugins.dietcode.lib.agent.roadmap.freshness import assess_checkpoint_freshness, format_explain_stale_report
        from plugins.dietcode.lib.agent.roadmap.progress import (
            format_progress_report,
            format_watch_report,
            read_last_error,
            read_tail,
        )
        from plugins.dietcode.lib.agent.roadmap.roadmap_checkpoint import (
            checkpoint_brief,
            operational_status,
            status_snapshot,
            template_brief,
            validate_roadmap,
        )
        from plugins.dietcode.lib.agent.roadmap.explain_gate import build_explain_gate_payload
        from plugins.dietcode.lib.agent.roadmap.skill_install import ensure_workspace_skills
    except ImportError as exc:
        return f"❌ Roadmap module unavailable: {exc}"

    try:
        root = resolve_workspace_root()
    except RoadmapWorkspaceError as exc:
        return f"❌ {exc}"

    if sub == "cockpit":
        return format_cockpit_report(workspace=root)

    if sub == "doctor":
        install = ensure_workspace_skills(root)
        report = run_checks(workspace=root)
        lines = [
            f"🗺️ Roadmap doctor — {root}",
            f"OK: {report.get('ok')}",
            f"Skill install: {len(install.get('installed') or [])} new, {len(install.get('skipped') or [])} skipped",
        ]
        for chk in report.get("checks") or []:
            mark = "✅" if chk.get("ok") else "⚠️"
            lines.append(f"{mark} {chk.get('name')}: {chk.get('detail')}")
        for rec in report.get("recommendations") or []:
            lines.append(f"→ {rec}")
        return "\n".join(lines)

    if sub == "status":
        data = status_snapshot(workspace=root)
        parsed = data.get("parsed") or {}
        lines = [
            f"🗺️ Roadmap status — {root}",
            f"Exists: {parsed.get('exists', False)}",
        ]
        if parsed.get("health_status"):
            lines.append(f"Health: {parsed['health_status']}")
        if parsed.get("code_soup_risk"):
            lines.append(f"Code soup risk: {parsed['code_soup_risk']}")
        if parsed.get("recent_checkpoint_date"):
            lines.append(f"Last checkpoint: {parsed['recent_checkpoint_date']}")
        missing = parsed.get("sections_missing") or []
        if missing:
            lines.append(f"Missing sections: {len(missing)}")
        return "\n".join(lines)

    if sub == "evidence":
        data = evidence_mod.gather_evidence(root, context_hint=context, tier="full")
        roadmap = data.get("roadmap") or {}
        git = data.get("git") or {}
        lines = [
            f"🗺️ Roadmap evidence — {root}",
            f"ROADMAP.md: {'present' if roadmap.get('exists') else 'missing'}",
            f"READMEs: {len(data.get('readmes') or [])}",
            f"Git commits: {len(git.get('recent_commits') or [])}",
            f"TODO/FIXME markers: {len(data.get('todo_markers') or [])}",
        ]
        uncertainty = data.get("uncertainty") or []
        if uncertainty:
            lines.append("Uncertainty:")
            lines.extend(f"  - {note}" for note in uncertainty[:5])
        return "\n".join(lines)

    if sub == "checkpoint":
        data = checkpoint_brief(workspace=root, context=context)
        lines = [
            f"🗺️ Roadmap checkpoint briefing — {root}",
            f"Phase: {data.get('phase')}",
            f"Skill: {data.get('skill_path')}",
            data.get("operator_summary", ""),
            f"Next: {data.get('agent_next_call', '')}",
        ]
        uncertainty = (data.get("evidence") or {}).get("uncertainty") or []
        if uncertainty:
            lines.append("Uncertainty:")
            lines.extend(f"  - {note}" for note in uncertainty[:5])
        lines.append("Use `roadmap(action='checkpoint')` tool for full JSON briefing.")
        return "\n".join(lines)

    if sub == "validate":
        data = validate_roadmap(workspace=root)
        validation = data.get("validation") or {}
        lines = [
            f"🗺️ Roadmap validate — {root}",
            f"Valid: {validation.get('valid')}",
            f"Schema complete: {validation.get('schema_complete')}",
            f"Now items: {validation.get('now_item_count')}",
        ]
        for issue in validation.get("issues") or []:
            lines.append(f"  • [{issue.get('severity')}] {issue.get('message')}")
        lines.append(f"Next: {data.get('agent_next_call', '')}")
        return "\n".join(lines)

    if sub == "template":
        data = template_brief(workspace=root)
        skeleton = data.get("skeleton") or ""
        preview = "\n".join(skeleton.splitlines()[:24])
        return (
            f"🗺️ Roadmap template — {root}\n"
            f"{data.get('operator_summary', '')}\n"
            f"Next: {data.get('agent_next_call', '')}\n\n"
            f"--- skeleton preview ---\n{preview}\n…"
        )

    if sub == "progress":
        if "--current" in argv:
            from plugins.dietcode.lib.agent.roadmap.progress import build_progress_snapshot
            return json.dumps(build_progress_snapshot(workspace=root), indent=2, ensure_ascii=False)
        if "--tail" in argv:
            return json.dumps(read_tail(lines=20), indent=2)
        timeline = "--timeline" in argv
        last = 5
        for token in argv[1:]:
            if token.isdigit():
                last = int(token)
        return format_progress_report(timeline=timeline, last=last, workspace=root)

    if sub == "watch":
        return format_watch_report()

    if sub == "last-error":
        err = read_last_error()
        if not err:
            return "🗺️ No roadmap errors recorded this session."
        return json.dumps(err, indent=2, ensure_ascii=False)

    if sub in ("explain-gate", "explain_gate"):
        data = build_explain_gate_payload(workspace=root)
        return data.get("report") or json.dumps(data, indent=2, ensure_ascii=False)

    if sub == "explain-stale":
        from plugins.dietcode.lib.agent.roadmap.snapshot import get_workspace_snapshot

        snap = get_workspace_snapshot(root, tier="light")
        fresh = snap.gate_inputs.get("freshness") or assess_checkpoint_freshness(
            recent_checkpoint_date=(snap.evidence.get("roadmap") or {}).get("recent_checkpoint_date"),
            git_commits=((snap.evidence.get("git") or {}).get("recent_commits") or []),
            schema_valid=snap.validation.valid if snap.validation else None,
        )
        return format_explain_stale_report(fresh)

    if sub == "guide":
        data = operational_status(workspace=root, context_hint=context)
        lines = [
            f"🗺️ Roadmap guide — {root}",
            f"Phase: {data.get('phase')}",
            f"ROADMAP.md: {'present' if data.get('roadmap_exists') else 'missing'}",
        ]
        if data.get("health_status"):
            lines.append(f"Health: {data['health_status']}")
        if data.get("code_soup_risk"):
            lines.append(f"Code soup risk: {data['code_soup_risk']}")
        lines.append(data.get("operator_summary", ""))
        lines.append(f"Next call: {data.get('agent_next_call', '')}")
        hints = data.get("_roadmap_operator_hints") or {}
        if hints.get("suggested_slash_command"):
            lines.append(f"Slash: {hints['suggested_slash_command']}")
        return "\n".join(lines)

    return f"Unknown subcommand: {sub}\n\n{_ROADMAP_HELP}"
