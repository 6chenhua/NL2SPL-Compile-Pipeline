"""Prompt isolation tests for Stage 3: AmbiguityResolver.

Tests the LLM prompt for ambiguity resolution independently from the full pipeline,
using mock LLM responses loaded from shared fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage3_ambiguity_resolver import AmbiguityResolver
from tests.fixtures.stage_prompt_fixtures import (
    STAGE1_EXPECTED_SPANS,
    STAGE2_EXPECTED_AMBIGUITY_UPDATES,
    STAGE2_EXPECTED_ROUTES,
    STAGE3_MOCK_LLM_RESPONSE,
    load_mock_response,
)

# =============================================================================
# Pytest Markers
# =============================================================================

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage3]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def input_spans() -> list[SpanIR]:
    """Spans produced by Stage 1 (input for Stage 3)."""
    return STAGE1_EXPECTED_SPANS


@pytest.fixture
def input_routes() -> FieldRouteIR:
    """Field routes produced by Stage 2 (input for Stage 3)."""
    return STAGE2_EXPECTED_ROUTES


@pytest.fixture
def input_ambiguity_updates() -> list[dict]:
    """Ambiguity updates from Stage 2 (input for Stage 3)."""
    return STAGE2_EXPECTED_AMBIGUITY_UPDATES


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM JSON response for Stage 3."""
    return STAGE3_MOCK_LLM_RESPONSE


@pytest.fixture
def resolver(pipeline_config: MagicMock, mock_client: MagicMock) -> AmbiguityResolver:
    """Create AmbiguityResolver instance with mock client."""
    return AmbiguityResolver(pipeline_config, mock_client)


# =============================================================================
# Tests
# =============================================================================


class TestStage3Prompt:
    """Test Stage 3 AmbiguityResolver prompt in isolation."""

    def test_prompt_no_ambiguity_returns_original(
        self,
        resolver: AmbiguityResolver,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_ambiguity_updates: list[dict],
    ) -> None:
        """When no ambiguity updates, resolver returns original spans and routes."""
        # No LLM call should be made when ambiguity_updates is empty
        resolved_spans, resolved_routes = resolver.execute(
            (input_spans, input_routes, input_ambiguity_updates)
        )

        assert resolved_spans is input_spans, "Should return original spans when no ambiguity"
        assert resolved_routes is input_routes, "Should return original routes when no ambiguity"

    def test_prompt_with_ambiguity_produces_resolved_output(
        self,
        resolver: AmbiguityResolver,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
    ) -> None:
        """Verify that with ambiguity updates and mock LLM response, execute() resolves correctly."""
        # Create ambiguity updates to trigger LLM call
        ambiguity_updates = [
            {
                "span_id": "s1",
                "is_ambiguous": True,
                "reasons": ["Contains both identity and task family info"],
                "needs_split": True,
            }
        ]
        mock_client.call_json.return_value = mock_llm_response

        resolved_spans, resolved_routes = resolver.execute(
            (input_spans, input_routes, ambiguity_updates)
        )

        # Assert - structure
        assert isinstance(resolved_spans, list), "First output must be a list"
        assert isinstance(resolved_routes, FieldRouteIR), "Second output must be FieldRouteIR"

        # Assert - ambiguous span s1 was removed and replaced with resolved spans
        resolved_ids = {s.span_id for s in resolved_spans}
        assert "s1" not in resolved_ids, "Ambiguous span s1 should be removed"
        assert "s1a" in resolved_ids, "Resolved span s1a should be present"

        # Assert - resolved routes have correct structure
        assert "s5" in resolved_routes.rules, "Rules field should still contain s5"
        assert len(resolved_routes.behavior) > 0, "Behavior field should not be empty"

    def test_prompt_calls_llm_with_correct_stage_name(
        self,
        resolver: AmbiguityResolver,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
    ) -> None:
        """Verify the LLM is called with the correct stage_name when ambiguity exists."""
        ambiguity_updates = [
            {"span_id": "s1", "is_ambiguous": True, "reasons": ["test"], "needs_split": True}
        ]
        mock_client.call_json.return_value = mock_llm_response
        resolver.execute((input_spans, input_routes, ambiguity_updates))

        mock_client.call_json.assert_called_once()
        call_kwargs = mock_client.call_json.call_args[1]
        assert call_kwargs["stage_name"] == "stage3_ambiguity_resolver"

    def test_prompt_no_llm_call_without_ambiguity(
        self,
        resolver: AmbiguityResolver,
        mock_client: MagicMock,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
    ) -> None:
        """Verify no LLM call is made when there are no ambiguity updates."""
        resolver.execute((input_spans, input_routes, []))
        mock_client.call_json.assert_not_called()

    def test_prompt_resolved_routes_no_overlap(
        self,
        resolver: AmbiguityResolver,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
    ) -> None:
        """Verify resolved routes have no overlapping spans."""
        ambiguity_updates = [
            {"span_id": "s1", "is_ambiguous": True, "reasons": ["test"], "needs_split": True}
        ]
        mock_client.call_json.return_value = mock_llm_response
        _, resolved_routes = resolver.execute((input_spans, input_routes, ambiguity_updates))

        overlaps = resolved_routes.validate_no_overlap()
        assert len(overlaps) == 0, f"Overlapping spans in resolved routes: {overlaps}"

    def test_prompt_fixture_loader(self) -> None:
        """Verify load_mock_response() returns the same fixture data."""
        loaded = load_mock_response(3)
        assert loaded == STAGE3_MOCK_LLM_RESPONSE
