"""Usage-example prompt test for Stage 8 only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.pipeline.stages.stage8_profile_extractor import ProfileExtractor
from tests.fixtures.usage_prompt_expectations import (
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage6_symbol_table,
    usage_stage8_profile,
    usage_stage_response,
)


pytestmark = [pytest.mark.prompt_test, pytest.mark.stage8]


class TestUsageStage8Prompt:
    """Debug Stage 8 prompt behavior without running the full pipeline."""

    def test_usage_profile_extracts_best_expected_profile(
        self,
        pipeline_config: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        """Stage 8 should infer a non-empty persona role from the usage text."""
        mock_client.call_json.return_value = usage_stage_response(8)
        extractor = ProfileExtractor(pipeline_config, mock_client)

        profile = extractor.execute(
            (usage_stage3_spans(), usage_stage3_routes(), usage_stage6_symbol_table())
        )

        assert profile == usage_stage8_profile()
        assert profile.persona.role == "Internal communications specialist"
        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage8_profile_extractor"
        assert "all source spans" in call_kwargs["user_prompt"]
        assert "The role field must never be an empty string" in call_kwargs["system_prompt"]
