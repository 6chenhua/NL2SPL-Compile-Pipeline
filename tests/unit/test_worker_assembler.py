"""Unit tests for Stage 10: WorkerAssembler."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import AlternativeFlow, ExceptionFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage10_worker_assembler import WorkerAssembler


class TestWorkerAssembler:
    """Tests for WorkerAssembler."""

    def test_basic_assembly(self) -> None:
        """Test basic worker assembly."""
        # Arrange
        assembler = WorkerAssembler()
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        steps = [StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND")]
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("user_request", "text", True, "User request", "input"),
                VariableSpec("draft", "text", True, "Draft", "output"),
            ]
        )
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert len(worker.inputs) == 1
        assert len(worker.outputs) == 1
        assert worker.inputs[0].name == "user_request"
        assert worker.outputs[0].name == "draft"
        assert worker.worker_name == "MainWorker"

    def test_multiple_inputs_outputs(self) -> None:
        """Test assembly with multiple inputs and outputs."""
        # Arrange
        assembler = WorkerAssembler()
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        steps = []
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("input1", "text", True, "Input 1", "input"),
                VariableSpec("input2", "text", False, "Input 2", "input"),
                VariableSpec("output1", "text", True, "Output 1", "output"),
                VariableSpec("output2", "text", False, "Output 2", "output"),
            ]
        )
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert len(worker.inputs) == 2
        assert len(worker.outputs) == 2
        assert worker.inputs[0].required is True
        assert worker.inputs[1].required is False

    def test_alternative_flows(self) -> None:
        """Test assembly with alternative flows."""
        # Arrange
        assembler = WorkerAssembler()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            alternative_flows=[
                AlternativeFlow("alt_1", "condition", ["s2"]),
                AlternativeFlow("alt_2", "condition2", ["s3"]),
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
            alternative_flow_blocks={
                "alt_1": [BlockIR("b2", "SEQUENTIAL", None, ["s2"])],
                "alt_2": [BlockIR("b3", "SEQUENTIAL", None, ["s3"])],
            },
        )
        steps = []
        resources = ResourceRegistryIR()
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert len(worker.alternative_flows) == 2
        assert worker.alternative_flows[0].flow_id == "alt_1"
        assert worker.alternative_flows[1].flow_id == "alt_2"

    def test_exception_flows(self) -> None:
        """Test assembly with exception flows."""
        # Arrange
        assembler = WorkerAssembler()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow("exc_1", "error", ["s2"]),
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
            exception_flow_blocks={
                "exc_1": [BlockIR("b2", "SEQUENTIAL", None, ["s2"])],
            },
        )
        steps = []
        resources = ResourceRegistryIR()
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert len(worker.exception_flows) == 1
        assert worker.exception_flows[0].flow_id == "exc_1"

    def test_api_refs(self) -> None:
        """Test assembly with API references."""
        # Arrange
        assembler = WorkerAssembler()
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        steps = []
        from nl2spl.ir.resource_registry_ir import APISpec

        resources = ResourceRegistryIR(
            apis=[
                APISpec("api1", "none", "API 1"),
                APISpec("api2", "none", "API 2"),
            ]
        )
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert len(worker.api_refs) == 2
        assert "api1" in worker.api_refs
        assert "api2" in worker.api_refs

    def test_child_worker_refs(self) -> None:
        """Test assembly with child worker references."""
        # Arrange
        assembler = WorkerAssembler()
        from nl2spl.ir.flow_structure_ir import DelegationCandidate

        flow = FlowStructureIR(
            delegation_candidates=[
                DelegationCandidate("dc_1", ["s1"], "reason", "child_worker"),
                DelegationCandidate("dc_2", ["s2"], "reason", "api_call"),
            ],
        )
        blocks = BlockStructureIR()
        steps = []
        resources = ResourceRegistryIR()
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert len(worker.child_worker_refs) == 1
        assert "child_dc_1" in worker.child_worker_refs
        assert len(worker.child_workers) == 1
        assert worker.child_workers[0].worker_name == "child_dc_1"

    def test_child_worker_definitions_use_invoke_step_io(self) -> None:
        """Test child worker definitions mirror the resolved invocation."""
        assembler = WorkerAssembler()
        from nl2spl.ir.flow_structure_ir import DelegationCandidate

        flow = FlowStructureIR(
            delegation_candidates=[
                DelegationCandidate(
                    "dc_1",
                    ["s1"],
                    "Source gathering can be delegated.",
                    "child_worker",
                    ["needed_sources"],
                    ["retrieved_sources"],
                )
            ],
        )
        steps = [
            StepIR(
                "st1",
                "Retrieve sources using approved source recipes",
                ["s1"],
                "INVOKE_WORKER",
                inputs=["available_connectors"],
                outputs=["retrieved_sources"],
                integration_ref="child_dc_1",
            )
        ]
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("available_connectors", "List[text]", True, "Connectors", "input"),
                VariableSpec("retrieved_sources", "List[text]", True, "Sources", "step"),
            ]
        )

        worker = assembler.assemble(flow, BlockStructureIR(), steps, resources, SymbolTable())

        assert worker.child_workers[0].inputs[0].name == "available_connectors"
        assert worker.child_workers[0].outputs[0].name == "retrieved_sources"
        assert worker.child_workers[0].task_text == "Retrieve sources using approved source recipes"

    def test_empty_configuration(self) -> None:
        """Test assembly with empty configuration."""
        # Arrange
        assembler = WorkerAssembler()
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        steps = []
        resources = ResourceRegistryIR()
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert len(worker.inputs) == 0
        assert len(worker.outputs) == 0
        assert len(worker.alternative_flows) == 0
        assert len(worker.exception_flows) == 0
        assert len(worker.api_refs) == 0
        assert len(worker.child_worker_refs) == 0

    def test_main_flow_blocks(self) -> None:
        """Test that main flow blocks are correctly assembled."""
        # Arrange
        assembler = WorkerAssembler()
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        blocks = BlockStructureIR(
            main_flow_blocks=[
                BlockIR("b1", "SEQUENTIAL", None, ["s1"]),
                BlockIR("b2", "IF", None, ["s2"]),
            ]
        )
        steps = []
        resources = ResourceRegistryIR()
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert len(worker.main_flow.blocks) == 2
        assert worker.main_flow.blocks[0].block_id == "b1"
        assert worker.main_flow.blocks[1].block_id == "b2"

    def test_worker_name_and_description(self) -> None:
        """Test worker name and description."""
        # Arrange
        assembler = WorkerAssembler()
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        steps = []
        resources = ResourceRegistryIR()
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert worker.worker_name == "MainWorker"
        assert worker.description == "Main worker"

    def test_input_output_required_flags(self) -> None:
        """Test that required flags are preserved."""
        # Arrange
        assembler = WorkerAssembler()
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        steps = []
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("req_input", "text", True, "Required", "input"),
                VariableSpec("opt_input", "text", False, "Optional", "input"),
                VariableSpec("req_output", "text", True, "Required", "output"),
                VariableSpec("opt_output", "text", False, "Optional", "output"),
            ]
        )
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert worker.inputs[0].required is True
        assert worker.inputs[1].required is False
        assert worker.outputs[0].required is True
        assert worker.outputs[1].required is False

    def test_step_variables_not_in_inputs_outputs(self) -> None:
        """Test that step variables are not included in inputs/outputs."""
        # Arrange
        assembler = WorkerAssembler()
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        steps = []
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("input_var", "text", True, "Input", "input"),
                VariableSpec("step_var", "text", True, "Step", "step"),
                VariableSpec("output_var", "text", True, "Output", "output"),
            ]
        )
        symbols = SymbolTable()

        # Act
        worker = assembler.assemble(flow, blocks, steps, resources, symbols)

        # Assert
        assert len(worker.inputs) == 1
        assert len(worker.outputs) == 1
        assert worker.inputs[0].name == "input_var"
        assert worker.outputs[0].name == "output_var"
