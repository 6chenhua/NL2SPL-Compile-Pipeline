"""Usage-example prompt test for Stage 2 only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
from tests.fixtures.usage_prompt_expectations import (
    assert_field_routes_equal,
    usage_stage1_spans,
    usage_stage2_ambiguity_updates,
    usage_stage2_routes,
    usage_stage_response,
)


pytestmark = [pytest.mark.prompt_test, pytest.mark.stage2]


class TestUsageStage2Prompt:
    """Debug Stage 2 prompt behavior without running the full pipeline."""

    def test_usage_spans_route_to_best_expected_fields(
        self,
        pipeline_config: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        """Stage 2 should route usage spans and mark mixed delegation content."""
        input_spans = usage_stage1_spans()
        mock_client.call_json.return_value = usage_stage_response(2)
        router = FieldRouter(pipeline_config, mock_client)

        routes, ambiguity_updates = router.execute(input_spans)

        assert_field_routes_equal(routes, usage_stage2_routes())
        assert ambiguity_updates == usage_stage2_ambiguity_updates()
        assert input_spans[-1].ambiguity.is_ambiguous
        assert input_spans[-1].ambiguity.needs_split
        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage2_field_router"
        assert '"span_id": "s18"' in call_kwargs["user_prompt"]
