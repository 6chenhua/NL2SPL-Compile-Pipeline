"""Tests for Stage 10 WorkerAssembler worker-scoped methods."""

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_ir import ChildWorkerIR, FlowRef
from nl2spl.ir.worker_plan_ir import (
    ContractFieldIR,
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
    WorkerStepPlanIR,
)
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler


class TestWorkerAssemblerWorkerScoped:
    """Test worker-scoped assembly methods."""

    def _make_worker_plan(self) -> WorkerPlanIR:
        """Create a simple worker plan with main + child worker."""
        return WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    worker_id="w_main",
                    worker_name="MainWorker",
                    kind="main",
                    purpose="Main worker",
                    input_contract=[ContractFieldIR(name="input1", data_type="string", required=True, description="Input", source="input")],
                    output_contract=[ContractFieldIR(name="output1", data_type="string", required=True, description="Output", source="output")],
                ),
                WorkerSpecIR(
                    worker_id="w_child",
                    worker_name="ChildWorker",
                    kind="child",
                    purpose="Child worker task",
                    input_contract=[ContractFieldIR(name="child_in", data_type="string", required=True, description="Child input", source="input")],
                    output_contract=[ContractFieldIR(name="child_out", data_type="string", required=True, description="Child output", source="output")],
                ),
            ],
            handoffs=[
                WorkerHandoffIR(
                    handoff_id="h1",
                    from_worker="w_main",
                    to_worker="w_child",
                    api_ref=None,
                    mode="invoke",
                    condition_text=None,
                    ordering="after",
                ),
            ],
        )

    def test_assemble_from_worker_scoped_single_worker(self):
        """Test assemble_from_worker_scoped with single main worker."""
        assembler = WorkerAssembler()
        worker_plan = WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    worker_id="w_main",
                    worker_name="MainWorker",
                    kind="main",
                    purpose="Main worker",
                ),
            ],
        )
        step_plan = WorkerStepPlanIR(
            main_worker_id="w_main",
            worker_steps={
                "w_main": [
                    StepIR(
                        step_id="st1",
                        text="Do something",
                        source_span_ids=["s1"],
                        command_type="GENERAL_COMMAND",
                    ),
                ],
            },
        )
        resources = ResourceRegistryIR()
        symbol_table = SymbolTable()

        result = assembler.assemble_from_worker_scoped(
            step_plan, resources, symbol_table, worker_plan
        )

        assert result.worker_name == "MainWorker"
        assert len(result.child_workers) == 0
        assert len(result.main_flow.blocks) == 0

    def test_assemble_from_worker_scoped_multiple_workers(self):
        """Test assemble_from_worker_scoped with main + child workers."""
        assembler = WorkerAssembler()
        worker_plan = self._make_worker_plan()
        step_plan = WorkerStepPlanIR(
            main_worker_id="w_main",
            worker_steps={
                "w_main": [
                    StepIR(
                        step_id="st1",
                        text="Main step",
                        source_span_ids=["s1"],
                        command_type="INVOKE_WORKER",
                        integration_ref="ChildWorker",
                    ),
                ],
                "w_child": [
                    StepIR(
                        step_id="st2",
                        text="Child step",
                        source_span_ids=["s2"],
                        command_type="GENERAL_COMMAND",
                    ),
                ],
            },
        )
        resources = ResourceRegistryIR()
        symbol_table = SymbolTable()

        result = assembler.assemble_from_worker_scoped(
            step_plan, resources, symbol_table, worker_plan
        )

        assert result.worker_name == "MainWorker"
        assert len(result.child_workers) == 1
        assert result.child_workers[0].worker_name == "ChildWorker"
        assert len(result.child_workers[0].steps) == 1

    def test_assemble_from_worker_scoped_with_flow(self):
        """Test assemble_from_worker_scoped with flow information."""
        assembler = WorkerAssembler()
        worker_plan = self._make_worker_plan()
        step_plan = WorkerStepPlanIR(
            main_worker_id="w_main",
            worker_steps={
                "w_main": [
                    StepIR(step_id="st1", text="Main step", source_span_ids=["s1"], command_type="INVOKE_WORKER", integration_ref="ChildWorker"),
                ],
                "w_child": [
                    StepIR(step_id="st2", text="Child step", source_span_ids=["s2"], command_type="GENERAL_COMMAND"),
                ],
            },
        )
        flow_plan = WorkerFlowPlanIR(
            worker_flows={
                "w_main": FlowStructureIR(main_flow_spans=["s1"]),
                "w_child": FlowStructureIR(main_flow_spans=["s2"]),
            }
        )
        block_plan = WorkerBlockPlanIR(
            worker_blocks={
                "w_main": BlockStructureIR(main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])]),
                "w_child": BlockStructureIR(main_flow_blocks=[BlockIR(block_id="b2", block_type="SEQUENTIAL", spans=["s2"])]),
            }
        )
        resources = ResourceRegistryIR()
        symbol_table = SymbolTable()

        result = assembler.assemble_from_worker_scoped(
            step_plan, resources, symbol_table, worker_plan, flow_plan, block_plan
        )

        assert len(result.main_flow.blocks) == 1
        assert result.main_flow.blocks[0].block_id == "b1"
        assert len(result.child_workers) == 1
        assert len(result.child_workers[0].main_flow.blocks) == 1
        assert result.child_workers[0].main_flow.blocks[0].block_id == "b2"

    def test_build_child_worker_with_flow(self):
        """Test _build_child_worker with flow."""
        assembler = WorkerAssembler()
        spec = WorkerSpecIR(
            worker_id="w_child",
            worker_name="ChildWorker",
            kind="child",
            purpose="Child task",
        )
        steps = [
            StepIR(step_id="st1", text="Step 1", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
        ]
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])],
        )

        result = assembler._build_child_worker(spec, steps, flow, blocks)

        assert result.worker_name == "ChildWorker"
        assert len(result.steps) == 1
        assert len(result.main_flow.blocks) == 1
        assert result.main_flow.blocks[0].block_id == "b1"

    def test_build_child_worker_with_steps(self):
        """Test _build_child_worker with steps."""
        assembler = WorkerAssembler()
        spec = WorkerSpecIR(
            worker_id="w_child",
            worker_name="ChildWorker",
            kind="child",
            purpose="Child task",
        )
        steps = [
            StepIR(step_id="st1", text="Step 1", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
            StepIR(step_id="st2", text="Step 2", source_span_ids=["s2"], command_type="CALL_API", integration_ref="api_1"),
        ]

        result = assembler._build_child_worker(spec, steps, None, None)

        assert len(result.steps) == 2
        assert "api_1" in result.api_refs

    def test_build_child_worker_with_all_fields(self):
        """Test _build_child_worker with all fields."""
        assembler = WorkerAssembler()
        spec = WorkerSpecIR(
            worker_id="w_child",
            worker_name="ChildWorker",
            kind="child",
            purpose="Child task",
        )
        steps = [
            StepIR(step_id="st1", text="Step 1", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
        ]
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])],
        )

        result = assembler._build_child_worker(spec, steps, flow, blocks)

        assert result.worker_name == "ChildWorker"
        assert len(result.steps) == 1
        assert len(result.main_flow.blocks) == 1

    def test_build_child_worker_with_alternative_flows(self):
        """Test _build_child_worker builds alternative_flows from flow + blocks."""
        assembler = WorkerAssembler()
        spec = WorkerSpecIR(
            worker_id="w_child",
            worker_name="ChildWorker",
            kind="child",
            purpose="Child task",
        )
        steps = [
            StepIR(step_id="st1", text="Main step", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
            StepIR(step_id="st2", text="Alt step", source_span_ids=["s2"], command_type="CALL_API", integration_ref="child_api"),
        ]
        from nl2spl.ir.flow_structure_ir import AlternativeFlow

        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            alternative_flows=[
                AlternativeFlow(flow_id="alt_1", condition_text="if alternative", spans=["s2"]),
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])],
            alternative_flow_blocks={
                "alt_1": [BlockIR(block_id="b2", block_type="IF", condition_text="if alternative", spans=["s2"])],
            },
        )

        result = assembler._build_child_worker(spec, steps, flow, blocks)

        assert len(result.main_flow.blocks) == 1
        assert len(result.alternative_flows) == 1
        assert result.alternative_flows[0].flow_id == "alt_1"
        assert result.alternative_flows[0].condition_text == "if alternative"
        assert len(result.alternative_flows[0].blocks) == 1
        assert result.alternative_flows[0].blocks[0].block_id == "b2"
        assert "child_api" in result.api_refs

    def test_build_child_worker_with_exception_flows(self):
        """Test _build_child_worker builds exception_flows from flow + blocks."""
        assembler = WorkerAssembler()
        spec = WorkerSpecIR(
            worker_id="w_child",
            worker_name="ChildWorker",
            kind="child",
            purpose="Child task",
        )
        steps = [
            StepIR(step_id="st1", text="Main step", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
            StepIR(step_id="st2", text="Handle error", source_span_ids=["s2"], command_type="GENERAL_COMMAND"),
        ]
        from nl2spl.ir.flow_structure_ir import ExceptionFlow

        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(flow_id="exc_1", condition_text="on timeout", spans=["s2"]),
                ExceptionFlow(flow_id="exc_2", condition_text="on auth failure", spans=[]),
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR(block_id="b1", block_type="SEQUENTIAL", spans=["s1"])],
            exception_flow_blocks={
                "exc_1": [BlockIR(block_id="b2", block_type="SEQUENTIAL", spans=["s2"])],
                "exc_2": [],
            },
        )

        result = assembler._build_child_worker(spec, steps, flow, blocks)

        assert len(result.main_flow.blocks) == 1
        assert len(result.exception_flows) == 2
        assert result.exception_flows[0].flow_id == "exc_1"
        assert result.exception_flows[0].condition_text == "on timeout"
        assert len(result.exception_flows[0].blocks) == 1
        assert result.exception_flows[1].flow_id == "exc_2"
        assert result.exception_flows[1].blocks == []

    def test_build_child_worker_without_flow_or_blocks(self):
        """Test _build_child_worker gracefully handles None flow and blocks."""
        assembler = WorkerAssembler()
        spec = WorkerSpecIR(
            worker_id="w_child",
            worker_name="ChildWorker",
            kind="child",
            purpose="Fallback task",
        )
        steps = [
            StepIR(step_id="st1", text="Step 1", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
        ]

        # No flow, no blocks
        result = assembler._build_child_worker(spec, steps, None, None)

        assert result.worker_name == "ChildWorker"
        assert len(result.steps) == 1
        assert result.main_flow.blocks == []
        assert result.alternative_flows == []
        assert result.exception_flows == []
        assert result.api_refs == []

        # Flow but no blocks
        flow = FlowStructureIR(main_flow_spans=["s1"])
        result = assembler._build_child_worker(spec, steps, flow, None)

        assert result.main_flow.blocks == []
        assert result.alternative_flows == []  # No blocks → no alternative flows
        assert result.exception_flows == []   # No blocks → no exception flows

    def test_assemble_from_worker_scoped_child_inputs_outputs_from_contract(self):
        """Test child worker inputs/outputs match WorkerSpecIR contracts."""
        assembler = WorkerAssembler()
        worker_plan = WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    worker_id="w_main",
                    worker_name="MainWorker",
                    kind="main",
                    purpose="Main",
                    input_contract=[
                        ContractFieldIR("main_in", "text", True, "Main input", source="input"),
                    ],
                    output_contract=[
                        ContractFieldIR("main_out", "text", True, "Main output", source="output"),
                    ],
                ),
                WorkerSpecIR(
                    worker_id="w_child",
                    worker_name="ChildWorker",
                    kind="child",
                    purpose="Child task",
                    input_contract=[
                        ContractFieldIR("child_in", "object", True, "Child input", source="input"),
                        ContractFieldIR("opt_in", "text", False, "Optional input", source="input"),
                    ],
                    output_contract=[
                        ContractFieldIR("child_out", "list", True, "Child output", source="output"),
                    ],
                ),
            ],
            handoffs=[
                WorkerHandoffIR(
                    handoff_id="h1",
                    from_worker="w_main",
                    to_worker="w_child",
                    api_ref=None,
                    mode="invoke",
                    condition_text=None,
                    ordering="after",
                ),
            ],
        )
        step_plan = WorkerStepPlanIR(
            main_worker_id="w_main",
            worker_steps={
                "w_main": [
                    StepIR(
                        step_id="st1",
                        text="Invoke ChildWorker",
                        source_span_ids=["s1"],
                        command_type="INVOKE_WORKER",
                        integration_ref="ChildWorker",
                    ),
                ],
                "w_child": [
                    StepIR(
                        step_id="st2",
                        text="Child step",
                        source_span_ids=["s2"],
                        command_type="GENERAL_COMMAND",
                    ),
                ],
            },
        )

        result = assembler.assemble_from_worker_scoped(
            step_plan, ResourceRegistryIR(), SymbolTable(), worker_plan
        )

        assert len(result.child_workers) == 1
        child = result.child_workers[0]
        assert child.worker_name == "ChildWorker"

        # Verify inputs from contract
        assert len(child.inputs) == 2
        assert child.inputs[0].name == "child_in"
        assert child.inputs[0].required is True
        assert child.inputs[1].name == "opt_in"
        assert child.inputs[1].required is False

        # Verify outputs from contract
        assert len(child.outputs) == 1
        assert child.outputs[0].name == "child_out"
        assert child.outputs[0].required is True

    def test_assemble_from_worker_scoped_handoff_contract_consistency(self):
        """Test Stage 10 child inputs/outputs consistent with WorkerSpecIR contracts.

        Stage 10 uses WorkerSpecIR.input_contract/output_contract directly.
        Stage 6 produces HandoffContractIR from handoff bindings.
        Both should agree on the child worker's interface variables.
        """
        assembler = WorkerAssembler()
        worker_plan = WorkerPlanIR(
            main_worker_id="w_main",
            workers=[
                WorkerSpecIR(
                    worker_id="w_main",
                    worker_name="MainWorker",
                    kind="main",
                    purpose="Main",
                    input_contract=[
                        ContractFieldIR("query", "text", True, "Query", source="input"),
                    ],
                    output_contract=[
                        ContractFieldIR("result", "text", True, "Result", source="output"),
                    ],
                ),
                WorkerSpecIR(
                    worker_id="w_child",
                    worker_name="ChildWorker",
                    kind="child",
                    purpose="Child task",
                    input_contract=[
                        ContractFieldIR("child_query", "text", True, "Child query", source="input"),
                    ],
                    output_contract=[
                        ContractFieldIR("child_result", "object", True, "Child result", source="output"),
                    ],
                ),
            ],
            handoffs=[
                WorkerHandoffIR(
                    handoff_id="h1",
                    from_worker="w_main",
                    to_worker="w_child",
                    api_ref=None,
                    mode="invoke",
                    condition_text=None,
                    ordering="after",
                    input_bindings=[],
                    output_bindings=[],
                ),
            ],
        )
        step_plan = WorkerStepPlanIR(
            main_worker_id="w_main",
            worker_steps={
                "w_main": [
                    StepIR(
                        step_id="st1",
                        text="Invoke ChildWorker",
                        source_span_ids=["s1"],
                        command_type="INVOKE_WORKER",
                        integration_ref="ChildWorker",
                    ),
                ],
                "w_child": [
                    StepIR(
                        step_id="st2",
                        text="Child step",
                        source_span_ids=["s2"],
                        command_type="GENERAL_COMMAND",
                    ),
                ],
            },
        )

        result = assembler.assemble_from_worker_scoped(
            step_plan, ResourceRegistryIR(), SymbolTable(), worker_plan
        )

        child_spec = worker_plan.workers[1]
        child_worker = result.child_workers[0]
        assert [i.name for i in child_worker.inputs] == [
            f.name for f in child_spec.input_contract
        ]
        assert [o.name for o in child_worker.outputs] == [
            f.name for f in child_spec.output_contract
        ]

    def test_build_child_worker_invoke_text_fallback(self):
        """Test _build_child_worker uses invoke_text when provided."""
        assembler = WorkerAssembler()
        spec = WorkerSpecIR(
            worker_id="w_child",
            worker_name="ChildWorker",
            kind="child",
            purpose="Child task",
            reason="Legacy reason",
        )
        steps = [
            StepIR(step_id="st1", text="Step 1", source_span_ids=["s1"], command_type="GENERAL_COMMAND"),
        ]

        # With invoke_text, task_text should be the invoke text
        result = assembler._build_child_worker(spec, steps, None, None, invoke_text="Invoke: ChildWorker")
        assert result.task_text == "Invoke: ChildWorker"

        # Without invoke_text, task_text should fall back to purpose
        result = assembler._build_child_worker(spec, steps, None, None)
        assert result.task_text == "Child task"

        # Without invoke_text and purpose, fall back to reason
        spec_no_purpose = WorkerSpecIR(
            worker_id="w_child2",
            worker_name="ChildWorker2",
            kind="child",
            purpose="",
            reason="Legacy reason for worker",
        )
        result = assembler._build_child_worker(spec_no_purpose, steps, None, None)
        assert result.task_text == "Legacy reason for worker"
