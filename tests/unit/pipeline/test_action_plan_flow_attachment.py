from __future__ import annotations

from nl2spl.ir.action_placement_ir import (
    ExecutableActionCandidate,
    ExecutableActionPlacement,
    ExecutableActionPlacementPlan,
)
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR
from nl2spl.pipeline.orchestrator import _attach_action_plan_spans_to_worker_flows


def test_accepted_action_span_omitted_by_stage4_is_attached_to_main_flow() -> None:
    worker_flow_plan = WorkerFlowPlanIR(
        worker_flows={"worker_main": FlowStructureIR(main_flow_spans=["s1"])}
    )
    action_plan = ExecutableActionPlacementPlan(
        candidates=(
            ExecutableActionCandidate(
                candidate_id="action_s2",
                source_span_ids=("s2",),
                action_text="Maintain provenance for externally sourced facts.",
                source="stage1_action_segmentation",
                status="accepted",
                reason="atomic_action",
            ),
        ),
        placements=(
            ExecutableActionPlacement(
                candidate_id="action_s2",
                worker_id="worker_main",
                flow_ref=None,
                block_ref=None,
                status="placed",
                reason="worker_owned",
            ),
        ),
    )

    _attach_action_plan_spans_to_worker_flows(worker_flow_plan, action_plan)

    assert worker_flow_plan.worker_flows["worker_main"].main_flow_spans == ["s1", "s2"]
