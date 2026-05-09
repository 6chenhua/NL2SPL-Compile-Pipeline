"""Prompt isolation tests for Stage 4: FlowAssembler.

Tests the LLM prompt for flow assembly independently from the full pipeline,
using mock LLM responses loaded from shared fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler
from tests.fixtures.stage_prompt_fixtures import (
    STAGE1_EXPECTED_SPANS,
    STAGE2_EXPECTED_ROUTES,
    STAGE4_EXPECTED_FLOW,
    STAGE4_MOCK_LLM_RESPONSE,
    compare_flow_structures,
    generate_test_report,
    load_mock_response,
)


# =============================================================================
# Pytest Markers
# =============================================================================

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage4]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def input_spans() -> list[SpanIR]:
    """Spans produced by Stage 1 (input for Stage 4)."""
    return STAGE1_EXPECTED_SPANS


@pytest.fixture
def input_routes() -> FieldRouteIR:
    """Field routes produced by Stage 2 (input for Stage 4)."""
    return STAGE2_EXPECTED_ROUTES


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM JSON response for Stage 4."""
    return STAGE4_MOCK_LLM_RESPONSE


@pytest.fixture
def expected_flow() -> FlowStructureIR:
    """Expected flow structure output for Stage 4."""
    return STAGE4_EXPECTED_FLOW


@pytest.fixture
def assembler(pipeline_config: MagicMock, mock_client: MagicMock) -> FlowAssembler:
    """Create FlowAssembler instance with mock client."""
    return FlowAssembler(pipeline_config, mock_client)


# =============================================================================
# Tests
# =============================================================================


class TestStage4Prompt:
    """Test Stage 4 FlowAssembler prompt in isolation."""

    def test_prompt_produces_expected_flow(
        self,
        assembler: FlowAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        expected_flow: FlowStructureIR,
    ) -> None:
        """Verify that with a mock LLM response, execute() produces expected flow structure."""
        mock_client.call_json.return_value = mock_llm_response

        flow = assembler.execute((input_spans, input_routes))

        # Assert - structure
        assert isinstance(flow, FlowStructureIR), "Output must be FlowStructureIR"

        # Assert - key fields
        mismatches = compare_flow_structures(flow, expected_flow)
        report = generate_test_report(4, "FlowAssembler", mismatches)
        assert not mismatches, f"Stage 4 prompt test failed:\n{report}"

    def test_prompt_calls_llm_with_correct_stage_name(
        self,
        assembler: FlowAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
    ) -> None:
        """Verify the LLM is called with the correct stage_name."""
        mock_client.call_json.return_value = mock_llm_response
        assembler.execute((input_spans, input_routes))

        mock_client.call_json.assert_called_once()
        call_kwargs = mock_client.call_json.call_args[1]
        assert call_kwargs["stage_name"] == "stage4_flow_assembler"

    def test_prompt_main_flow_spans(
        self,
        assembler: FlowAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
    ) -> None:
        """Verify main flow spans are populated correctly."""
        mock_client.call_json.return_value = mock_llm_response
        flow = assembler.execute((input_spans, input_routes))

        assert isinstance(flow.main_flow_spans, list), "main_flow_spans must be a list"
        assert len(flow.main_flow_spans) > 0, "main_flow_spans should not be empty"

    def test_prompt_delegation_candidates(
        self,
        assembler: FlowAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        expected_flow: FlowStructureIR,
    ) -> None:
        """Verify delegation candidates are extracted correctly."""
        mock_client.call_json.return_value = mock_llm_response
        flow = assembler.execute((input_spans, input_routes))

        assert len(flow.delegation_candidates) == len(expected_flow.delegation_candidates), (
            f"Expected {len(expected_flow.delegation_candidates)} delegation candidates, "
            f"got {len(flow.delegation_candidates)}"
        )
        if flow.delegation_candidates:
            dc = flow.delegation_candidates[0]
            assert dc.candidate_id.startswith("dc_"), f"candidate_id must start with 'dc_', got {dc.candidate_id}"
            assert dc.suggested_type in ("child_worker", "api_call"), (
                f"suggested_type must be 'child_worker' or 'api_call', got {dc.suggested_type}"
            )

    def test_prompt_exception_flows(
        self,
        assembler: FlowAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        expected_flow: FlowStructureIR,
    ) -> None:
        """Verify exception flows are extracted correctly."""
        mock_client.call_json.return_value = mock_llm_response
        flow = assembler.execute((input_spans, input_routes))

        assert len(flow.exception_flows) == len(expected_flow.exception_flows), (
            f"Expected {len(expected_flow.exception_flows)} exception flows, "
            f"got {len(flow.exception_flows)}"
        )
        if flow.exception_flows:
            exc = flow.exception_flows[0]
            assert exc.flow_id.startswith("exc_"), f"flow_id must start with 'exc_', got {exc.flow_id}"
            assert exc.condition_text, "Exception flow must have condition_text"
            assert len(exc.spans) > 0, "Exception flow must have spans"

    def test_prompt_fixture_loader(self) -> None:
        """Verify load_mock_response() returns the same fixture data."""
        loaded = load_mock_response(4)
        assert loaded == STAGE4_MOCK_LLM_RESPONSE
