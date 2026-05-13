"""Tests for ChildWorkerIR data structure."""

from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import (
    AlternativeFlowRef,
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerInput,
    WorkerOutput,
)


class TestChildWorkerIR:
    """Test ChildWorkerIR initialization and field access."""

    def test_init_with_defaults(self):
        """Test ChildWorkerIR initialization with default values."""
        child = ChildWorkerIR(
            worker_name="test_worker",
            description="Test worker",
            task_text="Do something",
        )
        assert child.worker_name == "test_worker"
        assert child.description == "Test worker"
        assert child.task_text == "Do something"
        assert child.inputs == []
        assert child.outputs == []
        assert child.main_flow.blocks == []
        assert child.alternative_flows == []
        assert child.exception_flows == []
        assert child.api_refs == []
        assert child.steps == []

    def test_init_with_inputs_outputs(self):
        """Test ChildWorkerIR initialization with inputs and outputs."""
        child = ChildWorkerIR(
            worker_name="test_worker",
            description="Test worker",
            task_text="Do something",
            inputs=[WorkerInput(name="input1", required=True)],
            outputs=[WorkerOutput(name="output1", required=False)],
        )
        assert len(child.inputs) == 1
        assert child.inputs[0].name == "input1"
        assert child.inputs[0].required is True
        assert len(child.outputs) == 1
        assert child.outputs[0].name == "output1"
        assert child.outputs[0].required is False

    def test_init_with_flow(self):
        """Test ChildWorkerIR initialization with main flow."""
        blocks = [BlockIR(block_id="b1", block_type="SEQUENTIAL")]
        child = ChildWorkerIR(
            worker_name="test_worker",
            description="Test worker",
            task_text="Do something",
            main_flow=FlowRef(blocks=blocks),
        )
        assert len(child.main_flow.blocks) == 1
        assert child.main_flow.blocks[0].block_id == "b1"

    def test_init_with_alternative_flows(self):
        """Test ChildWorkerIR initialization with alternative flows."""
        alt_flow = AlternativeFlowRef(
            flow_id="alt_1",
            condition_text="if condition",
            blocks=[BlockIR(block_id="b1", block_type="IF")],
        )
        child = ChildWorkerIR(
            worker_name="test_worker",
            description="Test worker",
            task_text="Do something",
            alternative_flows=[alt_flow],
        )
        assert len(child.alternative_flows) == 1
        assert child.alternative_flows[0].flow_id == "alt_1"

    def test_init_with_exception_flows(self):
        """Test ChildWorkerIR initialization with exception flows."""
        exc_flow = ExceptionFlowRef(
            flow_id="exc_1",
            condition_text="on error",
            blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL")],
        )
        child = ChildWorkerIR(
            worker_name="test_worker",
            description="Test worker",
            task_text="Do something",
            exception_flows=[exc_flow],
        )
        assert len(child.exception_flows) == 1
        assert child.exception_flows[0].flow_id == "exc_1"

    def test_init_with_steps(self):
        """Test ChildWorkerIR initialization with steps."""
        steps = [
            StepIR(
                step_id="st1",
                text="Step 1",
                source_span_ids=["s1"],
                command_type="GENERAL_COMMAND",
            ),
            StepIR(
                step_id="st2",
                text="Step 2",
                source_span_ids=["s2"],
                command_type="CALL_API",
                integration_ref="api_1",
            ),
        ]
        child = ChildWorkerIR(
            worker_name="test_worker",
            description="Test worker",
            task_text="Do something",
            steps=steps,
        )
        assert len(child.steps) == 2
        assert child.steps[0].step_id == "st1"
        assert child.steps[1].command_type == "CALL_API"

    def test_init_with_api_refs(self):
        """Test ChildWorkerIR initialization with API refs."""
        child = ChildWorkerIR(
            worker_name="test_worker",
            description="Test worker",
            task_text="Do something",
            api_refs=["api_1", "api_2"],
        )
        assert len(child.api_refs) == 2
        assert "api_1" in child.api_refs
        assert "api_2" in child.api_refs

    def test_init_with_all_fields(self):
        """Test ChildWorkerIR initialization with all fields."""
        child = ChildWorkerIR(
            worker_name="full_worker",
            description="Full worker",
            task_text="Do everything",
            inputs=[WorkerInput(name="in1", required=True)],
            outputs=[WorkerOutput(name="out1", required=True)],
            main_flow=FlowRef(blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL")]),
            alternative_flows=[
                AlternativeFlowRef(
                    flow_id="alt_1",
                    condition_text="alt condition",
                    blocks=[BlockIR(block_id="b2", block_type="IF")],
                )
            ],
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="on error",
                    blocks=[BlockIR(block_id="b3", block_type="SEQUENTIAL")],
                )
            ],
            api_refs=["api_1"],
            steps=[
                StepIR(
                    step_id="st1",
                    text="Step 1",
                    source_span_ids=["s1"],
                    command_type="GENERAL_COMMAND",
                )
            ],
        )
        assert child.worker_name == "full_worker"
        assert len(child.inputs) == 1
        assert len(child.outputs) == 1
        assert len(child.main_flow.blocks) == 1
        assert len(child.alternative_flows) == 1
        assert len(child.exception_flows) == 1
        assert len(child.api_refs) == 1
        assert len(child.steps) == 1
