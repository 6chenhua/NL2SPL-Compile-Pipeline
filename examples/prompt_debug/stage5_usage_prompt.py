"""Run Stage 5 prompt against expected Stage 4 output and show a diff."""

from __future__ import annotations

from common import run_stage
from nl2spl.pipeline.stages.stage5_block_assembler import BlockAssembler
from usage_expectations import (
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage4_flow,
    usage_stage5_blocks,
)


STAGE_NAME = "stage5_block_assembler"
EXPECTED_INPUT = (usage_stage3_spans(), usage_stage3_routes(), usage_stage4_flow())
EXPECTED_OUTPUT = usage_stage5_blocks()


if __name__ == "__main__":
    run_stage(STAGE_NAME, BlockAssembler, EXPECTED_INPUT, EXPECTED_OUTPUT)
