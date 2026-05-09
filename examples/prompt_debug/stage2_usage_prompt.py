"""Run Stage 2 prompt against expected Stage 1 spans and show a diff."""

from __future__ import annotations

from common import print_comparison, make_client, make_config
from nl2spl.pipeline.stages.stage2_field_router import FieldRouter
from usage_expectations import (
    usage_stage1_spans,
    usage_stage2_ambiguity_updates,
    usage_stage2_routes,
)


STAGE_NAME = "stage2_field_router"
EXPECTED_INPUT = usage_stage1_spans()
EXPECTED_OUTPUT = {
    "routes": usage_stage2_routes(),
    "ambiguity_updates": usage_stage2_ambiguity_updates(),
}


if __name__ == "__main__":
    config = make_config(STAGE_NAME)
    stage = FieldRouter(config, make_client(config))
    routes, ambiguity_updates = stage.execute(EXPECTED_INPUT)
    actual_output = {
        "routes": routes,
        "ambiguity_updates": ambiguity_updates,
    }
    print_comparison(STAGE_NAME, EXPECTED_OUTPUT, actual_output)
