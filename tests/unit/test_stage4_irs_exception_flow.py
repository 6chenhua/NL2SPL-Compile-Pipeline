"""Unit tests for Stage 4 IRS exception flow checker."""

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR
from nl2spl.pipeline.stages.stage4_flow_assembler.irs_checker import (
    check_exception_flows_irs,
    check_worker_flow_plan_exception_flows_irs,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_flow(*exc_flows: ExceptionFlow) -> FlowStructureIR:
    return FlowStructureIR(
        main_flow_spans=["s1", "s2"],
        exception_flows=list(exc_flows),
    )


# ---------------------------------------------------------------------------
# No exception flows
# ---------------------------------------------------------------------------

class TestNoExceptionFlows:
    def test_empty_flow_produces_no_reports(self):
        flow = FlowStructureIR(main_flow_spans=["s1"])
        reports, diagnostics = check_exception_flows_irs(flow)
        assert reports == []
        assert diagnostics == []

    def test_no_exception_flows_no_diagnostics(self):
        flow = _make_flow()
        reports, diagnostics = check_exception_flows_irs(flow)
        assert reports == []
        assert diagnostics == []


# ---------------------------------------------------------------------------
# Source-backed condition (spans non-empty)
# ---------------------------------------------------------------------------

class TestSourceBackedCondition:
    def test_condition_satisfied_when_spans_present(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Quoted pricing is over budget",
                spans=["s20"],
            )
        )
        reports, diagnostics = check_exception_flows_irs(flow)

        assert len(reports) == 1
        assert len(diagnostics) == 0

        report = reports[0]
        assert report.construct_id == "exception_flow:exc_1"
        assert report.construct_type == "EXCEPTION_FLOW"
        assert report.completeness == "partial"
        assert report.renderable is True

        cond = _find_slot(report, "condition")
        assert cond.status == "satisfied"
        assert cond.relation == "direct"
        assert cond.source_span_ids == ["s20"]

    def test_condition_satisfied_multiple_spans(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Non-compliance detected",
                spans=["s21", "s22"],
            )
        )
        reports, diagnostics = check_exception_flows_irs(flow)
        cond = _find_slot(reports[0], "condition")
        assert cond.status == "satisfied"
        assert set(cond.source_span_ids) == {"s21", "s22"}

    def test_handler_action_not_applicable_at_stage4(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Over budget",
                spans=["s20"],
            )
        )
        reports, _ = check_exception_flows_irs(flow)
        handler = _find_slot(reports[0], "handler_action")
        assert handler.status == "not_applicable"

    def test_trigger_step_not_applicable_at_stage4(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Over budget",
                spans=["s20"],
            )
        )
        reports, _ = check_exception_flows_irs(flow)
        trigger = _find_slot(reports[0], "trigger_step")
        assert trigger.status == "not_applicable"


# ---------------------------------------------------------------------------
# Assumed condition (spans empty)
# ---------------------------------------------------------------------------

class TestAssumedCondition:
    def test_empty_spans_produces_ambiguity_diagnostic(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Handle errors appropriately",
                spans=[],
            )
        )
        reports, diagnostics = check_exception_flows_irs(flow)

        assert len(reports) == 1
        assert len(diagnostics) == 1

        assert diagnostics[0].kind == "type_or_contract_ambiguity"
        assert "exc_1" in diagnostics[0].message
        assert diagnostics[0].blocks_rendering is True
        assert diagnostics[0].blocks_completion is True

    def test_empty_spans_condition_is_assumed(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Handle errors",
                spans=[],
            )
        )
        reports, _ = check_exception_flows_irs(flow)
        cond = _find_slot(reports[0], "condition")
        assert cond.status == "assumed"
        assert cond.relation == "assumed"
        assert cond.diagnostic_kind == "type_or_contract_ambiguity"

    def test_empty_spans_not_renderable(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Handle errors",
                spans=[],
            )
        )
        reports, _ = check_exception_flows_irs(flow)
        assert reports[0].renderable is False


# ---------------------------------------------------------------------------
# Multiple exception flows
# ---------------------------------------------------------------------------

class TestMultipleExceptionFlows:
    def test_mixed_source_backed_and_assumed(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Over budget",
                spans=["s20"],
            ),
            ExceptionFlow(
                flow_id="exc_2",
                condition_text="Handle errors",
                spans=[],
            ),
        )
        reports, diagnostics = check_exception_flows_irs(flow)

        assert len(reports) == 2
        assert len(diagnostics) == 1  # only exc_2 is ambiguous

        exc1 = reports[0]
        assert exc1.renderable is True
        assert _find_slot(exc1, "condition").status == "satisfied"

        exc2 = reports[1]
        assert exc2.renderable is False
        assert _find_slot(exc2, "condition").status == "assumed"

    def test_all_source_backed_no_diagnostics(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Over budget",
                spans=["s20"],
            ),
            ExceptionFlow(
                flow_id="exc_2",
                condition_text="Non-compliance",
                spans=["s21"],
            ),
        )
        _, diagnostics = check_exception_flows_irs(flow)
        assert diagnostics == []


