"""Tests for Stage 11 SPLRenderer child worker rendering."""

from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.block_structure_ir import BlockIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import (
    AlternativeFlowRef,
    ChildWorkerIR,
    ExceptionFlowRef,
    FlowRef,
    WorkerInput,
    WorkerIR,
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
        """Empty child worker renders contract with empty main flow — no synthesis."""
        renderer = SPLRenderer()
        child = ChildWorkerIR(
            worker_name="ChildWorker",
            description="Child worker task",
            task_text="Do something important",
            inputs=[WorkerInput(name="input1", required=True)],
            outputs=[WorkerOutput(name="output1", required=True)],
        )

        result = renderer._render_child_worker(child)
        text = "\n".join(result)

        assert "[MAIN_FLOW]" in text
        assert "[END_MAIN_FLOW]" in text
        # No synthetic step — empty flow only declares the contract
        assert "[SEQUENTIAL_BLOCK]" not in text
        assert "Do something important" not in text

    def test_render_child_worker_with_steps_but_no_blocks_uses_real_steps(self):
        """Existing child steps should render instead of synthetic st_child."""
        renderer = SPLRenderer()
        child = ChildWorkerIR(
            worker_name="ChildWorker",
            description="Child worker task",
            task_text="Synthetic fallback should not render",
            steps=[
                StepIR(
                    step_id="st_real",
                    text="Process child-owned work",
                    source_span_ids=["s_child"],
                    command_type="GENERAL_COMMAND",
                )
            ],
        )

        result = renderer._render_child_worker(child)
        text = "\n".join(result)

        assert "Process child-owned work" in text
        assert "Synthetic fallback should not render" not in text
        assert child.steps[0].block_ref == "b_ChildWorker_fallback"

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

    def test_render_main_worker_uses_scoped_steps_not_global_child_steps(self):
        """Main rendering must not select child steps with colliding block ids."""
        renderer = SPLRenderer()
        main_step = StepIR(
            step_id="st_main",
            text="Main work",
            source_span_ids=["s1"],
            command_type="GENERAL_COMMAND",
            outputs=["main_output"],
            block_ref="b1",
        )
        child_step = StepIR(
            step_id="st_child",
            text="Child work",
            source_span_ids=["s2"],
            command_type="GENERAL_COMMAND",
            outputs=["child_output"],
            block_ref="b1",
        )
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Main worker",
            outputs=[WorkerOutput("main_output", True)],
            main_flow=FlowRef([BlockIR("b1", "SEQUENTIAL", spans=["s1"])]),
            steps=[main_step],
            scoped_steps=True,
            child_workers=[
                ChildWorkerIR(
                    worker_name="ChildWorker",
                    description="Child worker",
                    task_text="Child task",
                    outputs=[WorkerOutput("child_output", True)],
                    main_flow=FlowRef([BlockIR("b1", "SEQUENTIAL", spans=["s2"])]),
                    steps=[child_step],
                )
            ],
        )
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("main_output", "text", True, "Main output", "output"),
                VariableSpec("child_output", "text", True, "Child output", "output"),
            ]
        )
        symbols = SymbolTable()
        for variable in resources.variables:
            symbols.declare(
                variable.name,
                variable.data_type,
                variable.source,
                variable.description,
            )

        spl, _, _ = renderer.render(
            worker,
            AgentProfileIR(),
            resources,
            symbols,
            [main_step, child_step],
            [],
        )

        main_worker_section = spl.split('[DEFINE_WORKER: "Main worker" MainWorker]')[1]
        assert "Main work" in main_worker_section
        assert "Child work" not in main_worker_section
