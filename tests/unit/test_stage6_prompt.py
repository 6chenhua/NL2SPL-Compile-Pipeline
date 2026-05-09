"""Prompt isolation tests for Stage 6: ResourceExtractor.

Tests the LLM prompt for resource extraction independently from the full pipeline,
using mock LLM responses loaded from shared fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.resource_registry_ir import ResourceRegistryIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor
from tests.fixtures.stage_prompt_fixtures import (
    STAGE1_EXPECTED_SPANS,
    STAGE2_EXPECTED_ROUTES,
    STAGE6_EXPECTED_RESOURCES,
    STAGE6_EXPECTED_SYMBOL_TABLE,
    STAGE6_MOCK_LLM_RESPONSE,
    compare_resource_registries,
    generate_test_report,
    load_mock_response,
)


# =============================================================================
# Pytest Markers
# =============================================================================

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage6]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def input_spans() -> list[SpanIR]:
    """Spans produced by Stage 1 (input for Stage 6)."""
    return STAGE1_EXPECTED_SPANS


@pytest.fixture
def input_routes() -> FieldRouteIR:
    """Field routes produced by Stage 2 (input for Stage 6)."""
    return STAGE2_EXPECTED_ROUTES


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM JSON response for Stage 6."""
    return STAGE6_MOCK_LLM_RESPONSE


@pytest.fixture
def expected_resources() -> ResourceRegistryIR:
    """Expected resource registry output for Stage 6."""
    return STAGE6_EXPECTED_RESOURCES


@pytest.fixture
def expected_symbol_table() -> SymbolTable:
    """Expected symbol table output for Stage 6."""
    return STAGE6_EXPECTED_SYMBOL_TABLE


@pytest.fixture
def extractor(pipeline_config: MagicMock, mock_client: MagicMock) -> ResourceExtractor:
    """Create ResourceExtractor instance with mock client."""
    return ResourceExtractor(pipeline_config, mock_client)


# =============================================================================
# Tests
# =============================================================================


class TestStage6Prompt:
    """Test Stage 6 ResourceExtractor prompt in isolation."""

    def test_prompt_produces_expected_resources(
        self,
        extractor: ResourceExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        expected_resources: ResourceRegistryIR,
    ) -> None:
        """Verify that with a mock LLM response, execute() produces expected resources."""
        mock_client.call_json.return_value = mock_llm_response

        resources, symbol_table = extractor.execute((input_spans, input_routes))

        # Assert - structure
        assert isinstance(resources, ResourceRegistryIR), "First output must be ResourceRegistryIR"
        assert isinstance(symbol_table, SymbolTable), "Second output must be SymbolTable"

        # Assert - key fields
        mismatches = compare_resource_registries(resources, expected_resources)
        report = generate_test_report(6, "ResourceExtractor", mismatches)
        assert not mismatches, f"Stage 6 prompt test failed:\n{report}"

    def test_prompt_calls_llm_with_correct_stage_name(
        self,
        extractor: ResourceExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
    ) -> None:
        """Verify the LLM is called with the correct stage_name."""
        mock_client.call_json.return_value = mock_llm_response
        extractor.execute((input_spans, input_routes))

        mock_client.call_json.assert_called_once()
        call_kwargs = mock_client.call_json.call_args[1]
        assert call_kwargs["stage_name"] == "stage6_resource_extractor"

    def test_prompt_symbol_table_populated(
        self,
        extractor: ResourceExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        expected_symbol_table: SymbolTable,
    ) -> None:
        """Verify symbol table is populated with expected variables."""
        mock_client.call_json.return_value = mock_llm_response
        _, symbol_table = extractor.execute((input_spans, input_routes))

        expected_var_names = set(expected_symbol_table.variables.keys())
        actual_var_names = set(symbol_table.variables.keys())
        assert actual_var_names == expected_var_names, (
            f"Variable names mismatch: {sorted(actual_var_names)} != {sorted(expected_var_names)}"
        )

    def test_prompt_variables_have_required_fields(
        self,
        extractor: ResourceExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
    ) -> None:
        """Verify all extracted variables have name, data_type, and source."""
        mock_client.call_json.return_value = mock_llm_response
        resources, _ = extractor.execute((input_spans, input_routes))

        for var in resources.variables:
            assert var.name, "Variable must have a name"
            assert var.data_type, f"Variable {var.name} must have a data_type"
            assert var.source in ("input", "output", "step", "api", "file"), (
                f"Variable {var.name} has invalid source: {var.source}"
            )

    def test_prompt_input_variables_present(
        self,
        extractor: ResourceExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
    ) -> None:
        """Verify input variables are extracted."""
        mock_client.call_json.return_value = mock_llm_response
        resources, _ = extractor.execute((input_spans, input_routes))

        input_vars = [v for v in resources.variables if v.source == "input"]
        assert len(input_vars) > 0, "At least one input variable should be extracted"
        assert any(v.name == "user_request" for v in input_vars), (
            "user_request should be an input variable"
        )

    def test_prompt_output_variables_present(
        self,
        extractor: ResourceExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
    ) -> None:
        """Verify output variables are extracted."""
        mock_client.call_json.return_value = mock_llm_response
        resources, _ = extractor.execute((input_spans, input_routes))

        output_vars = [v for v in resources.variables if v.source == "output"]
        assert len(output_vars) > 0, "At least one output variable should be extracted"

    def test_prompt_fixture_loader(self) -> None:
        """Verify load_mock_response() returns the same fixture data."""
        loaded = load_mock_response(6)
        assert loaded == STAGE6_MOCK_LLM_RESPONSE
