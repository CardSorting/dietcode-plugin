"""Checkpoint freshness — detect stale steering surface vs project activity."""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional


def _parse_checkpoint_date(raw: Optional[str]) -> Optional[date]:
    if not raw:
        return None
    try:
        return datetime.strptime(raw.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def assess_checkpoint_freshness(
    *,
    recent_checkpoint_date: Optional[str],
    git_commits: list[str],
    schema_valid: Optional[bool] = None,
    stale_days: int = 7,
) -> dict[str, Any]:
    """Return staleness signals for operator ergonomics."""
    checkpoint = _parse_checkpoint_date(recent_checkpoint_date)
    today = datetime.now(timezone.utc).date()
    git_activity = len(git_commits or [])

    if not checkpoint:
        return {
            "stale": True,
            "reason": "no_recent_checkpoint_date",
            "summary": "ROADMAP.md has no parsed Recent Checkpoint date — steering may be outdated.",
            "days_since_checkpoint": None,
            "git_commits_since_checkpoint": git_activity,
            "recommended_action": "roadmap(action='checkpoint', context='refresh checkpoint')",
        }

    days_since = (today - checkpoint).days
    stale = False
    reason = "fresh"
    summary = f"Last checkpoint {recent_checkpoint_date} ({days_since}d ago)."

    if schema_valid is False:
        stale = True
        reason = "schema_invalid"
        summary = "ROADMAP.md failed schema validation — checkpoint pass incomplete."
    elif days_since > stale_days and git_activity >= 3:
        stale = True
        reason = "checkpoint_older_than_git_activity"
        summary = (
            f"Checkpoint is {days_since}d old with {git_activity} recent git commits — "
            "roadmap may not reflect current direction."
        )
    elif days_since > stale_days * 2:
        stale = True
        reason = "checkpoint_expired"
        summary = f"Checkpoint is {days_since}d old — schedule a roadmap refresh."

    return {
        "stale": stale,
        "reason": reason,
        "summary": summary,
        "days_since_checkpoint": days_since,
        "git_commits_since_checkpoint": git_activity,
        "recommended_action": (
            "roadmap(action='checkpoint', context='stale refresh')"
            if stale
            else "roadmap(action='guide')"
        ),
        "checkpoint_date": recent_checkpoint_date,
    }


def format_explain_stale_report(freshness: dict[str, Any]) -> str:
    lines = [
        "🗺️ Roadmap checkpoint freshness",
        f"Stale: {freshness.get('stale')}",
        f"Reason: {freshness.get('reason')}",
        freshness.get("summary") or "",
    ]
    if freshness.get("days_since_checkpoint") is not None:
        lines.append(f"Days since checkpoint: {freshness['days_since_checkpoint']}")
    lines.append(f"Recent git commits in evidence window: {freshness.get('git_commits_since_checkpoint')}")
    lines.append(f"Next: {freshness.get('recommended_action')}")
    return "\n".join(lines)
