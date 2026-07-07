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
from nl2spl.pipeline.stages.stage7_step_extractor.api_call_materializer import (
    materialize_direct_api_calls,
)


def test_direct_api_call_conflicts_with_existing_handoff_call_api() -> None:
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_api_handoff_search",
                    text="Call API: SearchAPI",
                    source_span_ids=["s2"],
                    command_type="CALL_API",
                    integration_ref="SearchAPI",
                    flow_ref="main",
                    block_ref="block_main",
                    kind="tool",
                    handoff_id="handoff_search",
                    metadata={
                        "origin": "handoff_derived",
                        "source_handoff_id": "handoff_search",
                    },
                )
            ]
        },
    )

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        _construct_plan("Retrieve approved sources using SearchAPI."),
        _api_plan(),
        [_placement()],
        _resources(),
        _spans("Retrieve approved sources using SearchAPI."),
    )

    steps = worker_steps.worker_steps["worker_main"]
    assert [step.step_id for step in steps] == ["st_api_handoff_search"]
    assert len(diagnostics) == 1
    assert diagnostics[0].kind == "duplicate_api_action_claim"
    assert diagnostics[0].metadata["direct_api_demand_id"] == "api_call_search"
    assert diagnostics[0].metadata["handoff_id"] == "handoff_search"


def test_direct_api_call_does_not_conflict_with_different_source_span() -> None:
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_api_handoff_search",
                    text="Call API: SearchAPI",
                    source_span_ids=["s3"],
                    command_type="CALL_API",
                    integration_ref="SearchAPI",
                    flow_ref="main",
                    block_ref="block_main",
                    kind="tool",
                    handoff_id="handoff_search",
                )
            ]
        },
    )

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        _construct_plan("Retrieve approved sources using SearchAPI."),
        _api_plan(),
        [_placement()],
        _resources(),
        _spans("Retrieve approved sources using SearchAPI."),
    )

    steps = worker_steps.worker_steps["worker_main"]
    assert [step.command_type for step in steps] == ["CALL_API", "CALL_API"]
    assert diagnostics == []


def _construct_plan(operation: str) -> ConstructPlan:
    return ConstructPlan(
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
                action_text=operation,
                source_span_ids=["s2"],
                operation_coverage=[
                    OperationCoverageIR(
                        coverage_id="cov_search",
                        source_span_id="s2",
                        operation_surface=operation,
                        char_start=0,
                        char_end=len(operation),
                    )
                ],
                consumes_behavior_span_ids=["s2"],
                behavior_lowering_policy="api_call_replaces_behavior",
            ),
        ],
    )


def _api_plan() -> APIMaterializationPlanIR:
    return APIMaterializationPlanIR(
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


def _placement() -> APICallPlacementIR:
    return APICallPlacementIR(
        call_demand_id="api_call_search",
        owner_worker_id="worker_main",
        flow_ref="main",
        block_ref="block_main",
        status="placed",
        source_span_ids=["s2"],
    )


def _resources() -> ResourceRegistryIR:
    return ResourceRegistryIR(
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


def _spans(operation: str) -> list[SpanIR]:
    return [
        SpanIR(span_id="s1", text="SearchAPI declaration."),
        SpanIR(span_id="s2", text=operation),
        SpanIR(span_id="s3", text="Call SearchAPI for another operation."),
    ]
