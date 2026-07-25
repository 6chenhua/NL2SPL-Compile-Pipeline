"""R6.5 Factory and Runner-level tests for Stage 4/7 checkers.

Tests that the factory correctly registers Stage4ExceptionFlowIRSChecker
and Stage7StepIRSChecker, and that the runner can execute them.
"""

from __future__ import annotations

from nl2spl.compiler.irs import (
    IRSCheckContext,
    build_irs_checker_registry,
    build_irs_runner,
)
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.step_ir import StepIR

# ------------------------------------------------------------------
# Factory registration
# ------------------------------------------------------------------


class TestFactoryRegistration:
    """Checker registration via factory."""

    def test_enable_exception_flow_registers_checker(self) -> None:
        """enable_exception_flow=True registers Stage4ExceptionFlowIRSChecker."""
        registry = build_irs_checker_registry(enable_exception_flow=True)
        checkers = registry.get_for_stage("stage4")
        assert len(checkers) == 1
        assert checkers[0].checker_id == "stage4_exception_flow"

    def test_enable_step_registers_checker(self) -> None:
        """enable_step=True registers Stage7StepIRSChecker."""
        registry = build_irs_checker_registry(enable_step=True)
        checkers = registry.get_for_stage("stage7")
        assert len(checkers) == 1
        assert checkers[0].checker_id == "stage7_step"

    def test_default_registry_empty_for_stage4(self) -> None:
        """Default registry has no checker for stage4."""
        registry = build_irs_checker_registry()
        assert registry.get_for_stage("stage4") == []

    def test_default_registry_empty_for_stage7(self) -> None:
        """Default registry has no checker for stage7."""
        registry = build_irs_checker_registry()
        assert registry.get_for_stage("stage7") == []


# ------------------------------------------------------------------
# Runner integration
# ------------------------------------------------------------------


class TestRunnerIntegration:
    """Runner can execute Stage 4/7 checkers."""

    def test_runner_can_run_stage4(self) -> None:
        """Runner with exception_flow checker can run stage4 context."""
        runner = build_irs_runner(enable_exception_flow=True)
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Missing timeframe", ["s1"]),
            ],
        )
        context = IRSCheckContext(stage_name="stage4", flow=flow)
        result = runner.run_stage("stage4", context)

        assert len(result.reports) == 1
        assert result.reports[0].construct_type == "EXCEPTION_FLOW"

    def test_runner_can_run_stage7(self) -> None:
        """Runner with step checker can run stage7 context."""
        runner = build_irs_runner(enable_step=True)
        step = StepIR(
            step_id="st_1",
            text="Do something",
            command_type="GENERAL_COMMAND",
            source_span_ids=["s1"],
        )
        context = IRSCheckContext(stage_name="stage7", steps=(step,))
        result = runner.run_stage("stage7", context)

        assert len(result.reports) == 1
        assert result.reports[0].construct_type == "GENERAL_COMMAND"

    def test_runner_stage4_produces_diagnostics(self) -> None:
        """Runner produces diagnostics for assumed exception flow condition."""
        runner = build_irs_runner(enable_exception_flow=True)
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Missing timeframe", []),
            ],
        )
        context = IRSCheckContext(stage_name="stage4", flow=flow)
        result = runner.run_stage("stage4", context)

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].kind == "type_or_contract_ambiguity"

    def test_runner_stage7_produces_diagnostics(self) -> None:
        """Runner produces diagnostics for assumed step."""
        runner = build_irs_runner(enable_step=True)
        step = StepIR(
            step_id="st_1",
            text="Do something",
            command_type="GENERAL_COMMAND",
            source_span_ids=[],
        )
        context = IRSCheckContext(stage_name="stage7", steps=(step,))
        result = runner.run_stage("stage7", context)

        assert len(result.diagnostics) == 1
        assert result.diagnostics[0].kind == "assumed_command_not_renderable"


# ------------------------------------------------------------------
# Combined registration
# ------------------------------------------------------------------


class TestCombinedRegistration:
    """Multiple checkers registered together."""

    def test_all_checkers_registered(self) -> None:
        """All three flags register checkers for their stages."""
        registry = build_irs_checker_registry(
            enable_worker_delegation=True,
            enable_exception_flow=True,
            enable_step=True,
        )
        assert len(registry.get_for_stage("stage3_5")) == 1
        assert len(registry.get_for_stage("stage4")) == 1
        assert len(registry.get_for_stage("stage7")) == 1

    def test_worker_delegation_not_regressed(self) -> None:
        """enable_worker_delegation still works after R6 changes."""
        registry = build_irs_checker_registry(enable_worker_delegation=True)
        checkers = registry.get_for_stage("stage3_5")
        assert len(checkers) == 1
        assert checkers[0].checker_id == "worker_delegation"
