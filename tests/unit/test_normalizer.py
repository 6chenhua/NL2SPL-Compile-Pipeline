"""Unit tests for Stage 9.5: IRNormalizer."""

from __future__ import annotations

from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.flow_structure_ir import DelegationCandidate, ExceptionFlow, FlowStructureIR
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR, VariableSpec
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage9_5_normalizer import IRNormalizer


class TestIRNormalizer:
    """Tests for IRNormalizer."""

    def test_reference_validation_unknown_variable(self) -> None:
        """Test validation of unknown variable references."""
        # Arrange
        normalizer = IRNormalizer()
        steps = [StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND", inputs=["unknown_var"])]
        constraints = []
        symbols = SymbolTable()
        resources = ResourceRegistryIR()

        # Act
        _, _, _, _, _, errors, _ = normalizer.normalize(
            FlowStructureIR(), BlockStructureIR(), resources, symbols, steps, constraints
        )

        # Assert
        assert any("unknown_var" in e for e in errors)

    def test_reference_validation_unknown_api(self) -> None:
        """Test validation of unknown API references."""
        # Arrange
        normalizer = IRNormalizer()
        steps = [StepIR("st1", "Test", ["s1"], "CALL_API", integration_ref="unknown_api")]
        constraints = []
        symbols = SymbolTable()
        resources = ResourceRegistryIR()

        # Act
        _, _, _, _, _, errors, _ = normalizer.normalize(
            FlowStructureIR(), BlockStructureIR(), resources, symbols, steps, constraints
        )

        # Assert
        assert any("unknown_api" in e for e in errors)

    def test_reference_validation_unknown_step_target(self) -> None:
        """Test validation of unknown step target in constraints."""
        # Arrange
        normalizer = IRNormalizer()
        steps = []
        constraints = [
            ConstraintIR(
                "c1",
                "test",
                "prohibition",
                targets=["step:unknown_step"],
                source_span_ids=[],
            )
        ]
        symbols = SymbolTable()
        resources = ResourceRegistryIR()

        # Act
        _, _, _, _, _, errors, _ = normalizer.normalize(
            FlowStructureIR(), BlockStructureIR(), resources, symbols, steps, constraints
        )

        # Assert
        assert any("unknown_step" in e for e in errors)

    def test_reference_validation_unknown_variable_target(self) -> None:
        """Test validation of unknown variable target in constraints."""
        # Arrange
        normalizer = IRNormalizer()
        steps = []
        constraints = [
            ConstraintIR(
                "c1",
                "test",
                "prohibition",
                targets=["variable:unknown_var"],
                source_span_ids=[],
            )
        ]
        symbols = SymbolTable()
        resources = ResourceRegistryIR()

        # Act
        _, _, _, _, _, errors, _ = normalizer.normalize(
            FlowStructureIR(), BlockStructureIR(), resources, symbols, steps, constraints
        )

        # Assert
        assert any("unknown_var" in e for e in errors)

    def test_coverage_validation_uncovered_spans(self) -> None:
        """Test validation of uncovered spans."""
        # Arrange
        normalizer = IRNormalizer()
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        steps = [StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND")]

        # Act
        _, _, _, _, _, _, warnings = normalizer.normalize(
            flow, BlockStructureIR(), ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Assert
        assert any("s2" in w for w in warnings)

    def test_coverage_validation_all_covered(self) -> None:
        """Test validation when all spans are covered."""
        # Arrange
        normalizer = IRNormalizer()
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        steps = [
            StepIR("st1", "Test 1", ["s1"], "GENERAL_COMMAND"),
            StepIR("st2", "Test 2", ["s2"], "GENERAL_COMMAND"),
        ]

        # Act
        _, _, _, _, _, _, warnings = normalizer.normalize(
            flow, BlockStructureIR(), ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Assert
        assert not any("not covered" in w for w in warnings)

    def test_reconcile_steps_flow_ref(self) -> None:
        """Test reconciliation of step flow_ref."""
        # Arrange
        normalizer = IRNormalizer()
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR()
        steps = [StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND", flow_ref="")]

        # Act
        _, _, normalized_steps, _, _, _, _ = normalizer.normalize(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Assert
        assert normalized_steps[0].flow_ref == "main"

    def test_reconcile_steps_block_ref(self) -> None:
        """Test reconciliation of step block_ref."""
        # Arrange
        normalizer = IRNormalizer()
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        steps = [StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND", block_ref="")]

        # Act
        _, _, normalized_steps, _, _, _, _ = normalizer.normalize(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Assert
        assert normalized_steps[0].block_ref == "b1"

    def test_reconcile_constraints_empty_targets(self) -> None:
        """Test reconciliation of constraint targets."""
        # Arrange
        normalizer = IRNormalizer()
        constraints = [ConstraintIR("c1", "test", "prohibition", targets=[], source_span_ids=[])]

        # Act
        _, _, _, normalized_constraints, _, _, _ = normalizer.normalize(
            FlowStructureIR(),
            BlockStructureIR(),
            ResourceRegistryIR(),
            SymbolTable(),
            [],
            constraints,
        )

        # Assert
        assert normalized_constraints[0].targets == ["global"]

    def test_reconcile_constraints_existing_targets(self) -> None:
        """Test that existing constraint targets are preserved."""
        # Arrange
        normalizer = IRNormalizer()
        constraints = [
            ConstraintIR("c1", "test", "prohibition", targets=["step:st1"], source_span_ids=[])
        ]

        # Act
        _, _, _, normalized_constraints, _, _, _ = normalizer.normalize(
            FlowStructureIR(),
            BlockStructureIR(),
            ResourceRegistryIR(),
            SymbolTable(),
            [],
            constraints,
        )

        # Assert
        assert normalized_constraints[0].targets == ["step:st1"]

    def test_valid_configuration_no_errors(self) -> None:
        """Test that valid configuration produces no errors."""
        # Arrange
        normalizer = IRNormalizer()
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        resources = ResourceRegistryIR(
            variables=[VariableSpec("var1", "text", True, "Test", "input")],
            apis=[APISpec("api1", "none", "Test API")],
        )
        symbols = SymbolTable()
        symbols.declare("var1", "text", "input", "Test")
        steps = [
            StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND", inputs=["var1"], outputs=["var1"])
        ]
        constraints = []

        # Act
        _, _, _, _, _, errors, warnings = normalizer.normalize(
            flow, blocks, resources, symbols, steps, constraints
        )

        # Assert
        assert len(errors) == 0

    def test_multiple_errors(self) -> None:
        """Test that multiple errors are collected."""
        # Arrange
        normalizer = IRNormalizer()
        steps = [
            StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND", inputs=["var1", "var2"]),
            StepIR("st2", "Test", ["s2"], "CALL_API", integration_ref="api1"),
        ]
        constraints = [
            ConstraintIR("c1", "test", "prohibition", targets=["step:st3"], source_span_ids=[])
        ]
        symbols = SymbolTable()
        resources = ResourceRegistryIR()

        # Act
        _, _, _, _, _, errors, _ = normalizer.normalize(
            FlowStructureIR(), BlockStructureIR(), resources, symbols, steps, constraints
        )

        # Assert
        assert len(errors) >= 3  # var1, var2, st3

    def test_empty_configuration(self) -> None:
        """Test normalization with empty configuration."""
        # Arrange
        normalizer = IRNormalizer()

        # Act
        flow, blocks, steps, constraints, symbols, errors, warnings = normalizer.normalize(
            FlowStructureIR(),
            BlockStructureIR(),
            ResourceRegistryIR(),
            SymbolTable(),
            [],
            [],
        )

        # Assert
        assert len(errors) == 0
        assert len(warnings) == 0
        assert len(steps) == 0
        assert len(constraints) == 0

    def test_alternative_flow_coverage(self) -> None:
        """Test coverage validation with alternative flows."""
        # Arrange
        normalizer = IRNormalizer()
        from nl2spl.ir.flow_structure_ir import AlternativeFlow

        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            alternative_flows=[AlternativeFlow("alt_1", "condition", ["s2"])],
        )
        steps = [StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND")]

        # Act
        _, _, _, _, _, _, warnings = normalizer.normalize(
            flow, BlockStructureIR(), ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Assert
        assert any("s2" in w for w in warnings)

    def test_exception_flow_coverage(self) -> None:
        """Test coverage validation with exception flows."""
        # Arrange
        normalizer = IRNormalizer()

        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[ExceptionFlow("exc_1", "error", ["s2"])],
        )
        steps = [StepIR("st1", "Test", ["s1"], "GENERAL_COMMAND")]

        # Act
        _, _, _, _, _, _, warnings = normalizer.normalize(
            flow, BlockStructureIR(), ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Assert
        assert any("s2" in w for w in warnings)

    def test_non_exception_conditional_flow_moves_to_main(self) -> None:
        """Test normal conditional work is not kept as an exception flow."""
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s1", "s3"],
            exception_flows=[
                ExceptionFlow("exc_1", "If sources are needed and available", ["s2"])
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[
                BlockIR("b1", "SEQUENTIAL", None, ["s1"]),
                BlockIR("b3", "SEQUENTIAL", None, ["s3"]),
            ],
            exception_flow_blocks={
                "exc_1": [BlockIR("b2", "IF", "If sources are needed and available", ["s2"])]
            },
        )
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("available_connectors", "List[text]", True, "Connectors", "input")
            ]
        )
        symbols = SymbolTable()
        symbols.declare("available_connectors", "List[text]", "input", "Connectors")
        steps = [
            StepIR("st1", "Prepare", ["s1"], "GENERAL_COMMAND"),
            StepIR(
                "st2",
                "Retrieve sources using approved recipes",
                ["s2"],
                "GENERAL_COMMAND",
                inputs=["available_connectors"],
                outputs=["retrieved_sources"],
                flow_ref="exc_1",
                block_ref="b2",
            ),
            StepIR("st3", "Draft", ["s3"], "GENERAL_COMMAND"),
        ]

        normalized_flow, normalized_blocks, normalized_steps, *_ = normalizer.normalize(
            flow, blocks, resources, symbols, steps, []
        )

        assert normalized_flow.exception_flows == []
        assert normalized_flow.main_flow_spans == ["s1", "s2", "s3"]
        assert [block.block_id for block in normalized_blocks.main_flow_blocks] == [
            "b1",
            "b2",
            "b3",
        ]
        assert normalized_steps[1].flow_ref == "main"
        assert normalized_steps[1].block_ref == "b2"

    def test_unresolved_invoke_worker_is_rejected(self) -> None:
        """Test unresolved worker calls produce validation errors."""
        normalizer = IRNormalizer()
        steps = [
            StepIR(
                "st1",
                "Produce a draft",
                ["s1"],
                "INVOKE_WORKER",
                outputs=["draft"],
                kind="invoke",
            )
        ]
        symbols = SymbolTable()
        symbols.declare("draft", "text", "output", "Draft")
        resources = ResourceRegistryIR(
            variables=[VariableSpec("draft", "text", True, "Draft", "output")]
        )

        _, _, normalized_steps, _, _, errors, _ = normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            resources,
            symbols,
            steps,
            [],
        )

        assert normalized_steps[0].command_type == "INVOKE_WORKER"
        assert normalized_steps[0].kind == "invoke"
        assert any("no concrete child worker" in error for error in errors)

    def test_invoke_worker_resolves_to_matching_delegation_candidate(self) -> None:
        """Test worker calls get concrete targets from delegation candidates."""
        normalizer = IRNormalizer()
        steps = [
            StepIR(
                "st1",
                "Produce a draft",
                ["s1"],
                "INVOKE_WORKER",
                outputs=["draft"],
                kind="invoke",
            )
        ]
        symbols = SymbolTable()
        symbols.declare("draft", "text", "output", "Draft")
        resources = ResourceRegistryIR(
            variables=[VariableSpec("draft", "text", True, "Draft", "output")]
        )

        _, _, normalized_steps, _, _, errors, warnings = normalizer.normalize(
            FlowStructureIR(
                main_flow_spans=["s1"],
                delegation_candidates=[
                    DelegationCandidate(
                        "dc_1",
                        ["s1"],
                        "Drafting can be delegated.",
                        "child_worker",
                        [],
                        ["draft"],
                    )
                ],
            ),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            resources,
            symbols,
            steps,
            [],
        )

        assert errors == []
        assert normalized_steps[0].command_type == "INVOKE_WORKER"
        assert normalized_steps[0].integration_ref == "child_dc_1"
        assert any("delegation candidate dc_1" in warning for warning in warnings)

    def test_required_outputs_get_normal_path_producers(self) -> None:
        """Test missing required outputs are produced on the main path."""
        normalizer = IRNormalizer()
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("draft", "text", True, "Draft", "output"),
                VariableSpec("assumptions_log", "text", True, "Assumptions", "output"),
                VariableSpec("completion_status", "boolean", True, "Status", "output"),
            ]
        )
        symbols = SymbolTable()
        for var in resources.variables:
            symbols.declare(var.name, var.data_type, var.source, var.description)
        steps = [
            StepIR("st1", "Produce a draft", ["s1"], "GENERAL_COMMAND", outputs=["draft"])
        ]

        _, blocks, normalized_steps, _, symbols, _, _ = normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            resources,
            symbols,
            steps,
            [],
        )

        main_outputs = {
            output
            for step in normalized_steps
            if step.flow_ref == "main"
            for output in step.outputs
        }
        synthetic_steps = [step for step in normalized_steps if not step.source_span_ids]
        assert {"draft", "assumptions_log", "completion_status"} <= main_outputs
        assert all(
            step.block_ref == blocks.main_flow_blocks[-1].block_id
            for step in synthetic_steps
        )
        assert symbols.variables["assumptions_log"].producer_step is not None

    def test_source_retrieval_uses_available_connectors_not_unproduced_planning_vars(self) -> None:
        """Test source retrieval consumes runtime connectors instead of orphan variables."""
        normalizer = IRNormalizer()
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("available_connectors", "List[text]", True, "Connectors", "input"),
                VariableSpec("needed_sources", "List[text]", True, "Needed sources", "step"),
                VariableSpec("approved_recipes", "List[text]", True, "Recipes", "step"),
                VariableSpec("retrieved_sources", "List[text]", True, "Retrieved", "step"),
            ]
        )
        symbols = SymbolTable()
        for var in resources.variables:
            symbols.declare(var.name, var.data_type, var.source, var.description)
        steps = [
            StepIR(
                "st1",
                "Retrieve sources using approved source recipes",
                ["s1"],
                "GENERAL_COMMAND",
                inputs=["needed_sources", "approved_recipes"],
                outputs=["retrieved_sources"],
            )
        ]

        _, _, normalized_steps, _, _, _, _ = normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            resources,
            symbols,
            steps,
            [],
        )

        assert normalized_steps[0].inputs == ["available_connectors"]
