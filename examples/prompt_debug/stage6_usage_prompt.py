"""Run Stage 6 prompt against expected Stage 3 output and show a diff."""

from __future__ import annotations

from common import print_comparison, make_client, make_config
from nl2spl.pipeline.stages.stage6_resource_extractor import ResourceExtractor
from usage_expectations import (
    usage_stage3_routes,
    usage_stage3_spans,
    usage_stage6_resources,
    usage_stage6_symbol_table,
)


STAGE_NAME = "stage6_resource_extractor"
EXPECTED_INPUT = (usage_stage3_spans(), usage_stage3_routes())
EXPECTED_OUTPUT = {
    "resources": usage_stage6_resources(),
    "symbol_table": usage_stage6_symbol_table(),
}


if __name__ == "__main__":
    config = make_config(STAGE_NAME)
    stage = ResourceExtractor(config, make_client(config))
    resources, symbol_table = stage.execute(EXPECTED_INPUT)
    actual_output = {
        "resources": resources,
        "symbol_table": symbol_table,
    }
    print_comparison(STAGE_NAME, EXPECTED_OUTPUT, actual_output)
