"""Usage-example prompt test for Stage 7 only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor
from tests.fixtures.usage_prompt_expectations import (
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage4_flow,
    usage_stage5_blocks,
    usage_stage6_symbol_table,
    usage_stage7_steps,
    usage_stage_response,
)


pytestmark = [pytest.mark.prompt_test, pytest.mark.stage7]


class TestUsageStage7Prompt:
    """Debug Stage 7 prompt behavior without running the full pipeline."""

    def test_usage_ir_extracts_best_expected_steps(
        self,
        pipeline_config: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        """Stage 7 should extract canonical action text and variable IO."""
        mock_client.call_json.return_value = usage_stage_response(7)
        extractor = StepExtractor(pipeline_config, mock_client)

        steps, updated_symbol_table = extractor.execute(
            (
                usage_stage3_spans(),
                usage_stage3_routes(),
                usage_stage4_flow(),
                usage_stage5_blocks(),
                usage_stage6_symbol_table(),
            )
        )

        assert steps == usage_stage7_steps()
        assert updated_symbol_table.variables["communication_type"].producer_step == "st_1"
        assert updated_symbol_table.variables["user_request"].consumer_steps
        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage7_step_extractor"
        assert "Canonical action text" in call_kwargs["system_prompt"]
        assert "Known Variable List" in call_kwargs["system_prompt"]
