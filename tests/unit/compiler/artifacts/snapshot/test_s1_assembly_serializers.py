"""S1 assembly serializer round-trip tests — using actual IR field names."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.serialization.registry import build_default_registry
from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import (
    AlternativeFlowRef,
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerInput,
    WorkerIR,
    WorkerOutput,
)


def _rt(registry, obj):
    data = registry.serialize(obj)
    restored = registry.deserialize(data)
    return data, restored


class TestWorkerInputRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        wi = WorkerInput(name="draft", required=True, requiredness="required")
        data, restored = _rt(reg, wi)
        assert data["$type"] == "WorkerInput"
        assert restored.name == "draft"

    def test_none_required_preserved(self) -> None:
        reg = build_default_registry()
        wi = WorkerInput(name="opt_field", required=None, requiredness="unspecified")
        _data, restored = _rt(reg, wi)
        assert restored.required is None


class TestWorkerOutputRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        wo = WorkerOutput(name="result", required=True)
        data, restored = _rt(reg, wo)
        assert data["$type"] == "WorkerOutput"
        assert restored.name == "result"


class TestFlowRefRoundTrip:
    def test_with_blocks(self) -> None:
        reg = build_default_registry()
        fr = FlowRef(blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL")])
        data, restored = _rt(reg, fr)
        assert data["$type"] == "FlowRef"
        assert len(restored.blocks) == 1
        assert isinstance(restored.blocks[0], BlockIR)

    def test_empty_flow(self) -> None:
        reg = build_default_registry()
        fr = FlowRef()
        _data, restored = _rt(reg, fr)
        assert restored.blocks == []


class TestAlternativeFlowRefRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        af = AlternativeFlowRef(
            flow_id="alt_1", condition_text="If urgent",
            blocks=[BlockIR(block_id="b_alt", block_type="SEQUENTIAL")],
        )
        data, restored = _rt(reg, af)
        assert data["$type"] == "AlternativeFlowRef"
        assert restored.flow_id == "alt_1"


class TestExceptionFlowRefRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        ef = ExceptionFlowRef(
            flow_id="exc_1", condition_text="On error",
            blocks=[BlockIR(block_id="b_exc", block_type="SEQUENTIAL")],
            spans=["s_error"],
        )
        data, restored = _rt(reg, ef)
        assert data["$type"] == "ExceptionFlowRef"
        assert restored.spans == ["s_error"]


class TestChildWorkerIRRoundTrip:
    def test_minimal_roundtrip(self) -> None:
        reg = build_default_registry()
        cw = ChildWorkerIR(
            worker_name="SubWorker", description="Handles sub-task",
            task_text="Process the draft",
            main_flow=FlowRef(blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL")]),
        )
        data, restored = _rt(reg, cw)
        assert data["$type"] == "ChildWorkerIR"
        assert restored.worker_name == "SubWorker"


class TestWorkerIRRoundTrip:
    def test_minimal_roundtrip(self) -> None:
        reg = build_default_registry()
        w = WorkerIR(
            worker_name="MainWorker", description="Main processing worker",
            main_flow=FlowRef(blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL")]),
        )
        data, restored = _rt(reg, w)
        assert data["$type"] == "WorkerIR"
        assert restored.worker_name == "MainWorker"

    def test_with_child_workers(self) -> None:
        reg = build_default_registry()
        w = WorkerIR(
            worker_name="MainWorker", description="Orchestrator",
            main_flow=FlowRef(blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL")]),
            child_worker_refs=["SubWorker"],
            child_workers=[
                ChildWorkerIR(
                    worker_name="SubWorker", description="Sub", task_text="Do work",
                    main_flow=FlowRef(blocks=[BlockIR(block_id="b_sub", block_type="SEQUENTIAL")]),
                ),
            ],
        )
        data, restored = _rt(reg, w)
        assert len(restored.child_workers) == 1
        assert isinstance(restored.child_workers[0], ChildWorkerIR)

    def test_full_worker(self) -> None:
        reg = build_default_registry()
        w = WorkerIR(
            worker_name="FullWorker", description="Worker with features",
            inputs=[WorkerInput(name="raw_data", required=True)],
            outputs=[WorkerOutput(name="report", required=True)],
            main_flow=FlowRef(blocks=[BlockIR(block_id="b_main", block_type="SEQUENTIAL")]),
            alternative_flows=[
                AlternativeFlowRef(flow_id="alt_1", condition_text="If urgent",
                                   blocks=[BlockIR(block_id="b_alt", block_type="IF")]),
            ],
            exception_flows=[
                ExceptionFlowRef(flow_id="exc_1", condition_text="On error",
                                 blocks=[BlockIR(block_id="b_exc", block_type="SEQUENTIAL")]),
            ],
            api_refs=["EmailAPI", "SlackAPI"],
            steps=[StepIR(step_id="st1", text="Extract", source_span_ids=["s1"],
                          command_type="GENERAL_COMMAND", flow_ref="main")],
            scoped_steps=True,
            child_worker_refs=["SubWorker"],
            child_workers=[
                ChildWorkerIR(
                    worker_name="SubWorker", description="Sub", task_text="Do work",
                    main_flow=FlowRef(blocks=[BlockIR(block_id="b_sub", block_type="SEQUENTIAL")]),
                ),
            ],
        )
        data, restored = _rt(reg, w)
        assert data["$type"] == "WorkerIR"
        assert restored.worker_name == "FullWorker"
        assert len(restored.steps) == 1
        assert isinstance(restored.main_flow, FlowRef)
        assert restored.scoped_steps is True
        assert len(restored.child_workers) == 1
        assert isinstance(restored.child_workers[0], ChildWorkerIR)
