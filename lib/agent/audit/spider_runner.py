"""Spider gate runner — Hermes RPC with AgentContext fallback."""
from __future__ import annotations

import json
from typing import Any


def run_spider_gate(*, scope: str = "changed-files") -> dict[str, Any]:
    """Run BroccoliDB Spider gate; return normalized result dict."""
    from plugins.dietcode.lib.tools.broccolidb_tools.agent_rpc import run_agent_rpc

    raw = run_agent_rpc("spider_gate", {"scope": scope}, flush=False)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"success": False, "error": raw, "blocked": True, "exitCode": 1}
    if not isinstance(data, dict):
        return {"success": False, "error": "invalid spider_gate response", "blocked": True, "exitCode": 1}
    blocked = bool(data.get("blocked"))
    finding_count = int(data.get("findingCount") or data.get("violationCount") or 0)
    quality = "PASSED"
    if blocked or data.get("exitCode") == 1:
        quality = "FAILED"
    elif finding_count > 0:
        quality = "WARNING"
    return {
        "success": bool(data.get("success", True)),
        "blocked": blocked,
        "exitCode": int(data.get("exitCode") or (1 if blocked else 0)),
        "conclusion": data.get("conclusion"),
        "findingCount": finding_count,
        "qualityGate": quality,
        "findings": data.get("findings") or [],
    }
