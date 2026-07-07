"""Build executable action candidate and placement plans."""

from __future__ import annotations

from nl2spl.compiler.construct_plan import ConstructPlan
from nl2spl.ir.action_placement_ir import (
    ExecutableActionCandidate,
    ExecutableActionPlacement,
    ExecutableActionPlacementPlan,
    MaterializationExclusion,
    WorkerExecutableActionSet,
)
from nl2spl.ir.field_route_ir import FieldRouteIR
from nl2spl.ir.span_ir import SpanIR
from nl2spl.ir.worker_plan_ir import WorkerPlanIR


def build_executable_action_placement_plan(
    spans: list[SpanIR],
    routes: FieldRouteIR,
    worker_plan: WorkerPlanIR,
    construct_plan: ConstructPlan | None = None,
) -> ExecutableActionPlacementPlan:
    """Project source-backed executable action candidates.

    This does not materialize steps or decide variable production. It only
    captures which source spans may become executable actions and which worker
    currently owns them.
    """
    span_by_id = {span.span_id: span for span in spans}
    executable_ids = _executable_span_ids(spans, routes, construct_plan)
    api_span_to_demand = _api_span_to_demand(construct_plan)
    candidates: list[ExecutableActionCandidate] = []
    placements: list[ExecutableActionPlacement] = []

    for span_id in sorted(executable_ids, key=_span_sort_key):
        span = span_by_id.get(span_id)
        if span is None:
            continue
        candidate = ExecutableActionCandidate(
            candidate_id=f"action_{span_id}",
            source_span_ids=(span_id,),
            action_text=span.action_text_exact or span.text,
            source=_candidate_source(span, routes),
            status="accepted",
            reason="accepted_executable_source",
            command_type_hint=("CALL_API" if span_id in api_span_to_demand else None),
            guard_text=span.guard_text_exact,
        )
        candidates.append(candidate)
        placements.append(_placement_for_candidate(candidate, worker_plan))

    candidates.extend(
        _rejected_candidates(
            spans,
            routes,
            executable_ids,
        )
    )
    worker_actions = _worker_action_sets(
        placements,
        candidates,
        worker_plan,
        api_span_to_demand,
    )
    return ExecutableActionPlacementPlan(
        candidates=tuple(candidates),
        placements=tuple(placements),
        worker_actions=tuple(worker_actions),
        audit={
            "total_candidates": len(candidates),
            "source": "stage1/routes/construct_plan",
        },
    )


def _executable_span_ids(
    spans: list[SpanIR],
    routes: FieldRouteIR,
    construct_plan: ConstructPlan | None,
) -> set[str]:
    ids = (
        set(routes.get_executable_behavior_span_ids())
        if routes.annotations
        else set(routes.behavior)
    )
    for span in spans:
        if _is_stage1_process_action(span):
            ids.add(span.span_id)
    if construct_plan is not None:
        for demand in construct_plan.api_call_demands():
            slot = demand.slots.get("call_action")
            ids.update(slot.source_span_ids if slot is not None else demand.source_span_ids)
    return ids


def _rejected_candidates(
    spans: list[SpanIR],
    routes: FieldRouteIR,
    executable_ids: set[str],
) -> list[ExecutableActionCandidate]:
    rejected: list[ExecutableActionCandidate] = []
    non_executable = set(routes.get_non_executable_behavior_span_ids())
    for span in spans:
        if span.span_id in executable_ids:
            continue
        reason = _rejection_reason(span, routes, non_executable)
        if reason is None:
            continue
        rejected.append(
            ExecutableActionCandidate(
                candidate_id=f"action_{span.span_id}",
                source_span_ids=(span.span_id,),
                action_text=span.action_text_exact or span.text,
                source="route_executable_role",
                status="rejected_non_executable",
                reason=reason,
                guard_text=span.guard_text_exact,
            )
        )
    return rejected


def _rejection_reason(
    span: SpanIR,
    routes: FieldRouteIR,
    non_executable: set[str],
) -> str | None:
    if span.span_id in non_executable:
        roles = {
            ann.semantic_role
            for ann in routes.get_annotations(span.span_id)
            if ann.semantic_role
        }
        if roles & {"failure_mode", "failure_condition"}:
            return "failure_condition_only"
        if roles & {"constraint"}:
            return "constraint_only"
        return "route_non_executable"
    annotations = routes.get_annotations(span.span_id)
    roles = {ann.semantic_role for ann in annotations if ann.semantic_role}
    if roles & {"output_contract", "input_contract"}:
        return "required_output_or_input_declaration"
    if roles & {"profile_domain"}:
        return "persona_profile_or_concept"
    return None


