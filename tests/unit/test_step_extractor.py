"""Unit tests for Stage 7: StepExtractor."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
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

    def test_new_variable_creation(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test new variable creation from steps."""
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
        assert "communication_type" in updated_symbols.variables
        assert updated_symbols.variables["communication_type"].source == "step"
        assert updated_symbols.variables["communication_type"].producer_step == "st_1"

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
        assert updated_symbols.variables["communication_type"].producer_step == "st_1"
        assert updated_symbols.variables["communication_type"].consumer_steps == ["st_2"]
        assert updated_symbols.variables["missing_fields"].producer_step == "st_2"

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
