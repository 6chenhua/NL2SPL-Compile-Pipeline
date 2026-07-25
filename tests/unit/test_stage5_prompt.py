"""Prompt isolation tests for Stage 5: BlockAssembler.

Tests the LLM prompt for block assembly independently from the full pipeline,
using mock LLM responses loaded from shared fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler
from tests.fixtures.stage_prompt_fixtures import (
    STAGE1_EXPECTED_SPANS,
    STAGE2_EXPECTED_ROUTES,
    STAGE4_EXPECTED_FLOW,
    STAGE5_EXPECTED_BLOCKS,
    STAGE5_MOCK_LLM_RESPONSE,
    compare_block_structures,
    generate_test_report,
    load_mock_response,
)

# =============================================================================
# Pytest Markers
# =============================================================================

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage5]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def input_spans() -> list[SpanIR]:
    """Spans produced by Stage 1 (input for Stage 5)."""
    return STAGE1_EXPECTED_SPANS


@pytest.fixture
def input_routes() -> FieldRouteIR:
    """Field routes produced by Stage 2 (input for Stage 5)."""
    return STAGE2_EXPECTED_ROUTES


@pytest.fixture
def input_flow() -> FlowStructureIR:
    """Flow structure produced by Stage 4 (input for Stage 5)."""
    return STAGE4_EXPECTED_FLOW


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM JSON response for Stage 5."""
    return STAGE5_MOCK_LLM_RESPONSE


@pytest.fixture
def expected_blocks() -> BlockStructureIR:
    """Expected block structure output for Stage 5."""
    return STAGE5_EXPECTED_BLOCKS


@pytest.fixture
def assembler(pipeline_config: MagicMock, mock_client: MagicMock) -> BlockAssembler:
    """Create BlockAssembler instance with mock client."""
    return BlockAssembler(pipeline_config, mock_client)


# =============================================================================
# Tests
# =============================================================================


class TestStage5Prompt:
    """Test Stage 5 BlockAssembler prompt in isolation."""

    def test_prompt_produces_expected_blocks(
        self,
        assembler: BlockAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        expected_blocks: BlockStructureIR,
    ) -> None:
        """Verify that with a mock LLM response, execute() produces expected block structure."""
        mock_client.call_json.return_value = mock_llm_response

        blocks = assembler.execute((input_spans, input_routes, input_flow))

        # Assert - structure
        assert isinstance(blocks, BlockStructureIR), "Output must be BlockStructureIR"

        # Assert - key fields
        mismatches = compare_block_structures(blocks, expected_blocks)
        report = generate_test_report(5, "BlockAssembler", mismatches)
        assert not mismatches, f"Stage 5 prompt test failed:\n{report}"

    def test_prompt_calls_llm_with_correct_stage_name(
        self,
        assembler: BlockAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
    ) -> None:
        """Verify the LLM is called with the correct stage_name."""
        mock_client.call_json.return_value = mock_llm_response
        assembler.execute((input_spans, input_routes, input_flow))

        mock_client.call_json.assert_called_once()
        call_kwargs = mock_client.call_json.call_args[1]
        assert call_kwargs["stage_name"] == "stage5_block_assembler"

    def test_prompt_main_flow_blocks_populated(
        self,
        assembler: BlockAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
    ) -> None:
        """Verify main flow blocks are populated."""
        mock_client.call_json.return_value = mock_llm_response
        blocks = assembler.execute((input_spans, input_routes, input_flow))

        assert len(blocks.main_flow_blocks) > 0, "main_flow_blocks should not be empty"

    def test_prompt_block_ids_valid(
        self,
        assembler: BlockAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
    ) -> None:
        """Verify all block IDs have valid format (b{N})."""
        mock_client.call_json.return_value = mock_llm_response
        blocks = assembler.execute((input_spans, input_routes, input_flow))

        for block in blocks.get_all_blocks():
            assert block.block_id.startswith("b"), f"block_id {block.block_id} must start with 'b'"

    def test_prompt_block_types_valid(
        self,
        assembler: BlockAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
    ) -> None:
        """Verify all block types are valid (SEQUENTIAL/IF/FOR/WHILE)."""
        mock_client.call_json.return_value = mock_llm_response
        blocks = assembler.execute((input_spans, input_routes, input_flow))

        valid_types = {"SEQUENTIAL", "IF", "FOR", "WHILE"}
        for block in blocks.get_all_blocks():
            assert block.block_type in valid_types, (
                f"block_type {block.block_type} must be one of {valid_types}"
            )

    def test_prompt_exception_flow_blocks(
        self,
        assembler: BlockAssembler,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        expected_blocks: BlockStructureIR,
    ) -> None:
        """Verify exception flow blocks are populated correctly."""
        mock_client.call_json.return_value = mock_llm_response
        blocks = assembler.execute((input_spans, input_routes, input_flow))

        assert set(blocks.exception_flow_blocks.keys()) == set(
            expected_blocks.exception_flow_blocks.keys()
        ), f"Exception flow block keys mismatch: {list(blocks.exception_flow_blocks.keys())}"

    def test_prompt_fixture_loader(self) -> None:
        """Verify load_mock_response() returns the same fixture data."""
        loaded = load_mock_response(5)
        assert loaded == STAGE5_MOCK_LLM_RESPONSE