def _candidate_source(span: SpanIR, routes: FieldRouteIR) -> str:
    if span.segmentation_kind in {"atomic_action_candidate", "guarded_action"}:
        return "stage1_action_segmentation"
    if span.span_id in set(routes.get_executable_behavior_span_ids()):
        return "route_executable_role"
    return "construct_plan_executable_demand"


def _is_stage1_process_action(span: SpanIR) -> bool:
    return (
        span.segmentation_kind in {
            "atomic_action_candidate",
            "guarded_action",
            "continuation_repaired",
        }
        and span.source_section_id == "sec_reusable_process"
    )


def _api_span_to_demand(construct_plan: ConstructPlan | None) -> dict[str, str]:
    result: dict[str, str] = {}
    if construct_plan is None:
        return result
    for demand in construct_plan.api_call_demands():
        slot = demand.slots.get("call_action")
        source_span_ids = slot.source_span_ids if slot is not None else demand.source_span_ids
        for span_id in source_span_ids:
            result[span_id] = demand.demand_id
    return result


def _worker_action_sets(
    placements: list[ExecutableActionPlacement],
    candidates: list[ExecutableActionCandidate],
    worker_plan: WorkerPlanIR,
    api_span_to_demand: dict[str, str],
) -> list[WorkerExecutableActionSet]:
    accepted_by_id = {
        candidate.candidate_id: candidate
        for candidate in candidates
        if candidate.status == "accepted"
    }
    placement_spans_by_worker: dict[str, set[str]] = {
        worker.worker_id: set() for worker in worker_plan.workers
    }
    generic_spans_by_worker: dict[str, set[str]] = {
        worker.worker_id: set() for worker in worker_plan.workers
    }
    exclusions_by_worker: dict[str, list[MaterializationExclusion]] = {
        worker.worker_id: [] for worker in worker_plan.workers
    }
    for placement in placements:
        if placement.status != "placed" or placement.worker_id is None:
            continue
        candidate = accepted_by_id.get(placement.candidate_id)
        if candidate is None:
            continue
        for span_id in candidate.source_span_ids:
            placement_spans_by_worker.setdefault(placement.worker_id, set()).add(span_id)
            if span_id in api_span_to_demand:
                exclusions_by_worker.setdefault(placement.worker_id, []).append(
                    MaterializationExclusion(
                        span_id=span_id,
                        excluded_from="general_command_extraction",
                        owning_authority="api_call",
                        authority_ref=api_span_to_demand[span_id],
                        reason="api_call_materializer_owns_command_type",
                    )
                )
                continue
            generic_spans_by_worker.setdefault(placement.worker_id, set()).add(span_id)
    result: list[WorkerExecutableActionSet] = []
    for worker in worker_plan.workers:
        result.append(
            WorkerExecutableActionSet(
                worker_id=worker.worker_id,
                placement_span_ids=tuple(
                    sorted(
                        placement_spans_by_worker.get(worker.worker_id, set()),
                        key=_span_sort_key,
                    )
                ),
                generic_step_extraction_span_ids=tuple(
                    sorted(generic_spans_by_worker.get(worker.worker_id, set()), key=_span_sort_key)
                ),
                materialization_exclusions=tuple(
                    sorted(
                        exclusions_by_worker.get(worker.worker_id, []),
                        key=lambda item: _span_sort_key(item.span_id),
                    )
                ),
            )
        )
    return result


def _placement_for_candidate(
    candidate: ExecutableActionCandidate,
    worker_plan: WorkerPlanIR,
) -> ExecutableActionPlacement:
    span_ids = set(candidate.source_span_ids)
    owners = [
        worker.worker_id
        for worker in worker_plan.workers
        if span_ids.intersection(worker.owned_span_ids)
    ]
    if len(owners) == 1:
        return ExecutableActionPlacement(
            candidate_id=candidate.candidate_id,
            worker_id=owners[0],
            flow_ref=None,
            block_ref=None,
            status="placed",
            reason="worker_owned",
        )
    if not owners:
        return ExecutableActionPlacement(
            candidate_id=candidate.candidate_id,
            worker_id=None,
            flow_ref=None,
            block_ref=None,
            status="unplaced",
            reason="worker_not_resolved",
        )
    return ExecutableActionPlacement(
        candidate_id=candidate.candidate_id,
        worker_id=None,
        flow_ref=None,
        block_ref=None,
        status="ambiguous",
        reason="multiple_worker_owners",
    )


def _span_sort_key(span_id: str) -> tuple[int, str]:
    digits = "".join(ch for ch in span_id if ch.isdigit())
    return (int(digits) if digits else 10**9, span_id)
