"""Prompt isolation tests for Stage 2: FieldRouter.

Tests the LLM prompt for field routing independently from the full pipeline,
using mock LLM responses loaded from shared fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
from tests.fixtures.stage_prompt_fixtures import (
    STAGE1_EXPECTED_SPANS,
    STAGE2_EXPECTED_AMBIGUITY_UPDATES,
    STAGE2_EXPECTED_ROUTES,
    STAGE2_MOCK_LLM_RESPONSE,
    compare_field_routes,
    generate_test_report,
    load_mock_response,
)


# =============================================================================
# Pytest Markers
# =============================================================================

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage2]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def input_spans() -> list[SpanIR]:
    """Spans produced by Stage 1 (input for Stage 2)."""
    return STAGE1_EXPECTED_SPANS


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM JSON response for Stage 2."""
    return STAGE2_MOCK_LLM_RESPONSE


@pytest.fixture
def expected_routes() -> FieldRouteIR:
    """Expected field route output for Stage 2."""
    return STAGE2_EXPECTED_ROUTES


@pytest.fixture
def expected_ambiguity_updates() -> list[dict]:
    """Expected ambiguity updates for Stage 2."""
    return STAGE2_EXPECTED_AMBIGUITY_UPDATES


@pytest.fixture
def router(pipeline_config: MagicMock, mock_client: MagicMock) -> FieldRouter:
    """Create FieldRouter instance with mock client."""
    return FieldRouter(pipeline_config, mock_client)


# =============================================================================
# Tests
# =============================================================================


class TestStage2Prompt:
    """Test Stage 2 FieldRouter prompt in isolation."""

    def test_prompt_produces_expected_routes(
        self,
        router: FieldRouter,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        expected_routes: FieldRouteIR,
    ) -> None:
        """Verify that with a mock LLM response, execute() produces expected routes."""
        mock_client.call_json.return_value = mock_llm_response

        routes, ambiguity_updates = router.execute(input_spans)

        # Assert - structure
        assert isinstance(routes, FieldRouteIR), "First output must be FieldRouteIR"
        assert isinstance(ambiguity_updates, list), "Second output must be a list"

        # Assert - key fields
        mismatches = compare_field_routes(routes, expected_routes)
        report = generate_test_report(2, "FieldRouter", mismatches)
        assert not mismatches, f"Stage 2 prompt test failed:\n{report}"

    def test_prompt_calls_llm_with_correct_stage_name(
        self,
        router: FieldRouter,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
    ) -> None:
        """Verify the LLM is called with the correct stage_name."""
        mock_client.call_json.return_value = mock_llm_response
        router.execute(input_spans)

        mock_client.call_json.assert_called_once()
        call_kwargs = mock_client.call_json.call_args[1]
        assert call_kwargs["stage_name"] == "stage2_field_router"

    def test_prompt_output_has_all_six_fields(
        self,
        router: FieldRouter,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
    ) -> None:
        """Verify the output FieldRouteIR has all 6 semantic fields."""
        mock_client.call_json.return_value = mock_llm_response
        routes, _ = router.execute(input_spans)

        for field_name in ["identity", "audience", "rules", "domain", "integrations", "behavior"]:
            assert hasattr(routes, field_name), f"FieldRouteIR missing field: {field_name}"
            assert isinstance(getattr(routes, field_name), list), f"{field_name} must be a list"

    def test_prompt_output_no_overlap(
        self,
        router: FieldRouter,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
    ) -> None:
        """Verify no span appears in multiple fields."""
        mock_client.call_json.return_value = mock_llm_response
        routes, _ = router.execute(input_spans)

        overlaps = routes.validate_no_overlap()
        assert len(overlaps) == 0, f"Overlapping spans detected: {overlaps}"

    def test_prompt_ambiguity_updates(
        self,
        router: FieldRouter,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        expected_ambiguity_updates: list[dict],
    ) -> None:
        """Verify ambiguity updates match expected."""
        mock_client.call_json.return_value = mock_llm_response
        _, ambiguity_updates = router.execute(input_spans)

        assert len(ambiguity_updates) == len(expected_ambiguity_updates), (
            f"Expected {len(expected_ambiguity_updates)} ambiguity updates, got {len(ambiguity_updates)}"
        )

    def test_prompt_rules_field_populated(
        self,
        router: FieldRouter,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
    ) -> None:
        """Verify the rules field contains expected span IDs."""
        mock_client.call_json.return_value = mock_llm_response
        routes, _ = router.execute(input_spans)

        assert "s5" in routes.rules, "s5 (policies span) should be in rules field"

    def test_prompt_fixture_loader(
        self,
        router: FieldRouter,
        mock_client: MagicMock,
        input_spans: list[SpanIR],
    ) -> None:
        """Verify load_mock_response() returns the same fixture data."""
        loaded = load_mock_response(2)
        assert loaded == STAGE2_MOCK_LLM_RESPONSE

        mock_client.call_json.return_value = loaded
        routes, _ = router.execute(input_spans)
        assert set(routes.rules) == set(STAGE2_EXPECTED_ROUTES.rules)
