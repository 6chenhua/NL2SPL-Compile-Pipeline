"""Run Stage 7 prompt against expected upstream IRs and show a diff."""

from __future__ import annotations

from common import print_comparison, make_client, make_config
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor
from usage_expectations import (
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage4_flow,
    usage_stage5_blocks,
    usage_stage6_symbol_table,
    usage_stage7_steps,
)


STAGE_NAME = "stage7_step_extractor"
EXPECTED_INPUT = (
    usage_stage3_spans(),
    usage_stage3_routes(),
    usage_stage4_flow(),
    usage_stage5_blocks(),
    usage_stage6_symbol_table(),
)
EXPECTED_OUTPUT = usage_stage7_steps()


if __name__ == "__main__":
    config = make_config(STAGE_NAME)
    stage = StepExtractor(config, make_client(config))
    steps, _ = stage.execute(EXPECTED_INPUT)
    print_comparison(STAGE_NAME, EXPECTED_OUTPUT, steps)
