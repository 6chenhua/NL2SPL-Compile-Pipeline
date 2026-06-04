"""R6.3 Stage7StepIRSChecker tests.

Tests for the v6-style step checker at Stage 7.
Verifies instance extraction, slot satisfaction for all 4 command types,
and worker-scoped paths.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.step import Stage7StepIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.instance import ConstructInstance
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR


def _make_step(
    step_id: str = "st_1",
    command_type: str = "GENERAL_COMMAND",
    text: str = "Do something",
    source_span_ids: list[str] | None = None,
    integration_ref: str | None = None,
    handoff_id: str | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
) -> StepIR:
    """Build a minimal StepIR."""
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


def _make_context(
    *,
    steps: tuple[StepIR, ...] = (),
    worker_steps: WorkerStepPlanIR | None = None,
) -> IRSCheckContext:
    """Build a minimal IRSCheckContext for Stage 7."""
    return IRSCheckContext(
        stage_name="stage7",
        steps=steps,
        worker_steps=worker_steps,
    )


@pytest.fixture
def checker() -> Stage7StepIRSChecker:
    return Stage7StepIRSChecker()


@pytest.fixture
def registry() -> SPLConstructRegistry:
    return SPLConstructRegistry.default()


# ------------------------------------------------------------------
# extract_instances
# ------------------------------------------------------------------


class TestExtractInstances:
    """Instance extraction from context.steps and worker_steps."""

    def test_extract_from_context_steps(
        self,
        checker: Stage7StepIRSChecker,
    ) -> None:
        """Extract instances from context.steps tuple."""
        steps = (
            _make_step("st_1", "GENERAL_COMMAND", source_span_ids=["s1"]),
            _make_step("st_2", "REQUEST_INPUT", source_span_ids=["s2"]),
        )
        ctx = _make_context(steps=steps)
        instances = checker.extract_instances(ctx)

        assert len(instances) == 2
        assert instances[0].construct_type == "GENERAL_COMMAND"
        assert instances[0].construct_id == "step:st_1"
        assert instances[1].construct_type == "REQUEST_INPUT"
        assert instances[1].construct_id == "step:st_2"

    def test_extract_from_worker_step_plan(
        self,
        checker: Stage7StepIRSChecker,
    ) -> None:
        """Extract instances from WorkerStepPlanIR."""
        worker_steps = WorkerStepPlanIR(
            main_worker_id="main",
            worker_steps={
                "main": [_make_step("st_1", "GENERAL_COMMAND")],
                "child": [_make_step("st_2", "CALL_API", integration_ref="api")],
            },
        )
        ctx = _make_context(worker_steps=worker_steps)
        instances = checker.extract_instances(ctx)

        assert len(instances) == 2
        assert instances[0].construct_id == "worker:main.step:st_1"
        assert instances[1].construct_id == "worker:child.step:st_2"

    def test_extract_skips_display_message(
        self,
        checker: Stage7StepIRSChecker,
    ) -> None:
        """DISPLAY_MESSAGE steps are skipped."""
        steps = (
            _make_step("st_1", "DISPLAY_MESSAGE"),
            _make_step("st_2", "GENERAL_COMMAND"),
        )
        ctx = _make_context(steps=steps)
        instances = checker.extract_instances(ctx)

        assert len(instances) == 1
        assert instances[0].construct_id == "step:st_2"

    def test_extract_no_steps_returns_empty(
        self,
        checker: Stage7StepIRSChecker,
    ) -> None:
        """Empty context returns no instances."""
        ctx = _make_context()
        instances = checker.extract_instances(ctx)
        assert len(instances) == 0

    def test_instance_ir_ref_is_step(
        self,
        checker: Stage7StepIRSChecker,
    ) -> None:
        """ir_ref points to the StepIR object."""
        step = _make_step("st_1", "GENERAL_COMMAND")
        ctx = _make_context(steps=(step,))
        instances = checker.extract_instances(ctx)
        assert instances[0].ir_ref is step


# ------------------------------------------------------------------
# GENERAL_COMMAND
# ------------------------------------------------------------------


class TestGeneralCommand:
    """GENERAL_COMMAND slot checks."""

    def test_source_backed_complete(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """With source → complete, renderable."""
        step = _make_step(source_span_ids=["s1"])
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="GENERAL_COMMAND",
            ir_ref=step,
            source_span_ids=["s1"],
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("GENERAL_COMMAND")
        report = checker.check_instance(instance, irs, _make_context())

        assert report.completeness == "complete"
        assert report.renderable is True
        assert report.frontier_status == "leaf"
        assert all(s.diagnostic_kind is None for s in report.slots)

    def test_no_source_assumed(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """Without source → partial, not renderable, assumed_command_not_renderable."""
        step = _make_step(source_span_ids=[])
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="GENERAL_COMMAND",
            ir_ref=step,
            source_span_ids=[],
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("GENERAL_COMMAND")
        report = checker.check_instance(instance, irs, _make_context())

        assert report.completeness == "partial"
        assert report.renderable is False

        evidence_slot = next(s for s in report.slots if s.slot_name == "source_evidence")
        assert evidence_slot.status == "missing"
        assert evidence_slot.diagnostic_kind == "assumed_command_not_renderable"


# ------------------------------------------------------------------
# REQUEST_INPUT
# ------------------------------------------------------------------


class TestRequestInput:
    """REQUEST_INPUT slot checks."""

    def test_source_backed_complete(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """With source → complete."""
        step = _make_step(command_type="REQUEST_INPUT", source_span_ids=["s1"])
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="REQUEST_INPUT",
            ir_ref=step,
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("REQUEST_INPUT")
        report = checker.check_instance(instance, irs, _make_context())

        assert report.completeness == "complete"
        assert report.renderable is True

    def test_no_source_ambiguity(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """Without source → type_or_contract_ambiguity."""
        step = _make_step(command_type="REQUEST_INPUT", source_span_ids=[])
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="REQUEST_INPUT",
            ir_ref=step,
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("REQUEST_INPUT")
        report = checker.check_instance(instance, irs, _make_context())

        assert report.renderable is False
        target_slot = next(s for s in report.slots if s.slot_name == "value_target")
        assert target_slot.status == "missing"
        assert target_slot.diagnostic_kind == "type_or_contract_ambiguity"


# ------------------------------------------------------------------
# CALL_API
# ------------------------------------------------------------------


class TestCallApi:
    """CALL_API slot checks."""

    def test_both_present_complete(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """Both integration_ref and source → complete."""
        step = _make_step(
            command_type="CALL_API",
            source_span_ids=["s1"],
            integration_ref="payment_api",
        )
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="CALL_API",
            ir_ref=step,
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("CALL_API")
        report = checker.check_instance(instance, irs, _make_context())

        assert report.completeness == "complete"
        assert report.renderable is True

    def test_missing_integration_ref(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """Missing integration_ref → api_name missing."""
        step = _make_step(
            command_type="CALL_API",
            source_span_ids=["s1"],
            integration_ref=None,
        )
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="CALL_API",
            ir_ref=step,
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("CALL_API")
        report = checker.check_instance(instance, irs, _make_context())

        assert report.renderable is False
        api_slot = next(s for s in report.slots if s.slot_name == "api_name")
        assert api_slot.status == "missing"
        assert api_slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_missing_source(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """Missing source_span_ids → call_action missing."""
        step = _make_step(
            command_type="CALL_API",
            source_span_ids=[],
            integration_ref="payment_api",
        )
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="CALL_API",
            ir_ref=step,
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("CALL_API")
        report = checker.check_instance(instance, irs, _make_context())

        assert report.renderable is False
        action_slot = next(s for s in report.slots if s.slot_name == "call_action")
        assert action_slot.status == "missing"
        assert action_slot.diagnostic_kind == "type_or_contract_ambiguity"


# ------------------------------------------------------------------
# INVOKE_WORKER
# ------------------------------------------------------------------


class TestInvokeWorker:
    """INVOKE_WORKER slot checks."""

    def test_both_present_complete(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """Both handoff_id and integration_ref → complete."""
        step = _make_step(
            command_type="INVOKE_WORKER",
            source_span_ids=["s1"],
            integration_ref="child_worker",
            handoff_id="ho_1",
        )
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="INVOKE_WORKER",
            ir_ref=step,
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("INVOKE_WORKER")
        report = checker.check_instance(instance, irs, _make_context())

        assert report.completeness == "complete"
        assert report.renderable is True

    def test_missing_handoff_id(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """Missing handoff_id → handoff_id slot missing."""
        step = _make_step(
            command_type="INVOKE_WORKER",
            source_span_ids=["s1"],
            integration_ref="child_worker",
            handoff_id=None,
        )
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="INVOKE_WORKER",
            ir_ref=step,
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("INVOKE_WORKER")
        report = checker.check_instance(instance, irs, _make_context())

        assert report.renderable is False
        handoff_slot = next(s for s in report.slots if s.slot_name == "handoff_id")
        assert handoff_slot.status == "missing"
        assert handoff_slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_missing_integration_ref(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """Missing integration_ref → target_worker slot missing."""
        step = _make_step(
            command_type="INVOKE_WORKER",
            source_span_ids=["s1"],
            integration_ref=None,
            handoff_id="ho_1",
        )
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="INVOKE_WORKER",
            ir_ref=step,
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("INVOKE_WORKER")
        report = checker.check_instance(instance, irs, _make_context())

        assert report.renderable is False
        target_slot = next(s for s in report.slots if s.slot_name == "target_worker")
        assert target_slot.status == "missing"
        assert target_slot.diagnostic_kind == "type_or_contract_ambiguity"


# ------------------------------------------------------------------
# Report fields and worker-scoped path
# ------------------------------------------------------------------


class TestReportFields:
    """Construct path, worker-scoped IDs, and immutability."""

    def test_construct_path_populated(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """Report inherits construct_path from instance."""
        step = _make_step(source_span_ids=["s1"])
        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="GENERAL_COMMAND",
            ir_ref=step,
            construct_path=("steps", "st_1"),
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("GENERAL_COMMAND")
        report = checker.check_instance(instance, irs, _make_context())
        assert report.construct_path == ("steps", "st_1")

    def test_worker_scoped_construct_id(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """Worker-scoped construct_id = worker:{wid}.step:{sid}."""
        step = _make_step(source_span_ids=["s1"])
        instance = ConstructInstance(
            construct_id="worker:main.step:st_1",
            construct_type="GENERAL_COMMAND",
            ir_ref=step,
            metadata={"step_ir": step, "worker_id": "main"},
        )
        irs = registry.get("GENERAL_COMMAND")
        report = checker.check_instance(instance, irs, _make_context())
        assert report.construct_id == "worker:main.step:st_1"

    def test_does_not_modify_step_ir(
        self,
        checker: Stage7StepIRSChecker,
        registry: SPLConstructRegistry,
    ) -> None:
        """StepIR is unchanged after checking."""
        step = _make_step(
            command_type="CALL_API",
            source_span_ids=["s1"],
            integration_ref="api",
            inputs=["x"],
            outputs=["y"],
        )
        original_spans = list(step.source_span_ids)
        original_ref = step.integration_ref

        instance = ConstructInstance(
            construct_id="step:st_1",
            construct_type="CALL_API",
            ir_ref=step,
            metadata={"step_ir": step, "worker_id": None},
        )
        irs = registry.get("CALL_API")
        checker.check_instance(instance, irs, _make_context())

        assert step.source_span_ids == original_spans
        assert step.integration_ref == original_ref


# ------------------------------------------------------------------
# Dict worker path
# ------------------------------------------------------------------


class TestDictWorkerPath:
    """Worker-steps passed as plain dict (not WorkerStepPlanIR)."""

    def test_extract_from_dict_worker_steps(
        self,
        checker: Stage7StepIRSChecker,
    ) -> None:
        """Plain dict[str, list[StepIR]] works as worker_steps."""
        steps = [_make_step("st_1", "GENERAL_COMMAND", source_span_ids=["s1"])]
        ctx = IRSCheckContext(
            stage_name="stage7",
            worker_steps={"w1": steps},
        )
        instances = checker.extract_instances(ctx)

        assert len(instances) == 1
        assert instances[0].construct_id == "worker:w1.step:st_1"
