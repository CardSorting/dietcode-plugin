"""Compact checkpoint payload for agent context — omits heavy evidence blobs."""
from __future__ import annotations

from typing import Any


def is_digest_context(context: str) -> bool:
    ctx = (context or "").strip().lower()
    return ctx in ("digest", "compact") or "digest" in ctx or "compact" in ctx


def slim_checkpoint_payload(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), dict) else None
    roadmap = (evidence or {}).get("roadmap") if isinstance((evidence or {}).get("roadmap"), dict) else {}
    code_soup = (evidence or {}).get("code_soup_audit") if isinstance((evidence or {}).get("code_soup_audit"), dict) else {}
    git = (evidence or {}).get("git") if isinstance((evidence or {}).get("git"), dict) else {}

    slim_evidence: dict[str, Any] | None = None
    if evidence:
        sections_present = roadmap.get("sections_present")
        recent_commits = git.get("recent_commits")
        issues = code_soup.get("issues")
        slim_evidence = {
            "project_fingerprint": evidence.get("project_fingerprint"),
            "project_steering_digest": evidence.get("project_steering_digest"),
            "project_identity_line": evidence.get("project_identity_line"),
            "uncertainty": evidence.get("uncertainty"),
            "roadmap": {
                "exists": roadmap.get("exists"),
                "health_status": roadmap.get("health_status"),
                "code_soup_risk": roadmap.get("code_soup_risk"),
                "sections_missing": roadmap.get("sections_missing"),
                "sections_present_count": len(sections_present) if isinstance(sections_present, list) else None,
                "now_item_count": roadmap.get("now_item_count"),
                "recent_checkpoint_date": roadmap.get("recent_checkpoint_date"),
            },
            "git": {
                "recent_commits_count": len(recent_commits) if isinstance(recent_commits, list) else 0,
                "branch": git.get("branch"),
            },
            "code_soup_audit": {
                "overall_risk": code_soup.get("overall_risk"),
                "issue_count": len(issues) if isinstance(issues, list) else 0,
            },
        }

    fill_plan = payload.get("bootstrap_fill_plan") if isinstance(payload.get("bootstrap_fill_plan"), dict) else None
    slim_fill_plan: dict[str, Any] | None = None
    if fill_plan:
        tasks = fill_plan.get("tasks")
        sample_task = tasks[0] if isinstance(tasks, list) and tasks else None
        slim_fill_plan = {
            "remaining_count": fill_plan.get("remaining_count"),
            "bootstrap_complete": fill_plan.get("bootstrap_complete"),
            "agent_next_call": fill_plan.get("agent_next_call"),
            "task_count": len(tasks) if isinstance(tasks, list) else 0,
            "sample_task": sample_task,
        }

    rest = {
        k: v
        for k, v in payload.items()
        if k
        not in (
            "evidence",
            "existing_roadmap_summary",
            "code_soup_pre_audit",
            "suggested_bootstrap",
        )
    }

    return {
        **rest,
        "context_mode": "digest",
        "evidence": slim_evidence,
        "bootstrap_fill_plan": slim_fill_plan if slim_fill_plan is not None else payload.get("bootstrap_fill_plan"),
        "evidence_digest_note": (
            "Heavy evidence omitted in digest mode — use roadmap(action='evidence') "
            "or checkpoint without context='digest'."
        ),
    }
