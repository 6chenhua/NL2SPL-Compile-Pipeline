"""Phase 0 baseline: Stage 10 must build child workers from WorkerSpecIR,
not only from handoffs.
"""

from __future__ import annotations

from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import WorkerInput, WorkerOutput
from nl2spl.ir.worker_plan_ir import ContractFieldIR, WorkerPlanIR, WorkerSpecIR
from nl2spl.pipeline.stages.stage10_worker_assembler.child_worker_builder import (
    ChildWorkerBuilderMixin,
)


def _field(name: str, source: str = "input") -> ContractFieldIR:
    return ContractFieldIR(name, "text", True, f"{name} field", source)


# ---------------------------------------------------------------------------
# Test double: provides the methods that ChildWorkerBuilderMixin calls on self
# but that live on other mixins / WorkerAssembler proper.
# ---------------------------------------------------------------------------


class _TestChildWorkerBuilder(ChildWorkerBuilderMixin):
    """Minimal concrete class for testing _child_workers_from_plan in isolation."""

    def _inputs_from_contract(self, fields: list[ContractFieldIR]) -> list[WorkerInput]:
        return [
            WorkerInput(name=f.name, requiredness=f.requiredness, required=f.required)
            for f in fields
            if f.name
        ]

    def _outputs_from_contract(self, fields: list[ContractFieldIR]) -> list[WorkerOutput]:
        return [
            WorkerOutput(name=f.name, requiredness=f.requiredness, required=f.required)
            for f in fields
            if f.name
        ]

    def _find_invoke_step_by_worker_name(
        self, steps: list[StepIR], worker_name: str,
    ) -> StepIR | None:
        return None


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


def _worker_plan_with_child(
    *,
    child_inputs: list[ContractFieldIR] | None = None,
    child_outputs: list[ContractFieldIR] | None = None,
    child_purpose: str = "Gather sources",
    child_span_ids: list[str] | None = None,
    child_reason: str = "Detected subtask boundary",
    include_handoff: bool = False,
) -> WorkerPlanIR:
    from nl2spl.ir.worker_plan_ir import InputBindingIR, OutputBindingIR, WorkerHandoffIR

    main = WorkerSpecIR(
        worker_id="worker_main",
        worker_name="MainWorker",
        kind="main",
        purpose="Coordinate request",
        owned_span_ids=["s1"],
        input_contract=[_field("request")],
        output_contract=[_field("draft", "output")],
        boundary_kind="main_worker",
    )
    child = WorkerSpecIR(
        worker_id="worker_child",
        worker_name="ChildWorker",
        kind="child",
        purpose=child_purpose,
        owned_span_ids=child_span_ids if child_span_ids is not None else ["s2"],
        input_contract=child_inputs if child_inputs is not None else [],
        output_contract=child_outputs if child_outputs is not None else [],
        boundary_kind="bounded_subtask",
        reason=child_reason,
    )
    handoffs = []
    if include_handoff:
        handoffs.append(
            WorkerHandoffIR(
                handoff_id="h1",
                from_worker="worker_main",
                to_worker="worker_child",
                api_ref=None,
                mode="invoke",
                condition_text=None,
                ordering="conditional",
                input_bindings=[InputBindingIR("request", "source_list", True)],
                output_bindings=[OutputBindingIR("evidence", "result", True, "set")],
            )
        )
    return WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[main, child],
        handoffs=handoffs,
        candidates=[],
        decisions=[],
        rejected_candidates=[],
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestStage10ChildWorkerFromSpec:
    """Stage 10 must build ChildWorkerIR from WorkerSpecIR, not only from handoffs."""

    def _builder(self) -> _TestChildWorkerBuilder:
        return _TestChildWorkerBuilder()

    def test_builds_child_worker_from_worker_spec_without_handoff(self) -> None:
        """Even without a complete handoff, a child WorkerSpecIR should become
        a ChildWorkerIR."""
        plan = _worker_plan_with_child(include_handoff=False)
        refs, child_workers = self._builder()._child_workers_from_plan(plan, [])

        assert "ChildWorker" in refs, (
            f"Expected ChildWorker in refs, got {refs}"
        )
        assert len(child_workers) >= 1, (
            f"Expected at least 1 child worker from plan.workers (kind=child), "
            f"got {len(child_workers)}"
        )

    def test_empty_contract_maps_to_empty_worker_inputs_outputs(self) -> None:
        """A child worker with no contract should render with empty inputs/outputs."""
        plan = _worker_plan_with_child(
            child_inputs=[], child_outputs=[], include_handoff=False,
        )
        _refs, child_workers = self._builder()._child_workers_from_plan(plan, [])

        assert len(child_workers) >= 1
        child = child_workers[0]
        assert len(child.inputs) == 0, (
            f"Empty contract should produce empty inputs, got {child.inputs}"
        )
        assert len(child.outputs) == 0, (
            f"Empty contract should produce empty outputs, got {child.outputs}"
        )

    def test_no_empty_shell_without_responsibility(self) -> None:
        """A WorkerSpecIR with no purpose, no reason, and no owned spans
        should not become a rendered child worker."""
        plan = _worker_plan_with_child(
            child_purpose="", child_span_ids=[], child_reason="",
            include_handoff=False,
        )
        _refs, child_workers = self._builder()._child_workers_from_plan(plan, [])

        assert len(child_workers) == 0, (
            f"Empty-shell worker with no responsibility should NOT be rendered. "
            f"Got {len(child_workers)}"
        )
