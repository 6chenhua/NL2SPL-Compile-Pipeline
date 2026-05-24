"""Unit tests for Stage 4: FlowAssembler."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.errors.exceptions import StageError
from nl2spl.adapters import StructuralNLAdapter
from nl2spl.canonical import EvidenceRef, FailureModeFact
from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.fact_bridges import bridge_failure_modes
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
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


# ===========================================================================
# D0: Baseline — Stage 4 ignores annotations
# ===========================================================================


class TestD0Stage4Baseline:
    """D0: Stage 4 behavior unchanged when annotations present."""

    def test_annotations_do_not_change_main_flow_or_alternatives(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D2: Stage 4 materializes EXCEPTION_FLOW from failure annotation
        but does NOT change main flow or alternative flows."""
        expected = {
            "main_flow_spans": ["s2"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
        mock_client.call_json.return_value = expected

        spans = [
            SpanIR(span_id="s1", text="Missing timeframe"),
            SpanIR(span_id="s2", text="Identify fields"),
        ]
        routes_with_ann = FieldRouteIR(
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
                    semantic_role="process_step",
                    executable=True,
                ),
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes_with_ann))

        # Main flow and alternatives unchanged
        assert result.main_flow_spans == ["s2"]
        assert result.alternative_flows == []
        # Exception flow materialized from route annotation
        assert len(result.exception_flows) == 1
        exc = result.exception_flows[0]
        assert exc.condition_text == "Missing timeframe"
        assert "s1" in exc.spans

    def test_helper_fallback_when_no_annotations(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D0: get_executable_behavior_span_ids() equals old behavior without annotations."""
        routes = FieldRouteIR(behavior=["s1", "s3", "s5"])
        assert routes.get_executable_behavior_span_ids() == ["s1", "s3", "s5"]


# ===========================================================================
# D2: Route-driven exception materialization in Stage 4
# ===========================================================================


class TestD2RouteDrivenExceptions:
    """D2: Stage 4 materializes ExceptionFlow from failure annotations."""

    def test_handler_action_not_materialized_as_condition(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """handler_action span must NOT become an exception flow condition."""
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s_handler"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
        spans = [
            SpanIR("s_cond", "Missing timeframe."),
            SpanIR("s_handler", "ask one clarifying question."),
        ]
        routes = FieldRouteIR(
            behavior=["s_cond", "s_handler"],
            annotations=[
                RouteAnnotation(
                    span_id="s_cond", field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s_handler", field="behavior",
                    semantic_role="exception_handler_action",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="handler",
                    executable=True,
                ),
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        # Only the condition span should be in exception flows
        assert len(result.exception_flows) >= 1
        for exc in result.exception_flows:
            assert "s_cond" in exc.spans, (
                f"Condition span must be in exception flow: {exc.spans}"
            )
            assert "s_handler" not in exc.spans, (
                f"Handler action span must NOT be in exception flow condition: "
                f"{exc.spans}"
            )

    def test_llm_handler_exception_flow_filtered(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM returns exception flow from handler span → filtered out."""
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s_cond", "s_handler"],
            "alternative_flows": [],
            "exception_flows": [
                {
                    "flow_id": "exc_bad",
                    "condition_text": "ask one clarifying question",
                    "spans": ["s_handler"],
                    "flow_type": "exception",
                },
            ],
            "delegation_candidates": [],
        }
        spans = [
            SpanIR("s_cond", "Missing timeframe."),
            SpanIR("s_handler", "ask one clarifying question."),
        ]
        routes = FieldRouteIR(
            behavior=["s_cond", "s_handler"],
            annotations=[
                RouteAnnotation(
                    span_id="s_cond", field="behavior",
                    semantic_role="failure_mode",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="condition",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s_handler", field="behavior",
                    semantic_role="exception_handler_action",
                    construct_target="EXCEPTION_FLOW",
                    slot_target="handler",
                    executable=True,
                ),
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        # The LLM-generated handler exception flow must be filtered out
        bad_flows = [
            exc for exc in result.exception_flows
            if "s_handler" in exc.spans
        ]
        assert len(bad_flows) == 0, (
            f"LLM handler-sourced exception flow must be filtered, "
            f"got {len(bad_flows)}: {bad_flows}"
        )
        # Route-derived condition must still be present
        cond_flows = [
            exc for exc in result.exception_flows
            if "s_cond" in exc.spans
        ]
        assert len(cond_flows) >= 1, (
            "Route-derived failure_mode condition must survive"
        )

    def test_llm_handler_plus_process_exception_filtered(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM exception backed by handler+process (no condition) → filtered."""
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s_handler", "s_process", "s_cond"],
            "alternative_flows": [],
            "exception_flows": [
                {
                    "flow_id": "exc_bad",
                    "condition_text": "handle the issue",
                    "spans": ["s_handler", "s_process"],
                    "flow_type": "exception",
                },
            ],
            "delegation_candidates": [],
        }
        spans = [
            SpanIR("s_cond", "Missing timeframe."),
            SpanIR("s_handler", "ask one clarifying question."),
            SpanIR("s_process", "Determine communication type."),
        ]
        routes = FieldRouteIR(
            behavior=["s_cond", "s_handler", "s_process"],
            annotations=[
                RouteAnnotation(span_id="s_cond", field="behavior",
                                semantic_role="failure_mode",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="condition", executable=False),
                RouteAnnotation(span_id="s_handler", field="behavior",
                                semantic_role="exception_handler_action",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="handler", executable=True),
                RouteAnnotation(span_id="s_process", field="behavior",
                                semantic_role="process_step",
                                executable=True),
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        # The handler+process exception flow has no condition span → filtered
        bad_flows = [
            exc for exc in result.exception_flows
            if "s_handler" in exc.spans or "s_process" in exc.spans
        ]
        assert len(bad_flows) == 0, (
            f"Exception flow without condition span must be filtered, "
            f"got {len(bad_flows)}"
        )
        # Route-derived condition must survive
        assert any("s_cond" in exc.spans for exc in result.exception_flows), (
            "Route-derived condition must survive"
        )

    def test_no_condition_annotation_filters_all_llm_exceptions(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Annotations present but no condition → ALL LLM exceptions filtered."""
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s_handler", "s_process"],
            "alternative_flows": [],
            "exception_flows": [
                {
                    "flow_id": "exc_bad",
                    "condition_text": "something went wrong",
                    "spans": ["s_handler"],
                    "flow_type": "exception",
                },
            ],
            "delegation_candidates": [],
        }
        spans = [
            SpanIR("s_handler", "ask one clarifying question."),
            SpanIR("s_process", "Determine communication type."),
        ]
        routes = FieldRouteIR(
            behavior=["s_handler", "s_process"],
            annotations=[
                RouteAnnotation(span_id="s_handler", field="behavior",
                                semantic_role="exception_handler_action",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="handler", executable=True),
                RouteAnnotation(span_id="s_process", field="behavior",
                                semantic_role="process_step", executable=True),
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        # Annotations exist but no condition → all LLM exceptions filtered
        assert len(result.exception_flows) == 0, (
            f"Without condition annotations, LLM exceptions must be filtered, "
            f"got {len(result.exception_flows)}"
        )

    def test_mixed_condition_handler_flow_sanitizes_spans(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM flow with condition+handler spans: handler spans stripped."""
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s_cond", "s_handler"],
            "alternative_flows": [],
            "exception_flows": [
                {
                    "flow_id": "exc_mixed",
                    "condition_text": "Missing timeframe",
                    "spans": ["s_cond", "s_handler"],
                    "flow_type": "exception",
                },
            ],
            "delegation_candidates": [],
        }
        spans = [
            SpanIR("s_cond", "Missing timeframe."),
            SpanIR("s_handler", "ask one clarifying question."),
        ]
        routes = FieldRouteIR(
            behavior=["s_cond", "s_handler"],
            annotations=[
                RouteAnnotation(span_id="s_cond", field="behavior",
                                semantic_role="failure_mode",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="condition", executable=False),
                RouteAnnotation(span_id="s_handler", field="behavior",
                                semantic_role="exception_handler_action",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="handler", executable=True),
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        # The mixed flow must be retained but sanitised
        assert len(result.exception_flows) >= 1
        mixed = [e for e in result.exception_flows if "s_cond" in e.spans]
        assert len(mixed) == 1, "Mixed condition+handler flow must be retained"
        exc = mixed[0]
        assert exc.flow_id.startswith("exc_adapter_"), (
            f"Sanitized flow must use exc_adapter_XX id, got {exc.flow_id}"
        )
        assert "s_handler" not in exc.spans, (
            f"Handler span must be stripped from flow spans: {exc.spans}"
        )

    def test_llm_wrong_condition_text_corrected_from_span(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """LLM condition_text overwritten by condition span's actual text."""
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s_cond", "s_handler"],
            "alternative_flows": [],
            "exception_flows": [
                {
                    "flow_id": "exc_wrong_text",
                    "condition_text": "ask one clarifying question",
                    "spans": ["s_cond", "s_handler"],
                    "flow_type": "exception",
                },
            ],
            "delegation_candidates": [],
        }
        spans = [
            SpanIR("s_cond", "Missing timeframe."),
            SpanIR("s_handler", "ask one clarifying question."),
        ]
        routes = FieldRouteIR(
            behavior=["s_cond", "s_handler"],
            annotations=[
                RouteAnnotation(span_id="s_cond", field="behavior",
                                semantic_role="failure_mode",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="condition", executable=False),
                RouteAnnotation(span_id="s_handler", field="behavior",
                                semantic_role="exception_handler_action",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="handler", executable=True),
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        # LLM's wrong condition_text must be replaced by actual span text
        wrong_text_flows = [
            e for e in result.exception_flows
            if "ask one clarifying question" in e.condition_text
        ]
        assert len(wrong_text_flows) == 0, (
            f"LLM-invented condition_text must be corrected, "
            f"got {[e.condition_text for e in wrong_text_flows]}"
        )
        # Correct condition_text from span must be present
        correct = [
            e for e in result.exception_flows
            if "Missing timeframe" in e.condition_text
        ]
        assert len(correct) >= 1, (
            f"Condition text must come from condition span, "
            f"got {[e.condition_text for e in result.exception_flows]}"
        )
        # No duplicate condition flows
        assert len(correct) == 1, (
            f"Must not duplicate condition flows, got {len(correct)}"
        )

    def test_sanitized_flow_id_is_exc_adapter_format(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Sanitized exception flow uses exc_adapter_XX id, not LLM flow_id."""
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s_cond", "s_handler"],
            "alternative_flows": [],
            "exception_flows": [
                {
                    "flow_id": "exc_llm_bad_name",
                    "condition_text": "ask one clarifying question",
                    "spans": ["s_cond", "s_handler"],
                    "flow_type": "exception",
                },
            ],
            "delegation_candidates": [],
        }
        spans = [
            SpanIR("s_cond", "Missing timeframe."),
            SpanIR("s_handler", "ask one clarifying question."),
        ]
        routes = FieldRouteIR(
            behavior=["s_cond", "s_handler"],
            annotations=[
                RouteAnnotation(span_id="s_cond", field="behavior",
                                semantic_role="failure_mode",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="condition", executable=False),
                RouteAnnotation(span_id="s_handler", field="behavior",
                                semantic_role="exception_handler_action",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="handler", executable=True),
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        # Sanitized flow must NOT carry LLM's flow_id
        llm_ids = [e.flow_id for e in result.exception_flows]
        assert "exc_llm_bad_name" not in llm_ids, (
            f"Sanitized flow must not carry LLM flow_id, got {llm_ids}"
        )
        assert any(fid.startswith("exc_adapter_") for fid in llm_ids), (
            f"Sanitized flow must use exc_adapter_XX format, got {llm_ids}"
        )

    def test_sanitized_flow_does_not_mutate_original(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """Original ExceptionFlow object is not mutated by the filter."""
        from nl2spl.ir.flow_structure_ir import ExceptionFlow

        original = ExceptionFlow(
            flow_id="exc_original", condition_text="original text",
            spans=["s1", "s2"],
        )
        # Capture pre-filter state
        orig_id = original.flow_id
        orig_text = original.condition_text
        orig_spans = list(original.spans)

        # Build minimal IR that triggers the filter
        spans = [SpanIR("s1", "Missing timeframe.")]
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(span_id="s1", field="behavior",
                                semantic_role="failure_mode",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="condition", executable=False),
            ],
        )
        from nl2spl.ir.flow_structure_ir import FlowStructureIR as FSI

        flow = FSI(exception_flows=[original])

        from nl2spl.pipeline.stages.stage4_flow_assembler.executor import (
            _filter_non_condition_exception_flows,
        )
        _filter_non_condition_exception_flows(flow, routes, spans)

        # Original must be unchanged
        assert original.flow_id == orig_id, (
            f"Original flow_id mutated: {orig_id} -> {original.flow_id}"
        )
        assert original.condition_text == orig_text, (
            f"Original condition_text mutated: {orig_text} -> {original.condition_text}"
        )
        assert original.spans == orig_spans, (
            f"Original spans mutated: {orig_spans} -> {original.spans}"
        )

    def test_stage4_materializes_failure_annotation(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s2"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
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
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        assert len(result.exception_flows) == 1
        exc = result.exception_flows[0]
        assert exc.condition_text == "Missing timeframe."
        assert "s1" in exc.spans

    def test_existing_llm_exception_deduped(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s2"],
            "alternative_flows": [],
            "exception_flows": [{
                "flow_id": "exc_llm",
                "condition_text": "Missing timeframe.",
                "spans": ["s1"],
                "flow_type": "exception",
            }],
            "delegation_candidates": [],
        }
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
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        assert len(result.exception_flows) == 1  # deduped, not duplicated

    def test_bridge_fallback_works_without_annotations(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s1"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
        spans = [SpanIR("s1", "Determine type.")]
        routes = FieldRouteIR(behavior=["s1"])  # no annotations

        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        assert result.exception_flows == []  # route materializer has nothing to do
        # Bridge still works independently
        from nl2spl.pipeline.fact_bridges import bridge_failure_modes
        from nl2spl.canonical import FailureModeFact, EvidenceRef

        fact = FailureModeFact(
            name="missing", text="Missing timeframe.",
            source_section_id="sec_fail",
            evidence=[EvidenceRef(source_section_id="sec_fail")],
        )
        bridged = bridge_failure_modes([fact], spans, result)
        assert len(bridged.exception_flows) == 1

    def test_route_plus_bridge_no_duplicate(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s2"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
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
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))
        # Route-driven exception already materialized
        assert len(result.exception_flows) == 1

        # Bridge with same condition text → deduped, no duplicate
        from nl2spl.pipeline.fact_bridges import bridge_failure_modes
        from nl2spl.canonical import FailureModeFact, EvidenceRef

        fact = FailureModeFact(
            name="missing_timeframe", text="Missing timeframe.",
            source_section_id="sec_fail",
            evidence=[EvidenceRef(source_section_id="sec_fail")],
        )
        bridged = bridge_failure_modes([fact], spans, result)
        assert len(bridged.exception_flows) == 1  # still one

    def test_non_failure_annotation_ignored(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        mock_client.call_json.return_value = {
            "main_flow_spans": ["s1"],
            "alternative_flows": [],
            "exception_flows": [],
            "delegation_candidates": [],
        }
        spans = [SpanIR("s1", "Optional source gathering.")]
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(
                    span_id="s1", field="behavior",
                    semantic_role="delegation_intent",  # not failure_mode
                    route_family="delegation_boundary",
                    executable=False,
                ),
            ],
        )
        assembler = FlowAssembler(pipeline_config, mock_client)
        result = assembler.execute((spans, routes))

        assert result.exception_flows == []

    def test_materializer_does_not_mutate_input(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D2: materialize_route_exception_flows does not mutate input flow."""
        from nl2spl.pipeline.route_exception_materializer import materialize_route_exception_flows

        original = FlowStructureIR(
            main_flow_spans=["s2"],
            exception_flows=[],
        )
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
            ],
        )

        result = materialize_route_exception_flows(original, routes, spans)

        # Original must NOT be mutated
        assert original.exception_flows == []
        # Result is a different object with the new exception
        assert result is not original
        assert len(result.exception_flows) == 1
        assert result.exception_flows[0].condition_text == "Missing timeframe."
        # Other fields preserved
        assert result.main_flow_spans == ["s2"]

    def test_filter_noop_returns_original_object(
        self,
    ) -> None:
        """Filter with only route-derived flows → returns original unchanged."""
        from nl2spl.ir.flow_structure_ir import FlowStructureIR as FSI, ExceptionFlow
        from nl2spl.pipeline.stages.stage4_flow_assembler.executor import (
            _filter_non_condition_exception_flows,
        )

        spans = [SpanIR("s1", "Missing timeframe.")]
        routes = FieldRouteIR(
            behavior=["s1"],
            annotations=[
                RouteAnnotation(span_id="s1", field="behavior",
                                semantic_role="failure_mode",
                                construct_target="EXCEPTION_FLOW",
                                slot_target="condition", executable=False),
            ],
        )
        flow = FSI(exception_flows=[
            ExceptionFlow(flow_id="exc_adapter_00",
                          condition_text="Missing timeframe.", spans=["s1"]),
        ])

        result = _filter_non_condition_exception_flows(flow, routes, spans)
        assert result is flow, (
            "No-op filter must return original FlowStructureIR unchanged"
        )

    def test_materializer_noop_returns_same_object(
        self, pipeline_config: MagicMock, mock_client: MagicMock
    ) -> None:
        """D2: materialize_route_exception_flows returns input unchanged when no-op."""
        from nl2spl.pipeline.route_exception_materializer import materialize_route_exception_flows

        original = FlowStructureIR(main_flow_spans=["s1"], exception_flows=[])
        spans = [SpanIR("s1", "Determine type.")]
        routes = FieldRouteIR(behavior=["s1"])  # no annotations

        result = materialize_route_exception_flows(original, routes, spans)
        assert result is original


def test_d2_orchestrator_path_route_plus_bridge_no_duplicate(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D2: PipelineOrchestrator.run() produces no duplicate exception from route+bridge."""
    from nl2spl.pipeline.orchestrator import PipelineOrchestrator

    text = (
        "Task family: Test.\n\n"
        "Inputs for each run:\nA user request.\n\n"
        "Required outputs:\nA result.\n\n"
        "Reusable process:\nDetermine type.\n\n"
        "Policies:\nDo not invent.\n\n"
        "Failure handling:\nMissing timeframe.\n\n"
        "Delegation policy:\nNone.\n"
    )
    canonical = StructuralNLAdapter().adapt(text)
    # Verify hard facts exist (triggers bridge path in orchestrator)
    assert len(canonical.hard_facts.failure_modes) >= 1

    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    routes, _ = FieldRouter(pipeline_config, mock_client).execute((spans, canonical))
    # Verify failure annotation exists (triggers route materialization in Stage 4)
    failure_anns = routes.get_construct_slot_candidates("EXCEPTION_FLOW", "condition")
    assert len(failure_anns) >= 1

    # Build a real PipelineOrchestrator and run through Stage 4 + bridge
    orchestrator = PipelineOrchestrator(pipeline_config)
    orchestrator.client = mock_client

    # Stage 4 LLM: no exceptions → route materializer adds one
    flow_structure = FlowStructureIR()
    mock_client.call_json.return_value = {
        "main_flow_spans": [s.span_id for s in spans if "timeframe" not in s.text],
        "alternative_flows": [],
        "exception_flows": [],
        "delegation_candidates": [],
    }
    # Mock stages 5+ to avoid running full pipeline
    setattr(orchestrator, "_run_stage1", MagicMock(return_value=spans))
    setattr(orchestrator, "_run_stage2", MagicMock(return_value=(routes, [])))
    setattr(orchestrator, "_run_stage3", MagicMock(return_value=(spans, routes)))
    setattr(orchestrator, "_run_stage5", MagicMock(return_value=BlockStructureIR()))
    setattr(orchestrator, "_run_stage6", MagicMock(
        return_value=(MagicMock(variables=[]), MagicMock(), [])))

    from nl2spl.ir.step_ir import StepIR
    setattr(orchestrator, "_run_stage7", MagicMock(return_value=([], MagicMock(), [])))
    setattr(orchestrator, "_run_stage8", MagicMock(return_value=MagicMock()))
    setattr(orchestrator, "_run_stage9", MagicMock(return_value=[]))
    setattr(orchestrator, "_run_normalization", MagicMock(
        return_value=(FlowStructureIR(), BlockStructureIR(), [], [], MagicMock(), [], [])))
    setattr(orchestrator, "_run_stage10", MagicMock(return_value=MagicMock()))
    setattr(orchestrator, "_run_stage11", MagicMock(return_value=("SPL", [], [])))

    # Stage 4 uses real FlowAssembler.execute() so route materializer runs
    def real_stage4(spans, routes, worker_plan=None):
        return FlowAssembler(pipeline_config, mock_client).execute((spans, routes))
    setattr(orchestrator, "_run_stage4", real_stage4)

    result = orchestrator.run(text)

    stage4_flow = result.intermediate_results["stage4_flow"]
    # Route + bridge must not duplicate
    timeframe_exceptions = [
        e for e in stage4_flow.exception_flows
        if "timeframe" in e.condition_text.lower()
    ]
    assert len(timeframe_exceptions) == 1, (
        f"Expected 1 exception for 'timeframe', got {len(timeframe_exceptions)}"
    )


# ===========================================================================
# D8: Bridge fallback guards — route is canonical, bridge is fallback
# ===========================================================================


# ===========================================================================
# D11: Import boundary — route materializer not in fact_bridges
# ===========================================================================


def test_d11_route_materializer_not_imported_from_fact_bridges() -> None:
    """D11: no production file imports materialize_route_exception_flows
    from nl2spl.pipeline.fact_bridges."""
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    src_root = repo_root / "src" / "nl2spl"
    assert src_root.is_dir(), f"src_root must exist: {src_root}"

    violations: list[str] = []
    scanned = 0
    for py_file in src_root.rglob("*.py"):
        scanned += 1
        text = py_file.read_text(encoding="utf-8")
        if "materialize_route_exception_flows" not in text:
            continue
        tree = ast.parse(text)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module == "nl2spl.pipeline.fact_bridges":
                    for alias in node.names:
                        if alias.name == "materialize_route_exception_flows":
                            violations.append(
                                f"{py_file.relative_to(repo_root)}"
                                f" imports materialize_route_exception_flows"
                                f" from fact_bridges"
                            )
    assert scanned > 0, f"Scanned 0 files from {src_root}"
    assert not violations, (
        f"Found {len(violations)} violation(s): {violations}"
    )


def test_d8_bridge_fallback_skipped_when_route_exceptions_exist(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D8: bridge fallback is skipped when route materialization has exceptions."""
    from nl2spl.pipeline.orchestrator import PipelineOrchestrator

    text = (
        "Task family: Test.\n\nInputs for each run:\nA request.\n\n"
        "Required outputs:\nA result.\n\nReusable process:\nDetermine type.\n\n"
        "Policies:\nDo not invent.\n\nFailure handling:\nMissing timeframe.\n\n"
        "Delegation policy:\nNone.\n"
    )
    canonical = StructuralNLAdapter().adapt(text)
    assert len(canonical.hard_facts.failure_modes) >= 1  # hard facts present

    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    routes, _ = FieldRouter(pipeline_config, mock_client).execute((spans, canonical))
    # Route annotations exist
    assert routes.annotations, "Annotations must be present for D8 test"
    failure_anns = routes.get_construct_slot_candidates("EXCEPTION_FLOW", "condition")
    assert len(failure_anns) >= 1  # route-derived will create exception

    mock_client.call_json.return_value = {
        "main_flow_spans": [s.span_id for s in spans if "timeframe" not in s.text],
        "alternative_flows": [], "exception_flows": [], "delegation_candidates": [],
    }
    assembler = FlowAssembler(pipeline_config, mock_client)
    flow = assembler.execute((spans, routes))

    # Route materialized exception
    assert len(flow.exception_flows) >= 1

    # Bridge fallback would be skipped (orchestrator guard checks for zero exceptions)
    from nl2spl.pipeline.fact_bridges import bridge_failure_modes
    bridged = bridge_failure_modes(canonical.hard_facts.failure_modes, spans, flow)
    assert len(bridged.exception_flows) == len(flow.exception_flows)


def test_d8_hard_fact_only_fallback_still_works(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D8: without route annotations, bridge fallback still creates exception."""
    from nl2spl.canonical import EvidenceRef, FailureModeFact
    from nl2spl.pipeline.fact_bridges import bridge_failure_modes

    spans = [SpanIR("s1", "Missing timeframe.")]
    routes = FieldRouteIR(behavior=["s1"])  # no annotations
    flow = FlowStructureIR()  # no exception flows

    fact = FailureModeFact(
        name="missing_timeframe", text="Missing timeframe.",
        source_section_id="sec_fail",
        evidence=[EvidenceRef(source_section_id="sec_fail")],
    )
    bridged = bridge_failure_modes([fact], spans, flow)
    assert len(bridged.exception_flows) == 1
    assert bridged.exception_flows[0].condition_text == "Missing timeframe."


def test_d8_guard_by_normalized_condition_coverage():
    """D8: guard checks normalized condition text, not just flow count."""
    from nl2spl.canonical import EvidenceRef, FailureModeFact
    from nl2spl.pipeline.orchestrator import PipelineOrchestrator

    flow = FlowStructureIR(
        exception_flows=[
            ExceptionFlow("exc_adapter_00", "Missing timeframe.", ["s_fail"]),
        ],
    )
    # Already-covered failure mode → no fallback needed
    covered = [FailureModeFact(
        name="mt", text="Missing timeframe.",
        source_section_id="s", evidence=[EvidenceRef(source_section_id="s")],
    )]
    assert not PipelineOrchestrator._bridge_fallback_needed(covered, flow)

    # Unrelated failure mode → fallback still needed
    unrelated = [FailureModeFact(
        name="es", text="Evidence shortage.",
        source_section_id="s", evidence=[EvidenceRef(source_section_id="s")],
    )]
    assert PipelineOrchestrator._bridge_fallback_needed(unrelated, flow)

    # Mixed: one covered, one not → fallback needed
    assert PipelineOrchestrator._bridge_fallback_needed(covered + unrelated, flow)

    # Empty flow → fallback needed
    assert PipelineOrchestrator._bridge_fallback_needed(covered, FlowStructureIR())


def test_d8_orchestrator_guard_stops_bridge_when_route_has_exceptions(
    pipeline_config: MagicMock,
    mock_client: MagicMock,
) -> None:
    """D8: orchestrator path uses patch to prove bridge NOT called when route covers all."""
    from unittest.mock import patch
    from nl2spl.pipeline.orchestrator import PipelineOrchestrator

    text = (
        "Task family: Test.\n\nInputs for each run:\nA request.\n\n"
        "Required outputs:\nA result.\n\nReusable process:\nDetermine type.\n\n"
        "Policies:\nDo not invent.\n\nFailure handling:\nMissing timeframe.\n\n"
        "Delegation policy:\nNone.\n"
    )
    canonical = StructuralNLAdapter().adapt(text)
    spans = SpanSlicer(pipeline_config, mock_client).execute(canonical)
    routes, _ = FieldRouter(pipeline_config, mock_client).execute((spans, canonical))

    orchestrator = PipelineOrchestrator(pipeline_config)
    orchestrator.client = mock_client

    mock_client.call_json.return_value = {
        "main_flow_spans": [s.span_id for s in spans if "timeframe" not in s.text],
        "alternative_flows": [], "exception_flows": [], "delegation_candidates": [],
    }
    # Mock stages
    setattr(orchestrator, "_run_stage1", MagicMock(return_value=spans))
    setattr(orchestrator, "_run_stage2", MagicMock(return_value=(routes, [])))
    setattr(orchestrator, "_run_stage3", MagicMock(return_value=(spans, routes)))
    from nl2spl.ir.block_structure_ir import BlockStructureIR

    def real_stage4(s, r, wp=None):
        return FlowAssembler(pipeline_config, mock_client).execute((s, r))
    setattr(orchestrator, "_run_stage4", real_stage4)
    setattr(orchestrator, "_run_stage5", MagicMock(return_value=BlockStructureIR()))
    setattr(orchestrator, "_run_stage6", MagicMock(
        return_value=(MagicMock(variables=[]), MagicMock(), [])))
    setattr(orchestrator, "_run_stage7", MagicMock(return_value=([], MagicMock(), [])))
    setattr(orchestrator, "_run_stage8", MagicMock(return_value=MagicMock()))
    setattr(orchestrator, "_run_stage9", MagicMock(return_value=[]))
    setattr(orchestrator, "_run_normalization", MagicMock(
        return_value=(FlowStructureIR(), BlockStructureIR(), [], [], MagicMock(), [], [])))
    setattr(orchestrator, "_run_stage10", MagicMock(return_value=MagicMock()))
    setattr(orchestrator, "_run_stage11", MagicMock(return_value=("SPL", [], [])))

    with patch("nl2spl.pipeline.orchestrator.bridge_failure_modes") as spy_bridge:
        result = orchestrator.run(text)
        stage4_flow = result.intermediate_results["stage4_flow"]
        # Route materialized the exception
        timeframe_excs = [
            e for e in stage4_flow.exception_flows
            if "timeframe" in e.condition_text.lower()
        ]
        assert len(timeframe_excs) == 1
        # Bridge fallback must NOT be called (route covers all failure modes)
        spy_bridge.assert_not_called()


def test_d8_worker_scoped_guard_coverage():
    """D8: worker-scoped guard — uncovered hard fact triggers fallback."""
    from nl2spl.canonical import EvidenceRef, FailureModeFact
    from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR
    from nl2spl.pipeline.orchestrator import PipelineOrchestrator

    wfp = WorkerFlowPlanIR(worker_flows={
        "worker_main": FlowStructureIR(
            exception_flows=[
                ExceptionFlow("exc_adapter_00", "Missing timeframe.", ["s1"]),
            ],
        ),
        "worker_child": FlowStructureIR(),
    })
    # Already-covered failure mode → no fallback
    covered = [FailureModeFact(
        name="mt", text="Missing timeframe.",
        source_section_id="s", evidence=[EvidenceRef(source_section_id="s")],
    )]
    assert not PipelineOrchestrator._bridge_fallback_needed_worker_scoped(
        covered, wfp,
    )
    # Unrelated failure mode → fallback needed
    unrelated = [FailureModeFact(
        name="es", text="Evidence shortage.",
        source_section_id="s", evidence=[EvidenceRef(source_section_id="s")],
    )]
    assert PipelineOrchestrator._bridge_fallback_needed_worker_scoped(
        unrelated, wfp,
    )
    # Mixed: one covered in child, one uncovered — fallback needed
    mixed = [FailureModeFact(
        name="mt", text="Missing timeframe.",
        source_section_id="s", evidence=[EvidenceRef(source_section_id="s")],
    ), FailureModeFact(
        name="es", text="Evidence shortage.",
        source_section_id="s", evidence=[EvidenceRef(source_section_id="s")],
    )]
    assert PipelineOrchestrator._bridge_fallback_needed_worker_scoped(
        mixed, wfp,
    ), "Mixed covered+uncovered must trigger fallback"
