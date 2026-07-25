"""Usage-example prompt test for Stage 3 only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.pipeline.stages.stage3_ambiguity_resolver import AmbiguityResolver
from tests.fixtures.usage_prompt_expectations import (
    usage_stage1_spans,
    usage_stage2_ambiguity_updates,
    usage_stage2_routes,
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage_response,
)

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage3]


class TestUsageStage3Prompt:
    """Debug Stage 3 prompt behavior without running the full pipeline."""

    def test_usage_ambiguous_delegation_span_is_split(
        self,
        pipeline_config: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        """Stage 3 should split s18 into behavior and rules sub-spans."""
        mock_client.call_json.return_value = usage_stage_response(3)
        resolver = AmbiguityResolver(pipeline_config, mock_client)

        spans, routes = resolver.execute(
            (
                usage_stage1_spans(),
                usage_stage2_routes(),
                usage_stage2_ambiguity_updates(),
            )
        )

        assert spans == usage_stage3_spans()
        expected_routes = usage_stage3_routes()
        assert routes.get_all_span_ids() == expected_routes.get_all_span_ids()
        assert routes.annotations == expected_routes.annotations
        assert all(
            diagnostic.startswith("Stage 3: split child 's18")
            for diagnostic in routes.route_diagnostics
        )
        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage3_ambiguity_resolver"
        assert '"span_id": "s18"' in call_kwargs["user_prompt"]
