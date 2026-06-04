"""R6.1 Baseline Compatibility Audit — lock Stage 4/7 IRS behavior.

These tests document the observable behavior of the Stage 4 and Stage 7
IRS checkers.  After R6.4 migration, diagnostic_id format changed from
diag_stage4_*/diag_stage7_* to irs_{hash}, and missing_slot is now
populated by DiagnosticProjector.
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
# Stage 4 baseline
# ------------------------------------------------------------------


class TestR6Stage4Baseline:
    """Lock Stage 4 EXCEPTION_FLOW IRS observable behavior."""

    def test_stage4_condition_satisfied_report_fields(self) -> None:
        """Condition with text + spans → partial, renderable, no diagnostic."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe",
                    spans=["s1", "s2"],
                ),
            ],
        )
        reports, diags = check_exception_flows_irs(flow)

        assert len(reports) == 1
        r = reports[0]
        assert r.construct_type == "EXCEPTION_FLOW"
        assert r.completeness == "partial"
        assert r.renderable is True
        assert r.construct_id == "exception_flow:exc_1"
        assert len(diags) == 0

        # Slot states
        condition_slot = next(s for s in r.slots if s.slot_name == "condition")
        assert condition_slot.status == "satisfied"
        assert condition_slot.source_span_ids == ["s1", "s2"]

        handler_slot = next(s for s in r.slots if s.slot_name == "handler_action")
        assert handler_slot.status == "not_applicable"

        trigger_slot = next(s for s in r.slots if s.slot_name == "trigger_step")
        assert trigger_slot.status == "not_applicable"

    def test_stage4_condition_assumed_diagnostic_fields(self) -> None:
        """Condition with text but no spans → assumed, diagnostic emitted."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe",
                    spans=[],
                ),
            ],
        )
        reports, diags = check_exception_flows_irs(flow)

        assert len(reports) == 1
        r = reports[0]
        assert r.renderable is False
        assert r.completeness == "partial"

        # Diagnostic
        assert len(diags) == 1
        d = diags[0]
        assert d.kind == "type_or_contract_ambiguity"
        assert d.severity == "warning"
        assert d.blocks_rendering is True
        assert d.blocks_completion is True
        assert d.target_ref == "exception_flow:exc_1"
        assert d.source_span_ids == []

        # R6.4: missing_slot is now populated by DiagnosticProjector
        assert d.missing_slot is not None
        assert d.missing_slot.slot_name == "condition"

        # Condition slot
        condition_slot = next(s for s in r.slots if s.slot_name == "condition")
        assert condition_slot.status == "assumed"
        assert condition_slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_stage4_handler_action_always_not_applicable(self) -> None:
        """handler_action is never checked at Stage 4."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe",
                    spans=["s1"],
                ),
            ],
        )
        reports, diags = check_exception_flows_irs(flow)

        handler_slot = next(s for s in reports[0].slots if s.slot_name == "handler_action")
        assert handler_slot.status == "not_applicable"

        # No missing_handler diagnostic
        assert all(d.kind != "missing_handler" for d in diags)

    def test_stage4_condition_satisfied_slot_has_source_spans(self) -> None:
        """Condition slot source_span_ids come from ExceptionFlow.spans."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe",
                    spans=["s3", "s4"],
                ),
            ],
        )
        reports, diags = check_exception_flows_irs(flow)
        condition_slot = next(s for s in reports[0].slots if s.slot_name == "condition")
        assert condition_slot.source_span_ids == ["s3", "s4"]
        assert len(diags) == 0

    def test_stage4_diagnostic_id_is_deterministic(self) -> None:
        """Diagnostic ID is deterministic (same input → same ID)."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe",
                    spans=[],
                ),
            ],
        )
        _, diags1 = check_exception_flows_irs(flow, worker_id="worker_main")
        _, diags2 = check_exception_flows_irs(flow, worker_id="worker_main")
        assert diags1[0].diagnostic_id == diags2[0].diagnostic_id
        # R6.4: ID format is irs_{hash}
        assert diags1[0].diagnostic_id.startswith("irs_")

    def test_stage4_worker_scoped_target_ref_format(self) -> None:
        """Worker-scoped target_ref = worker:{worker_id}.exception_flow:{flow_id}."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe",
                    spans=[],
                ),
            ],
        )
        reports, diags = check_exception_flows_irs(flow, worker_id="child_review")
        assert reports[0].construct_id == "worker:child_review.exception_flow:exc_1"
        assert diags[0].target_ref == "worker:child_review.exception_flow:exc_1"


# ------------------------------------------------------------------
# Stage 7 baseline
# ------------------------------------------------------------------


class TestR6Stage7Baseline:
    """Lock Stage 7 step-level IRS observable behavior."""

    def _make_step(
        self,
        step_id: str = "st_1",
        command_type: str = "GENERAL_COMMAND",
        text: str = "Do something",
        source_span_ids: list[str] | None = None,
        integration_ref: str | None = None,
        handoff_id: str | None = None,
        inputs: list[str] | None = None,
        outputs: list[str] | None = None,
    ) -> StepIR:
        return StepIR(
            step_id=step_id,
            text=text,
            command_type=command_type,
            source_span_ids=source_span_ids if source_span_ids is not None else [],
            integration_ref=integration_ref,
            handoff_id=handoff_id,
            inputs=inputs or [],
            outputs=outputs or [],
        )

    def test_stage7_general_command_assumed_diagnostic(self) -> None:
        """GENERAL_COMMAND without source → assumed_command_not_renderable."""
        step = self._make_step(source_span_ids=[])
        reports, diags = check_steps_irs([step])

        assert len(reports) == 1
        r = reports[0]
        assert r.construct_type == "GENERAL_COMMAND"
        assert r.renderable is False
        assert r.completeness == "partial"
        assert r.construct_id == "step:st_1"

        assert len(diags) == 1
        d = diags[0]
        assert d.kind == "assumed_command_not_renderable"
        assert d.blocks_rendering is True
        assert d.blocks_completion is True
        assert d.target_ref == "step:st_1"

        # R6.4: missing_slot is now populated
        assert d.missing_slot is not None
        assert d.missing_slot.slot_name == "source_evidence"

        source_slot = next(s for s in r.slots if s.slot_name == "source_evidence")
        assert source_slot.status == "missing"

    def test_stage7_general_command_satisfied(self) -> None:
        """GENERAL_COMMAND with source → complete, renderable, no diagnostic."""
        step = self._make_step(source_span_ids=["s1"])
        reports, diags = check_steps_irs([step])

        assert len(reports) == 1
        r = reports[0]
        assert r.renderable is True
        assert r.completeness == "complete"
        assert len(diags) == 0

    def test_stage7_request_input_no_source(self) -> None:
        """REQUEST_INPUT without source → type_or_contract_ambiguity."""
        step = self._make_step(
            command_type="REQUEST_INPUT",
            source_span_ids=[],
        )
        reports, diags = check_steps_irs([step])

        assert len(diags) == 1
        d = diags[0]
        assert d.kind == "type_or_contract_ambiguity"
        assert d.blocks_rendering is True
        assert d.target_ref == "step:st_1"

        # R6.4: missing_slot is now populated
        assert d.missing_slot is not None
        assert d.missing_slot.slot_name == "value_target"

        value_slot = next(s for s in reports[0].slots if s.slot_name == "value_target")
        assert value_slot.status == "missing"

    def test_stage7_call_api_missing_integration_ref(self) -> None:
        """CALL_API without integration_ref → type_or_contract_ambiguity."""
        step = self._make_step(
            command_type="CALL_API",
            source_span_ids=["s1"],
            integration_ref=None,
        )
        reports, diags = check_steps_irs([step])

        # R6.4: filter by missing_slot.slot_name instead of diagnostic_id
        api_diags = [d for d in diags
                     if d.missing_slot and d.missing_slot.slot_name == "api_name"]
        assert len(api_diags) == 1
        assert api_diags[0].kind == "type_or_contract_ambiguity"

    def test_stage7_call_api_missing_source(self) -> None:
        """CALL_API without source_span_ids → type_or_contract_ambiguity."""
        step = self._make_step(
            command_type="CALL_API",
            source_span_ids=[],
            integration_ref="payment_api",
        )
        reports, diags = check_steps_irs([step])

        # R6.4: filter by missing_slot.slot_name instead of diagnostic_id
        call_diags = [d for d in diags
                      if d.missing_slot and d.missing_slot.slot_name == "call_action"]
        assert len(call_diags) == 1
        assert call_diags[0].kind == "type_or_contract_ambiguity"

    def test_stage7_invoke_worker_missing_handoff_id(self) -> None:
        """INVOKE_WORKER without handoff_id → type_or_contract_ambiguity."""
        step = self._make_step(
            command_type="INVOKE_WORKER",
            source_span_ids=["s1"],
            integration_ref="child_worker",
            handoff_id=None,
        )
        reports, diags = check_steps_irs([step])

        # R6.4: filter by missing_slot.slot_name instead of diagnostic_id
        handoff_diags = [d for d in diags
                         if d.missing_slot and d.missing_slot.slot_name == "handoff_id"]
        assert len(handoff_diags) == 1
        assert handoff_diags[0].kind == "type_or_contract_ambiguity"

    def test_stage7_diagnostic_id_is_deterministic(self) -> None:
        """Diagnostic ID is deterministic (same input → same ID)."""
        step = self._make_step(
            command_type="GENERAL_COMMAND",
            source_span_ids=[],
        )
        _, diags1 = check_steps_irs([step], worker_id="worker_main")
        _, diags2 = check_steps_irs([step], worker_id="worker_main")
        assert diags1[0].diagnostic_id == diags2[0].diagnostic_id
        # R6.4: ID format is irs_{hash}
        assert diags1[0].diagnostic_id.startswith("irs_")

    def test_stage7_display_message_skipped(self) -> None:
        """DISPLAY_MESSAGE steps produce no reports or diagnostics."""
        step = self._make_step(
            command_type="DISPLAY_MESSAGE",
            source_span_ids=["s1"],
        )
        reports, diags = check_steps_irs([step])
        assert len(reports) == 0
        assert len(diags) == 0


# ------------------------------------------------------------------
# Diagnostic format contract (R6.4 updated)
# ------------------------------------------------------------------


class TestR6DiagnosticFormatContract:
    """Lock the diagnostic format produced by v6 checkers via DiagnosticProjector.

    After R6.4 migration, missing_slot is populated and diagnostic_id
    uses irs_{hash} format.
    """

    def test_stage4_diagnostic_has_missing_slot(self) -> None:
        """R6.4: Stage 4 diagnostic has populated missing_slot."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe",
                    spans=[],
                ),
            ],
        )
        _, diags = check_exception_flows_irs(flow)
        assert diags[0].missing_slot is not None
        assert diags[0].missing_slot.slot_name == "condition"

    def test_stage7_diagnostic_has_missing_slot(self) -> None:
        """R6.4: Stage 7 diagnostic has populated missing_slot."""
        step = StepIR(
            step_id="st_1",
            text="Ask user",
            command_type="REQUEST_INPUT",
            source_span_ids=[],
        )
        _, diags = check_steps_irs([step])
        assert diags[0].missing_slot is not None
        assert diags[0].missing_slot.slot_name == "value_target"
