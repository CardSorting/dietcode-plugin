"""Workspace snapshot — single-pass evidence, validation, and gate for operator surfaces."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

EvidenceTier = Literal["light", "standard", "full"]

_CACHE: dict[str, tuple[float, float, str, "WorkspaceSnapshot"]] = {}
_TIER_RANK = {"light": 0, "standard": 1, "full": 2}


@dataclass
class WorkspaceSnapshot:
    workspace: str
    roadmap_path: str
    roadmap_mtime: float
    roadmap_text: str
    evidence: dict[str, Any]
    validation: Any = None
    gate_inputs: dict[str, Any] = field(default_factory=dict)
    gate_state: dict[str, Any] = field(default_factory=dict)

    def validation_dict(self) -> Optional[dict[str, Any]]:
        if self.validation is None:
            return None
        return self.validation.to_dict()


def invalidate_snapshot(workspace: str | Path) -> None:
    """Drop cached snapshot after ROADMAP.md mutation or validate."""
    prefix = str(Path(workspace).expanduser().resolve()) + ":"
    for cache_key in list(_CACHE):
        if cache_key.startswith(prefix):
            _CACHE.pop(cache_key, None)
    try:
        from plugins.dietcode.lib.agent.roadmap.evidence import invalidate_doc_cache, invalidate_git_cache
        from plugins.dietcode.lib.agent.roadmap.roadmap_core import invalidate_roadmap_core
        from plugins.dietcode.lib.agent.roadmap.workspace_scan import invalidate_heavy_scan
        from plugins.dietcode.lib.agent.roadmap.workspace_state import invalidate_state_cache

        invalidate_heavy_scan(workspace)
        invalidate_roadmap_core(workspace)
        invalidate_git_cache(workspace)
        invalidate_doc_cache(workspace)
        invalidate_state_cache(workspace)
    except Exception:
        pass


def _roadmap_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime if path.is_file() else 0.0
    except OSError:
        return 0.0


def _workspace_state_token(workspace: Path) -> str:
    from plugins.dietcode.lib.agent.roadmap.workspace_state import read_state

    ws = read_state(workspace)
    return str(ws.get("updated_at") or "")


def _cache_ttl() -> float:
    from plugins.dietcode.lib.agent.roadmap.config import get_roadmap_config

    return float(get_roadmap_config().evidence_cache_ttl_seconds)


def _try_promote_snapshot(
    root: Path,
    *,
    tier: EvidenceTier,
    mtime: float,
    ws_token: str,
) -> Optional[WorkspaceSnapshot]:
    """Reuse lighter cached snapshot core and only extend evidence tier."""
    target_rank = _TIER_RANK[tier]
    from plugins.dietcode.lib.agent.roadmap.evidence import extend_evidence

    for src_tier in ("standard", "light"):
        if _TIER_RANK[src_tier] >= target_rank:
            continue
        key = f"{root}:{src_tier}"
        cached = _CACHE.get(key)
        if cached is None:
            continue
        cached_at, cached_mtime, cached_ws, base = cached
        if cached_mtime != mtime or cached_ws != ws_token:
            continue
        if (time.monotonic() - cached_at) > _cache_ttl():
            continue

        evidence = extend_evidence(base.evidence, tier=tier)
        return WorkspaceSnapshot(
            workspace=base.workspace,
            roadmap_path=base.roadmap_path,
            roadmap_mtime=base.roadmap_mtime,
            roadmap_text=base.roadmap_text,
            evidence=evidence,
            validation=base.validation,
            gate_inputs=base.gate_inputs,
            gate_state=base.gate_state,
        )
    return None


def get_workspace_snapshot(
    workspace: str | Path,
    *,
    tier: EvidenceTier = "standard",
    force_refresh: bool = False,
    include_gate: bool = True,
) -> WorkspaceSnapshot:
    """Return cached or freshly built workspace snapshot (evidence + validation + gate)."""
    from plugins.dietcode.lib.agent.roadmap.config import resolve_workspace_root
    from plugins.dietcode.lib.agent.roadmap.evidence import gather_evidence
    from plugins.dietcode.lib.agent.roadmap.gate import collect_gate_inputs, gate_state_from_inputs
    from plugins.dietcode.lib.agent.roadmap.roadmap_core import read_roadmap_core

    root = Path(resolve_workspace_root(str(workspace) if workspace else None))
    key = f"{root}:{tier}"
    roadmap_path = root / "ROADMAP.md"
    mtime = _roadmap_mtime(roadmap_path)
    ws_token = _workspace_state_token(root)

    if not force_refresh:
        cached = _CACHE.get(key)
        if cached is not None:
            cached_at, cached_mtime, cached_ws, snap = cached
            if (
                cached_mtime == mtime
                and cached_ws == ws_token
                and (time.monotonic() - cached_at) <= _cache_ttl()
            ):
                return snap

        promoted = _try_promote_snapshot(root, tier=tier, mtime=mtime, ws_token=ws_token)
        if promoted is not None:
            _CACHE[key] = (time.monotonic(), mtime, ws_token, promoted)
            return promoted

    core = read_roadmap_core(root)
    evidence = gather_evidence(root, tier=tier, roadmap_text=core.text)
    gate_inputs = collect_gate_inputs(
        workspace=str(root),
        evidence=evidence,
        roadmap_text=core.text,
        validation=core.validation,
    )
    gate_state = gate_state_from_inputs(gate_inputs) if include_gate else {}

    snap = WorkspaceSnapshot(
        workspace=str(root),
        roadmap_path=core.roadmap_path,
        roadmap_mtime=core.mtime,
        roadmap_text=core.text,
        evidence=evidence,
        validation=core.validation,
        gate_inputs=gate_inputs,
        gate_state=gate_state,
    )
    _CACHE[key] = (time.monotonic(), mtime, ws_token, snap)
    return snap
