"""Usage-example prompt test for Stage 5 only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler
from tests.fixtures.usage_prompt_expectations import (
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage4_flow,
    usage_stage5_blocks,
    usage_stage_response,
)

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage5]


class TestUsageStage5Prompt:
    """Debug Stage 5 prompt behavior without running the full pipeline."""

    def test_usage_flows_assemble_to_best_expected_blocks(
        self,
        pipeline_config: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        """Stage 5 should build sequential and conditional blocks."""
        mock_client.call_json.return_value = usage_stage_response(5)
        assembler = BlockAssembler(pipeline_config, mock_client)

        blocks = assembler.execute(
            (usage_stage3_spans(), usage_stage3_routes(), usage_stage4_flow())
        )

        assert blocks == usage_stage5_blocks()
        assert [block.block_type for block in blocks.main_flow_blocks] == [
            "SEQUENTIAL",
            "IF",
            "SEQUENTIAL",
            "IF",
        ]
        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage5_block_assembler"
        assert "sources are needed and available" in call_kwargs["user_prompt"]
        assert "Flow structure with span text" in call_kwargs["user_prompt"]
        assert '"span_id": "s8"' in call_kwargs["user_prompt"]
        assert "behavior spans" not in call_kwargs["user_prompt"]
        assert "ambiguity" not in call_kwargs["user_prompt"]
