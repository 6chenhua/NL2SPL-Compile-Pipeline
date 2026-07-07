from __future__ import annotations

from nl2spl.compiler.construct_plan import APICallDemand, APICallPlacementIR, OperationCoverageIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage7_step_extractor.action_projection import (
    APIResidualActionProjector,
)


def test_project_retrieve_and_maintain_provenance() -> None:
    # 1. Setup projector and inputs
    projector = APIResidualActionProjector()
    span = SpanIR(
        span_id="s16",
        text=(
            "If sources are needed and available, retrieve them using approved "
            "source recipes. Maintain provenance for externally sourced facts."
        ),
    )
    span_by_id = {"s16": span}

    # API covers "retrieve them using approved source recipes"
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

    placement = APICallPlacementIR(
        call_demand_id="api_call_s16",
        owner_worker_id="worker_main",
        flow_ref="main",
        block_ref="block_main",
        status="placed",
        source_span_ids=["s16"],
    )

    # 2. Execute projection
    projection = projector.project(
        call=call,
        span_by_id=span_by_id,
        placement=placement,
    )

    # 3. Assertions
    assert projection.diagnostics == ()
    assert projection.call_action is not None
    assert projection.call_action.command_type == "CALL_API"
    assert projection.call_action.action_text == (
        "If sources are needed and available, retrieve them using approved source recipes."
    )

    assert len(projection.residual_actions) == 1
    res = projection.residual_actions[0]
    assert res.command_type == "GENERAL_COMMAND"
    assert res.action_text == "Maintain provenance for externally sourced facts."
    assert res.output_policy == "no_output"
    assert projection.coverage_report.status == "has_uncovered_residual"


def test_project_api_only_span() -> None:
    projector = APIResidualActionProjector()
    span = SpanIR(
        span_id="s2",
        text="Retrieve needed sources.",
    )
    span_by_id = {"s2": span}

    call = APICallDemand(
        demand_id="api_call_s2",
        declaration_demand_id="api_decl_s2",
        api_group_id="search",
        action_text="Retrieve needed sources.",
        source_span_ids=["s2"],
        operation_coverage=[
            OperationCoverageIR(
                coverage_id="cov_s2",
                source_span_id="s2",
                operation_surface="Retrieve needed sources.",
                char_start=0,
                char_end=len("Retrieve needed sources."),
            )
        ],
        consumes_behavior_span_ids=["s2"],
        residual_behavior_span_ids=["s2"],
        behavior_lowering_policy="api_call_replaces_behavior",
    )

    placement = APICallPlacementIR(
        call_demand_id="api_call_s2",
        owner_worker_id="worker_main",
        flow_ref="main",
        block_ref="block_main",
        status="placed",
        source_span_ids=["s2"],
    )

    projection = projector.project(
        call=call,
        span_by_id=span_by_id,
        placement=placement,
    )

    assert projection.diagnostics == ()
    assert projection.call_action is not None
    assert projection.call_action.command_type == "CALL_API"
    assert len(projection.residual_actions) == 0
    assert projection.coverage_report.status == "fully_partitioned"


def test_project_ambiguous_coverage() -> None:
    projector = APIResidualActionProjector()
    span = SpanIR(
        span_id="s2",
        text="Retrieve needed sources.",
    )
    span_by_id = {"s2": span}

    # Offsets are invalid (char_end is past span length)
    call = APICallDemand(
        demand_id="api_call_s2",
        declaration_demand_id="api_decl_s2",
        api_group_id="search",
        action_text="Retrieve needed sources.",
        source_span_ids=["s2"],
        operation_coverage=[
            OperationCoverageIR(
                coverage_id="cov_s2",
                source_span_id="s2",
                operation_surface="Retrieve needed sources.",
                char_start=0,
                char_end=100,
            )
        ],
        consumes_behavior_span_ids=["s2"],
        residual_behavior_span_ids=["s2"],
        behavior_lowering_policy="api_call_replaces_behavior",
    )

    placement = APICallPlacementIR(
        call_demand_id="api_call_s2",
        owner_worker_id="worker_main",
        flow_ref="main",
        block_ref="block_main",
        status="placed",
        source_span_ids=["s2"],
    )

    projection = projector.project(
        call=call,
        span_by_id=span_by_id,
        placement=placement,
    )

    assert len(projection.diagnostics) == 1
    assert projection.diagnostics[0].kind == "stage7_api_residual_coverage_ambiguous"
    assert projection.call_action is None
    assert len(projection.residual_actions) == 0
    assert projection.coverage_report.status == "ambiguous"


def test_project_normalized_whitespace_coverage() -> None:
    projector = APIResidualActionProjector()
    span = SpanIR(
        span_id="s2",
        text="Retrieve   needed   sources.",
    )
    span_by_id = {"s2": span}

    call = APICallDemand(
        demand_id="api_call_s2",
        declaration_demand_id="api_decl_s2",
        api_group_id="search",
        action_text="Retrieve needed sources.",
        source_span_ids=["s2"],
        operation_coverage=[
            OperationCoverageIR(
                coverage_id="cov_s2",
                source_span_id="s2",
                operation_surface="Retrieve   needed   sources",
                char_start=0,
                char_end=len("Retrieve   needed   sources"),
                relation="normalized_whitespace",
            )
        ],
        consumes_behavior_span_ids=["s2"],
        residual_behavior_span_ids=["s2"],
        behavior_lowering_policy="api_call_augments_behavior",
    )

    placement = APICallPlacementIR(
        call_demand_id="api_call_s2",
        owner_worker_id="worker_main",
        flow_ref="main",
        block_ref="block_main",
        status="placed",
        source_span_ids=["s2"],
    )

    projection = projector.project(
        call=call,
        span_by_id=span_by_id,
        placement=placement,
    )

    assert projection.diagnostics == ()
    assert projection.call_action is not None
    assert projection.call_action.covered_ranges[0].relation == "normalized_whitespace"
    # Residual should be just the trailing dot
    assert len(projection.residual_actions) == 0  # cleaned dot becomes empty string, so no action


def test_project_multiple_ranges() -> None:
    projector = APIResidualActionProjector()
    span = SpanIR(
        span_id="s2",
        text="PartA Retrieve PartB and retrieve.",
    )
    span_by_id = {"s2": span}

    call = APICallDemand(
        demand_id="api_call_s2",
        declaration_demand_id="api_decl_s2",
        api_group_id="search",
        action_text="Retrieve",
        source_span_ids=["s2"],
        operation_coverage=[
            OperationCoverageIR(
                coverage_id="cov_s2_1",
                source_span_id="s2",
                operation_surface="Retrieve",
                char_start=6,
                char_end=14,
            ),
            OperationCoverageIR(
                coverage_id="cov_s2_2",
                source_span_id="s2",
                operation_surface="retrieve",
                char_start=25,
                char_end=33,
            ),
        ],
        consumes_behavior_span_ids=["s2"],
        residual_behavior_span_ids=["s2"],
        behavior_lowering_policy="api_call_augments_behavior",
    )

    placement = APICallPlacementIR(
        call_demand_id="api_call_s2",
        owner_worker_id="worker_main",
        flow_ref="main",
        block_ref="block_main",
        status="placed",
        source_span_ids=["s2"],
    )

    projection = projector.project(
        call=call,
        span_by_id=span_by_id,
        placement=placement,
    )

    assert len(projection.diagnostics) == 1
    assert projection.diagnostics[0].kind == "stage7_api_residual_coverage_ambiguous"
    assert len(projection.residual_actions) == 0
