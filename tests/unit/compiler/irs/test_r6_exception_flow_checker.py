"""R6.2 Stage4ExceptionFlowIRSChecker tests.

Tests for the v6-style EXCEPTION_FLOW checker at Stage 4.
Verifies instance extraction, slot satisfaction, frontier/cutline,
and worker-scoped paths.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.exception_flow import Stage4ExceptionFlowIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.instance import ConstructInstance
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR


def _make_context(
    *,
    flow: FlowStructureIR | None = None,
    worker_flows: WorkerFlowPlanIR | None = None,
) -> IRSCheckContext:
    """Build a minimal IRSCheckContext for Stage 4."""
    return IRSCheckContext(
        stage_name="stage4",
        flow=flow,
        worker_flows=worker_flows,
    )


@pytest.fixture
def checker() -> Stage4ExceptionFlowIRSChecker:
    return Stage4ExceptionFlowIRSChecker()


@pytest.fixture
def registry() -> SPLConstructRegistry:
    return SPLConstructRegistry.default()


@pytest.fixture
def exception_flow_irs(registry: SPLConstructRegistry):
    return registry.get("EXCEPTION_FLOW")


# ------------------------------------------------------------------
# extract_instances
# ------------------------------------------------------------------


class TestExtractInstances:
    """Instance extraction from FlowStructureIR and WorkerFlowPlanIR."""

    def test_extract_from_flow_structure(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
    ) -> None:
        """Extract instances from FlowStructureIR (legacy path)."""
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_1", "Missing timeframe", ["s1"]),
                ExceptionFlow("exc_2", "Invalid format", ["s2"]),
            ],
        )
        ctx = _make_context(flow=flow)
        instances = checker.extract_instances(ctx)

        assert len(instances) == 2
        assert instances[0].construct_type == "EXCEPTION_FLOW"
        assert instances[0].construct_id == "exception_flow:exc_1"
        assert instances[1].construct_id == "exception_flow:exc_2"

    def test_extract_from_worker_flow_plan(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
    ) -> None:
        """Extract instances from WorkerFlowPlanIR (worker-scoped path)."""
        flow1 = FlowStructureIR(
            exception_flows=[ExceptionFlow("exc_1", "Missing timeframe", ["s1"])],
        )
        flow2 = FlowStructureIR(
            exception_flows=[ExceptionFlow("exc_2", "Invalid format", ["s2"])],
        )
        worker_flows = WorkerFlowPlanIR(
            worker_flows={"main": flow1, "child_review": flow2},
        )
        ctx = _make_context(worker_flows=worker_flows)
        instances = checker.extract_instances(ctx)

        assert len(instances) == 2
        assert instances[0].construct_id == "worker:main.exception_flow:exc_1"
        assert instances[1].construct_id == "worker:child_review.exception_flow:exc_2"

    def test_extract_empty_flows(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
    ) -> None:
        """Empty exception_flows returns no instances."""
        flow = FlowStructureIR(exception_flows=[])
        ctx = _make_context(flow=flow)
        instances = checker.extract_instances(ctx)
        assert len(instances) == 0

    def test_extract_no_flow_returns_empty(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
    ) -> None:
        """No flow or worker_flows returns empty."""
        ctx = _make_context()
        instances = checker.extract_instances(ctx)
        assert len(instances) == 0

    def test_instance_materialized_and_source_demanded(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
    ) -> None:
        """Instances are materialized=True, source_demanded=True."""
        flow = FlowStructureIR(
            exception_flows=[ExceptionFlow("exc_1", "Cond", ["s1"])],
        )
        ctx = _make_context(flow=flow)
        instances = checker.extract_instances(ctx)

        assert instances[0].materialized is True
        assert instances[0].source_demanded is True
        assert instances[0].candidate_only is False

    def test_instance_ir_ref_is_exception_flow(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
    ) -> None:
        """ir_ref points to the ExceptionFlow object."""
        exc = ExceptionFlow("exc_1", "Cond", ["s1"])
        flow = FlowStructureIR(exception_flows=[exc])
        ctx = _make_context(flow=flow)
        instances = checker.extract_instances(ctx)

        assert instances[0].ir_ref is exc


# ------------------------------------------------------------------
# check_instance
# ------------------------------------------------------------------


class TestCheckInstance:
    """Slot satisfaction and report fields."""

    def test_condition_satisfied(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
        exception_flow_irs,
    ) -> None:
        """Condition with text + spans → partial, renderable, no diagnostic."""
        exc = ExceptionFlow("exc_1", "Missing timeframe", ["s1", "s2"])
        instance = ConstructInstance(
            construct_id="exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            ir_ref=exc,
            source_span_ids=["s1", "s2"],
            metadata={"exception_flow_ir": exc, "worker_id": None},
        )
        report = checker.check_instance(instance, exception_flow_irs, _make_context())

        assert report.completeness == "partial"
        assert report.renderable is True
        assert report.frontier_status == "cutline_partial"
        assert report.cutline_reason == "missing_required_for_complete"

        condition_slot = next(s for s in report.slots if s.slot_name == "condition")
        assert condition_slot.status == "satisfied"
        assert condition_slot.source_span_ids == ["s1", "s2"]
        assert condition_slot.diagnostic_kind is None

    def test_condition_assumed(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
        exception_flow_irs,
    ) -> None:
        """Condition with text but no spans → assumed, diagnostic_kind set."""
        exc = ExceptionFlow("exc_1", "Missing timeframe", [])
        instance = ConstructInstance(
            construct_id="exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            ir_ref=exc,
            source_span_ids=[],
            metadata={"exception_flow_ir": exc, "worker_id": None},
        )
        report = checker.check_instance(instance, exception_flow_irs, _make_context())

        assert report.renderable is False
        assert report.completeness == "partial"
        assert report.frontier_status == "cutline_blocked"
        assert report.cutline_reason == "missing_required_for_partial"

        condition_slot = next(s for s in report.slots if s.slot_name == "condition")
        assert condition_slot.status == "assumed"
        assert condition_slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_handler_action_not_applicable(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
        exception_flow_irs,
    ) -> None:
        """handler_action is always not_applicable at Stage 4."""
        exc = ExceptionFlow("exc_1", "Cond", ["s1"])
        instance = ConstructInstance(
            construct_id="exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            ir_ref=exc,
            metadata={"exception_flow_ir": exc, "worker_id": None},
        )
        report = checker.check_instance(instance, exception_flow_irs, _make_context())

        handler_slot = next(s for s in report.slots if s.slot_name == "handler_action")
        assert handler_slot.status == "not_applicable"
        assert handler_slot.diagnostic_kind is None

        # No missing_handler diagnostic_kind on any slot
        assert all(s.diagnostic_kind != "missing_handler" for s in report.slots)

    def test_trigger_step_not_applicable(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
        exception_flow_irs,
    ) -> None:
        """trigger_step is always not_applicable at Stage 4."""
        exc = ExceptionFlow("exc_1", "Cond", ["s1"])
        instance = ConstructInstance(
            construct_id="exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            ir_ref=exc,
            metadata={"exception_flow_ir": exc, "worker_id": None},
        )
        report = checker.check_instance(instance, exception_flow_irs, _make_context())

        trigger_slot = next(s for s in report.slots if s.slot_name == "trigger_step")
        assert trigger_slot.status == "not_applicable"

    def test_construct_path_populated(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
        exception_flow_irs,
    ) -> None:
        """Report inherits construct_path from instance."""
        exc = ExceptionFlow("exc_1", "Cond", ["s1"])
        instance = ConstructInstance(
            construct_id="exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            ir_ref=exc,
            construct_path=("flow", "exception_flows", "exc_1"),
            metadata={"exception_flow_ir": exc, "worker_id": None},
        )
        report = checker.check_instance(instance, exception_flow_irs, _make_context())
        assert report.construct_path == ("flow", "exception_flows", "exc_1")

    def test_source_span_ids_from_exception_flow(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
        exception_flow_irs,
    ) -> None:
        """Report source_span_ids come from ExceptionFlow.spans."""
        exc = ExceptionFlow("exc_1", "Cond", ["s3", "s4"])
        instance = ConstructInstance(
            construct_id="exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            ir_ref=exc,
            metadata={"exception_flow_ir": exc, "worker_id": None},
        )
        report = checker.check_instance(instance, exception_flow_irs, _make_context())
        assert report.source_span_ids == ["s3", "s4"]


# ------------------------------------------------------------------
# Worker-scoped path
# ------------------------------------------------------------------


class TestWorkerScopedPath:
    """Worker-scoped construct_id and metadata."""

    def test_worker_scoped_construct_id(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
        exception_flow_irs,
    ) -> None:
        """Worker-scoped construct_id = worker:{wid}.exception_flow:{fid}."""
        exc = ExceptionFlow("exc_1", "Cond", ["s1"])
        instance = ConstructInstance(
            construct_id="worker:main.exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            ir_ref=exc,
            metadata={"exception_flow_ir": exc, "worker_id": "main"},
        )
        report = checker.check_instance(instance, exception_flow_irs, _make_context())
        assert report.construct_id == "worker:main.exception_flow:exc_1"

    def test_worker_scoped_metadata_preserved(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
        exception_flow_irs,
    ) -> None:
        """Worker_id is preserved in report metadata."""
        exc = ExceptionFlow("exc_1", "Cond", ["s1"])
        instance = ConstructInstance(
            construct_id="worker:child.exception_flow:exc_1",
            construct_type="EXCEPTION_FLOW",
            ir_ref=exc,
            metadata={"exception_flow_ir": exc, "worker_id": "child"},
        )
        report = checker.check_instance(instance, exception_flow_irs, _make_context())
        assert report.metadata["worker_id"] == "child"


# ------------------------------------------------------------------
# Immutability
# ------------------------------------------------------------------


class TestImmutability:
    """Checker must not modify input IR."""

    def test_does_not_modify_flow_structure(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
    ) -> None:
        """FlowStructureIR is unchanged after extraction and checking."""
        exc = ExceptionFlow("exc_1", "Cond", ["s1"])
        flow = FlowStructureIR(exception_flows=[exc])
        original_spans = list(exc.spans)
        original_text = exc.condition_text

        ctx = _make_context(flow=flow)
        instances = checker.extract_instances(ctx)

        registry = SPLConstructRegistry.default()
        irs = registry.get("EXCEPTION_FLOW")
        checker.check_instance(instances[0], irs, ctx)

        assert exc.spans == original_spans
        assert exc.condition_text == original_text
        assert len(flow.exception_flows) == 1


# ------------------------------------------------------------------
# Dict worker path
# ------------------------------------------------------------------


class TestDictWorkerPath:
    """Worker-flows passed as plain dict (not WorkerFlowPlanIR)."""

    def test_extract_from_dict_worker_flows(
        self,
        checker: Stage4ExceptionFlowIRSChecker,
    ) -> None:
        """Plain dict[str, FlowStructureIR] works as worker_flows."""
        flow = FlowStructureIR(
            exception_flows=[ExceptionFlow("exc_1", "Cond", ["s1"])],
        )
        ctx = IRSCheckContext(
            stage_name="stage4",
            worker_flows={"w1": flow},
        )
        instances = checker.extract_instances(ctx)

        assert len(instances) == 1
        assert instances[0].construct_id == "worker:w1.exception_flow:exc_1"
