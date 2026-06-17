"""Quality audit gate — SonarQube-style completion enforcement for Hermes."""

__all__ = (
    "CompletionGateDecision",
    "build_gate_block_message",
    "evaluate_completion_gate",
    "explain_quality_gate",
    "get_completion_gate_config",
    "kanban_complete_allowed",
    "record_governance_block",
    "record_tool_quality_result",
)


def __getattr__(name: str):
    if name == "CompletionGateDecision":
        from plugins.dietcode.lib.agent.audit.completion_gate import CompletionGateDecision

        return CompletionGateDecision
    if name in ("build_gate_block_message", "evaluate_completion_gate"):
        from plugins.dietcode.lib.agent.audit import completion_gate as mod

        return getattr(mod, name)
    if name == "get_completion_gate_config":
        from plugins.dietcode.lib.agent.audit.config import get_completion_gate_config

        return get_completion_gate_config
    if name in (
        "explain_quality_gate",
        "kanban_complete_allowed",
        "record_governance_block",
        "record_tool_quality_result",
    ):
        from plugins.dietcode.lib.agent.audit import quality_gate as mod

        return getattr(mod, name)
    raise AttributeError(name)
