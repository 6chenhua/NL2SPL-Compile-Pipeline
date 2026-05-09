"""Usage-example prompt test for Stage 1 only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
from tests.fixtures.usage_prompt_expectations import (
    USAGE_RAW_TEXT,
    usage_stage1_spans,
    usage_stage_response,
)


pytestmark = [pytest.mark.prompt_test, pytest.mark.stage1]


class TestUsageStage1Prompt:
    """Debug Stage 1 prompt behavior without running the full pipeline."""

    def test_usage_raw_text_slices_to_best_expected_spans(
        self,
        pipeline_config: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        """Stage 1 should parse the usage raw text into semantic spans."""
        mock_client.call_json.return_value = usage_stage_response(1)
        slicer = SpanSlicer(pipeline_config, mock_client)

        spans = slicer.execute(USAGE_RAW_TEXT)

        assert spans == usage_stage1_spans()
        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage1_span_slicer"
        assert "Internal newsletters" in call_kwargs["user_prompt"]
        assert "Delegation policy" in call_kwargs["user_prompt"]
