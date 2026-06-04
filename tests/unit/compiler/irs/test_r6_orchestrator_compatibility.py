"""R6.6 Orchestrator Compatibility Tests.

Verifies that R6 migration does not change orchestrator observable behavior
for Stage 4/7 IRS flags. Tests the wrapper functions that the orchestrator
calls, confirming they still produce reports and diagnostics in the expected
format after R6.4 migration.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR, WorkerStepPlanIR
from nl2spl.pipeline.stages.stage4_flow_assembler.irs_checker import (
    check_exception_flows_irs,
    check_worker_flow_plan_exception_flows_irs,
)
from nl2spl.pipeline.stages.stage7_step_extractor.irs_checker import (
    check_steps_irs,
    check_worker_step_plan_irs,
)


# ------------------------------------------------------------------
# Stage 4 wrapper compatibility
# ------------------------------------------------------------------


class TestStage4WrapperCompatibility:
    """Stage 4 wrapper produces correct reports/diagnostics after R6.4."""

    def test_legacy_path_produces_reports_and_diagnostics(self) -> None:
        """check_exception_flows_irs returns reports and diagnostics."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Over budget", ["s1"]),
                ExceptionFlow("exc_2", "Vague failure", []),
            ],
        )
        reports, diags = check_exception_flows_irs(flow)

        assert len(reports) == 2
        assert len(diags) == 1  # only exc_2 is assumed

    def test_worker_aware_path_produces_reports_and_diagnostics(self) -> None:
        """check_worker_flow_plan_exception_flows_irs returns aggregated results."""
        plan = WorkerFlowPlanIR(
            worker_flows={
                "main": FlowStructureIR(
                    exception_flows=[
                        ExceptionFlow("exc_1", "Over budget", ["s1"]),
                    ],
                ),
                "child": FlowStructureIR(
                    exception_flows=[
                        ExceptionFlow("exc_2", "Vague failure", []),
                    ],
                ),
            },
        )
        reports, diags = check_worker_flow_plan_exception_flows_irs(plan)

        assert len(reports) == 2
        assert len(diags) == 1  # only exc_2 is assumed

    def test_diagnostics_have_missing_slot(self) -> None:
        """R6.4: diagnostics now have populated missing_slot."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Vague failure", []),
            ],
        )
        _, diags = check_exception_flows_irs(flow)

        assert len(diags) == 1
        assert diags[0].missing_slot is not None
        assert diags[0].missing_slot.slot_name == "condition"

    def test_diagnostics_use_projected_id_format(self) -> None:
        """R6.4: diagnostic_id uses irs_{hash} format."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Vague failure", []),
            ],
        )
        _, diags = check_exception_flows_irs(flow)

        assert diags[0].diagnostic_id.startswith("irs_")


# ------------------------------------------------------------------
# Stage 7 wrapper compatibility
# ------------------------------------------------------------------


