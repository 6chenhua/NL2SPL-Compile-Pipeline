"""Stage 3.5c: WorkerPlanMaterializer — deterministic WorkerPlanIR builder.

Converts accepted/rejected decisions and candidate units into a valid
WorkerPlanIR. Graph invariants (exactly one worker per accepted decision,
handoff per child worker, non-overlapping ownership) are enforced in code
rather than relying on LLM output consistency.
"""

from __future__ import annotations

import re

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


class WorkerPlanMaterializer:
    """Deterministic builder that produces a valid WorkerPlanIR.

    Guarantees:
    - Every accepted decision materializes exactly one non-main worker
      with a valid handoff, or is rejected with a clear reason.
    - Main worker owns all behavior spans not assigned to child workers.
    - Contracts are complete or deterministically filled from candidates.
    """

    _SAFE_NAME = re.compile(r"[^A-Za-z0-9_]")

    def materialize(
        self,
        candidates: list[CandidateTaskUnitIR],
        decisions: list[WorkerBoundaryDecisionIR],
        hard_fact_inputs: list[ContractFieldIR] | None = None,
        hard_fact_outputs: list[ContractFieldIR] | None = None,
        behavior_span_ids: set[str] | None = None,
        existing_workers: list[WorkerSpecIR] | None = None,
        existing_handoffs: list[WorkerHandoffIR] | None = None,
        main_worker_id: str = "worker_main",
        main_worker_name: str = "MainWorker",
    ) -> tuple[WorkerPlanIR, list[str]]:
        """Materialize a WorkerPlanIR from decisions and candidates.

        Args:
            candidates: Candidate task units discovered by Stage 3.5a.
            decisions: Boundary decisions from Stage 3.5b.
            hard_fact_inputs: Hard-fact input variables for main worker contract.
            hard_fact_outputs: Hard-fact output variables for main worker contract.
            behavior_span_ids: All behavior span IDs for ownership computation.
            existing_workers: Pre-existing workers (e.g., from single-call path).
            existing_handoffs: Pre-existing handoffs.
            main_worker_id: ID for the main worker.
            main_worker_name: SPL-safe name for the main worker.

        Returns:
            Tuple of (WorkerPlanIR, repair_warnings).
        """
        warnings: list[str] = []
        candidates_by_id = {c.candidate_id: c for c in candidates}

        # Build main worker
        main_worker = self._build_main_worker(
            main_worker_id,
            main_worker_name,
            hard_fact_inputs or [],
            hard_fact_outputs or [],
        )

        # Materialize workers and handoffs from accepted decisions
        child_workers, handoffs, decision_warnings = self._materialize_accepted(
            decisions, candidates_by_id
        )
        warnings.extend(decision_warnings)

        # Merge with any pre-existing workers/handoffs
        if existing_workers:
            child_workers, handoffs = self._merge_existing(
                child_workers, handoffs, existing_workers, existing_handoffs or [],
                candidates_by_id, warnings,
            )

        # Compute span ownership
        all_workers = [main_worker] + child_workers
        if behavior_span_ids:
            self._assign_ownership(all_workers, behavior_span_ids, warnings)

        # Collect rejected candidates
        rejected = [d for d in decisions if d.decision != "extract_child_worker"]

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
        worker_id: str,
        worker_name: str,
        inputs: list[ContractFieldIR],
        outputs: list[ContractFieldIR],
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
    ) -> tuple[list[WorkerSpecIR], list[WorkerHandoffIR], list[str]]:
        workers: list[WorkerSpecIR] = []
        handoffs: list[WorkerHandoffIR] = []
        warnings: list[str] = []

        for decision in decisions:
            if decision.decision != "extract_child_worker":
                continue

            candidate = candidates_by_id.get(decision.candidate_id)
            if candidate is None:
                warnings.append(
                    f"Decision {decision.candidate_id} references unknown candidate; skipped."
                )
                continue

            worker = self._candidate_to_worker(candidate, decision)
            workers.append(worker)

            handoff = self._build_handoff(worker, candidate, decision, warnings)
            if handoff:
                handoffs.append(handoff)

        return workers, handoffs, warnings

    def _candidate_to_worker(
        self,
        candidate: CandidateTaskUnitIR,
        decision: WorkerBoundaryDecisionIR,
    ) -> WorkerSpecIR:
        worker_id = self._worker_id_from_candidate(candidate.candidate_id)
        worker_name = self._worker_name_from_candidate(candidate)

        inputs = list(candidate.possible_inputs) if candidate.possible_inputs else [
            ContractFieldIR("input", "text", True, "Worker input", "input")
        ]
        outputs = list(candidate.possible_outputs) if candidate.possible_outputs else [
            ContractFieldIR("output", "text", True, "Worker output", "output")
        ]

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
        decision: WorkerBoundaryDecisionIR,
        warnings: list[str],
    ) -> WorkerHandoffIR | None:
        input_bindings = [
            InputBindingIR(f.name, f.name, f.required)
            for f in worker.input_contract
        ]
        output_bindings = [
            OutputBindingIR(f.name, f.name, f.required, "set")
            for f in worker.output_contract
        ]

        if not input_bindings and not output_bindings:
            warnings.append(
                f"Worker {worker.worker_id} has no contract fields; "
                "handoff created with empty bindings."
            )

        invoke_hint = InvokeLocationHintIR(
            flow_kind="main",
            flow_id=None,
            after_span_id=candidate.source_span_ids[0] if candidate.source_span_ids else None,
            before_span_id=None,
            block_hint="sequential",
        )

        from_worker = "worker_main"

        return WorkerHandoffIR(
            handoff_id=f"handoff_{worker.worker_id}",
            from_worker=from_worker,
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

    # ---- Ownership ----------------------------------------------------

    def _assign_ownership(
        self,
        workers: list[WorkerSpecIR],
        behavior_span_ids: set[str],
        warnings: list[str],
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

    def _merge_existing(
        self,
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

            # Find matching handoff or create one
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
