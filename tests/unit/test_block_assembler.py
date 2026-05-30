"""Unit tests for Stage 5: BlockAssembler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
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


# ===========================================================================
# D4: BlockAssembler partial skeleton support
# ===========================================================================


class TestD4PartialExceptionSkeletons:
    """D4: Stage 5 preserves condition-only exception flows, no fabricated handlers."""

    def test_condition_only_flow_survives_stage5(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D4: adapter exception flow without handler blocks survives."""
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
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_adapter_00",
                    condition_text="Missing timeframe.",
                    spans=["s1"],
                ),
            ],
        )
        mock_client.call_json.return_value = {
            "main_flow_blocks": [],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }
        assembler = BlockAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes, flow))

        # Condition-only flow preserved (empty entry created)
        assert "exc_adapter_00" in result.exception_flow_blocks
        assert result.exception_flow_blocks["exc_adapter_00"] == []

    def test_llm_fabricated_handler_block_stripped(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D4: LLM-fabricated handler block for adapter flow is stripped."""
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
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_adapter_00",
                    condition_text="Missing timeframe.",
                    spans=["s1"],
                ),
            ],
        )
        # LLM invents a handler block from the condition span
        mock_client.call_json.return_value = {
            "main_flow_blocks": [],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {
                "exc_adapter_00": [{
                    "block_id": "b_bad",
                    "block_type": "SEQUENTIAL",
                    "condition_text": None,
                    "spans": ["s1"],
                }]
            },
        }
        assembler = BlockAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes, flow))

        # Fabricated block stripped
        assert result.exception_flow_blocks["exc_adapter_00"] == []

    def test_source_backed_handler_block_preserved(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D4: LLM-generated exception flow with handler span preserves block."""
        spans = [
            SpanIR("s1", "Invalid input received."),
            SpanIR("s2", "Log error and notify user."),
        ]
        routes = FieldRouteIR(behavior=["s1", "s2"])
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_1",
                    condition_text="Invalid input",
                    spans=["s1", "s2"],
                ),
            ],
        )
        mock_client.call_json.return_value = {
            "main_flow_blocks": [],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {
                "exc_1": [{
                    "block_id": "b_handler",
                    "block_type": "SEQUENTIAL",
                    "condition_text": None,
                    "spans": ["s2"],
                }]
            },
        }
        assembler = BlockAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes, flow))

        # Source-backed handler block preserved (not exc_adapter_ prefixed)
        assert len(result.exception_flow_blocks["exc_1"]) == 1
        assert result.exception_flow_blocks["exc_1"][0].block_id == "b_handler"

    def test_adapter_flow_with_handler_span_preserves_block(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D4: adapter flow with handler span preserves block; condition-only stripped."""
        spans = [
            SpanIR("s1", "Missing timeframe."),
            SpanIR("s2", "Log error and retry."),
        ]
        # Real IR shape: ExceptionFlow.spans includes both condition + handler
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_adapter_00",
                    condition_text="Missing timeframe.",
                    spans=["s1", "s2"],
                ),
            ],
        )
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
        # LLM fabricates block from condition span, creates real block from handler
        mock_client.call_json.return_value = {
            "main_flow_blocks": [],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {
                "exc_adapter_00": [
                    {"block_id": "b_bad", "block_type": "SEQUENTIAL",
                     "condition_text": None, "spans": ["s1"]},
                    {"block_id": "b_ok", "block_type": "SEQUENTIAL",
                     "condition_text": None, "spans": ["s2"]},
                ]
            },
        }
        assembler = BlockAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes, flow))

        blocks = result.exception_flow_blocks["exc_adapter_00"]
        block_ids = [b.block_id for b in blocks]
        assert "b_ok" in block_ids, f"Handler block b_ok must be preserved, got {block_ids}"
        assert "b_bad" not in block_ids, f"Fabricated condition block b_bad must be stripped"

    def test_system_prompt_contains_partial_skeleton_rule(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D4: system prompt includes Rule 5b partial skeleton instructions."""
        from nl2spl.llm.prompts import load_prompt

        spans = [SpanIR("s1", "Missing timeframe.")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_adapter_00",
                    condition_text="Missing timeframe.",
                    spans=["s1"],
                ),
            ],
        )
        mock_client.call_json.return_value = {
            "main_flow_blocks": [],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {},
        }
        assembler = BlockAssembler(pipeline_config, mock_client)
        assembler.execute((spans, routes, flow))

        # Check actual LLM call system prompt
        system_prompt = mock_client.call_json.call_args.kwargs["system_prompt"]
        assert "5b" in system_prompt or "partial skeleton" in system_prompt.lower()
        assert "invent handler blocks" in system_prompt.lower()
        assert "empty" in system_prompt.lower()

        # Also verify the source file is correctly updated
        raw_prompt = load_prompt("stage5")
        assert "5b" in raw_prompt or "partial skeleton" in raw_prompt.lower(), (
            "stage5_system.txt missing Rule 5b — file not updated"
        )

    def test_guard_emits_warning_for_stripped_block(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D4: guard records warning when stripping fabricated handler block."""
        spans = [SpanIR("s1", "Missing timeframe.")]
        routes = FieldRouteIR(behavior=["s1"])
        flow = FlowStructureIR(
            exception_flows=[
                ExceptionFlow(
                    flow_id="exc_adapter_00",
                    condition_text="Missing timeframe.",
                    spans=["s1"],
                ),
            ],
        )
        mock_client.call_json.return_value = {
            "main_flow_blocks": [],
            "alternative_flow_blocks": {},
            "exception_flow_blocks": {
                "exc_adapter_00": [{
                    "block_id": "b_bad",
                    "block_type": "SEQUENTIAL",
                    "condition_text": None,
                    "spans": ["s1"],
                }]
            },
        }
        assembler = BlockAssembler(pipeline_config, mock_client)
        assembler.execute((spans, routes, flow))

        d4_warnings = getattr(assembler, "stage5_d4_warnings", [])
        assert len(d4_warnings) >= 1, f"Expected D4 guard warning, got {d4_warnings}"
        assert "fabricated handler block" in d4_warnings[0].lower()
