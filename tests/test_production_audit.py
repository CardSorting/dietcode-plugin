"""Production hardening audit unit tests."""
from __future__ import annotations

import unittest

from tests.support import bootstrap_plugins_namespace


class ProductionAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bootstrap_plugins_namespace()

    def test_production_hardening_passes(self) -> None:
        from plugins.dietcode.lib.agent.production_audit import run_production_hardening_audit

        result = run_production_hardening_audit()
        self.assertTrue(result["ok"], result.get("failures"))

    def test_self_check_includes_hardening(self) -> None:
        from plugins.dietcode.lib.agent.self_check import run_self_check

        result = run_self_check()
        self.assertTrue(result["ok"], result.get("failures"))
        self.assertIn("production_hardening", result)

    def test_operator_brief_shape(self) -> None:
        from plugins.dietcode.lib.agent.ergonomics import build_operator_brief

        brief = build_operator_brief()
        self.assertIn("agent_next_call", brief)
        self.assertIn("operator_summary", brief)
        self.assertIn("recovery_steps", brief)
        self.assertIn("playbooks", brief)

    def test_recovery_catalog_concrete_commands(self) -> None:
        from plugins.dietcode.lib.agent.recovery_catalog import (
            joyzoning_verify_command,
            kanban_complete_command,
            resolve_kanban_complete_flow,
        )

        cmd = joyzoning_verify_command(mutation_id="mut_abc123")
        self.assertIn("mut_abc123", cmd)
        self.assertNotIn("<", cmd)
        flow = resolve_kanban_complete_flow(ctx={"anchor_scope_id": "task-1", "scope_id": "task-1"})
        self.assertIn("kanban_complete(task_id='task-1')", flow)
        self.assertIn("convergence_mark_converged", flow)
        self.assertEqual(kanban_complete_command(scope_id="task-9"), "kanban_complete(task_id='task-9')")

    def test_response_envelope_attaches_hints(self) -> None:
        from plugins.dietcode.lib.agent.response_envelope import attach_operator_envelope

        with unittest.mock.patch(
            "plugins.dietcode.lib.agent.ergonomics.build_operator_brief",
            return_value={
                "operator_summary": "blocked",
                "agent_next_call": "roadmap(action='explain_gate')",
                "recovery_steps": [{"command": "roadmap(action='explain_gate')", "detail": "x"}],
                "kanban_complete_allowed": False,
            },
        ):
            out = attach_operator_envelope({"success": True})
        self.assertIn("_dietcode_operator_hints", out)
        self.assertEqual(out["agent_next_call"], "roadmap(action='explain_gate')")
        from plugins.dietcode.lib.agent.audit.config import CompletionGateConfig
        from plugins.dietcode.lib.agent.audit.quality_gate import explain_quality_gate

        with unittest.mock.patch(
            "plugins.dietcode.lib.agent.audit.quality_gate.get_completion_gate_config",
            return_value=CompletionGateConfig(enabled=False),
        ):
            payload = explain_quality_gate("scope-test")
        recovery = payload.get("recovery") or []
        self.assertTrue(recovery)
        self.assertIsInstance(recovery[0], dict)
        self.assertIn("command", recovery[0])


if __name__ == "__main__":
    unittest.main()
