"""Run Stage 9 prompt against expected upstream IRs and show a diff."""

from __future__ import annotations

from common import run_stage
from nl2spl.pipeline.stages.stage9_constraint_extractor import ConstraintExtractor
from usage_expectations import (
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage4_flow,
    usage_stage5_blocks,
    usage_stage6_symbol_table,
    usage_stage7_steps,
    usage_stage9_constraints,
)


STAGE_NAME = "stage9_constraint_extractor"
EXPECTED_INPUT = (
    usage_stage3_spans(),
    usage_stage3_routes(),
    usage_stage4_flow(),
    usage_stage5_blocks(),
    usage_stage6_symbol_table(),
    usage_stage7_steps(),
)
EXPECTED_OUTPUT = usage_stage9_constraints()


if __name__ == "__main__":
    run_stage(STAGE_NAME, ConstraintExtractor, EXPECTED_INPUT, EXPECTED_OUTPUT)
