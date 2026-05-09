"""Run Stage 1 prompt against examples/usage.py raw_text and show a diff."""

from __future__ import annotations

from common import run_stage
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer
from usage_expectations import USAGE_RAW_TEXT, usage_stage1_spans


STAGE_NAME = "stage1_span_slicer"
EXPECTED_INPUT = USAGE_RAW_TEXT
EXPECTED_OUTPUT = usage_stage1_spans()


if __name__ == "__main__":
    run_stage(STAGE_NAME, SpanSlicer, EXPECTED_INPUT, EXPECTED_OUTPUT)
