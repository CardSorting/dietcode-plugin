# -*- coding: utf-8 -*-
"""Project map planning tool — ports codemarie ProjectMapHandler (Spider + BroccoliDB)."""
from __future__ import annotations

import json
from typing import Any

from tools.registry import registry, tool_error

from plugins.dietcode.lib.tools.broccolidb_tools.runner import (
    _BOOTSTRAP_TIMEOUT,
    check_requirements,
    run_standalone_script,
)


def _disk_path_exists(path: str) -> bool:
    from pathlib import Path

    try:
        return Path(path).is_file()
    except OSError:
        return False


def _enrich_map(payload: dict[str, Any], *, path: str, max_files: int) -> dict[str, Any]:
    """Add BroccoliDB co-change and chokepoint signals when DB is available."""
    semantic_path = (path or "").strip()
    if not semantic_path or not check_requirements():
        return payload

    from plugins.dietcode.lib.tools.broccolidb_tools.agent_rpc import run_agent_rpc

    connections = list(payload.get("connections") or [])
    risks = list(payload.get("risks") or [])
    evidence = list(payload.get("evidence") or [])
    seen_conn = {f"{c.get('path')}:{c.get('reason')}" for c in connections if isinstance(c, dict)}

    try:
        raw = run_agent_rpc(
            "get_context_graph",
            {"path": semantic_path, "limit": max_files},
            flush=False,
        )
        data = json.loads(raw)
        if data.get("success"):
            added = 0
            for item in data.get("connections") or []:
                if not isinstance(item, dict):
                    continue
                p = str(item.get("path") or "")
                weight = float(item.get("weight") or 0)
                reason = f"Often changes with the starting point (weight {weight})"
                key = f"{p}:{reason}"
                if key in seen_conn:
                    continue
                seen_conn.add(key)
                connections.append({
                    "path": p,
                    "reason": reason,
                    "weight": min(0.95, 0.4 + weight * 0.05),
                    "category": "often_changes_with",
                })
                added += 1
            if added:
                evidence.append({
                    "type": "broccolidb",
                    "description": f"Added {added} semantic/co-change connection(s).",
                })
    except Exception:
        pass

    try:
        raw = run_agent_rpc("detect_chokepoints", {"limit": min(5, max_files)}, flush=False)
        data = json.loads(raw)
        if data.get("success"):
            for choke in data.get("chokepoints") or []:
                if not isinstance(choke, dict):
                    continue
                cp = str(choke.get("path") or "")
                if not cp or not _disk_path_exists(cp):
                    continue
                score = float(choke.get("score") or 0)
                churn = float(choke.get("churn") or score)
                risks.append({
                    "path": cp,
                    "level": "high" if score > 10 else "warning",
                    "reason": f"Often changes across recent snapshots (churn {int(churn)}).",
                    "mitigation": "Verify whether this churny area is in scope before expanding the plan.",
                })
            evidence.append({
                "type": "broccolidb",
                "description": f"Checked {len(data.get('chokepoints') or [])} recent change chokepoint(s).",
            })
    except Exception:
        pass

    payload["connections"] = sorted(
        connections,
        key=lambda c: float((c or {}).get("weight") or 0),
        reverse=True,
    )[:max_files]
    payload["risks"] = risks[:max_files]
    if evidence:
        payload["evidence"] = evidence[:12]
    return payload


def project_map(
    path: str = "",
    symbol: str = "",
    query: str = "",
    maxFiles: int = 12,
    includeEvidence: bool = True,
    **_: Any,
) -> str:
    """Build a structural project map for planning before broad exploration."""
    if not (path or symbol or query):
        return tool_error("Provide at least one of: path, symbol, or query")

    max_files = max(3, min(30, int(maxFiles or 12)))
    params = {
        "path": (path or "").strip(),
        "symbol": (symbol or "").strip(),
        "query": (query or "").strip(),
        "maxFiles": max_files,
        "includeEvidence": includeEvidence,
    }
    body = f"""\
    const params = {json.dumps(params)};
    const {{ buildProjectMap }} = await import('./infrastructure/hermes/project_map.js');
    const result = await buildProjectMap(cwd, params);
    console.log(JSON.stringify(result));
"""
    raw = run_standalone_script(body, timeout=_BOOTSTRAP_TIMEOUT)
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and parsed.get("success") is False:
            return tool_error(str(parsed.get("error") or "project_map failed"))
        if isinstance(parsed, dict) and parsed.get("success"):
            enriched = _enrich_map(parsed, path=params["path"], max_files=max_files)
            return json.dumps(enriched, ensure_ascii=False)
    except json.JSONDecodeError:
        pass
    return raw


registry.register(
    name="project_map",
    toolset="broccolidb",
    schema={
        "name": "project_map",
        "description": (
            "Build a Project Map for planning. Use before broad grep/read exploration to identify "
            "starting files, connected files, risk areas, targeted fact-check searches/reads, "
            "confidence, and safe/recommended/refactor choices. Spider + BroccoliDB when available."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Plain-language task or feature description when no exact file/symbol is known",
                },
                "path": {
                    "type": "string",
                    "description": "Known file path as the structural starting point",
                },
                "symbol": {
                    "type": "string",
                    "description": "Function, class, type, or exported symbol to locate",
                },
                "maxFiles": {
                    "type": "integer",
                    "description": "Max files per section (default 12, cap 30)",
                },
                "includeEvidence": {
                    "type": "boolean",
                    "description": "Include evidence list for map provenance (default true)",
                },
            },
        },
    },
    handler=lambda args, **kw: project_map(
        path=args.get("path", ""),
        symbol=args.get("symbol", ""),
        query=args.get("query", ""),
        maxFiles=int(args.get("maxFiles") or 12),
        includeEvidence=args.get("includeEvidence", True) is not False,
    ),
    check_fn=check_requirements,
    emoji="🗺️",
)
