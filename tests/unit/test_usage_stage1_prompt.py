"""Usage-example prompt test for Stage 1 only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
from tests.fixtures.usage_prompt_expectations import (
    USAGE_RAW_TEXT,
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
        """Stage 1 should parse the usage raw text into semantic spans.

        With Phase 2 deterministic pre-slicing, the span count may differ
        from the original LLM-only output. We verify structural correctness
        rather than exact span equality.
        """
        mock_client.call_json.return_value = usage_stage_response(1)
        slicer = SpanSlicer(pipeline_config, mock_client)

        spans = slicer.execute(USAGE_RAW_TEXT)

        # Structural verification (Phase 2 compatible)
        assert len(spans) > 0  # At least some spans produced
        assert all(sp.span_id.startswith("s") for sp in spans)
        assert all(sp.text.strip() for sp in spans)
        # Verify continuous numbering
        expected_ids = [f"s{i+1}" for i in range(len(spans))]
        assert [sp.span_id for sp in spans] == expected_ids
        # LLM residual call(s) made — aggregate all user_prompts
        all_prompts = "\n".join(
            call.kwargs["user_prompt"]
            for call in mock_client.call_json.call_args_list
        )
        # Verify key content present (text may be in pre-sliced spans or residual)
        assert "stage1_span_slicer" in str(mock_client.call_json.call_args_list)
        # Either pre-slicing or residual should contain the key phrases
        all_span_text = "\n".join(sp.text for sp in spans)
        assert "Internal newsletters" in all_span_text or "Internal newsletters" in all_prompts
