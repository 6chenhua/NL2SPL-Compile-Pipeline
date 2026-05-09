"""Prompt isolation tests for Stage 8: ProfileExtractor.

Tests the LLM prompt for profile extraction independently from the full pipeline,
using mock LLM responses loaded from shared fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.agent_profile_ir import AgentProfileIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.pipeline.stages.stage8_profile_extractor import ProfileExtractor
from tests.fixtures.stage_prompt_fixtures import (
    STAGE1_EXPECTED_SPANS,
    STAGE2_EXPECTED_ROUTES,
    STAGE6_EXPECTED_SYMBOL_TABLE,
    STAGE8_EXPECTED_PROFILE,
    STAGE8_MOCK_LLM_RESPONSE,
    compare_profiles,
    generate_test_report,
    load_mock_response,
)


# =============================================================================
# Pytest Markers
# =============================================================================

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage8]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def input_spans() -> list[SpanIR]:
    """Spans produced by Stage 1 (input for Stage 8)."""
    return STAGE1_EXPECTED_SPANS


@pytest.fixture
def input_routes() -> FieldRouteIR:
    """Field routes produced by Stage 2 (input for Stage 8)."""
    return STAGE2_EXPECTED_ROUTES


@pytest.fixture
def input_symbol_table() -> SymbolTable:
    """Symbol table produced by Stage 6 (input for Stage 8)."""
    return STAGE6_EXPECTED_SYMBOL_TABLE


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM JSON response for Stage 8."""
    return STAGE8_MOCK_LLM_RESPONSE


@pytest.fixture
def expected_profile() -> AgentProfileIR:
    """Expected agent profile output for Stage 8."""
    return STAGE8_EXPECTED_PROFILE


@pytest.fixture
def extractor(pipeline_config: MagicMock, mock_client: MagicMock) -> ProfileExtractor:
    """Create ProfileExtractor instance with mock client."""
    return ProfileExtractor(pipeline_config, mock_client)


# =============================================================================
# Tests
# =============================================================================


class TestStage8Prompt:
    """Test Stage 8 ProfileExtractor prompt in isolation."""

    def test_prompt_produces_expected_profile(
        self,
        extractor: ProfileExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_symbol_table: SymbolTable,
        expected_profile: AgentProfileIR,
    ) -> None:
        """Verify that with a mock LLM response, execute() produces expected profile."""
        mock_client.call_json.return_value = mock_llm_response

        profile = extractor.execute((input_spans, input_routes, input_symbol_table))

        # Assert - structure
        assert isinstance(profile, AgentProfileIR), "Output must be AgentProfileIR"

        # Assert - key fields
        mismatches = compare_profiles(profile, expected_profile)
        report = generate_test_report(8, "ProfileExtractor", mismatches)
        assert not mismatches, f"Stage 8 prompt test failed:\n{report}"

    def test_prompt_calls_llm_with_correct_stage_name(
        self,
        extractor: ProfileExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify the LLM is called with the correct stage_name."""
        mock_client.call_json.return_value = mock_llm_response
        extractor.execute((input_spans, input_routes, input_symbol_table))

        mock_client.call_json.assert_called_once()
        call_kwargs = mock_client.call_json.call_args[1]
        assert call_kwargs["stage_name"] == "stage8_profile_extractor"

    def test_prompt_persona_role_populated(
        self,
        extractor: ProfileExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify persona role is populated."""
        mock_client.call_json.return_value = mock_llm_response
        profile = extractor.execute((input_spans, input_routes, input_symbol_table))

        assert profile.persona is not None, "Persona must not be None"
        assert isinstance(profile.persona.role, str), "Persona role must be a string"
        assert len(profile.persona.role) > 0, "Persona role must not be empty"

    def test_prompt_persona_aspects_structure(
        self,
        extractor: ProfileExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify persona aspects have valid structure (name + text)."""
        mock_client.call_json.return_value = mock_llm_response
        profile = extractor.execute((input_spans, input_routes, input_symbol_table))

        for aspect in profile.persona.aspects:
            assert isinstance(aspect.name, str), f"Aspect name must be str, got {type(aspect.name)}"
            assert isinstance(aspect.text, str), f"Aspect text must be str, got {type(aspect.text)}"
            assert len(aspect.name) > 0, "Aspect name must not be empty"

    def test_prompt_audience_aspects_structure(
        self,
        extractor: ProfileExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify audience aspects have valid structure."""
        mock_client.call_json.return_value = mock_llm_response
        profile = extractor.execute((input_spans, input_routes, input_symbol_table))

        for aspect in profile.audience_aspects:
            assert isinstance(aspect.name, str), f"Audience aspect name must be str"
            assert isinstance(aspect.text, str), f"Audience aspect text must be str"
            assert len(aspect.name) > 0, "Audience aspect name must not be empty"

    def test_prompt_concepts_structure(
        self,
        extractor: ProfileExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_symbol_table: SymbolTable,
    ) -> None:
        """Verify concepts have valid structure (term + definition)."""
        mock_client.call_json.return_value = mock_llm_response
        profile = extractor.execute((input_spans, input_routes, input_symbol_table))

        for concept in profile.concepts:
            assert isinstance(concept.term, str), f"Concept term must be str"
            assert isinstance(concept.definition, str), f"Concept definition must be str"
            assert len(concept.term) > 0, "Concept term must not be empty"

    def test_prompt_expected_role_value(
        self,
        extractor: ProfileExtractor,
        mock_client: MagicMock,
        mock_llm_response: dict,
        input_spans: list[SpanIR],
        input_routes: FieldRouteIR,
        input_symbol_table: SymbolTable,
        expected_profile: AgentProfileIR,
    ) -> None:
        """Verify persona role matches expected value."""
        mock_client.call_json.return_value = mock_llm_response
        profile = extractor.execute((input_spans, input_routes, input_symbol_table))

        assert profile.persona.role == expected_profile.persona.role, (
            f"Persona role mismatch: {profile.persona.role!r} != {expected_profile.persona.role!r}"
        )

    def test_prompt_fixture_loader(self) -> None:
        """Verify load_mock_response() returns the same fixture data."""
        loaded = load_mock_response(8)
        assert loaded == STAGE8_MOCK_LLM_RESPONSE
