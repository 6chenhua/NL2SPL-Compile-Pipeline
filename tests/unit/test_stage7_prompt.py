"""Prompt isolation tests for Stage 7: StepExtractor.

Tests the LLM prompt for step extraction independently from the full pipeline,
using mock LLM responses loaded from shared fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor
from tests.fixtures.stage_prompt_fixtures import (
    STAGE1_EXPECTED_SPANS,
    STAGE2_EXPECTED_ROUTES,
    STAGE4_EXPECTED_FLOW,
    STAGE5_EXPECTED_BLOCKS,
    STAGE6_EXPECTED_SYMBOL_TABLE,
    STAGE7_EXPECTED_STEPS,
    STAGE7_MOCK_LLM_RESPONSE,
    compare_steps,
    generate_test_report,
    load_mock_response,
)


# =============================================================================
# Pytest Markers
# =============================================================================

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage7]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def input_spans() -> list[SpanIR]:
    """Spans produced by Stage 1 (input for Stage 7)."""
    return STAGE1_EXPECTED_SPANS


@pytest.fixture
def input_routes() -> FieldRouteIR:
    """Field routes produced by Stage 2 (input for Stage 7)."""
    return STAGE2_EXPECTED_ROUTES


@pytest.fixture
def input_flow() -> FlowStructureIR:
    """Flow structure produced by Stage 4 (input for Stage 7)."""
    return STAGE4_EXPECTED_FLOW


@pytest.fixture
def input_blocks() -> BlockStructureIR:
    """Block structure produced by Stage 5 (input for Stage 7)."""
    return STAGE5_EXPECTED_BLOCKS


@pytest.fixture
def input_symbol_table() -> SymbolTable:
    """Symbol table produced by Stage 6 (input for Stage 7)."""
    return STAGE6_EXPECTED_SYMBOL_TABLE


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM JSON response for Stage 7."""
    return STAGE7_MOCK_LLM_RESPONSE


@pytest.fixture
def expected_steps() -> list[StepIR]:
    """Expected step output for Stage 7."""
    return STAGE7_EXPECTED_STEPS


@pytest.fixture
def extractor(pipeline_config: MagicMock, mock_client: MagicMock) -> StepExtractor:
    """Create StepExtractor instance with mock client."""
    return StepExtractor(pipeline_config, mock_client)


# =============================================================================
# Tests
# =============================================================================


class TestStage7Prompt:
    """Test Stage 7 StepExtractor prompt in isolation."""

    def test_prompt_produces_expected_steps(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
        expected_steps: list[StepIR],
    ) -> None:
        """Verify that with a mock LLM response, execute() produces expected steps."""
        mock_client.call_json.return_value = mock_llm_response

        steps, updated_symbol_table = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        # Assert - structure
        assert isinstance(steps, list), "First output must be a list"
        assert all(isinstance(s, StepIR) for s in steps), "All items must be StepIR"
        assert isinstance(updated_symbol_table, SymbolTable), "Second output must be SymbolTable"

        # Assert - key fields
        mismatches = compare_steps(steps, expected_steps)
        report = generate_test_report(7, "StepExtractor", mismatches)
        assert not mismatches, f"Stage 7 prompt test failed:\n{report}"

    def test_prompt_calls_llm_with_correct_stage_name(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify the LLM is called with the correct stage_name."""
        mock_client.call_json.return_value = mock_llm_response
        extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        mock_client.call_json.assert_called_once()
        call_kwargs = mock_client.call_json.call_args[1]
        assert call_kwargs["stage_name"] == "stage7_step_extractor"

    def test_prompt_step_ids_valid(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify all step IDs have valid format (st{N})."""
        mock_client.call_json.return_value = mock_llm_response
        steps, _ = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        for step in steps:
            assert step.step_id.startswith("st"), f"step_id {step.step_id} must start with 'st'"

    def test_prompt_command_types_valid(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify all command types are valid."""
        mock_client.call_json.return_value = mock_llm_response
        steps, _ = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        valid_types = {"GENERAL_COMMAND", "CALL_API", "INVOKE_WORKER", "REQUEST_INPUT", "DISPLAY_MESSAGE"}
        for step in steps:
            assert step.command_type in valid_types, (
                f"command_type {step.command_type} must be one of {valid_types}"
            )

    def test_prompt_steps_have_io_variables(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify steps have input/output variable references."""
        mock_client.call_json.return_value = mock_llm_response
        steps, _ = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        for step in steps:
            assert isinstance(step.inputs, list), f"Step {step.step_id} inputs must be a list"
            assert isinstance(step.outputs, list), f"Step {step.step_id} outputs must be a list"

    def test_prompt_steps_reference_correct_flow(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify steps reference the correct flow."""
        mock_client.call_json.return_value = mock_llm_response
        steps, _ = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        for step in steps:
            assert step.flow_ref in ("main", "alt_1", "exc_1"), (
                f"Step {step.step_id} has unexpected flow_ref: {step.flow_ref}"
            )

    def test_prompt_symbol_table_updated(
        self,
        extractor: StepExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify symbol table is updated with producer/consumer info."""
        mock_client.call_json.return_value = mock_llm_response
        _, updated_table = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table)
        )

        # At least some variables should have producer/consumer info
        has_producer = any(v.producer_step for v in updated_table.variables.values())
        assert has_producer, "Symbol table should have at least one variable with a producer step"

    def test_prompt_fixture_loader(self) -> None:
        """Verify load_mock_response() returns the same fixture data."""
        loaded = load_mock_response(7)
        assert loaded == STAGE7_MOCK_LLM_RESPONSE
