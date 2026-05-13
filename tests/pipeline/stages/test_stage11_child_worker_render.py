"""Tests for Stage 11 SPLRenderer child worker rendering."""

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
from nl2spl.pipeline.stages.stage11_spl_renderer import SPLRenderer


class TestSPLRendererChildWorker:
    """Test child worker rendering with flow support."""

    def test_render_child_worker_with_flow(self):
        """Test _render_child_worker with main flow blocks."""
        renderer = SPLRenderer()
        child = ChildWorkerIR(
            worker_name="ChildWorker",
            description="Child worker task",
            task_text="Do something",
            inputs=[WorkerInput(name="input1", required=True)],
            outputs=[WorkerOutput(name="output1", required=True)],
            main_flow=FlowRef(
                blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="SEQUENTIAL",
                        spans=["s1"],
                    ),
                ]
            ),
            steps=[
                StepIR(
                    step_id="st1",
                    text="Process input",
                    source_span_ids=["s1"],
                    command_type="GENERAL_COMMAND",
                    inputs=["input1"],
                    outputs=["output1"],
                ),
            ],
        )

        result = renderer._render_child_worker(child)
        text = "\n".join(result)

        assert "[DEFINE_WORKER:" in text
        assert "ChildWorker" in text
        assert "[MAIN_FLOW]" in text
        assert "[SEQUENTIAL_BLOCK]" in text
        assert "[END_SEQUENTIAL_BLOCK]" in text
        assert "[END_MAIN_FLOW]" in text
        assert "[END_WORKER]" in text

    def test_render_child_worker_with_steps(self):
        """Test _render_child_worker renders actual steps."""
        renderer = SPLRenderer()
        child = ChildWorkerIR(
            worker_name="ChildWorker",
            description="Child worker task",
            task_text="Do something",
            main_flow=FlowRef(
                blocks=[
                    BlockIR(
                        block_id="b1",
                        block_type="SEQUENTIAL",
                        spans=["s1"],
                    ),
                ]
            ),
            steps=[
                StepIR(
                    step_id="st1",
                    text="Process data",
                    source_span_ids=["s1"],
                    command_type="GENERAL_COMMAND",
                ),
            ],
        )

        result = renderer._render_child_worker(child)
        text = "\n".join(result)

        # Should render the actual step, not synthetic st_child
        assert "Process data" in text or "[COMMAND" in text

    def test_render_child_worker_with_alternative_flows(self):
        """Test _render_child_worker with alternative flows."""
        renderer = SPLRenderer()
        child = ChildWorkerIR(
            worker_name="ChildWorker",
            description="Child worker task",
            task_text="Do something",
            main_flow=FlowRef(
                blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])]
            ),
            alternative_flows=[
                AlternativeFlowRef(
                    flow_id="alt_1",
                    condition_text="if alternative",
                    blocks=[BlockIR(block_id="b2", block_type="IF", spans=["s2"])],
                ),
            ],
            steps=[
                StepIR(step_id="st1", text="Step 1", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
                StepIR(step_id="st2", text="Step 2", source_span_ids=["s2"], command_type="GENERAL_COMMAND"),
            ],
        )

        result = renderer._render_child_worker(child)
        text = "\n".join(result)

        assert "[ALTERNATIVE_FLOW:" in text
        assert "[END_ALTERNATIVE_FLOW]" in text

    def test_render_child_worker_with_exception_flows(self):
        """Test _render_child_worker with exception flows."""
        renderer = SPLRenderer()
        child = ChildWorkerIR(
            worker_name="ChildWorker",
            description="Child worker task",
            task_text="Do something",
            main_flow=FlowRef(
                blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])]
            ),
            exception_flows=[
                ExceptionFlowRef(
                    flow_id="exc_1",
                    condition_text="on error",
                    blocks=[BlockIR(block_id="b2", block_type="SEQUENTIAL", spans=["s2"])],
                ),
            ],
            steps=[
                StepIR(step_id="st1", text="Step 1", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
                StepIR(step_id="st2", text="Handle error", source_span_ids=["s2"], command_type="GENERAL_COMMAND"),
            ],
        )

        result = renderer._render_child_worker(child)
        text = "\n".join(result)

        assert "[EXCEPTION_FLOW:" in text
        assert "[END_EXCEPTION_FLOW]" in text

    def test_render_child_worker_fallback_no_blocks(self):
        """Test _render_child_worker fallback when no blocks."""
        renderer = SPLRenderer()
        child = ChildWorkerIR(
            worker_name="ChildWorker",
            description="Child worker task",
            task_text="Do something important",
            inputs=[WorkerInput(name="input1", required=True)],
            outputs=[WorkerOutput(name="output1", required=True)],
            # No main_flow blocks - should fallback to synthetic step
        )

        result = renderer._render_child_worker(child)
        text = "\n".join(result)

        assert "[MAIN_FLOW]" in text
        assert "[SEQUENTIAL_BLOCK]" in text
        assert "[END_SEQUENTIAL_BLOCK]" in text
        assert "[END_MAIN_FLOW]" in text

    def test_render_block_sequential(self):
        """Test _render_block with SEQUENTIAL block."""
        renderer = SPLRenderer()
        blocks = [BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])]
        steps = [
            StepIR(step_id="st1", text="Do something", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
        ]

        result = renderer._render_blocks(blocks, steps, indent=4)
        text = "\n".join(result)

        assert "[SEQUENTIAL_BLOCK]" in text
        assert "[END_SEQUENTIAL_BLOCK]" in text

    def test_render_block_if(self):
        """Test _render_block with IF block."""
        renderer = SPLRenderer()
        blocks = [BlockIR(block_id="b1", block_type="IF", condition_text="if condition", spans=["s1"])]
        steps = [
            StepIR(step_id="st1", text="Do something", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
        ]

        result = renderer._render_blocks(blocks, steps, indent=4)
        text = "\n".join(result)

        assert "[IF" in text
        assert "[END_IF]" in text

    def test_render_step_general_command(self):
        """Test _render_step with GENERAL_COMMAND."""
        renderer = SPLRenderer()
        step = StepIR(
            step_id="st1",
            text="Process data",
            source_span_ids=["s1"],
            command_type="GENERAL_COMMAND",
            inputs=["input1"],
            outputs=["output1"],
        )
        renderer._command_index = 1

        result = renderer._render_step(step)

        assert "[COMMAND" in result
        assert "Process data" in result

    def test_render_step_call_api(self):
        """Test _render_step with CALL_API."""
        renderer = SPLRenderer()
        step = StepIR(
            step_id="st1",
            text="Call API",
            source_span_ids=["s1"],
            command_type="CALL_API",
            integration_ref="api_1",
            inputs=["input1"],
            outputs=["output1"],
        )
        renderer._command_index = 1

        result = renderer._render_step(step)

        assert "[CALL api_1" in result

    def test_render_step_invoke_worker(self):
        """Test _render_step with INVOKE_WORKER."""
        renderer = SPLRenderer()
        step = StepIR(
            step_id="st1",
            text="Invoke worker",
            source_span_ids=["s1"],
            command_type="INVOKE_WORKER",
            integration_ref="ChildWorker",
            inputs=["input1"],
            outputs=["output1"],
        )
        renderer._command_index = 1

        result = renderer._render_step(step)

        assert "[INVOKE ChildWorker" in result
