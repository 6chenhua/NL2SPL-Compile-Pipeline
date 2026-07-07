from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.compiler.construct_plan import (
    APICallDemand,
    ConstructPlan,
    OperationCoverageIR,
)
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.pipeline.stages.stage7_step_extractor.extractor import StepExtractor


def test_action_aware_unmapped_detection_unmaterialized() -> None:
    # 1. Setup mock config and client
    config = MagicMock()
    client = MagicMock()
    extractor = StepExtractor(config, client)

    # 2. Setup span s16 with residual
    spans = [
        SpanIR(
            span_id="s16",
            text=(
                "If sources are needed and available, retrieve them using approved "
                "source recipes. Maintain provenance for externally sourced facts."
            ),
        )
    ]

    # 3. Setup APICallDemand and ConstructPlan
    call = APICallDemand(
        demand_id="api_call_s16",
        declaration_demand_id="api_decl_s16",
        api_group_id="approved_source_recipes",
        action_text="retrieve them using approved source recipes",
        source_span_ids=["s16"],
        operation_coverage=[
            OperationCoverageIR(
                coverage_id="cov_s16_api",
                source_span_id="s16",
                operation_surface=(
                    "If sources are needed and available, "
                    "retrieve them using approved source recipes."
                ),
                char_start=0,
                char_end=81,
            )
        ],
        consumes_behavior_span_ids=["s16"],
        residual_behavior_span_ids=["s16"],
        behavior_lowering_policy="api_call_augments_behavior",
    )
    construct_plan = ConstructPlan(plan_id="cp", demands=[call])

    # 4. Setup steps: ONLY CALL_API step exists, NO residual GENERAL_COMMAND step
    steps = [
        StepIR(
            step_id="st_api_call",
            text="Retrieve sources using approved source recipes.",
            source_span_ids=["s16"],
            command_type="CALL_API",
            metadata={"origin": "source_backed", "construct_demand_ids": ["api_call_s16"]},
        )
    ]

    # 5. Execute detection
    extractor.stage7_diagnostics = []
    extractor._detect_unmapped_spans(
        steps=steps,
        behavior_spans=spans,
        llm_unmapped={},
        worker_id="worker_main",
        non_exec_span_ids=set(),
        construct_plan=construct_plan,
    )

    # 6. Assert unmaterialized diagnostic is raised
    diags = extractor.stage7_diagnostics
    assert len(diags) == 1
    assert diags[0].kind == "stage7_residual_action_unmaterialized"
    assert diags[0].blocks_completion is True
    assert diags[0].blocks_rendering is False


def test_action_aware_unmapped_detection_materialized() -> None:
    config = MagicMock()
    client = MagicMock()
    extractor = StepExtractor(config, client)

    spans = [
        SpanIR(
            span_id="s16",
            text=(
                "If sources are needed and available, retrieve them using approved "
                "source recipes. Maintain provenance for externally sourced facts."
            ),
        )
    ]

    call = APICallDemand(
        demand_id="api_call_s16",
        declaration_demand_id="api_decl_s16",
        api_group_id="approved_source_recipes",
        action_text="retrieve them using approved source recipes",
        source_span_ids=["s16"],
        operation_coverage=[
            OperationCoverageIR(
                coverage_id="cov_s16_api",
                source_span_id="s16",
                operation_surface=(
                    "If sources are needed and available, "
                    "retrieve them using approved source recipes."
                ),
                char_start=0,
                char_end=81,
            )
        ],
        consumes_behavior_span_ids=["s16"],
        residual_behavior_span_ids=["s16"],
        behavior_lowering_policy="api_call_augments_behavior",
    )
    construct_plan = ConstructPlan(plan_id="cp", demands=[call])

    # Both CALL_API and residual GENERAL_COMMAND steps exist
    steps = [
        StepIR(
            step_id="st_api_call",
            text="Retrieve sources using approved source recipes.",
            source_span_ids=["s16"],
            command_type="CALL_API",
            metadata={"origin": "source_backed", "construct_demand_ids": ["api_call_s16"]},
        ),
        StepIR(
            step_id="st_residual",
            text="Maintain provenance for externally sourced facts.",
            source_span_ids=["s16"],
            command_type="GENERAL_COMMAND",
            metadata={"origin": "residual_generated", "api_call_demand_id": "api_call_s16"},
        ),
    ]

    extractor.stage7_diagnostics = []
    extractor._detect_unmapped_spans(
        steps=steps,
        behavior_spans=spans,
        llm_unmapped={},
        worker_id="worker_main",
        non_exec_span_ids=set(),
        construct_plan=construct_plan,
    )

    diags = extractor.stage7_diagnostics
    assert len(diags) == 0