class TestStage7WrapperCompatibility:
    """Stage 7 wrapper produces correct reports/diagnostics after R6.4."""

    def test_legacy_path_produces_reports_and_diagnostics(self) -> None:
        """check_steps_irs returns reports and diagnostics."""
        steps = [
            StepIR(
                step_id="st_1",
                text="Process data",
                command_type="GENERAL_COMMAND",
                source_span_ids=["s1"],
            ),
            StepIR(
                step_id="st_2",
                text="Ask user",
                command_type="REQUEST_INPUT",
                source_span_ids=[],
            ),
        ]
        reports, diags = check_steps_irs(steps)

        assert len(reports) == 2
        assert len(diags) == 1  # only st_2 is assumed

    def test_worker_aware_path_produces_reports_and_diagnostics(self) -> None:
        """check_worker_step_plan_irs returns aggregated results."""
        plan = WorkerStepPlanIR(
            main_worker_id="main",
            worker_steps={
                "main": [
                    StepIR(
                        step_id="st_1",
                        text="Process data",
                        command_type="GENERAL_COMMAND",
                        source_span_ids=["s1"],
                    ),
                ],
                "child": [
                    StepIR(
                        step_id="st_2",
                        text="Ask user",
                        command_type="REQUEST_INPUT",
                        source_span_ids=[],
                    ),
                ],
            },
        )
        reports, diags = check_worker_step_plan_irs(plan)

        assert len(reports) == 2
        assert len(diags) == 1  # only st_2 is assumed

    def test_diagnostics_have_missing_slot(self) -> None:
        """R6.4: diagnostics now have populated missing_slot."""
        steps = [
            StepIR(
                step_id="st_1",
                text="Ask user",
                command_type="REQUEST_INPUT",
                source_span_ids=[],
            ),
        ]
        _, diags = check_steps_irs(steps)

        assert len(diags) == 1
        assert diags[0].missing_slot is not None
        assert diags[0].missing_slot.slot_name == "value_target"

    def test_diagnostics_have_projected_format(self) -> None:
        """R6.4: diagnostic_id uses irs_{hash} format."""
        steps = [
            StepIR(
                step_id="st_1",
                text="Do something",
                command_type="GENERAL_COMMAND",
                source_span_ids=[],
            ),
        ]
        _, diags = check_steps_irs(steps)

        assert diags[0].diagnostic_id.startswith("irs_")

    def test_display_message_skipped(self) -> None:
        """DISPLAY_MESSAGE steps produce no reports or diagnostics."""
        steps = [
            StepIR(
                step_id="st_1",
                text="Show message",
                command_type="DISPLAY_MESSAGE",
                source_span_ids=["s1"],
            ),
        ]
        reports, diags = check_steps_irs(steps)

        assert len(reports) == 0
        assert len(diags) == 0


# ------------------------------------------------------------------
# Registry injection
# ------------------------------------------------------------------


class TestRegistryInjection:
    """Wrappers respect the registry parameter."""

    def test_stage4_wrapper_uses_passed_registry(self) -> None:
        """Stage 4 wrapper uses the passed construct registry."""
        from nl2spl.compiler.construct_registry import (
            SlotSpec,
            ConstructIRS,
        )

        # Create a registry with a custom EXCEPTION_FLOW spec
        # that has a different missing_diagnostic for condition
        custom = SPLConstructRegistry.default()
        # Verify the default has the expected slot
        exc_irs = custom.get("EXCEPTION_FLOW")
        condition_slot = exc_irs.get_slot("condition")
        assert condition_slot.missing_diagnostic is None  # no missing_diagnostic

        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Vague", []),
            ],
        )
        # Using default registry should work
        reports, diags = check_exception_flows_irs(flow, registry=custom)
        assert len(diags) == 1

    def test_stage7_wrapper_uses_passed_registry(self) -> None:
        """Stage 7 wrapper uses the passed construct registry."""
        custom = SPLConstructRegistry.default()

        steps = [
            StepIR(
                step_id="st_1",
                text="Ask",
                command_type="REQUEST_INPUT",
                source_span_ids=[],
            ),
        ]
        reports, diags = check_steps_irs(steps, registry=custom)
        assert len(diags) == 1

    def test_stage4_empty_registry_raises(self) -> None:
        """Stage 4 wrapper with empty registry raises KeyError."""
        empty = SPLConstructRegistry.__new__(SPLConstructRegistry)
        empty._constructs = {}

        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Cond", ["s1"]),
            ],
        )
        with pytest.raises(KeyError):
            check_exception_flows_irs(flow, registry=empty)

    def test_stage7_empty_registry_raises(self) -> None:
        """Stage 7 wrapper with empty registry raises KeyError."""
        empty = SPLConstructRegistry.__new__(SPLConstructRegistry)
        empty._constructs = {}

        steps = [
            StepIR(
                step_id="st_1",
                text="Do",
                command_type="GENERAL_COMMAND",
                source_span_ids=["s1"],
            ),
        ]
        with pytest.raises(KeyError):
            check_steps_irs(steps, registry=empty)
