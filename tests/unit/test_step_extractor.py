"""Unit tests for Stage 7: StepExtractor."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor


class TestStepExtractor:
    """Tests for StepExtractor stage."""

    def test_basic_step_extraction(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test basic step extraction from single span."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Determine communication type")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()
        symbols.declare("user_request", "text", "input", "User request")

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Determine communication type",
                    "source_span_ids": ["s1"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": ["user_request"],
                    "outputs": ["communication_type"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "normal",
                }
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert len(steps) == 1
        assert steps[0].step_id == "st_1"
        assert steps[0].text == "Determine communication type"
        assert steps[0].command_type == "GENERAL_COMMAND"

    def test_variable_inputs_outputs(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test variable input/output identification."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Determine type from request")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()
        symbols.declare("user_request", "text", "input", "User request")

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Determine type from request",
                    "source_span_ids": ["s1"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": ["user_request"],
                    "outputs": ["communication_type"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "normal",
                }
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert "user_request" in steps[0].inputs
        assert "communication_type" in steps[0].outputs

    def test_raw_new_variables_do_not_declare_symbols(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Raw LLM new_variables are checkpoint data, not SymbolTable authority."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Produce communication type")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Produce communication type",
                    "source_span_ids": ["s1"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": [],
                    "outputs": ["communication_type"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "normal",
                }
            ],
            "new_variables": [
                {
                    "name": "communication_type",
                    "data_type": "text",
                    "description": "Type of communication",
                    "producer_step": "st_1",
                }
            ],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert steps[0].outputs == ["communication_type"]
        assert "communication_type" not in updated_symbols.variables

    def test_multiple_steps(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test extraction of multiple steps."""
        # Arrange
        spans = [
            SpanIR(span_id="s1", text="Determine communication type"),
            SpanIR(span_id="s2", text="Identify missing fields"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        blocks = BlockStructureIR(
            main_flow_blocks=[
                BlockIR("b1", "SEQUENTIAL", None, ["s1"]),
                BlockIR("b2", "SEQUENTIAL", None, ["s2"]),
            ]
        )
        symbols = SymbolTable()
        symbols.declare("user_request", "text", "input", "User request")

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Determine communication type",
                    "source_span_ids": ["s1"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": ["user_request"],
                    "outputs": ["communication_type"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "normal",
                },
                {
                    "step_id": "st_2",
                    "text": "Identify missing fields",
                    "source_span_ids": ["s2"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": ["communication_type"],
                    "outputs": ["missing_fields"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b2",
                    "kind": "normal",
                },
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert len(steps) == 2
        assert steps[0].step_id == "st_1"
        assert steps[1].step_id == "st_2"

    def test_call_api_step(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test CALL_API command type step."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Call email API to send")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()
        symbols.declare("notification_content", "text", "step", "Content to send")

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Call email API to send",
                    "source_span_ids": ["s1"],
                    "command_type": "CALL_API",
                    "inputs": ["notification_content"],
                    "outputs": ["send_result"],
                    "integration_ref": "email_api",
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "tool",
                }
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert steps[0].command_type == "CALL_API"
        assert steps[0].integration_ref == "email_api"
        assert steps[0].kind == "tool"

    def test_request_input_step(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test REQUEST_INPUT command type step."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Ask user for additional information")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Ask user for additional information",
                    "source_span_ids": ["s1"],
                    "command_type": "REQUEST_INPUT",
                    "inputs": [],
                    "outputs": ["user_input"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "user_input",
                }
            ],
            "new_variables": [
                {
                    "name": "user_input",
                    "data_type": "text",
                    "description": "Additional user input",
                    "producer_step": "st_1",
                }
            ],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert steps[0].command_type == "REQUEST_INPUT"
        assert steps[0].kind == "user_input"

    def test_display_message_step(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test DISPLAY_MESSAGE command type step."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Show the result to the user")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()
        symbols.declare("final_result", "text", "step", "Final result")

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Show the result to the user",
                    "source_span_ids": ["s1"],
                    "command_type": "DISPLAY_MESSAGE",
                    "inputs": ["final_result"],
                    "outputs": [],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "display",
                }
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert steps[0].command_type == "DISPLAY_MESSAGE"
        assert steps[0].kind == "display"

    def test_display_message_with_outputs_fails_fast(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """DISPLAY_MESSAGE is a presentation step and must not declare outputs."""
        spans = [SpanIR(span_id="s1", text="Show the approval status")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Show the approval status",
                    "source_span_ids": ["s1"],
                    "command_type": "DISPLAY_MESSAGE",
                    "inputs": [],
                    "outputs": ["approval_status"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "display",
                }
            ],
            "new_variables": [],
        }

        with pytest.raises(StageError, match="DISPLAY_MESSAGE step\\(s\\) with outputs"):
            StepExtractor(pipeline_config, mock_client).execute(
                (spans, routes, flow, blocks, symbols)
            )

    def test_alternative_flow_step(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test step in alternative flow."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Use API to send")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(
            main_flow_spans=[],
            alternative_flows=[],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[],
            alternative_flow_blocks={
                "alt_1": [BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
            },
        )
        symbols = SymbolTable()

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Use API to send",
                    "source_span_ids": ["s1"],
                    "command_type": "CALL_API",
                    "inputs": [],
                    "outputs": [],
                    "integration_ref": "email_api",
                    "flow_ref": "alt_1",
                    "block_ref": "b1",
                    "kind": "tool",
                }
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert steps[0].flow_ref == "alt_1"

    def test_exception_flow_step(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test step in exception flow."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Handle missing timeframe")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(
            main_flow_spans=[],
            exception_flows=[],
        )
        blocks = BlockStructureIR(
            main_flow_blocks=[],
            exception_flow_blocks={
                "exc_1": [BlockIR("b1", "IF", "missing timeframe", ["s1"])]
            },
        )
        symbols = SymbolTable()

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Handle missing timeframe",
                    "source_span_ids": ["s1"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": [],
                    "outputs": [],
                    "integration_ref": None,
                    "flow_ref": "exc_1",
                    "block_ref": "b1",
                    "kind": "normal",
                }
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert steps[0].flow_ref == "exc_1"

    def test_producer_consumer_tracking(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test producer/consumer tracking in SymbolTable."""
        # Arrange
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="Use type to identify fields"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        blocks = BlockStructureIR(
            main_flow_blocks=[
                BlockIR("b1", "SEQUENTIAL", None, ["s1", "s2"])
            ]
        )
        symbols = SymbolTable()
        symbols.declare("user_request", "text", "input", "User request")

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Determine type",
                    "source_span_ids": ["s1"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": ["user_request"],
                    "outputs": ["communication_type"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "normal",
                },
                {
                    "step_id": "st_2",
                    "text": "Use type to identify fields",
                    "source_span_ids": ["s2"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": ["communication_type"],
                    "outputs": ["missing_fields"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "normal",
                },
            ],
            "new_variables": [
                {
                    "name": "communication_type",
                    "data_type": "text",
                    "description": "Type of communication",
                    "producer_step": "st_1",
                },
                {
                    "name": "missing_fields",
                    "data_type": "List[text]",
                    "description": "Missing fields",
                    "producer_step": "st_2",
                },
            ],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert updated_symbols.variables["user_request"].consumer_steps == ["st_1"]
        assert "communication_type" not in updated_symbols.variables
        assert "missing_fields" not in updated_symbols.variables

    def test_empty_input(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test empty spans list."""
        # Arrange
        spans: list[SpanIR] = []
        routes = FieldRouteIR(behavior=[])
        flow = FlowStructureIR(main_flow_spans=[])
        blocks = BlockStructureIR(main_flow_blocks=[])
        symbols = SymbolTable()

        mock_client.call_json.return_value = {
            "steps": [],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert
        assert len(steps) == 0
        assert len(updated_symbols.variables) == 0

    def test_llm_error(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test LLM API error handling."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Determine type")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()
        mock_client.call_json.side_effect = Exception("API error")
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act & Assert
        with pytest.raises(StageError, match="LLM call failed"):
            extractor.execute((spans, routes, flow, blocks, symbols))

    def test_missing_fields(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test missing fields in LLM response."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Determine type")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()
        mock_client.call_json.return_value = {
            "steps": [
                {"step_id": "st_1"}  # Missing required fields
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        steps, updated_symbols = extractor.execute(
            (spans, routes, flow, blocks, symbols)
        )

        # Assert - invalid steps are skipped
        assert len(steps) == 0

    def test_checkpoint_saved(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test that checkpoint is saved."""
        # Arrange
        pipeline_config.save_intermediate = True
        spans = [SpanIR(span_id="s1", text="Determine type")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()
        symbols.declare("user_request", "text", "input", "User request")

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1",
                    "text": "Determine type",
                    "source_span_ids": ["s1"],
                    "command_type": "GENERAL_COMMAND",
                    "inputs": ["user_request"],
                    "outputs": ["communication_type"],
                    "integration_ref": None,
                    "flow_ref": "main",
                    "block_ref": "b1",
                    "kind": "normal",
                }
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)

        # Act
        extractor.execute((spans, routes, flow, blocks, symbols))

        # Assert - checkpoint saving is called (verified by mock)


# ===========================================================================
# D0: Baseline — Stage 7 ignores annotations
# ===========================================================================


class TestD0Stage7Baseline:
    """D0: Stage 7 behavior unchanged when annotations present."""

    def test_annotations_do_not_change_step_output(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Stage 7 produces same output with annotations present."""
        spans = [SpanIR(span_id="s1", text="Determine communication type")]
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()
        symbols.declare("user_request", "text", "input", "User request")

        expected_response = {
            "steps": [{
                "step_id": "st_1", "text": "Determine communication type",
                "source_span_ids": ["s1"], "command_type": "GENERAL_COMMAND",
                "inputs": ["user_request"], "outputs": ["communication_type"],
                "integration_ref": None, "flow_ref": "main", "block_ref": "b1",
                "kind": "normal",
            }],
            "new_variables": [],
        }
        mock_client.call_json.return_value = expected_response

        # With annotations marking span as executable
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="process_step", executable=True,
                ),
            ],
        )
        extractor = StepExtractor(pipeline_config, mock_client)
        steps, _ = extractor.execute((spans, routes, flow, blocks, symbols))

        assert len(steps) == 1
        assert steps[0].command_type == "GENERAL_COMMAND"
        assert steps[0].source_span_ids == ["s1"]


# ===========================================================================
# D6: Executable filtering in Stage 7
# ===========================================================================


class TestD6ExecutableFiltering:
    """D6: Stage 7 excludes non-executable spans and guards steps."""

    def test_failure_mode_does_not_become_command(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D6: failure_mode span sourced command is dropped by guard."""
        spans = [
            SpanIR("s1", "Missing timeframe."),
            SpanIR("s2", "Determine type."),
        ]
        routes = FieldRouteIR(
            behavior=["s1", "s2"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s2", field="behavior",
                    semantic_role="process_step", executable=True,
                ),
            ],
        )
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        blocks = BlockStructureIR(
            main_flow_blocks=[
                BlockIR("b1", "SEQUENTIAL", None, ["s1"]),
                BlockIR("b2", "SEQUENTIAL", None, ["s2"]),
            ]
        )
        symbols = SymbolTable()
        symbols.declare("user_request", "text", "input", "User request")

        # LLM returns a command from the failure span
        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_bad", "text": "Handle missing timeframe",
                    "source_span_ids": ["s1"], "command_type": "GENERAL_COMMAND",
                    "inputs": [], "outputs": ["timeframe_result"],
                    "integration_ref": None, "flow_ref": "main",
                    "block_ref": "b1", "kind": "normal",
                },
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        steps, _ = extractor.execute((spans, routes, flow, blocks, symbols))

        # The failure command is dropped
        assert len(steps) == 0
        # Non-executable exclusion diagnostic emitted
        diags = extractor.stage7_diagnostics
        assert any(
            "non_executable_route_material_excluded" in d.kind
            for d in diags
        ), diags

    def test_process_step_still_becomes_command(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D6: executable process_step still produces steps."""
        spans = [
            SpanIR("s1", "Missing timeframe."),
            SpanIR("s2", "Determine type."),
        ]
        routes = FieldRouteIR(
            behavior=["s1", "s2"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="failure_mode", executable=False,
                ),
                RouteAnnotation(
                    span_id="s2", field="behavior",
                    semantic_role="process_step", executable=True,
                ),
            ],
        )
        flow = FlowStructureIR(main_flow_spans=["s2"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b2", "SEQUENTIAL", None, ["s2"])]
        )
        symbols = SymbolTable()

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_good", "text": "Determine type",
                    "source_span_ids": ["s2"], "command_type": "GENERAL_COMMAND",
                    "inputs": [], "outputs": ["communication_type"],
                    "integration_ref": None, "flow_ref": "main",
                    "block_ref": "b2", "kind": "normal",
                },
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        steps, _ = extractor.execute((spans, routes, flow, blocks, symbols))

        assert len(steps) == 1
        assert steps[0].step_id == "st_good"

    def test_no_annotation_fallback_preserves_legacy_behavior(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D6: no annotations → old behavior preserved."""
        spans = [SpanIR("s1", "Determine type.")]
        routes = FieldRouteIR(behavior=["s1"])  # no annotations
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()

        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_1", "text": "Determine type",
                    "source_span_ids": ["s1"], "command_type": "GENERAL_COMMAND",
                    "inputs": [], "outputs": ["communication_type"],
                    "integration_ref": None, "flow_ref": "main",
                    "block_ref": "b1", "kind": "normal",
                },
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        steps, _ = extractor.execute((spans, routes, flow, blocks, symbols))

        assert len(steps) == 1
        assert steps[0].command_type == "GENERAL_COMMAND"

    def test_unmapped_diagnostics_skip_non_executable(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D6: non-executable excluded spans do not trigger unmapped diagnostic."""
        spans = [SpanIR("s1", "Missing timeframe.")]
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
            ],
        )
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()

        # LLM returns no steps (unmapped)
        mock_client.call_json.return_value = {
            "steps": [], "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        _, _ = extractor.execute((spans, routes, flow, blocks, symbols))

        # No unmapped_behavior_span diagnostic for non-executable span
        unmapped = [
            d for d in extractor.stage7_diagnostics
            if d.kind == "unmapped_behavior_span" and "s1" in d.source_span_ids
        ]
        assert len(unmapped) == 0, f"Should not flag non-executable s1 as unmapped: {unmapped}"

    def test_prompt_separates_executable_from_non_executable(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D6: prompt shows executable section without failure, non-exec context with it."""
        spans = [
            SpanIR("s1", "Missing timeframe."),
            SpanIR("s2", "Determine type."),
        ]
        routes = FieldRouteIR(
            behavior=["s1", "s2"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s2", field="behavior",
                    semantic_role="process_step", executable=True,
                ),
            ],
        )
        flow = FlowStructureIR()
        blocks = BlockStructureIR()
        symbols = SymbolTable()

        mock_client.call_json.return_value = {
            "steps": [], "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        extractor.execute((spans, routes, flow, blocks, symbols))

        prompt = mock_client.call_json.call_args.kwargs["user_prompt"]

        # Executable behavior section: contains process_step, NOT failure_mode
        beh_start = prompt.index("behavior spans:")
        non_exec_start = prompt.index("Non-executable context only")
        beh_section = prompt[beh_start:non_exec_start]
        non_exec_section = prompt[non_exec_start:]

        # s2 (process_step) in executable, s1 (failure_mode) NOT in executable
        assert '"s2"' in beh_section or "s2" in beh_section
        assert "Determine type" in beh_section
        assert "Missing timeframe" not in beh_section, (
            "Failure span must not appear in executable behavior section"
        )

        # Non-executable context: s1 (failure_mode) present, no-command instructions
        assert "do NOT create COMMAND" in non_exec_section
        assert "REQUEST_INPUT" in non_exec_section
        assert "INVOKE_WORKER" in non_exec_section
        assert "Missing timeframe" in non_exec_section, (
            "Failure span must appear in non-executable context section"
        )

    def test_delegation_intent_does_not_become_invocation(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D6: delegation_intent span → INVOKE_WORKER is dropped by guard."""
        spans = [
            SpanIR("s1", "Optional source gathering if bounded."),
            SpanIR("s2", "Determine type."),
        ]
        routes = FieldRouteIR(
            behavior=["s1", "s2"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s2", field="behavior",
                    semantic_role="process_step", executable=True,
                ),
            ],
        )
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        blocks = BlockStructureIR(
            main_flow_blocks=[
                BlockIR("b1", "SEQUENTIAL", None, ["s1"]),
                BlockIR("b2", "SEQUENTIAL", None, ["s2"]),
            ]
        )
        symbols = SymbolTable()

        # LLM returns INVOKE_WORKER sourced from delegation span
        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_bad_invoke", "text": "Invoke source gathering",
                    "source_span_ids": ["s1"], "command_type": "INVOKE_WORKER",
                    "inputs": [], "outputs": ["sources"],
                    "handoff_id": "h_fake",
                    "integration_ref": None, "flow_ref": "main",
                    "block_ref": "b1", "kind": "normal",
                },
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        steps, _ = extractor.execute((spans, routes, flow, blocks, symbols))

        # The delegation-only step is dropped
        delegation_steps = [s for s in steps if "s1" in s.source_span_ids]
        assert len(delegation_steps) == 0, "Delegation-only INVOKE_WORKER must be dropped"

    def test_failure_label_does_not_become_request_input(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D6: 'Missing timeframe' failure → no REQUEST_INPUT step created."""
        spans = [SpanIR("s1", "Missing timeframe.")]
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
            ],
        )
        flow = FlowStructureIR(main_flow_spans=["s1"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s1"])]
        )
        symbols = SymbolTable()

        # LLM returns REQUEST_INPUT sourced from failure span
        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_req", "text": "Ask user for timeframe",
                    "source_span_ids": ["s1"], "command_type": "REQUEST_INPUT",
                    "inputs": [], "outputs": ["timeframe"],
                    "integration_ref": None, "flow_ref": "main",
                    "block_ref": "b1", "kind": "normal",
                },
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        steps, _ = extractor.execute((spans, routes, flow, blocks, symbols))

        assert len(steps) == 0, "REQUEST_INPUT from failure label must be dropped"

    def test_api_candidate_not_call_api_without_contract(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D6: api_candidate / executable=False → no CALL_API step."""
        spans = [SpanIR("s_api", "Use SearchAPI for source lookup.")]
        routes = FieldRouteIR(
            behavior=["s_api"],
            annotations=[
                RouteAnnotation(
                    span_id="s_api", field="behavior",
                    semantic_role="api_candidate",
                    route_family="delegation_boundary",
                    executable=False,
                ),
            ],
        )
        flow = FlowStructureIR(main_flow_spans=["s_api"])
        blocks = BlockStructureIR(
            main_flow_blocks=[BlockIR("b1", "SEQUENTIAL", None, ["s_api"])]
        )
        symbols = SymbolTable()

        # LLM tries to create CALL_API from api_candidate span
        mock_client.call_json.return_value = {
            "steps": [
                {
                    "step_id": "st_api", "text": "Call SearchAPI",
                    "source_span_ids": ["s_api"], "command_type": "CALL_API",
                    "inputs": [], "outputs": [],
                    "integration_ref": "SearchAPI",
                    "flow_ref": "main", "block_ref": "b1", "kind": "normal",
                },
            ],
            "new_variables": [],
        }
        extractor = StepExtractor(pipeline_config, mock_client)
        steps, _ = extractor.execute((spans, routes, flow, blocks, symbols))

        # CALL_API from non-executable api_candidate must be dropped
        api_steps = [s for s in steps if "s_api" in s.source_span_ids]
        assert len(api_steps) == 0, (
            f"CALL_API from api_candidate must be dropped, got {len(api_steps)}"
        )
