"""Run Stage 3 prompt against expected Stage 2 output and show a diff."""

from __future__ import annotations

from common import print_comparison, make_client, make_config
from nl2spl.pipeline.stages.stage3_ambiguity_resolver import AmbiguityResolver
from usage_expectations import (
    usage_stage1_spans,
    usage_stage2_ambiguity_updates,
    usage_stage2_routes,
    usage_stage3_routes,
    usage_stage3_spans,
)


STAGE_NAME = "stage3_ambiguity_resolver"
EXPECTED_INPUT = (
    usage_stage1_spans(),
    usage_stage2_routes(),
    usage_stage2_ambiguity_updates(),
)
EXPECTED_OUTPUT = {
    "spans": usage_stage3_spans(),
    "routes": usage_stage3_routes(),
}


if __name__ == "__main__":
    config = make_config(STAGE_NAME)
    stage = AmbiguityResolver(config, make_client(config))
    spans, routes = stage.execute(EXPECTED_INPUT)
    actual_output = {
        "spans": spans,
        "routes": routes,
    }
    print_comparison(STAGE_NAME, EXPECTED_OUTPUT, actual_output)
