"""Deterministic API call placement projection for R-API-2.

The projector consumes only ConstructPlan demands plus worker/flow/block
ownership artifacts. It does not parse raw text, call LLMs, or materialize
StepIR.
"""

from __future__ import annotations

from nl2spl.compiler.construct_plan.model import (
    APICallDemand,
    APICallPlacementIR,
    ConstructPlan,
)
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerFlowPlanIR, WorkerPlanIR


def project_api_call_placements(
    construct_plan: ConstructPlan,
    worker_plan: WorkerPlanIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
) -> list[APICallPlacementIR]:
    """Project API call placement from structured worker/flow/block ownership."""
    return [
        _project_one(call, worker_plan, worker_flow_plan, worker_block_plan)
        for call in construct_plan.api_call_demands()
    ]


def _project_one(
    call: APICallDemand,
    worker_plan: WorkerPlanIR,
    worker_flow_plan: WorkerFlowPlanIR,
    worker_block_plan: WorkerBlockPlanIR,
) -> APICallPlacementIR:
    span_ids = _call_span_ids(call)
    owner_status, owner_id, owner_reason = _resolve_owner(
        call, span_ids, worker_plan,
    )
    if owner_status != "placed" or owner_id is None:
        return APICallPlacementIR(
            call_demand_id=call.demand_id,
            owner_worker_id=owner_id,
            status=owner_status,
            source_span_ids=span_ids,
            reason=owner_reason,
        )

    flow_status, flow_ref, flow_reason = _resolve_flow(
        owner_id, span_ids, worker_flow_plan,
    )
    if flow_status != "placed" or flow_ref is None:
        return APICallPlacementIR(
            call_demand_id=call.demand_id,
            owner_worker_id=owner_id,
            status=flow_status,
            source_span_ids=span_ids,
            reason=flow_reason,
        )

    block_status, block_ref, block_reason = _resolve_block(
        owner_id, flow_ref, span_ids, worker_block_plan,
    )
    return APICallPlacementIR(
        call_demand_id=call.demand_id,
        owner_worker_id=owner_id,
        flow_ref=flow_ref if block_status == "placed" else None,
        block_ref=block_ref,
        status=block_status,
        source_span_ids=span_ids,
        reason=block_reason,
    )


def _call_span_ids(call: APICallDemand) -> list[str]:
    slot = call.slots.get("call_action")
    if slot is not None and slot.source_span_ids:
        return list(dict.fromkeys(slot.source_span_ids))
    return list(dict.fromkeys(call.source_span_ids))


def _resolve_owner(
    call: APICallDemand,
    span_ids: list[str],
    worker_plan: WorkerPlanIR,
) -> tuple[str, str | None, str | None]:
    if not span_ids:
        return "unresolved", None, "missing_call_action_span"

    if call.owner_worker_id:
        owner = next(
            (
                worker for worker in worker_plan.workers
                if worker.worker_id == call.owner_worker_id
            ),
            None,
        )
        if owner is None:
            return "unresolved", None, "owner_worker_not_found"
        if set(span_ids).issubset(set(owner.owned_span_ids)):
            return "placed", owner.worker_id, None
        return "unresolved", owner.worker_id, "owner_worker_does_not_own_call_span"

    candidates = [
        worker.worker_id
        for worker in worker_plan.workers
        if set(span_ids).intersection(worker.owned_span_ids)
    ]
    if len(candidates) == 1:
        return "placed", candidates[0], None
    if not candidates:
        return "unresolved", None, "owner_not_resolved"
    return "ambiguous", None, "multiple_owner_candidates"


def _resolve_flow(
    owner_id: str,
    span_ids: list[str],
    worker_flow_plan: WorkerFlowPlanIR,
) -> tuple[str, str | None, str | None]:
    flow = worker_flow_plan.worker_flows.get(owner_id)
    if flow is None:
        return "unresolved", None, "worker_flow_not_found"
    flow_refs = {
        ref for span_id in span_ids
        if (ref := flow.get_flow_for_span(span_id)) is not None
    }
    if len(flow_refs) == 1:
        return "placed", next(iter(flow_refs)), None
    if not flow_refs:
        return "unresolved", None, "flow_not_resolved"
    return "ambiguous", None, "multiple_flow_candidates"


def _resolve_block(
    owner_id: str,
    flow_ref: str,
    span_ids: list[str],
    worker_block_plan: WorkerBlockPlanIR,
) -> tuple[str, str | None, str | None]:
    blocks = worker_block_plan.worker_blocks.get(owner_id)
    if blocks is None:
        return "unresolved", None, "worker_blocks_not_found"
    candidates = _blocks_for_flow(blocks, flow_ref)
    matching = {
        block.block_id
        for block in candidates
        if set(span_ids).intersection(block.spans)
    }
    if len(matching) == 1:
        return "placed", next(iter(matching)), None
    if not matching:
        return "unresolved", None, "block_not_resolved"
    return "ambiguous", None, "multiple_block_candidates"


def _blocks_for_flow(blocks: BlockStructureIR, flow_ref: str) -> list[BlockIR]:
    if flow_ref == "main":
        return list(blocks.main_flow_blocks)
    if flow_ref in blocks.alternative_flow_blocks:
        return list(blocks.alternative_flow_blocks[flow_ref])
    if flow_ref in blocks.exception_flow_blocks:
        return list(blocks.exception_flow_blocks[flow_ref])
    return []
