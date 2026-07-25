"""Prompt isolation tests for Stage 1: SpanSlicer.

Tests the LLM prompt for span slicing independently from the full pipeline,
using mock LLM responses loaded from shared fixtures.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
from tests.fixtures.stage_prompt_fixtures import (
    EXAMPLE_RAW_TEXT,
    STAGE1_EXPECTED_SPANS,
    STAGE1_MOCK_LLM_RESPONSE,
    compare_spans,
    generate_test_report,
    load_mock_response,
)

# =============================================================================
# Pytest Markers
# =============================================================================

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage1]


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def raw_text() -> str:
    """Example raw text input (from examples/usage.py pattern)."""
    return EXAMPLE_RAW_TEXT


@pytest.fixture
def mock_llm_response() -> dict:
    """Mock LLM JSON response for Stage 1."""
    return STAGE1_MOCK_LLM_RESPONSE


@pytest.fixture
def expected_spans() -> list[SpanIR]:
    """Expected span output for Stage 1."""
    return STAGE1_EXPECTED_SPANS


@pytest.fixture
def slicer(pipeline_config: MagicMock, mock_client: MagicMock) -> SpanSlicer:
    """Create SpanSlicer instance with mock client."""
    return SpanSlicer(pipeline_config, mock_client)


# =============================================================================
# Tests
# =============================================================================


class TestStage1Prompt:
    """Test Stage 1 SpanSlicer prompt in isolation."""

    def test_prompt_produces_expected_spans(
        self,
        slicer: SpanSlicer,
        mock_client: MagicMock,
        mock_llm_response: dict,
        raw_text: str,
        expected_spans: list[SpanIR],
    ) -> None:
        """Verify that with a mock LLM response, execute() produces expected spans."""
        # Arrange
        mock_client.call_json.return_value = mock_llm_response

        # Act
        actual_spans = slicer.execute(raw_text)

        # Assert - structure
        assert isinstance(actual_spans, list), "Output must be a list"
        assert all(isinstance(s, SpanIR) for s in actual_spans), "All items must be SpanIR"

        # Assert - key fields
        mismatches = compare_spans(actual_spans, expected_spans)
        report = generate_test_report(1, "SpanSlicer", mismatches)
        assert not mismatches, f"Stage 1 prompt test failed:\n{report}"

    def test_prompt_calls_llm_with_correct_stage_name(
        self,
        slicer: SpanSlicer,
        mock_client: MagicMock,
        mock_llm_response: dict,
        raw_text: str,
    ) -> None:
        """Verify the LLM is called with the correct stage_name."""
        mock_client.call_json.return_value = mock_llm_response
        slicer.execute(raw_text)

        mock_client.call_json.assert_called_once()
        call_kwargs = mock_client.call_json.call_args[1]
        assert call_kwargs["stage_name"] == "stage1_span_slicer"

    def test_prompt_output_has_valid_span_ids(
        self,
        slicer: SpanSlicer,
        mock_client: MagicMock,
        mock_llm_response: dict,
        raw_text: str,
    ) -> None:
        """Verify all output spans have valid span_id format (s{N})."""
        mock_client.call_json.return_value = mock_llm_response
        actual_spans = slicer.execute(raw_text)

        for span in actual_spans:
            assert span.span_id.startswith("s"), f"span_id {span.span_id} must start with 's'"

    def test_prompt_output_preserves_text(
        self,
        slicer: SpanSlicer,
        mock_client: MagicMock,
        mock_llm_response: dict,
        raw_text: str,
    ) -> None:
        """Verify output span texts are non-empty strings."""
        mock_client.call_json.return_value = mock_llm_response
        actual_spans = slicer.execute(raw_text)

        for span in actual_spans:
            assert isinstance(span.text, str), f"Span {span.span_id} text must be str"
            assert len(span.text) > 0, f"Span {span.span_id} text must not be empty"

    def test_prompt_output_span_count(
        self,
        slicer: SpanSlicer,
        mock_client: MagicMock,
        mock_llm_response: dict,
        raw_text: str,
        expected_spans: list[SpanIR],
    ) -> None:
        """Verify the number of spans matches expected."""
        mock_client.call_json.return_value = mock_llm_response
        actual_spans = slicer.execute(raw_text)

        assert len(actual_spans) == len(expected_spans), (
            f"Expected {len(expected_spans)} spans, got {len(actual_spans)}"
        )

    def test_prompt_with_empty_response(
        self,
        slicer: SpanSlicer,
        mock_client: MagicMock,
        raw_text: str,
    ) -> None:
        """Verify handling of empty LLM response (no spans)."""
        mock_client.call_json.return_value = {"spans": []}
        actual_spans = slicer.execute(raw_text)

        assert isinstance(actual_spans, list)
        assert len(actual_spans) == 0

    def test_prompt_fixture_loader(
        self,
        slicer: SpanSlicer,
        mock_client: MagicMock,
        raw_text: str,
    ) -> None:
        """Verify load_mock_response() returns the same fixture data."""
        loaded = load_mock_response(1)
        assert loaded == STAGE1_MOCK_LLM_RESPONSE

        mock_client.call_json.return_value = loaded
        actual_spans = slicer.execute(raw_text)
        assert len(actual_spans) == len(STAGE1_EXPECTED_SPANS)
