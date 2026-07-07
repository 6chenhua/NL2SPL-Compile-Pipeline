from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.compiler.construct_plan import (
    APICallArgumentBindingIR,
    APICallDemand,
    APICallPlacementIR,
    APIDeclarationDemand,
    ConstructPlan,
    OperationCoverageIR,
)
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.resource_registry_ir import APISpec, ResourceRegistryIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.symbol_table import SymbolTable
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage6_resource_extractor.api_materialization import (
    APICallBindingIR,
    APIMaterializationPlanIR,
)
from nl2spl.pipeline.stages.stage7_step_extractor import StepExtractor


def test_stage7_internal_comms_characterization_e2e(
    pipeline_config: MagicMock,
) -> None:
    """Integration characterization test for mixed span s16 behavior.

    Asserts that the worker-scoped step extraction correctly:
    1. Removes the fallback duplicate retrieve command.
    2. Generates the residual provenance command.
    """
    # 1. Setup mock LLM client to return buggy output (no residual provenance step extracted)
    mock_client = MagicMock()
    mock_client.call_json.return_value = {
        "steps": [
            {
                "step_id": "st_fallback_s16",
                "text": "Retrieve sources using approved source recipes.",
                "source_span_ids": ["s16"],
                "command_type": "GENERAL_COMMAND",
                "inputs": [],
                "outputs": [],
                "flow_ref": "main",
                "block_ref": "block_main",
                "kind": "normal",
                "metadata": {
                    "fallback_for_api_call_demand_id": "api_call_s16",
                },
            }
        ],
        "new_variables": [],
    }

    # 2. Setup inputs matching internal_comms s16 scenario
    spans = [
        SpanIR(
            span_id="s16",
            text=(
                "If sources are needed and available, retrieve them using approved "
                "source recipes. Maintain provenance for externally sourced facts."
            ),
        )
    ]
    routes = FieldRouteIR(behavior=["s16"])
    worker_flow_plan = WorkerFlowPlanIR(
        worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s16"])}
    )
    worker_block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[BlockIR("block_main", "SEQUENTIAL", spans=["s16"])]
            )
        }
    )
    symbol_table = SymbolTable()

    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            WorkerSpecIR(
                worker_id="worker_main",
                worker_name="MainWorker",
                kind="main",
                purpose="Coordinate communication",
                owned_span_ids=["s16"],
                input_contract=[],
                output_contract=[],
            )
        ],
    )

    construct_plan = ConstructPlan(
        plan_id="cp_internal_comms",
        api_call_argument_bindings=[
            APICallArgumentBindingIR(
                call_demand_id="api_call_s16",
                binding_status="not_required",
                source_span_ids=("s16",),
            )
        ],
        demands=[
            APIDeclarationDemand(
                demand_id="api_decl_s16",
                explicit_name_candidates=["ApprovedSourceRecipesAPI"],
                integration_admission="confirmed",
                mechanism_status="explicit",
                source_span_ids=["s15"],
            ),
            APICallDemand(
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
            ),
        ],
    )

    api_materialization_plan = APIMaterializationPlanIR(
        bindings=[
            APICallBindingIR(
                api_binding_id="api_binding:api_decl_s16",
                declaration_demand_id="api_decl_s16",
                api_id="api:ApprovedSourceRecipesAPI",
                api_name="ApprovedSourceRecipesAPI",
                call_demand_ids=["api_call_s16"],
                source_span_ids=["s15"],
            )
        ]
    )

    api_call_placements = [
        APICallPlacementIR(
            call_demand_id="api_call_s16",
            owner_worker_id="worker_main",
            flow_ref="main",
            block_ref="block_main",
            status="placed",
            source_span_ids=["s16"],
        )
    ]

    resources = ResourceRegistryIR(
        apis=[
            APISpec(
                api_id="api:ApprovedSourceRecipesAPI",
                api_name="ApprovedSourceRecipesAPI",
                auth="none",
                description="ApprovedSourceRecipesAPI.",
                declaration_status="partial_blocked",
                schema_status="unknown_placeholder",
                functions_status="unknown_placeholder",
                functions=[],
            )
        ]
    )

    extractor = StepExtractor(pipeline_config, mock_client)

    # 3. Execute
    worker_step_plan, updated_symbols = extractor.execute_worker_scoped(
        spans,
        routes,
        worker_flow_plan,
        worker_block_plan,
        symbol_table,
        worker_plan,
        construct_plan,
        api_materialization_plan,
        api_call_placements,
        resources,
    )

    # Assert correct behavior is achieved:
    steps = worker_step_plan.worker_steps["worker_main"]

    # 1. The fallback general command is removed, and CALL_API is materialized:
    assert len(steps) == 2
    call_steps = [step for step in steps if step.command_type == "CALL_API"]
    assert len(call_steps) == 1
    assert call_steps[0].integration_ref == "ApprovedSourceRecipesAPI"

    residual_steps = [step for step in steps if step.command_type == "GENERAL_COMMAND"]
    assert len(residual_steps) == 1
    assert residual_steps[0].text == "Maintain provenance for externally sourced facts."
