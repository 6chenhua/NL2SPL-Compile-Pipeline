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

        child_workers, handoffs, rejected, materialized_decisions, decision_warnings = (
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

        rejected += [d for d in materialized_decisions if d.decision != "extract_child_worker"]

        return WorkerPlanIR(
            main_worker_id=main_worker_id,
            workers=all_workers,
            handoffs=handoffs,
            candidates=candidates,
            decisions=materialized_decisions,
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
        list[WorkerSpecIR],
        list[WorkerHandoffIR],
        list[WorkerBoundaryDecisionIR],
        list[WorkerBoundaryDecisionIR],
        list[str],
    ]:
        workers: list[WorkerSpecIR] = []
        handoffs: list[WorkerHandoffIR] = []
        rejected: list[WorkerBoundaryDecisionIR] = []
        materialized_decisions: list[WorkerBoundaryDecisionIR] = []
        warnings: list[str] = []
        main_owned = set(main_worker.owned_span_ids)
        blocked_anchor_span_ids = self._blocked_handoff_anchor_spans(
            decisions,
            candidates_by_id,
        )

        for decision in decisions:
            if decision.decision != "extract_child_worker":
                materialized_decisions.append(decision)
                continue

            candidate = candidates_by_id.get(decision.candidate_id)
            if candidate is None:
                warnings.append(
                    f"Decision {decision.candidate_id} references unknown candidate; "
                    "treated as rejected."
                )
                rejected_decision = self._reject_decision(
                    decision,
                    "insufficient_semantic_boundary",
                    "Accepted decision references an unknown candidate.",
                )
                materialized_decisions.append(rejected_decision)
                continue

            worker = self._candidate_to_worker(candidate, decision, hard_inputs, hard_outputs)
            if worker is None:
                reason = self._missing_contract_reason(
                    candidate,
                    hard_inputs,
                    hard_outputs,
                )
                warnings.append(
                    f"Candidate {candidate.candidate_id} accepted but missing {reason}; "
                    "rejecting."
                )
                rejected_decision = self._reject_decision(
                    decision,
                    reason,
                    "Accepted candidate did not provide a deterministic worker contract.",
                )
                materialized_decisions.append(rejected_decision)
                continue

            main_owned.difference_update(worker.owned_span_ids)
            workers.append(worker)
            materialized_decisions.append(decision)

            handoff = self._build_handoff(
                worker,
                candidate,
                span_order,
                blocked_anchor_span_ids,
            )
            handoffs.append(handoff)

        main_worker.owned_span_ids = sorted(main_owned, key=lambda sid: int(sid[1:]))
        return workers, handoffs, rejected, materialized_decisions, warnings

    @staticmethod
    def _blocked_handoff_anchor_spans(
        decisions: list[WorkerBoundaryDecisionIR],
        candidates_by_id: dict[str, CandidateTaskUnitIR],
    ) -> set[str]:
        """Return spans that cannot anchor parent handoff placement.

        Child-owned spans and non-main control-flow spans are not valid
        caller anchors. Using them causes Stage 7 ownership warnings and can
        move fallback invocation blocks to the wrong location.
        """
        blocked: set[str] = set()
        for decision in decisions:
            candidate = candidates_by_id.get(decision.candidate_id)
            if candidate is None:
                continue
            if decision.decision in {
                "extract_child_worker",
                "compile_as_exception_flow",
                "compile_as_alternative_flow",
            }:
                blocked.update(candidate.source_span_ids)
        return blocked

    def _missing_contract_reason(
        self,
        candidate: CandidateTaskUnitIR,
        hard_inputs: list[ContractFieldIR],
        hard_outputs: list[ContractFieldIR],
    ) -> str:
        has_inputs = bool(
            candidate.possible_inputs
            or self._match_hard_fact_contracts(candidate, hard_inputs)
        )
        has_outputs = bool(
            candidate.possible_outputs
            or self._match_hard_fact_contracts(candidate, hard_outputs)
        )
        if not has_inputs:
            return "no_clear_input_contract"
        if not has_outputs:
            return "no_clear_output_contract"
        return "unclear_result_handoff"

    @staticmethod
    def _reject_decision(
        decision: WorkerBoundaryDecisionIR,
        rejection_reason: str,
        reason: str,
    ) -> WorkerBoundaryDecisionIR:
        return WorkerBoundaryDecisionIR(
            candidate_id=decision.candidate_id,
            decision="keep_in_main_worker",
            boundary_strength="weak",
            boundary_kind="not_a_worker",
            rejection_reason=rejection_reason,  # type: ignore[arg-type]
            reason=reason,
            evidence=list(decision.evidence),
        )

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

        if not inputs:
            inputs = self._match_hard_fact_contracts(candidate, hard_inputs)
        if not outputs:
            outputs = self._match_hard_fact_contracts(candidate, hard_outputs)
        if not inputs or not outputs:
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

    @staticmethod
    def _match_hard_fact_contracts(
        candidate: CandidateTaskUnitIR,
        facts: list[ContractFieldIR],
    ) -> list[ContractFieldIR]:
        """Conservatively recover missing contracts from hard facts.

        A hard fact is adopted only when every meaningful token in the
        snake_case variable name appears in the candidate text or purpose.
        This keeps repair deterministic while avoiding broad global IO
        leakage into child workers.
        """
        haystack = WorkerPlanMaterializer._normalize_contract_text(
            f"{candidate.task_text} {candidate.purpose}"
        )
        matches: list[ContractFieldIR] = []
        for fact in facts:
            tokens = [
                token
                for token in WorkerPlanMaterializer._normalize_contract_text(
                    fact.name
                ).split()
                if len(token) > 2
            ]
            if tokens and all(token in haystack for token in tokens):
                matches.append(fact)
        return matches

    @staticmethod
    def _normalize_contract_text(text: str) -> str:
        return " ".join(
            token
            for token in re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
            if token
        )

    def _build_handoff(
        self,
        worker: WorkerSpecIR,
        candidate: CandidateTaskUnitIR,
        span_order: list[str],
        blocked_anchor_span_ids: set[str],
    ) -> WorkerHandoffIR:
        """Build handoff with caller-owned invoke location.

        Uses the ordered behavior span list to find the nearest
        main-worker-owned span before the child's first span (after_span_id)
        and the nearest main-worker-owned span after the child's first
        contiguous child-owned region (before_span_id). Never uses
        child-owned spans for location hints.
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
            child_spans,
            span_order,
            blocked_anchor_span_ids,
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
        blocked_anchor_span_ids: set[str] | None = None,
    ) -> tuple[str | None, str | None]:
        """Find caller-owned neighbor spans around a child's span range.

        Scans the ordered behavior span list to find the span immediately
        before the child's first span and the span immediately after the
        first contiguous child-owned region. This avoids late policy or
        delegation spans inside the same candidate moving the invocation to
        the end of the main flow.

        Returns (after_span_id, before_span_id).
        """
        if not span_order or not child_span_ids:
            return None, None

        blocked = set(blocked_anchor_span_ids or set()).union(child_span_ids)
        first_idx: int | None = None
        for i, sid in enumerate(span_order):
            if sid in child_span_ids:
                first_idx = i
                break

        if first_idx is None:
            return None, None

        after = None
        for i in range(first_idx - 1, -1, -1):
            if span_order[i] not in blocked:
                after = span_order[i]
                break

        before = None
        for i in range(first_idx + 1, len(span_order)):
            if span_order[i] not in blocked:
                before = span_order[i]
                break
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
