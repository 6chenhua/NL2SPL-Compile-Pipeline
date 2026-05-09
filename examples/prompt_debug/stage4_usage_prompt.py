"""Run Stage 4 prompt against expected Stage 3 output and show a diff."""

from __future__ import annotations

from common import run_stage
from nl2spl.pipeline.stages.stage4_flow_assembler import FlowAssembler
from usage_expectations import usage_stage3_routes, usage_stage3_spans, usage_stage4_flow


STAGE_NAME = "stage4_flow_assembler"
EXPECTED_INPUT = (usage_stage3_spans(), usage_stage3_routes())
EXPECTED_OUTPUT = usage_stage4_flow()


if __name__ == "__main__":
    run_stage(STAGE_NAME, FlowAssembler, EXPECTED_INPUT, EXPECTED_OUTPUT)
