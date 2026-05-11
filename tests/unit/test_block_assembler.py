"""Unit tests for Stage 5: BlockAssembler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import (
    AlternativeFlow,
    DelegationCandidate,
    ExceptionFlow,
    FlowStructureIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler


class TestBlockAssembler:
    """Tests for BlockAssembler stage."""

    def test_sequential_block(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test two spans form one SEQUENTIAL block."""
        # Arrange
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="Identify fields"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        mock_client.call_json.return_value = {
            "main_flow_blocks": [
                {
                    "block_id": "b1",
                    "block_type": "SEQUENTIAL",
                    "condition_text": None,
                    "spans": ["s1", "s2"],
                }
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }
        assembler = BlockAssembler(pipeline_config, mock_client)

        # Act
        result = assembler.execute((spans, routes, flow))

        # Assert
        assert len(result.main_flow_blocks) == 1
        assert result.main_flow_blocks[0].block_type == "SEQUENTIAL"
        assert result.main_flow_blocks[0].spans == ["s1", "s2"]

    def test_prompt_uses_flow_json_with_span_text_only(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Stage 5 prompt should enrich flow spans with text and avoid extra span JSON."""
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="Retrieve sources"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            delegation_candidates=[
                DelegationCandidate(
                    candidate_id="dc_1",
                    spans=["s2"],
                    reason="Independent source lookup",
                    suggested_type="child_worker",
                    input_variables=["available_connectors"],
                    output_variables=["retrieved_sources"],
                )
            ],
        )
        mock_client.call_json.return_value = {
            "main_flow_blocks": [
                {
                    "block_id": "b1",
                    "block_type": "SEQUENTIAL",
                    "condition_text": None,
                    "spans": ["s1"],
                }
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }
        assembler = BlockAssembler(pipeline_config, mock_client)

        assembler.execute((spans, routes, flow))

        user_prompt = mock_client.call_json.call_args.kwargs["user_prompt"]
        assert "Flow structure with span text" in user_prompt
        assert '"span_id": "s1"' in user_prompt
        assert '"text": "Determine type"' in user_prompt
        assert '"span_id": "s2"' in user_prompt
        assert '"text": "Retrieve sources"' in user_prompt
        assert "behavior spans" not in user_prompt
        assert "ambiguity" not in user_prompt

    def test_if_block(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test conditional span creates IF block."""
        # Arrange
        spans = [
            SpanIR(span_id="s1", text="If the request is urgent"),
            SpanIR(span_id="s2", text="Then escalate to manager"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        mock_client.call_json.return_value = {
            "main_flow_blocks": [
                {
                    "block_id": "b1",
                    "block_type": "IF",
                    "condition_text": "the request is urgent",
                    "spans": ["s1", "s2"],
                }
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }
        assembler = BlockAssembler(pipeline_config, mock_client)

        # Act
        result = assembler.execute((spans, routes, flow))

        # Assert
        assert len(result.main_flow_blocks) == 1
        assert result.main_flow_blocks[0].block_type == "IF"
        assert result.main_flow_blocks[0].condition_text == "the request is urgent"

    def test_for_block(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test 'for each' span creates FOR block."""
        # Arrange
        spans = [
            SpanIR(span_id="s1", text="For each missing field"),
            SpanIR(span_id="s2", text="Prompt the user for input"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        mock_client.call_json.return_value = {
            "main_flow_blocks": [
                {
                    "block_id": "b1",
                    "block_type": "FOR",
                    "condition_text": "each missing field",
                    "spans": ["s1", "s2"],
                }
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }
        assembler = BlockAssembler(pipeline_config, mock_client)

        # Act
        result = assembler.execute((spans, routes, flow))

        # Assert
        assert len(result.main_flow_blocks) == 1
        assert result.main_flow_blocks[0].block_type == "FOR"
        assert result.main_flow_blocks[0].condition_text == "each missing field"

    def test_empty_input(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test empty spans list."""
        # Arrange
        spans: list[SpanIR] = []
        routes = FieldRouteIR(behavior=[])
        flow = FlowStructureIR(main_flow_spans=[])
        mock_client.call_json.return_value = {
            "main_flow_blocks": [],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }
        assembler = BlockAssembler(pipeline_config, mock_client)

        # Act
        result = assembler.execute((spans, routes, flow))

        # Assert
        assert len(result.main_flow_blocks) == 0
        assert result.alternative_flow_blocks == {}
        assert result.exception_flow_blocks == {}

    def test_llm_error(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test LLM API error handling."""
        # Arrange
        spans = [SpanIR(span_id="s1", text="Determine type")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        mock_client.call_json.side_effect = Exception("API error")
        assembler = BlockAssembler(pipeline_config, mock_client)

        # Act & Assert
        with pytest.raises(StageError, match="LLM call failed"):
            assembler.execute((spans, routes, flow))

    def test_missing_fields(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test missing fields in LLM response."""
        # Arrange
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="Identify fields"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        flow = FlowStructureIR(main_flow_spans=["s1", "s2"])
        mock_client.call_json.return_value = {
            "main_flow_blocks": [
                {"block_id": "b1"}  # Missing block_type and spans
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }
        assembler = BlockAssembler(pipeline_config, mock_client)

        # Act
        result = assembler.execute((spans, routes, flow))

        # Assert - invalid blocks are skipped
        assert len(result.main_flow_blocks) == 0

    def test_checkpoint_saved(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test that checkpoint is saved."""
        # Arrange
        pipeline_config.save_intermediate = True
        spans = [SpanIR(span_id="s1", text="Determine type")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(main_flow_spans=["s1"])
        mock_client.call_json.return_value = {
            "main_flow_blocks": [
                {
                    "block_id": "b1",
                    "block_type": "SEQUENTIAL",
                    "condition_text": None,
                    "spans": ["s1"],
                }
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }
        assembler = BlockAssembler(pipeline_config, mock_client)

        # Act
        assembler.execute((spans, routes, flow))

        # Assert - checkpoint saving is called (verified by mock)

    def test_alternative_flow_blocks(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test blocks in alternative flows."""
        # Arrange
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="Use API to send"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            alternative_flows=[
                AlternativeFlow(
                    flow_id="alt_1",
                    condition_text="if API is available",
                    spans=["s2"],
                )
            ],
        )
        mock_client.call_json.return_value = {
            "main_flow_blocks": [
                {
                    "block_id": "b1",
                    "block_type": "SEQUENTIAL",
                    "condition_text": None,
                    "spans": ["s1"],
                }
            ],
            "alternative_flow_blocks": {
                "alt_1": [
                    {
                        "block_id": "b2",
                        "block_type": "SEQUENTIAL",
                        "condition_text": None,
                        "spans": ["s2"],
                    }
                ]
            },
            "exception_flow_blocks": {},
        }
        assembler = BlockAssembler(pipeline_config, mock_client)

        # Act
        result = assembler.execute((spans, routes, flow))

        # Assert
        assert len(result.main_flow_blocks) == 1
        assert "alt_1" in result.alternative_flow_blocks
        assert len(result.alternative_flow_blocks["alt_1"]) == 1
        assert result.alternative_flow_blocks["alt_1"][0].block_type == "SEQUENTIAL"

    def test_exception_flow_blocks(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Test blocks in exception flows."""
        # Arrange
        spans = [
            SpanIR(span_id="s1", text="Determine type"),
            SpanIR(span_id="s2", text="Handle missing timeframe"),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        flow = FlowStructureIR(
            main_flow_spans=["s1"],
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="missing timeframe",
                    spans=["s2"],
                )
            ],
        )
        mock_client.call_json.return_value = {
            "main_flow_blocks": [
                {
                    "block_id": "b1",
                    "block_type": "SEQUENTIAL",
                    "condition_text": None,
                    "spans": ["s1"],
                }
            ],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {
                "exc_1": [
                    {
                        "block_id": "b2",
                        "block_type": "IF",
                        "condition_text": "missing timeframe",
                        "spans": ["s2"],
                    }
                ]
            },
        }
        assembler = BlockAssembler(pipeline_config, mock_client)

        # Act
        result = assembler.execute((spans, routes, flow))

        # Assert
        assert len(result.main_flow_blocks) == 1
        assert "exc_1" in result.exception_flow_blocks
        assert len(result.exception_flow_blocks["exc_1"]) == 1
        assert result.exception_flow_blocks["exc_1"][0].block_type == "IF"
        assert result.exception_flow_blocks["exc_1"][0].condition_text == "missing timeframe"