# ---------------------------------------------------------------------------
# No missing_handler emission
# ---------------------------------------------------------------------------

class TestNoMissingHandlerAtStage4:
    def test_source_backed_flow_does_not_emit_missing_handler(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Over budget",
                spans=["s20"],
            )
        )
        _, diagnostics = check_exception_flows_irs(flow)
        kinds = {d.kind for d in diagnostics}
        assert "missing_handler" not in kinds

    def test_assumed_flow_does_not_emit_missing_handler(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Handle errors",
                spans=[],
            )
        )
        _, diagnostics = check_exception_flows_irs(flow)
        kinds = {d.kind for d in diagnostics}
        assert "missing_handler" not in kinds


# ---------------------------------------------------------------------------
# Worker-aware path
# ---------------------------------------------------------------------------

class TestWorkerAwarePath:
    def test_worker_scoped_construct_ids(self):
        plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": _make_flow(
                    ExceptionFlow(
                        flow_id="exc_1",
                        condition_text="Over budget",
                        spans=["s20"],
                    )
                ),
            },
        )
        reports, _ = check_worker_flow_plan_exception_flows_irs(plan)

        assert len(reports) == 1
        assert reports[0].construct_id == "worker:worker_main.exception_flow:exc_1"

    def test_multiple_workers(self):
        plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": _make_flow(
                    ExceptionFlow(
                        flow_id="exc_1",
                        condition_text="Over budget",
                        spans=["s20"],
                    )
                ),
                "child_review": _make_flow(
                    ExceptionFlow(
                        flow_id="exc_2",
                        condition_text="Review failed",
                        spans=[],
                    )
                ),
            },
        )
        reports, diagnostics = check_worker_flow_plan_exception_flows_irs(plan)

        assert len(reports) == 2
        assert len(diagnostics) == 1  # only child_review has assumed condition

        ids = {r.construct_id for r in reports}
        assert "worker:worker_main.exception_flow:exc_1" in ids
        assert "worker:child_review.exception_flow:exc_2" in ids

    def test_worker_with_no_exception_flows(self):
        plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_a": FlowStructureIR(main_flow_spans=["s1"]),
                "worker_b": _make_flow(
                    ExceptionFlow(
                        flow_id="exc_1",
                        condition_text="Over budget",
                        spans=["s20"],
                    )
                ),
            },
        )
        reports, _ = check_worker_flow_plan_exception_flows_irs(plan)
        # Only worker_b has an exception flow
        assert len(reports) == 1

    def test_target_ref_includes_worker(self):
        plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": _make_flow(
                    ExceptionFlow(
                        flow_id="exc_1",
                        condition_text="Over budget",
                        spans=[],
                    )
                ),
            },
        )
        _, diagnostics = check_worker_flow_plan_exception_flows_irs(plan)
        assert diagnostics[0].target_ref == "worker:worker_main.exception_flow:exc_1"

    def test_unique_diagnostic_ids_across_workers(self):
        """Two workers with assumed exception flows must not collide."""
        plan = WorkerFlowPlanIR(
            worker_flows={
                "worker_main": _make_flow(
                    ExceptionFlow(
                        flow_id="exc_1",
                        condition_text="Handle errors",
                        spans=[],
                    )
                ),
                "child_review": _make_flow(
                    ExceptionFlow(
                        flow_id="exc_2",
                        condition_text="Review failure",
                        spans=[],
                    )
                ),
            },
        )
        _, diagnostics = check_worker_flow_plan_exception_flows_irs(plan)
        assert len(diagnostics) == 2
        ids = {d.diagnostic_id for d in diagnostics}
        assert len(ids) == 2, f"Duplicate diagnostic_id found: {ids}"
        # R6.4: diagnostic_id format changed to irs_{hash}
        assert all(did.startswith("irs_") for did in ids)


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_input_same_output(self):
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Over budget",
                spans=["s20"],
            )
        )
        a_reports, a_diags = check_exception_flows_irs(flow)
        b_reports, b_diags = check_exception_flows_irs(flow)
        assert len(a_reports) == len(b_reports)
        assert len(a_diags) == len(b_diags)


# ---------------------------------------------------------------------------
# Custom registry
# ---------------------------------------------------------------------------

class TestCustomRegistry:
    def test_accepts_custom_registry(self):
        registry = SPLConstructRegistry.default()
        flow = _make_flow(
            ExceptionFlow(
                flow_id="exc_1",
                condition_text="Over budget",
                spans=["s20"],
            )
        )
        reports, _ = check_exception_flows_irs(flow, registry=registry)
        assert len(reports) == 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_slot(report, slot_name: str):
    for slot in report.slots:
        if slot.slot_name == slot_name:
            return slot
    raise KeyError(slot_name)
