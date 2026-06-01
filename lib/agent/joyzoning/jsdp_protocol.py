"""JSDP protocol constants — mutation provider vocabulary (not habitat authority)."""
from __future__ import annotations

from typing import Any

PROTOCOL_ID = "JSDP"
PROTOCOL_NAME = "JoyZoning Sequential Delivery Protocol"

REQUIRED_OUTPUT_SECTIONS = (
    "Goal",
    "Scope",
    "Planned Changes",
    "Risks",
    "Deliverables",
    "Completion Criteria",
    "Follow-Up Notes",
)

GLOBAL_HANDOFF_RULES = (
    "Sequential execution only — one role per session; do not solve future roles.",
    "Shared canonical workspace — extend accepted work; do not fork competing architectures.",
    "Mandatory convergence gate — stop at ReadyForReview; operator accept-merge before next role.",
    "Preserve prior accepted intent — log improvements as Follow-Up Notes, do not implement now.",
    "Prevent concept drift — respect product lock and architecture lock from upstream roles.",
    "Local reasoning only — complete this role's scope; avoid architecture astronautics.",
    "Stable boring systems — prefer modification over reinvention; minimize surface area.",
)

CONVERGENCE_REQUIRED_CODE = "jsdp_convergence_required"

ROLLING_HORIZON_RULES = (
    "Never auto-plan the whole project — propose at most 3–5 nodes per cycle.",
    "Use jsdp_horizon(action='export') before validate/import; bounded horizon-context.json only.",
    "Do not export full spec, repo scan, or ledger — JoyZoning harness enforces byte budget.",
    "validate → diff → import --dry-run → import; harness allocates new node IDs append-only.",
    "After verify/continue, re-export horizon context before the next planning cycle.",
    "Do not import horizon over active verification failures unless force=True.",
    "Prefer incremental nodes anchored to verified/ready frontier — no full-project rewrite language.",
)

ROLLING_HORIZON_TOOL = "jsdp"


def validate_handoff_sections(text: str) -> dict[str, Any]:
    """Check that a handoff/deliverable contains required JSDP sections."""
    missing = []
    found = []
    lower = text.lower()
    for section in REQUIRED_OUTPUT_SECTIONS:
        markers = (f"## {section.lower()}", f"**{section.lower()}**", f"{section.lower()}:")
        if any(m in lower for m in markers):
            found.append(section)
        else:
            missing.append(section)
    return {
        "success": len(missing) == 0,
        "protocol_id": PROTOCOL_ID,
        "found_sections": found,
        "missing_sections": missing,
        "required_sections": list(REQUIRED_OUTPUT_SECTIONS),
    }


def rolling_horizon_prompt() -> str:
    rules = "\n".join(f"- {r}" for r in ROLLING_HORIZON_RULES)
    return (
        f"### JSDP rolling horizon (tool: `{ROLLING_HORIZON_TOOL}`)\n\n"
        f"{rules}\n\n"
        "Cycle: export → prompt → write horizon.json → validate → diff → "
        "import --dry-run → import → next → verify → continue → export again."
    )


def role_context_prompt(role: str, chain_id: str = "") -> str:
    rules = "\n".join(f"- {r}" for r in GLOBAL_HANDOFF_RULES)
    sections = "\n".join(f"- **{s}**" for s in REQUIRED_OUTPUT_SECTIONS)
    chain_line = f"Chain: `{chain_id}`\n" if chain_id else ""
    return (
        f"### {PROTOCOL_ID} bounded role session\n"
        f"{chain_line}"
        f"Role: `{role}`\n\n"
        f"Global rules:\n{rules}\n\n"
        f"Required output sections:\n{sections}\n\n"
        "Stop at ReadyForReview — use `convergence_request_review` before `kanban_complete`."
    )
