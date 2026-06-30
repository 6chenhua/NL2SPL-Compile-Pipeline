from __future__ import annotations

from nl2spl.compiler.construct_plan import APICallDemand, ConstructPlan, ConstructSlotDemand
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import AlternativeFlow, FlowStructureIR
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from nl2spl.pipeline.stages.stage5_block_assembler.api_call_placement import (
    project_api_call_placements,
)


def test_projector_places_api_call_from_structured_ownership_flow_and_block() -> None:
    plan = ConstructPlan(demands=[_call_demand("api_call_1", ["s2"])], plan_id="cp")
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[_worker("worker_main", ["s1", "s2", "s3"])],
    )
    flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(main_flow_spans=["s1", "s2", "s3"])
        }
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                main_flow_blocks=[
                    BlockIR("block_main", "SEQUENTIAL", spans=["s1", "s2", "s3"])
                ]
            )
        }
    )

    placements = project_api_call_placements(
        plan, worker_plan, flow_plan, block_plan,
    )

    assert len(placements) == 1
    placement = placements[0]
    assert placement.call_demand_id == "api_call_1"
    assert placement.placement_ref == "api_call_placement:api_call_1"
    assert placement.owner_worker_id == "worker_main"
    assert placement.flow_ref == "main"
    assert placement.block_ref == "block_main"
    assert placement.status == "placed"
    assert placement.source_span_ids == ["s2"]
    assert placement.reason is None


def test_projector_marks_multi_worker_owner_ambiguity_without_first_choice() -> None:
    plan = ConstructPlan(demands=[_call_demand("api_call_1", ["s2"])], plan_id="cp")
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[
            _worker("worker_main", ["s2"]),
            _worker("worker_child", ["s2"], kind="child"),
        ],
    )

    placements = project_api_call_placements(
        plan,
        worker_plan,
        WorkerFlowPlanIR(),
        WorkerBlockPlanIR(),
    )

    placement = placements[0]
    assert placement.status == "ambiguous"
    assert placement.owner_worker_id is None
    assert placement.flow_ref is None
    assert placement.block_ref is None
    assert placement.reason == "multiple_owner_candidates"


def test_projector_marks_unresolved_block_without_stage7_repair() -> None:
    plan = ConstructPlan(demands=[_call_demand("api_call_1", ["s2"])], plan_id="cp")
    worker_plan = WorkerPlanIR(
        main_worker_id="worker_main",
        workers=[_worker("worker_main", ["s2"])],
    )
    flow_plan = WorkerFlowPlanIR(
        worker_flows={
            "worker_main": FlowStructureIR(
                main_flow_spans=[],
                alternative_flows=[AlternativeFlow("alt_1", "condition", ["s2"])],
            )
        }
    )
    block_plan = WorkerBlockPlanIR(
        worker_blocks={
            "worker_main": BlockStructureIR(
                alternative_flow_blocks={"alt_1": []},
            )
        }
    )

    placement = project_api_call_placements(
        plan, worker_plan, flow_plan, block_plan,
    )[0]

    assert placement.status == "unresolved"
    assert placement.owner_worker_id == "worker_main"
    assert placement.flow_ref is None
    assert placement.block_ref is None
    assert placement.reason == "block_not_resolved"


def _call_demand(demand_id: str, span_ids: list[str]) -> APICallDemand:
    return APICallDemand(
        demand_id=demand_id,
        slots={
            "call_action": ConstructSlotDemand(
                slot_name="call_action",
                source_span_ids=span_ids,
                semantic_roles=["process_step"],
                executable_values=[True],
            )
        },
        source_span_ids=span_ids,
        call_annotation_ids=["ann_call"],
        api_group_id="search",
    )


def _worker(
    worker_id: str,
    owned_span_ids: list[str],
    *,
    kind: str = "main",
) -> WorkerSpecIR:
    return WorkerSpecIR(
        worker_id=worker_id,
        worker_name=worker_id,
        kind=kind,  # type: ignore[arg-type]
        purpose="test",
        owned_span_ids=owned_span_ids,
        boundary_kind="main_worker" if kind == "main" else "bounded_subtask",
    )
