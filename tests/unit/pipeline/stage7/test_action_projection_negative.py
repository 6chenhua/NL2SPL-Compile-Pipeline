from __future__ import annotations

from nl2spl.compiler.construct_plan import (
    APICallArgumentBindingIR,
    APICallDemand,
    APICallPlacementIR,
    APIDeclarationDemand,
    ConstructPlan,
    OperationCoverageIR,
)
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    APICallBindingIR,
    APIMaterializationPlanIR,
)
from nl2spl.pipeline.stages.stage7_step_extractor.action_projection import (
    APIResidualActionProjector,
)
from nl2spl.pipeline.stages.stage7_step_extractor.api_call_materializer import (
    materialize_direct_api_calls,
)


def test_unrelated_general_commands_are_not_deleted() -> None:
    # 1. Setup step plan with unrelated general commands on the same span s2
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                # Unrelated command 1
                StepIR(
                    step_id="st_validate",
                    text="Validate source quality before publication.",
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                ),
                # Fallback step
                StepIR(
                    step_id="st_fallback_s2",
                    text="Retrieve approved sources using SearchAPI and preserve provenance.",
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                    metadata={"fallback_for_api_call_demand_id": "api_call_search"},
                ),
                # Unrelated command 2
                StepIR(
                    step_id="st_notify",
                    text="Notify source owner.",
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                ),
            ]
        },
    )

    plan = ConstructPlan(
        plan_id="cp",
        api_call_argument_bindings=[
            APICallArgumentBindingIR(
                call_demand_id="api_call_search",
                binding_status="not_required",
                source_span_ids=("s2",),
            )
        ],
        demands=[
            APIDeclarationDemand(
                demand_id="api_decl_SearchAPI",
                explicit_name_candidates=["SearchAPI"],
                integration_admission="confirmed",
                mechanism_status="explicit",
                source_span_ids=["s1"],
            ),
            APICallDemand(
                demand_id="api_call_search",
                declaration_demand_id="api_decl_SearchAPI",
                api_group_id="search",
                action_text="Retrieve approved sources using SearchAPI.",
                source_span_ids=["s2"],
                operation_coverage=[
                    OperationCoverageIR(
                        coverage_id="cov_search",
                        source_span_id="s2",
                        operation_surface="Retrieve approved sources using SearchAPI.",
                        char_start=0,
                        char_end=len("Retrieve approved sources using SearchAPI."),
                    )
                ],
                consumes_behavior_span_ids=["s2"],
                residual_behavior_span_ids=["s2"],
                behavior_lowering_policy="api_call_augments_behavior",
            ),
        ],
    )

    api_plan = APIMaterializationPlanIR(
        bindings=[
            APICallBindingIR(
                api_binding_id="api_binding:api_decl_SearchAPI",
                declaration_demand_id="api_decl_SearchAPI",
                api_id="api:SearchAPI",
                api_name="SearchAPI",
                call_demand_ids=["api_call_search"],
                source_span_ids=["s1"],
            )
        ]
    )

    placement = APICallPlacementIR(
        call_demand_id="api_call_search",
        owner_worker_id="worker_main",
        flow_ref="main",
        block_ref="block_main",
        status="placed",
        source_span_ids=["s2"],
    )

    resources = ResourceRegistryIR(
        apis=[
            APISpec(
                api_id="api:SearchAPI",
                api_name="SearchAPI",
                auth="none",
                description="SearchAPI skeleton.",
                declaration_status="partial_blocked",
                schema_status="unknown_placeholder",
                functions_status="unknown_placeholder",
                functions=[],
            )
        ]
    )

    spans = [
        SpanIR(span_id="s1", text="SearchAPI declaration."),
        SpanIR(
            span_id="s2",
            text=(
                "Retrieve approved sources using SearchAPI. "
                "Validate source quality. Notify source owner."
            ),
        ),
    ]

    materialize_direct_api_calls(
        worker_steps,
        plan,
        api_plan,
        [placement],
        resources,
        spans,
    )

    # st_fallback_s2 is deleted. CALL_API search is materialized.
    # st_validate and st_notify must remain untouched!
    steps = worker_steps.worker_steps["worker_main"]
    assert len(steps) == 3
    assert steps[0].step_id == "st_validate"
    assert steps[1].step_id == "st_notify"
    assert steps[2].command_type == "CALL_API"


def test_unclassified_leading_clause_triggers_diagnostic() -> None:
    projector = APIResidualActionProjector()
    span = SpanIR(
        span_id="s2",
        text=(
            "Validate source quality before publication, "
            "retrieve them using approved source recipes."
        ),
    )
    span_by_id = {"s2": span}

    call = APICallDemand(
        demand_id="api_call_s2",
        declaration_demand_id="api_decl_s2",
        api_group_id="approved_source_recipes",
        action_text="retrieve them using approved source recipes",
        source_span_ids=["s2"],
        operation_coverage=[
            OperationCoverageIR(
                coverage_id="cov_s2",
                source_span_id="s2",
                operation_surface="retrieve them using approved source recipes",
                char_start=44,
                char_end=88,
            )
        ],
        consumes_behavior_span_ids=["s2"],
        residual_behavior_span_ids=["s2"],
        behavior_lowering_policy="api_call_augments_behavior",
    )

    projection = projector.project(
        call=call,
        span_by_id=span_by_id,
        placement=None,
    )

    # Ambiguous leading clause triggers diagnostic
    assert len(projection.diagnostics) == 1
    assert projection.diagnostics[0].kind == "stage7_api_residual_coverage_ambiguous"
    assert "unclassified_leading_clause" in projection.diagnostics[0].metadata["reason"]
    # No residual action generated
    assert len(projection.residual_actions) == 0


def test_unclassified_trailing_clause_triggers_diagnostic() -> None:
    projector = APIResidualActionProjector()
    span = SpanIR(
        span_id="s2",
        text="retrieve them using approved source recipes, and validate source quality.",
    )
    span_by_id = {"s2": span}

    call = APICallDemand(
        demand_id="api_call_s2",
        declaration_demand_id="api_decl_s2",
        api_group_id="approved_source_recipes",
        action_text="retrieve them using approved source recipes",
        source_span_ids=["s2"],
        operation_coverage=[
            OperationCoverageIR(
                coverage_id="cov_s2",
                source_span_id="s2",
                operation_surface="retrieve them using approved source recipes",
                char_start=0,
                char_end=44,
            )
        ],
        consumes_behavior_span_ids=["s2"],
        residual_behavior_span_ids=["s2"],
        behavior_lowering_policy="api_call_augments_behavior",
    )

    projection = projector.project(
        call=call,
        span_by_id=span_by_id,
        placement=None,
    )

    # Ambiguous trailing clause triggers diagnostic
    assert len(projection.diagnostics) == 1
    assert projection.diagnostics[0].kind == "stage7_api_residual_coverage_ambiguous"
    assert "unclassified_trailing_clause" in projection.diagnostics[0].metadata["reason"]
    assert len(projection.residual_actions) == 0
