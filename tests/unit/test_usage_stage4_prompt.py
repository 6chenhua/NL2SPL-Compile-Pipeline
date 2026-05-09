"""Usage-example prompt test for Stage 4 only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler
from tests.fixtures.usage_prompt_expectations import (
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage4_flow,
    usage_stage_response,
)


pytestmark = [pytest.mark.prompt_test, pytest.mark.stage4]


class TestUsageStage4Prompt:
    """Debug Stage 4 prompt behavior without running the full pipeline."""

    def test_usage_behavior_spans_assemble_to_best_expected_flows(
        self,
        pipeline_config: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        """Stage 4 should separate main, alternative, exception, and delegation."""
        mock_client.call_json.return_value = usage_stage_response(4)
        assembler = FlowAssembler(pipeline_config, mock_client)

        flow = assembler.execute((usage_stage3_spans(), usage_stage3_routes()))

        assert flow == usage_stage4_flow()
        assert flow.main_flow_spans == ["s4", "s5", "s6", "s7", "s8", "s9"]
        assert flow.alternative_flows[0].spans == ["s10"]
        assert flow.exception_flows[0].spans == ["s11"]
        assert flow.delegation_candidates[0].spans == ["s18a"]
        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage4_flow_assembler"
        assert '"span_id": "s18a"' in call_kwargs["user_prompt"]
