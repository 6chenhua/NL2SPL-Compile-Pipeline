"""Usage-example prompt test for Stage 9 only."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor
from tests.fixtures.usage_prompt_expectations import (
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage4_flow,
    usage_stage5_blocks,
    usage_stage6_symbol_table,
    usage_stage7_steps,
    usage_stage9_constraints,
    usage_stage_response,
)

pytestmark = [pytest.mark.prompt_test, pytest.mark.stage9]


class TestUsageStage9Prompt:
    """Debug Stage 9 prompt behavior without running the full pipeline."""

    def test_usage_rules_extract_best_expected_constraints(
        self,
        pipeline_config: MagicMock,
        mock_client: MagicMock,
    ) -> None:
        """Stage 9 should extract policy and gate constraints with targets."""
        mock_client.call_json.return_value = usage_stage_response(9)
        extractor = ConstraintExtractor(pipeline_config, mock_client)

        constraints = extractor.execute(
            (
                usage_stage3_spans(),
                usage_stage3_routes(),
                usage_stage4_flow(),
                usage_stage5_blocks(),
                usage_stage6_symbol_table(),
                usage_stage7_steps(),
            )
        )

        assert constraints == usage_stage9_constraints()
        assert {constraint.kind for constraint in constraints} >= {
            "prohibition",
            "evidence",
            "gate",
            "delegation_boundary",
        }
        call_kwargs = mock_client.call_json.call_args.kwargs
        assert call_kwargs["stage_name"] == "stage9_constraint_extractor"
        assert "Do not invent links" in call_kwargs["user_prompt"]
