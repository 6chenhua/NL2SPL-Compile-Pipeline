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


def test_materializer_residual_fix_outputs_empty() -> None:
    worker_steps = WorkerStepPlanIR(
        main_worker_id="worker_main",
        worker_steps={
            "worker_main": [
                StepIR(
                    step_id="st_fallback_s2",
                    text="Retrieve approved sources using SearchAPI and preserve provenance.",
                    source_span_ids=["s2"],
                    command_type="GENERAL_COMMAND",
                    metadata={"fallback_for_api_call_demand_id": "api_call_search"},
                )
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
                description="Partial API declaration skeleton for SearchAPI.",
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
            text="Retrieve approved sources using SearchAPI. Preserve provenance.",
        ),
    ]

    diagnostics = materialize_direct_api_calls(
        worker_steps,
        plan,
        api_plan,
        [placement],
        resources,
        spans,
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].kind == "stage7_sanitized_general_command_fallback"
    steps = worker_steps.worker_steps["worker_main"]
    assert len(steps) == 2
    assert steps[0].command_type == "CALL_API"
    assert steps[1].command_type == "GENERAL_COMMAND"
    assert steps[1].text == "Preserve provenance."
    assert steps[1].outputs == []
