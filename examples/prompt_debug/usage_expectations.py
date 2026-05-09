"""Usage-example prompt expectations for standalone debugging scripts.

The canonical expected IRs live in tests/fixtures so unit tests and these
standalone scripts compare against the same target. These scripts are not part
of the test suite; they just reuse the shared data to avoid drift.
"""

from __future__ import annotations

from tests.fixtures.usage_prompt_expectations import (
    USAGE_RAW_TEXT,
    usage_stage1_spans,
    usage_stage2_ambiguity_updates,
    usage_stage2_routes,
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage4_flow,
    usage_stage5_blocks,
    usage_stage6_resources,
    usage_stage6_symbol_table,
    usage_stage7_steps,
    usage_stage8_profile,
    usage_stage9_constraints,
)
