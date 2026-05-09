"""Usage-example prompt test for Stage 6 only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor
from tests.fixtures.usage_prompt_expectations import (
    assert_symbol_table_matches_resources,
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage6_resources,
    usage_stage_response,
)


pytestmark = [pytest.mark.prompt_test, pytest.mark.stage6]


class TestUsageStage6Prompt:
    """Debug Stage 6 prompt behavior without running the full pipeline."""

    def test_usage_spans_extract_best_expected_resources(
        self,
        pipeline_config: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        """Stage 6 should extract inputs, outputs, and step variables."""
        mock_client.call_json.return_value = usage_stage_response(6)
        extractor = ResourceExtractor(pipeline_config, mock_client)

        resources, symbol_table = extractor.execute(
            (usage_stage3_spans(), usage_stage3_routes())
        )

        expected = usage_stage6_resources()
        assert resources == expected
        assert_symbol_table_matches_resources(symbol_table, expected)
        assert "user_request" in resources.get_variable_names()
        assert "completion_status" in resources.get_variable_names()
        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage6_resource_extractor"
        assert "Inputs for each run" in call_kwargs["user_prompt"]
