"""Compatibility adapter from WorkerPlanIR to legacy DelegationCandidate."""

from __future__ import annotations

from copy import deepcopy

from nl2spl.ir.block_structure_ir import BlockStructureIR
from nl2spl.ir.flow_structure_ir import DelegationCandidate, FlowStructureIR
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    WorkerBlockPlanIR,
    WorkerBoundaryDecisionIR,
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
)


class WorkerPlanAdapter:
    """Convert first-class worker plans into temporary legacy bridge objects."""

    def to_delegation_candidates(self, plan: WorkerPlanIR) -> list[DelegationCandidate]:
        """Convert accepted worker extraction decisions to DelegationCandidate objects."""
        rejected_ids = {decision.candidate_id for decision in plan.rejected_candidates}
        candidates_by_id = {candidate.candidate_id: candidate for candidate in plan.candidates}

        delegation_candidates: list[DelegationCandidate] = []
        for decision in plan.decisions:
            if decision.decision != "extract_child_worker":
                continue
            if decision.candidate_id in rejected_ids:
                continue

            candidate = candidates_by_id.get(decision.candidate_id)
            worker = self._matching_worker(plan, decision, candidate)
            spans = (
                list(candidate.source_span_ids)
                if candidate is not None
                else list(worker.owned_span_ids)
                if worker is not None
                else []
            )
            inputs = self._field_names(
                worker.input_contract
                if worker is not None
                else candidate.possible_inputs
                if candidate is not None
                else []
            )
            outputs = self._field_names(
                worker.output_contract
                if worker is not None
                else candidate.possible_outputs
                if candidate is not None
                else []
            )
            delegation_candidates.append(
                DelegationCandidate(
                    candidate_id=decision.candidate_id,
                    spans=spans,
                    reason=decision.reason,
                    suggested_type="child_worker",
                    input_variables=inputs,
                    output_variables=outputs,
                )
            )

        return delegation_candidates

    def _matching_worker(
        self,
        plan: WorkerPlanIR,
        decision: WorkerBoundaryDecisionIR,
        candidate: CandidateTaskUnitIR | None,
    ) -> WorkerSpecIR | None:
        non_main_workers = [worker for worker in plan.workers if worker.kind != "main"]

        for worker in non_main_workers:
            if worker.worker_id == decision.candidate_id:
                return worker

        if candidate is None:
            return None

        candidate_spans = set(candidate.source_span_ids)
        exact_matches = [
            worker
            for worker in non_main_workers
            if set(worker.owned_span_ids) == candidate_spans
        ]
        if exact_matches:
            return exact_matches[0]

        overlapping = [
            worker
            for worker in non_main_workers
            if candidate_spans.intersection(worker.owned_span_ids)
        ]
        return overlapping[0] if overlapping else None

    def _field_names(self, fields: list[ContractFieldIR]) -> list[str]:
        return [field.name for field in fields]


def adapt_worker_plan_to_delegation_candidates(
    plan: WorkerPlanIR,
) -> list[DelegationCandidate]:
    """Convert WorkerPlanIR into legacy delegation candidates for migration."""
    return WorkerPlanAdapter().to_delegation_candidates(plan)


def worker_flow_plan_to_legacy_main_flow(
    worker_flow_plan: WorkerFlowPlanIR,
    worker_plan: WorkerPlanIR,
) -> FlowStructureIR:
    """Return the legacy Stage 6-10 flow view for the main worker.

    This adapter is intentionally not a full flattening operation: child-owned
    flow spans stay out of the parent flow. Downstream legacy stages receive the
    main worker's flow plus temporary delegation candidates derived from
    WorkerPlanIR handoffs.
    """
    main_flow = worker_flow_plan.worker_flows.get(worker_plan.main_worker_id)
    if main_flow is None:
        return FlowStructureIR(
            delegation_candidates=adapt_worker_plan_to_delegation_candidates(worker_plan)
        )

    legacy_flow = deepcopy(main_flow)
    legacy_flow.delegation_candidates = adapt_worker_plan_to_delegation_candidates(
        worker_plan
    )
    return legacy_flow


def worker_block_plan_to_legacy_main_blocks(
    worker_block_plan: WorkerBlockPlanIR,
    worker_plan: WorkerPlanIR,
) -> BlockStructureIR:
    """Return the legacy Stage 6-10 block view for the main worker.

    Child worker block structures remain available in WorkerBlockPlanIR for the
    worker-aware path. The temporary legacy path receives only the main worker's
    blocks so child-owned spans cannot leak into parent steps.
    """
    main_blocks = worker_block_plan.worker_blocks.get(worker_plan.main_worker_id)
    return deepcopy(main_blocks) if main_blocks is not None else BlockStructureIR()
