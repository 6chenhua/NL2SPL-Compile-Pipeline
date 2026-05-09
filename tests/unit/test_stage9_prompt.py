"""Prompt isolation tests for Stage 9: ConstraintExtractor.

Tests the LLM prompt for constraint extraction independently from the full pipeline,
using mock LLM responses loaded from shared fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.constraint_ir import ConstraintIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor
from tests.fixtures.stage_prompt_fixtures import (
    STAGE1_EXPECTED_SPANS,
    STAGE2_EXPECTED_ROUTES,
    STAGE4_EXPECTED_FLOW,
    STAGE5_EXPECTED_BLOCKS,
    STAGE6_EXPECTED_SYMBOL_TABLE,
    STAGE7_EXPECTED_STEPS,
    STAGE9_EXPECTED_CONSTRAINTS,
    STAGE9_MOCK_LLM_RESPONSE,
    compare_constraints,
    generate_test_report,
    load_mock_response,
)


# =============================================================================
# Pytest Markers
# =============================================================================

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage9]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def input_spans() -> list[SpanIR]:
    """Spans produced by Stage 1 (input for Stage 9)."""
    return STAGE1_EXPECTED_SPANS


@pytest.fixture
def input_routes() -> FieldRouteIR:
    """Field routes produced by Stage 2 (input for Stage 9)."""
    return STAGE2_EXPECTED_ROUTES


@pytest.fixture
def input_flow() -> FlowStructureIR:
    """Flow structure produced by Stage 4 (input for Stage 9)."""
    return STAGE4_EXPECTED_FLOW


@pytest.fixture
def input_blocks() -> BlockStructureIR:
    """Block structure produced by Stage 5 (input for Stage 9)."""
    return STAGE5_EXPECTED_BLOCKS


@pytest.fixture
def input_symbol_table() -> SymbolTable:
    """Symbol table produced by Stage 6 (input for Stage 9)."""
    return STAGE6_EXPECTED_SYMBOL_TABLE


@pytest.fixture
def input_steps() -> list[StepIR]:
    """Steps produced by Stage 7 (input for Stage 9)."""
    return STAGE7_EXPECTED_STEPS


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM JSON response for Stage 9."""
    return STAGE9_MOCK_LLM_RESPONSE


@pytest.fixture
def expected_constraints() -> list[ConstraintIR]:
    """Expected constraint output for Stage 9."""
    return STAGE9_EXPECTED_CONSTRAINTS


@pytest.fixture
def extractor(pipeline_config: MagicMock, mock_client: MagicMock) -> ConstraintExtractor:
    """Create ConstraintExtractor instance with mock client."""
    return ConstraintExtractor(pipeline_config, mock_client)


# =============================================================================
# Tests
# =============================================================================


class TestStage9Prompt:
    """Test Stage 9 ConstraintExtractor prompt in isolation."""

    def test_prompt_produces_expected_constraints(
        self,
        extractor: ConstraintExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
        input_steps: list[StepIR],
        expected_constraints: list[ConstraintIR],
    ) -> None:
        """Verify that with a mock LLM response, execute() produces expected constraints."""
        mock_client.call_json.return_value = mock_llm_response

        constraints = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table, input_steps)
        )

        # Assert - structure
        assert isinstance(constraints, list), "Output must be a list"
        assert all(isinstance(c, ConstraintIR) for c in constraints), "All items must be ConstraintIR"

        # Assert - key fields
        mismatches = compare_constraints(constraints, expected_constraints)
        report = generate_test_report(9, "ConstraintExtractor", mismatches)
        assert not mismatches, f"Stage 9 prompt test failed:\n{report}"

    def test_prompt_calls_llm_with_correct_stage_name(
        self,
        extractor: ConstraintExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
        input_steps: list[StepIR],
    ) -> None:
        """Verify the LLM is called with the correct stage_name."""
        mock_client.call_json.return_value = mock_llm_response
        extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table, input_steps)
        )

        mock_client.call_json.assert_called_once()
        call_kwargs = mock_client.call_json.call_args[1]
        assert call_kwargs["stage_name"] == "stage9_constraint_extractor"

    def test_prompt_constraint_ids_valid(
        self,
        extractor: ConstraintExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
        input_steps: list[StepIR],
    ) -> None:
        """Verify all constraint IDs have valid format (c{N})."""
        mock_client.call_json.return_value = mock_llm_response
        constraints = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table, input_steps)
        )

        for constraint in constraints:
            assert constraint.constraint_id.startswith("c"), (
                f"constraint_id {constraint.constraint_id} must start with 'c'"
            )

    def test_prompt_constraint_kinds_valid(
        self,
        extractor: ConstraintExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
        input_steps: list[StepIR],
    ) -> None:
        """Verify all constraint kinds are valid."""
        mock_client.call_json.return_value = mock_llm_response
        constraints = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table, input_steps)
        )

        valid_kinds = {
            "requirement", "prohibition", "gate", "evidence",
            "approval", "safety", "audit", "delegation_boundary",
            "promotion_requirement",
        }
        for constraint in constraints:
            assert constraint.kind in valid_kinds, (
                f"kind {constraint.kind} must be one of {valid_kinds}"
            )

    def test_prompt_constraints_have_targets(
        self,
        extractor: ConstraintExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
        input_steps: list[StepIR],
    ) -> None:
        """Verify all constraints have target references."""
        mock_client.call_json.return_value = mock_llm_response
        constraints = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table, input_steps)
        )

        for constraint in constraints:
            assert isinstance(constraint.targets, list), (
                f"Constraint {constraint.constraint_id} targets must be a list"
            )
            assert len(constraint.targets) > 0, (
                f"Constraint {constraint.constraint_id} must have at least one target"
            )

    def test_prompt_constraints_have_source_spans(
        self,
        extractor: ConstraintExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
        input_steps: list[StepIR],
    ) -> None:
        """Verify all constraints reference source spans."""
        mock_client.call_json.return_value = mock_llm_response
        constraints = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table, input_steps)
        )

        for constraint in constraints:
            assert isinstance(constraint.source_span_ids, list), (
                f"Constraint {constraint.constraint_id} source_span_ids must be a list"
            )

    def test_prompt_prohibition_constraint_present(
        self,
        extractor: ConstraintExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_flow: FlowStructureIR,
        input_blocks: BlockStructureIR,
        input_symbol_table: SymbolTable,
        input_steps: list[StepIR],
    ) -> None:
        """Verify at least one prohibition constraint is extracted."""
        mock_client.call_json.return_value = mock_llm_response
        constraints = extractor.execute(
            (input_spans, input_routes, input_flow, input_blocks, input_symbol_table, input_steps)
        )

        prohibition_kinds = [c for c in constraints if c.kind == "prohibition"]
        assert len(prohibition_kinds) > 0, "At least one prohibition constraint should be extracted"

    def test_prompt_fixture_loader(self) -> None:
        """Verify load_mock_response() returns the same fixture data."""
        loaded = load_mock_response(9)
        assert loaded == STAGE9_MOCK_LLM_RESPONSE
