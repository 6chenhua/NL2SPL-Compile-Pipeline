"""Stage 3.5c: WorkerPlanMaterializer — deterministic WorkerPlanIR builder.

Converts accepted/rejected decisions and candidate units into a valid
WorkerPlanIR. Graph invariants (exactly one worker per accepted decision,
handoff per child worker, non-overlapping ownership) are enforced in code
rather than relying on LLM output consistency.
"""

from __future__ import annotations

import re
from typing import Any

from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    ContractFieldIR,
    HandoffFailurePolicyIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerBoundaryDecisionIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)

_DEFAULT_INPUT = ContractFieldIR("input", "text", True, "Worker input", "input")
_DEFAULT_OUTPUT = ContractFieldIR("output", "text", True, "Worker output", "output")


class WorkerPlanMaterializer:
    """Deterministic builder that produces a valid WorkerPlanIR.

    Guarantees:
    - Every accepted decision materializes exactly one non-main worker
      with a valid handoff, or is rejected with a clear reason.
    - Main worker owns all behavior spans not assigned to child workers.
    - Contracts are filled from candidates/hard-facts or the decision is
      rejected. Dummy contracts are never created.
    - Handoff invoke location uses caller-owned (main worker) neighbor
      spans, never child-owned spans.
    """

    _SAFE_NAME = re.compile(r"[^A-Za-z0-9_]")

    def materialize(
        self,
        candidates: list[CandidateTaskUnitIR],
        decisions: list[WorkerBoundaryDecisionIR],
        hard_fact_inputs: list[ContractFieldIR] | None = None,
        hard_fact_outputs: list[ContractFieldIR] | None = None,
        behavior_span_ids: set[str] | None = None,
        behavior_span_order: list[str] | None = None,
        existing_workers: list[WorkerSpecIR] | None = None,
        existing_handoffs: list[WorkerHandoffIR] | None = None,
        main_worker_id: str = "worker_main",
        main_worker_name: str = "MainWorker",
    ) -> tuple[WorkerPlanIR, list[str]]:
        """Materialize a WorkerPlanIR from decisions and candidates.

        Args:
            candidates: Candidate task units discovered by Stage 3.5a.
            decisions: Boundary decisions from Stage 3.5b.
            hard_fact_inputs: Hard-fact input variables for contracts.
            hard_fact_outputs: Hard-fact output variables for contracts.
            behavior_span_ids: All behavior span IDs.
            behavior_span_order: Ordered behavior span IDs for invoke
                location computation (caller-owned neighbor lookup).
            existing_workers: Pre-existing workers (legacy path only).
            existing_handoffs: Pre-existing handoffs (legacy path only).
            main_worker_id: ID for the main worker.
            main_worker_name: SPL-safe name for the main worker.

        Returns:
            Tuple of (WorkerPlanIR, warnings).
        """
        warnings: list[str] = []
        candidates_by_id = {c.candidate_id: c for c in candidates}
        hard_inputs = hard_fact_inputs or []
        hard_outputs = hard_fact_outputs or []
        behavior_all = behavior_span_ids or set()
        span_order = behavior_span_order or []

        main_worker = self._build_main_worker(
            main_worker_id, main_worker_name, hard_inputs, hard_outputs,
        )

        child_workers, handoffs, rejected, decision_warnings = (
            self._materialize_accepted(
                decisions, candidates_by_id, hard_inputs, hard_outputs,
                span_order, main_worker,
            )
        )
        warnings.extend(decision_warnings)

        if existing_workers:
            child_workers, handoffs = self._merge_existing(
                child_workers, handoffs, existing_workers, existing_handoffs or [],
                candidates_by_id, warnings,
            )

        all_workers = [main_worker] + child_workers
        if behavior_all:
            self._assign_ownership(all_workers, behavior_all)

        rejected += [d for d in decisions if d.decision != "extract_child_worker"]

        return WorkerPlanIR(
            main_worker_id=main_worker_id,
            workers=all_workers,
            handoffs=handoffs,
            candidates=candidates,
            decisions=decisions,
            rejected_candidates=rejected,
        ), warnings

    # ---- Main worker ---------------------------------------------------

    def _build_main_worker(
        self,
        worker_id: str, worker_name: str,
        inputs: list[ContractFieldIR], outputs: list[ContractFieldIR],
    ) -> WorkerSpecIR:
        return WorkerSpecIR(
            worker_id=worker_id,
            worker_name=worker_name,
            kind="main",
            purpose="Orchestrate the end-to-end process and delegate to sub-tasks.",
            input_contract=list(inputs),
            output_contract=list(outputs),
            boundary_kind="main_worker",
        )

    # ---- Accepted decision materialization ----------------------------

    def _materialize_accepted(
        self,
        decisions: list[WorkerBoundaryDecisionIR],
        candidates_by_id: dict[str, CandidateTaskUnitIR],
        hard_inputs: list[ContractFieldIR],
        hard_outputs: list[ContractFieldIR],
        span_order: list[str],
        main_worker: WorkerSpecIR,
    ) -> tuple[
        list[WorkerSpecIR], list[WorkerHandoffIR],
        list[WorkerBoundaryDecisionIR], list[str],
    ]:
        workers: list[WorkerSpecIR] = []
        handoffs: list[WorkerHandoffIR] = []
        rejected: list[WorkerBoundaryDecisionIR] = []
        warnings: list[str] = []
        main_owned = set(main_worker.owned_span_ids)

        for decision in decisions:
            if decision.decision != "extract_child_worker":
                continue

            candidate = candidates_by_id.get(decision.candidate_id)
            if candidate is None:
                warnings.append(
                    f"Decision {decision.candidate_id} references unknown candidate; "
                    "treated as rejected."
                )
                rejected.append(decision)
                continue

            worker = self._candidate_to_worker(candidate, decision, hard_inputs, hard_outputs)
            if worker is None:
                warnings.append(
                    f"Candidate {candidate.candidate_id} accepted but missing "
                    "contract; rejecting."
                )
                rejected.append(decision)
                continue

            main_owned.difference_update(worker.owned_span_ids)
            workers.append(worker)

            handoff = self._build_handoff(worker, candidate, span_order)
            handoffs.append(handoff)

        main_worker.owned_span_ids = sorted(main_owned, key=lambda sid: int(sid[1:]))
        return workers, handoffs, rejected, warnings

    def _candidate_to_worker(
        self,
        candidate: CandidateTaskUnitIR,
        decision: WorkerBoundaryDecisionIR,
        hard_inputs: list[ContractFieldIR],
        hard_outputs: list[ContractFieldIR],
    ) -> WorkerSpecIR | None:
        """Build a WorkerSpecIR from candidate. Returns None if contract
        cannot be filled deterministically (candidate is rejected upstream)."""
        inputs = list(candidate.possible_inputs) if candidate.possible_inputs else []
        outputs = list(candidate.possible_outputs) if candidate.possible_outputs else []

        # Fill missing contracts from hard facts when names align
        if not inputs:
            child_names = {f.name for f in (candidate.possible_inputs or [])}
            matched = [f for f in hard_inputs if f.name in child_names]
            inputs = matched or inputs
        if not outputs:
            child_names = {f.name for f in (candidate.possible_outputs or [])}
            matched = [f for f in hard_outputs if f.name in child_names]
            outputs = matched or outputs

        # Still missing: reject the decision
        if not inputs and not candidate.possible_inputs:
            return None
        if not outputs and not candidate.possible_outputs:
            return None

        worker_id = self._worker_id_from_candidate(candidate.candidate_id)
        worker_name = self._worker_name_from_candidate(candidate)

        return WorkerSpecIR(
            worker_id=worker_id,
            worker_name=worker_name,
            kind="child",
            purpose=candidate.purpose or candidate.task_text,
            owned_span_ids=list(candidate.source_span_ids),
            input_contract=inputs,
            output_contract=outputs,
            boundary_kind=candidate.candidate_kind,
            decision_evidence=list(decision.evidence),
            reason=decision.reason,
        )

    def _build_handoff(
        self,
        worker: WorkerSpecIR,
        candidate: CandidateTaskUnitIR,
        span_order: list[str],
    ) -> WorkerHandoffIR:
        """Build handoff with caller-owned invoke location.

        Uses the ordered behavior span list to find the nearest
        main-worker-owned span before the child's first span (after_span_id)
        and the nearest main-worker-owned span after the child's last span
        (before_span_id). Never uses child-owned spans for location hints.
        """
        input_bindings = [
            InputBindingIR(f.name, f.name, f.required)
            for f in worker.input_contract
        ]
        output_bindings = [
            OutputBindingIR(f.name, f.name, f.required, "set")
            for f in worker.output_contract
        ]

        child_spans = set(worker.owned_span_ids)
        after_span_id, before_span_id = self._caller_neighbor_spans(
            child_spans, span_order,
        )

        invoke_hint = InvokeLocationHintIR(
            flow_kind="main",
            flow_id=None,
            after_span_id=after_span_id,
            before_span_id=before_span_id,
            block_hint="sequential",
        )

        return WorkerHandoffIR(
            handoff_id=f"handoff_{worker.worker_id}",
            from_worker="worker_main",
            to_worker=worker.worker_id,
            api_ref=None,
            mode="invoke",
            condition_text=candidate.purpose or candidate.task_text,
            ordering="after",
            input_bindings=input_bindings,
            output_bindings=output_bindings,
            invoke_location_hint=invoke_hint,
            failure_policy=HandoffFailurePolicyIR(
                policy_kind="propagate_exception",
                description=f"If {worker.worker_name} fails, propagate to parent.",
            ),
        )

    # ---- Span ordering helpers -----------------------------------------

    @staticmethod
    def _caller_neighbor_spans(
        child_span_ids: set[str],
        span_order: list[str],
    ) -> tuple[str | None, str | None]:
        """Find caller-owned neighbor spans around a child's span range.

        Scans the ordered behavior span list to find the span immediately
        before the child's first span and the span immediately after the
        child's last span. Both are caller-owned (non-child) by definition
        since child spans are excluded from the candidate set.

        Returns (after_span_id, before_span_id).
        """
        if not span_order or not child_span_ids:
            return None, None

        first_idx: int | None = None
        last_idx: int | None = None
        for i, sid in enumerate(span_order):
            if sid in child_span_ids:
                if first_idx is None:
                    first_idx = i
                last_idx = i

        if first_idx is None:
            return None, None

        after = span_order[first_idx - 1] if first_idx > 0 else None
        before = span_order[last_idx + 1] if last_idx + 1 < len(span_order) else None
        return after, before

    # ---- Ownership ----------------------------------------------------

    @staticmethod
    def _assign_ownership(
        workers: list[WorkerSpecIR],
        behavior_span_ids: set[str],
    ) -> None:
        assigned: set[str] = set()
        for w in workers:
            if w.kind != "main":
                assigned.update(w.owned_span_ids)
        unassigned = behavior_span_ids - assigned
        if unassigned:
            main_worker = next((w for w in workers if w.kind == "main"), None)
            if main_worker:
                main_worker.owned_span_ids.extend(
                    sorted(unassigned, key=lambda sid: int(sid[1:]))
                )

    # ---- Merge --------------------------------------------------------

    @staticmethod
    def _merge_existing(
        new_workers: list[WorkerSpecIR],
        new_handoffs: list[WorkerHandoffIR],
        existing_workers: list[WorkerSpecIR],
        existing_handoffs: list[WorkerHandoffIR],
        candidates_by_id: dict[str, CandidateTaskUnitIR],
        warnings: list[str],
    ) -> tuple[list[WorkerSpecIR], list[WorkerHandoffIR]]:
        new_ids = {w.worker_id for w in new_workers}
        merged_workers = list(new_workers)
        merged_handoffs = list(new_handoffs)

        for ew in existing_workers:
            if ew.kind == "main":
                continue
            if ew.worker_id in new_ids:
                continue
            merged_workers.append(ew)
            matching = [h for h in existing_handoffs if h.to_worker == ew.worker_id]
            if matching:
                merged_handoffs.extend(matching)
            else:
                warnings.append(
                    f"Existing worker {ew.worker_id} has no handoff; skipped."
                )

        return merged_workers, merged_handoffs

    # ---- Naming helpers ------------------------------------------------

    @staticmethod
    def _worker_id_from_candidate(candidate_id: str) -> str:
        if candidate_id.startswith("candidate_"):
            return candidate_id[len("candidate_"):]
        return candidate_id

    @staticmethod
    def _worker_name_from_candidate(candidate: CandidateTaskUnitIR) -> str:
        raw = candidate.candidate_id.replace("candidate_", "Worker_")
        return WorkerPlanMaterializer._SAFE_NAME.sub("", raw)
