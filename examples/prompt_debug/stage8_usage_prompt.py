"""Run Stage 8 prompt against expected upstream IRs and show a diff."""

from __future__ import annotations

from common import run_stage
from nl2spl.pipeline.stages.stage8_profile_extractor import ProfileExtractor
from usage_expectations import (
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage6_symbol_table,
    usage_stage8_profile,
)


STAGE_NAME = "stage8_profile_extractor"
EXPECTED_INPUT = (
    usage_stage3_spans(),
    usage_stage3_routes(),
    usage_stage6_symbol_table(),
)
EXPECTED_OUTPUT = usage_stage8_profile()


if __name__ == "__main__":
    run_stage(STAGE_NAME, ProfileExtractor, EXPECTED_INPUT, EXPECTED_OUTPUT)
