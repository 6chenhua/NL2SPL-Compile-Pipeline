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
        """Missing required outputs emit diagnostics, not synthetic steps."""
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

        _, _, normalized_steps, _, symbols, _, _ = normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            resources,
            symbols,
            steps,
            [],
        )

        # No synthetic steps should be created
        synthetic_steps = [step for step in normalized_steps if not step.source_span_ids]
        assert len(synthetic_steps) == 0

        # Existing source-backed step is preserved
        assert normalized_steps[0].step_id == "st1"
        assert normalized_steps[0].outputs == ["draft"]

        # Diagnostics emitted for missing producers
        missing_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "missing_output_producer"
        ]
        assert len(missing_diags) == 2  # assumptions_log, completion_status
        missing_outputs = {d.target_ref for d in missing_diags}
        assert "variable:assumptions_log" in missing_outputs
        assert "variable:completion_status" in missing_outputs

    def test_all_outputs_satisfied_emit_no_missing_producer_diagnostics(self) -> None:
        """When all required outputs have step producers, no diagnostics are emitted."""
        normalizer = IRNormalizer()
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("draft", "text", True, "Draft", "output"),
                VariableSpec("log", "text", True, "Log", "output"),
            ]
        )
        symbols = SymbolTable()
        for var in resources.variables:
            symbols.declare(var.name, var.data_type, var.source, var.description)
        steps = [
            StepIR("st1", "Produce draft", ["s1"], "GENERAL_COMMAND", outputs=["draft"]),
            StepIR("st2", "Produce log", ["s2"], "GENERAL_COMMAND", outputs=["log"]),
        ]

        normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1", "s2"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1", "s2"])]),
            resources,
            symbols,
            steps,
            [],
        )

        missing_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "missing_output_producer"
        ]
        assert len(missing_diags) == 0

    def test_required_output_without_producer_remains_declared(self) -> None:
        """Required output stays in resource registry even without a producer."""
        normalizer = IRNormalizer()
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("report", "text", True, "Final report", "output"),
            ]
        )
        symbols = SymbolTable()
        symbols.declare("report", "text", "output", "Final report")

        normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            resources,
            symbols,
            [StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")],
            [],
        )

        # Output is still declared in resources
        output_vars = [v for v in resources.variables if v.name == "report"]
        assert len(output_vars) == 1
        assert output_vars[0].required is True
        assert output_vars[0].source == "output"

        # Diagnostic is emitted
        missing_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "missing_output_producer"
        ]
        assert len(missing_diags) == 1
        assert missing_diags[0].target_ref == "variable:report"

    def test_missing_output_producer_does_not_obscure_validation_errors(self) -> None:
        """Validation errors and compile diagnostics coexist independently."""
        normalizer = IRNormalizer()
        resources = ResourceRegistryIR(
            variables=[
                VariableSpec("report", "text", True, "Final report", "output"),
            ]
        )
        symbols = SymbolTable()
        symbols.declare("report", "text", "output", "Final report")
        # Step references undeclared variable (validation error) + output has no
        # producer (compile diagnostic) — both must appear.
        steps = [
            StepIR(
                "st1", "Do work", ["s1"], "GENERAL_COMMAND",
                inputs=["undeclared_var"],
            )
        ]

        _, _, _, _, _, errors, _ = normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            resources,
            symbols,
            steps,
            [],
        )

        # Validation error still present
        assert any("undeclared_var" in e for e in errors)

        # Compile diagnostic still present
        missing_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "missing_output_producer"
        ]
        assert len(missing_diags) == 1

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

    # =========================================================================
    # TODO 3: Partial exception flow preservation
    # =========================================================================

    def test_exception_flow_without_handler_emits_missing_handler(self) -> None:
        """Exception flow with no handler blocks or steps → missing_handler."""
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    spans=["s2"],
                )
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
            # No exception_flow_blocks for exc_1
        )
        steps = [
            StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
        ]

        normalizer.normalize(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        missing_handler_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "missing_handler"
        ]
        assert len(missing_handler_diags) == 1
        assert missing_handler_diags[0].target_ref == "exception_flow:exc_1"
        assert "Missing timeframe" in missing_handler_diags[0].message
        assert not missing_handler_diags[0].blocks_rendering
        assert missing_handler_diags[0].blocks_completion

    def test_exception_flow_with_handler_step_does_not_emit_missing_handler(
        self,
    ) -> None:
        """Exception flow with a handler step → no missing_handler diagnostic."""
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    spans=["s2"],
                )
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
            exception_flow_blocks={
                "exc_1": [BlockIR("b_exc", "SEQUENTIAL", None, ["s2"])],
            },
        )
        steps = [
            StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
            StepIR(
                "st2",
                "Ask user for timeframe",
                ["s2"],
                "REQUEST_INPUT",
                flow_ref="exc_1",
                block_ref="b_exc",
            ),
        ]

        normalizer.normalize(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        missing_handler_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "missing_handler"
        ]
        assert len(missing_handler_diags) == 0

    def test_exception_flow_block_without_step_still_missing_handler(
        self,
    ) -> None:
        """Blocks without a handler step → missing_handler still fires."""
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    spans=["s2"],
                )
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
            exception_flow_blocks={
                # Block exists but no step references exc_1
                "exc_1": [BlockIR("b_exc", "SEQUENTIAL", None, ["s2"])],
            },
        )
        steps = [
            StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
        ]

        normalizer.normalize(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        missing_handler_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "missing_handler"
        ]
        assert len(missing_handler_diags) == 1
        assert "exc_1" in missing_handler_diags[0].target_ref

    def test_exception_flow_preserved_even_without_handler(self) -> None:
        """Exception flow without handler stays in the flow structure."""
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    spans=["s2"],
                )
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
        )
        steps = [
            StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
        ]

        normalized_flow, _, _, _, _, _, _ = normalizer.normalize(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Exception flow is preserved (not removed)
        assert len(normalized_flow.exception_flows) == 1
        assert normalized_flow.exception_flows[0].flow_id == "exc_1"
        assert normalized_flow.exception_flows[0].condition_text == "Missing timeframe."

    def test_multiple_exception_flows_partial_handler_coverage(self) -> None:
        """Mixed: one exception flow has handler, another doesn't."""
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Missing timeframe.",
                    spans=["s2"],
                ),
                ExceptionFlow(
                    flow_id="exc_2",
                    condition_text="Invalid input.",
                    spans=["s3"],
                ),
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
            exception_flow_blocks={
                "exc_2": [BlockIR("b_exc2", "SEQUENTIAL", None, ["s3"])],
            },
        )
        steps = [
            StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
            StepIR(
                "st2",
                "Report invalid input",
                ["s3"],
                "GENERAL_COMMAND",
                flow_ref="exc_2",
                block_ref="b_exc2",
            ),
        ]

        normalizer.normalize(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Only exc_1 is missing a handler
        missing_handler_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "missing_handler"
        ]
        assert len(missing_handler_diags) == 1
        assert "exc_1" in missing_handler_diags[0].target_ref

    # =========================================================================
    # TODO 4: type_or_contract_ambiguity + assumed_command_not_renderable
    # =========================================================================

    def test_call_api_without_integration_ref_is_ambiguity(self) -> None:
        """CALL_API without integration_ref emits type_or_contract_ambiguity."""
        normalizer = IRNormalizer()
        steps = [
            StepIR("st1", "Call external API", ["s1"], "CALL_API"),
        ]

        normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            ResourceRegistryIR(),
            SymbolTable(),
            steps,
            [],
        )

        ambiguity_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "type_or_contract_ambiguity"
        ]
        assert len(ambiguity_diags) >= 1
        assert any("st1" in d.target_ref for d in ambiguity_diags)
        assert any(d.blocks_rendering for d in ambiguity_diags)

    def test_invoke_worker_without_target_is_ambiguity(self) -> None:
        """INVOKE_WORKER without integration_ref emits ambiguity."""
        normalizer = IRNormalizer()
        steps = [
            StepIR("st1", "Delegate to worker", ["s1"], "INVOKE_WORKER"),
        ]

        normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            ResourceRegistryIR(),
            SymbolTable(),
            steps,
            [],
        )

        ambiguity_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "type_or_contract_ambiguity"
        ]
        assert any(
            "INVOKE_WORKER" in d.message for d in ambiguity_diags
        )

    def test_request_input_without_source_span_is_ambiguity(self) -> None:
        """REQUEST_INPUT with empty source_span_ids emits ambiguity."""
        normalizer = IRNormalizer()
        steps = [
            StepIR("st1", "Ask user for input", [], "REQUEST_INPUT"),
        ]

        normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            ResourceRegistryIR(),
            SymbolTable(),
            steps,
            [],
        )

        ambiguity_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "type_or_contract_ambiguity"
        ]
        assert any(
            "REQUEST_INPUT" in d.message and "no source-span" in d.message
            for d in ambiguity_diags
        )

    def test_source_backed_step_is_not_assumed(self) -> None:
        """Step with source_span_ids is not flagged as assumed."""
        normalizer = IRNormalizer()
        steps = [
            StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
        ]

        normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            ResourceRegistryIR(),
            SymbolTable(),
            steps,
            [],
        )

        assumed_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "assumed_command_not_renderable"
        ]
        assert len(assumed_diags) == 0

    def test_synthetic_step_without_source_is_assumed_not_renderable(self) -> None:
        """Step with empty source_span_ids, no handoff, no unpack → assumed."""
        normalizer = IRNormalizer()
        steps = [
            StepIR("st1", "Synthetic fallback", [], "GENERAL_COMMAND"),
        ]

        normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            ResourceRegistryIR(),
            SymbolTable(),
            steps,
            [],
        )

        assumed_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "assumed_command_not_renderable"
        ]
        assert len(assumed_diags) == 1
        assert assumed_diags[0].target_ref == "step:st1"
        assert assumed_diags[0].blocks_rendering is True
        assert assumed_diags[0].blocks_completion is True

    def test_compiler_unpack_step_is_not_assumed(self) -> None:
        """Compiler unpack steps (metadata.origin=compiler_unpack) are not assumed."""
        normalizer = IRNormalizer()
        steps = [
            StepIR(
                "st_unpack",
                "Extract field from structured",
                [],
                "GENERAL_COMMAND",
                metadata={"origin": "compiler_unpack"},
            ),
        ]

        normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            ResourceRegistryIR(),
            SymbolTable(),
            steps,
            [],
        )

        assumed_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "assumed_command_not_renderable"
        ]
        assert len(assumed_diags) == 0

    def test_handoff_step_is_not_assumed_in_legacy_path(self) -> None:
        """Legacy path: any non-None handoff_id bypasses assumed check."""
        normalizer = IRNormalizer()
        steps = [
            StepIR(
                "st_handoff",
                "Invoke child worker",
                [],
                "INVOKE_WORKER",
                integration_ref="ChildWorker",
                handoff_id="h1",
            ),
        ]

        normalizer.normalize(
            FlowStructureIR(main_flow_spans=["s1"]),
            BlockStructureIR(main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]),
            ResourceRegistryIR(),
            SymbolTable(),
            steps,
            [],
        )

        assumed_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "assumed_command_not_renderable"
        ]
        assert len(assumed_diags) == 0

    # =========================================================================
    # TODO 8: Anti-fabrication end-to-end behavior tests
    # =========================================================================

    def test_no_failure_source_no_exception_flow_no_missing_handler(self) -> None:
        """When there are no exception flows, no missing_handler is emitted."""
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
        )
        steps = [StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND")]

        normalizer.normalize(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        missing_handler_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "missing_handler"
        ]
        assert len(missing_handler_diags) == 0

    def test_vague_exception_policy_handler_is_assumed(self) -> None:
        """Exception flow with a handler step that has no source spans → assumed.

        The exception flow skeleton is preserved (partial SPL), but the
        handler step is flagged as assumed and will be blocked by the gate.
        """
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Handle failures properly.",
                    spans=["s_fail"],
                )
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
            exception_flow_blocks={
                "exc_1": [BlockIR("b_exc", "SEQUENTIAL", None, ["s_fail"])],
            },
        )
        steps = [
            StepIR("st1", "Do work", ["s1"], "GENERAL_COMMAND"),
            StepIR(
                "st_fail", "Handle failures", [], "GENERAL_COMMAND",
                flow_ref="exc_1", block_ref="b_exc",
            ),
        ]

        normalizer.normalize(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Handler step exists → no missing_handler ...
        missing_handler_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "missing_handler"
        ]
        assert len(missing_handler_diags) == 0

        # ... but the handler step is assumed (no source evidence)
        assumed_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "assumed_command_not_renderable"
        ]
        assert any(
            "st_fail" in d.target_ref for d in assumed_diags
        ), f"Expected assumed handler, got {[d.target_ref for d in assumed_diags]}"

        # Exception flow is preserved
        assert len(flow.exception_flows) == 1

    def test_incomplete_delegation_no_executable_child(self) -> None:
        """INVOKE_WORKER without integration_ref → ambiguity + assumed."""
        normalizer = IRNormalizer()
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            delegation_candidates=[
                DelegationCandidate(
                    candidate_id="dc_1",
                    spans=["s1"],
                    reason="Delegation mentioned but target unclear.",
                    suggested_type="child_worker",
                    input_variables=[],
                    output_variables=[],
                )
            ],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])],
        )
        steps = [
            StepIR("st1", "Delegate work", [], "INVOKE_WORKER"),
        ]

        normalizer.normalize(
            flow, blocks, ResourceRegistryIR(), SymbolTable(), steps, []
        )

        # Ambiguity: INVOKE_WORKER without target
        ambiguity_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "type_or_contract_ambiguity"
        ]
        assert any(
            "INVOKE_WORKER" in d.message for d in ambiguity_diags
        ), "Incomplete delegation should produce ambiguity"

        # Also assumed (no source_span_ids)
        assumed_diags = [
            d for d in normalizer.diagnostics
            if d.kind == "assumed_command_not_renderable"
        ]
        assert any(
            "st1" in d.target_ref for d in assumed_diags
        ), "INVOKE_WORKER without source is assumed, not renderable"
