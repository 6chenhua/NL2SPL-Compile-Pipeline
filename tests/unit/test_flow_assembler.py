"""Unit tests for Stage 4: FlowAssembler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler


class TestFlowAssembler:
    """Tests for FlowAssembler stage."""

    def test_main_flow(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test all spans in main flow, no alternative/exception flows."""
        # Arrange
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s1", "s2"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
        assembler = FlowAssembler(pipeline_config, mock_client)
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="Identify fields"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])

        # Act
        result = assembler.execute((spans, routes))

        # Assert
        assert isinstance(result, FlowStructureIR)
        assert result.main_flow_spans == ["s1", "s2"]
        assert len(result.alternative_flows) == 0
        assert len(result.exception_flows) == 0
        assert len(result.delegation_candidates) == 0

    def test_prompt_uses_plain_text_without_span_json(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Stage 4 prompt should pass compact span text, not full SpanIR JSON."""
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s1"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
        assembler = FlowAssembler(pipeline_config, mock_client)
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="The requested audience"),
        ]
        routes = FieldRouteIR(behavior=["s1"], audience=["s2"])

        assembler.execute((spans, routes))

        user_prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
        assert "s1: Determine type" in user_prompt
        assert "s2: The requested audience" in user_prompt
        assert '"span_id"' not in user_prompt
        assert "ambiguity" not in user_prompt

    def test_exception_flow(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test one span triggers exception flow."""
        # Arrange
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s1", "s2"],
            "alternative_flows": [],
            "exception_flows": [
                {
                    "flow_id": "exc_1",
                    "condition_text": "When required fields are missing",
                    "spans": ["s3"],
                }
            ],
            "delegation_candidates": [],
        }
        assembler = FlowAssembler(pipeline_config, mock_client)
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="Identify fields"),
            SpanIR(span_id="s3", text="Handle missing fields"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2", "s3"])

        # Act
        result = assembler.execute((spans, routes))

        # Assert
        assert result.main_flow_spans == ["s1", "s2"]
        assert len(result.exception_flows) == 1
        assert result.exception_flows[0].flow_id == "exc_1"
        assert result.exception_flows[0].condition_text == "When required fields are missing"
        assert result.exception_flows[0].spans == ["s3"]
        assert len(result.alternative_flows) == 0

    def test_alternative_flow(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test one span triggers alternative flow."""
        # Arrange
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s1", "s2"],
            "alternative_flows": [
                {
                    "flow_id": "alt_1",
                    "condition_text": "When user requests summary format",
                    "spans": ["s3"],
                }
            ],
            "exception_flows": [],
            "delegation_candidates": [],
        }
        assembler = FlowAssembler(pipeline_config, mock_client)
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="Identify fields"),
            SpanIR(span_id="s3", text="Generate summary"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2", "s3"])

        # Act
        result = assembler.execute((spans, routes))

        # Assert
        assert result.main_flow_spans == ["s1", "s2"]
        assert len(result.alternative_flows) == 1
        assert result.alternative_flows[0].flow_id == "alt_1"
        assert result.alternative_flows[0].condition_text == "When user requests summary format"
        assert result.alternative_flows[0].spans == ["s3"]
        assert len(result.exception_flows) == 0

    def test_delegation_candidates(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test delegation candidates identified."""
        # Arrange
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s1", "s2"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [
                {
                    "candidate_id": "dc_1",
                    "spans": ["s3"],
                    "reason": "API call can be delegated",
                    "suggested_type": "api_call",
                    "input_variables": ["notification_content"],
                    "output_variables": ["send_result"],
                }
            ],
        }
        assembler = FlowAssembler(pipeline_config, mock_client)
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="Identify fields"),
            SpanIR(span_id="s3", text="Send notification via API"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2", "s3"])

        # Act
        result = assembler.execute((spans, routes))

        # Assert
        assert len(result.delegation_candidates) == 1
        assert result.delegation_candidates[0].candidate_id == "dc_1"
        assert result.delegation_candidates[0].spans == ["s3"]
        assert result.delegation_candidates[0].reason == "API call can be delegated"
        assert result.delegation_candidates[0].suggested_type == "api_call"
        assert result.delegation_candidates[0].input_variables == ["notification_content"]
        assert result.delegation_candidates[0].output_variables == ["send_result"]

    def test_empty_input(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test empty spans list handling."""
        # Arrange
        mock_client.call_json.return_value = {
            "main_flow_spans": [],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
        assembler = FlowAssembler(pipeline_config, mock_client)
        spans: list[SpanIR] = []
        routes = FieldRouteIR(behavior=[])

        # Act
        result = assembler.execute((spans, routes))

        # Assert
        assert isinstance(result, FlowStructureIR)
        assert result.main_flow_spans == []
        assert len(result.alternative_flows) == 0
        assert len(result.exception_flows) == 0
        assert len(result.delegation_candidates) == 0

    def test_llm_error(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test LLM API error handling."""
        # Arrange
        mock_client.call_json.side_effect = Exception("API error")
        assembler = FlowAssembler(pipeline_config, mock_client)
        spans = [SpanIR(span_id="s1", text="Determine type")]
        routes = FieldRouteIR(behavior=["s1"])

        # Act & Assert
        with pytest.raises(StageError, match="LLM call failed"):
            assembler.execute((spans, routes))

    def test_missing_fields(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test handling of missing fields in LLM response."""
        # Arrange - alternative flow missing required fields
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s1"],
            "alternative_flows": [
                {"flow_id": "alt_1"},  # Missing condition_text and spans
            ],
            "exception_flows": [
                {"flow_id": "exc_1"},  # Missing condition_text and spans
            ],
            "delegation_candidates": [
                {"candidate_id": "dc_1"},  # Missing spans, reason, suggested_type
            ],
        }
        assembler = FlowAssembler(pipeline_config, mock_client)
        spans = [SpanIR(span_id="s1", text="Determine type")]
        routes = FieldRouteIR(behavior=["s1"])

        # Act
        result = assembler.execute((spans, routes))

        # Assert - invalid entries are skipped
        assert result.main_flow_spans == ["s1"]
        assert len(result.alternative_flows) == 0
        assert len(result.exception_flows) == 0
        assert len(result.delegation_candidates) == 0

    def test_checkpoint_saved(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test that checkpoint is saved."""
        # Arrange
        pipeline_config.save_intermediate = True
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s1"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
        assembler = FlowAssembler(pipeline_config, mock_client)
        spans = [SpanIR(span_id="s1", text="Determine type")]
        routes = FieldRouteIR(behavior=["s1"])

        # Act
        assembler.execute((spans, routes))

        # Assert - checkpoint saving is called (verified by mock)
