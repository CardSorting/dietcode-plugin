"""Gate policy constants — port of src/shared/audit/gatePolicy.ts."""
from __future__ import annotations

from typing import Optional

COMPLETION_GATE_SCORE_THRESHOLD = 50
MAX_COMPLETION_GATE_BLOCK_COUNT = 10
COMPLETION_GATE_WARN_THRESHOLD = 5
COMPLETION_RESULT_MIN_LENGTH = 40

DEFAULT_INTENT_THRESHOLD_ADJUSTMENTS: dict[str, int] = {
    "FIX": 10,
    "TEST": 10,
    "DELETE": 5,
    "INVESTIGATE": 5,
}


def resolve_effective_gate_threshold(
    base_threshold: int,
    intent: Optional[str] = None,
    *,
    intent_adjustments_enabled: bool = True,
) -> int:
    if not intent_adjustments_enabled:
        return base_threshold
    adjustment = DEFAULT_INTENT_THRESHOLD_ADJUSTMENTS.get((intent or "").upper(), 0)
    return max(0, min(100, base_threshold + adjustment))
