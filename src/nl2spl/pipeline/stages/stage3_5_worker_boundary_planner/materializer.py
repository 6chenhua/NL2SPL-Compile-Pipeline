"""Stage 3.5c: WorkerPlanMaterializer -- deterministic WorkerPlanIR builder.

Converts accepted/rejected decisions and candidate units into a valid
WorkerPlanIR. Graph invariants (exactly one worker per accepted decision,
handoff per child worker, non-overlapping ownership) are enforced in code
rather than relying on LLM output consistency.
"""

from __future__ import annotations

import re

from nl2spl.ir.field_route_ir import RouteAnnotation
from nl2spl.ir.worker_contract_status import derive_handoff_materialization_status
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


def _span_sort_key(sid: str) -> tuple[int, str]:
    """Sort key for span IDs like s5, s5a, s10, s10b."""
    m = re.match(r"s(\d+)(.*)", sid)
    if m:
        return int(m.group(1)), m.group(2)
    return (0, sid)


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
        annotations: list[RouteAnnotation] | None = None,
        demand_inputs: list[ContractFieldIR] | None = None,
        demand_outputs: list[ContractFieldIR] | None = None,
        api_consumed_span_ids: set[str] | None = None,
    ) -> tuple[WorkerPlanIR, list[str]]:
        """Materialize a WorkerPlanIR from decisions and candidates."""
        warnings: list[str] = []
        candidates_by_id = {c.candidate_id: c for c in candidates}
        hard_inputs = hard_fact_inputs or []
        hard_outputs = hard_fact_outputs or []
        demand_in = demand_inputs or []
        demand_out = demand_outputs or []
        all_demand_ids: set[str] = {
            f.contract_demand_id
            for f in demand_in + demand_out
            if f.contract_demand_id
        }
        behavior_all = behavior_span_ids or set()
        span_order = behavior_span_order or []

        # Build non-executable span set from annotations
        non_exec_span_ids: set[str] = set()
        if annotations:
            non_exec_span_ids = {
                a.span_id for a in annotations
                if a.executable is False and a.field == "behavior"
            }

        main_worker = self._build_main_worker(
            main_worker_id,
            main_worker_name,
            hard_inputs + demand_in,
            hard_outputs + demand_out,
        )

        child_workers, handoffs, rejected, materialized_decisions, decision_warnings = (
            self._materialize_accepted(
                decisions, candidates_by_id, hard_inputs, hard_outputs,
                span_order, main_worker, all_demand_ids,
                api_consumed_span_ids or set(),
            )
        )
        warnings.extend(decision_warnings)

        if existing_workers:
            child_workers, handoffs = self._merge_existing(
                child_workers, handoffs, existing_workers, existing_handoffs or [],
                candidates_by_id, warnings,
            )

        # D1 guard: reject child workers whose spans are all non-executable
        if non_exec_span_ids:
            kept_workers: list[WorkerSpecIR] = []
            kept_handoffs: list[WorkerHandoffIR] = []
            for i, child in enumerate(child_workers):
                owned = set(child.owned_span_ids)
                if owned and owned.issubset(non_exec_span_ids):
                    warnings.append(
                        f"D1 guard: rejecting child worker '{child.worker_id}': "
                        f"all owned spans {sorted(owned)} are non-executable "
                        f"(failure_mode / delegation_intent without contract)"
                    )
                    # Downgrade the matching accepted decision to rejected
                    candidate_id = self._find_candidate_id_for_spans(
                        owned, candidates_by_id,
                    )
                    if candidate_id:
                        for j, dec in enumerate(materialized_decisions):
                            if (
                                dec.candidate_id == candidate_id
                                and dec.decision == "extract_child_worker"
                            ):
                                materialized_decisions[j] = self._reject_decision(
                                    dec,
                                    "insufficient_semantic_boundary",
                                    "All source spans are non-executable "
                                    "(failure_mode / delegation_intent without contract).",
                                )
                                break
                    continue
                kept_workers.append(child)
                if i < len(handoffs):
                    kept_handoffs.append(handoffs[i])
            child_workers, handoffs = kept_workers, kept_handoffs

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
        all_demand_ids: set[str] | None = None,
        api_consumed_span_ids: set[str] | None = None,
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
        _ = all_demand_ids
        blocked_anchor_span_ids = self._blocked_handoff_anchor_spans(
            decisions,
            candidates_by_id,
        )
        api_consumed = set(api_consumed_span_ids or set())

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

            api_overlap = sorted(set(candidate.source_span_ids) & api_consumed)
            if api_overlap:
                warnings.append(
                    f"Candidate {candidate.candidate_id} accepted but consumes "
                    f"API-owned spans {api_overlap}; not materializing as child worker."
                )
                rejected_decision = self._reject_decision(
                    decision,
                    (
                        "single_api_call"
                        if set(candidate.source_span_ids).issubset(api_consumed)
                        else "insufficient_semantic_boundary"
                    ),
                    "Accepted candidate consumed confirmed API invocation spans.",
                )
                materialized_decisions.append(rejected_decision)
                continue

            worker = self._candidate_to_worker(candidate, decision, hard_inputs, hard_outputs)
            if worker is not None and not self._contract_fields_backed(
                worker, candidate, hard_inputs, hard_outputs,
            ):
                warnings.append(
                    f"Candidate {candidate.candidate_id} accepted but contract "
                    f"fields are not source-backed; rejecting."
                )
                rejected_decision = self._reject_decision(
                    decision,
                    "insufficient_semantic_boundary",
                    "Accepted candidate has invented (non-source-backed) contract fields.",
                )
                materialized_decisions.append(rejected_decision)
                continue

            if worker is None:
                # Attempt recovery from hard facts — only for candidates
                # that still have worker responsibility (contract-less
                # candidates are already handled by _candidate_to_worker
                # producing a partial worker; this path is for candidates
                # whose contracts weren't expressed by the LLM but exist
                # in adapter-provided hard facts).
                if self._has_worker_responsibility(candidate):
                    recovered = self._recover_from_hard_facts(
                        candidate, decision, hard_inputs, hard_outputs,
                    )
                else:
                    recovered = None
                if recovered is not None and self._contract_fields_backed(
                    recovered, candidate, hard_inputs, hard_outputs,
                ):
                    worker = recovered
                    warnings.append(
                        f"Candidate {candidate.candidate_id} recovered contract "
                        f"from adapter hard facts."
                    )
                else:
                    reason = self._missing_contract_reason(
                        candidate,
                        hard_inputs,
                        hard_outputs,
                    )
                    warnings.append(
                        f"Candidate {candidate.candidate_id} accepted but has "
                        f"insufficient worker responsibility evidence "
                        f"({reason}); not materializing as child worker."
                    )
                    rejected_decision = self._reject_decision(
                        decision,
                        reason,
                        "Accepted candidate did not provide a deterministic "
                        "worker contract.",
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

        main_worker.owned_span_ids = sorted(main_owned, key=_span_sort_key)
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
            or WorkerPlanMaterializer._match_hard_fact_contracts(candidate,hard_inputs)
        )
        has_outputs = bool(
            candidate.possible_outputs
            or WorkerPlanMaterializer._match_hard_fact_contracts(candidate,hard_outputs)
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
            evidence=[],
        )

    @staticmethod
    def _find_candidate_id_for_spans(
        span_ids: set[str],
        candidates_by_id: dict[str, CandidateTaskUnitIR],
    ) -> str | None:
        """Find the candidate whose source spans match *span_ids*."""
        for cid, candidate in candidates_by_id.items():
            if set(candidate.source_span_ids) == span_ids:
                return cid
        return None

    def _candidate_to_worker(
        self,
        candidate: CandidateTaskUnitIR,
        decision: WorkerBoundaryDecisionIR,
        hard_inputs: list[ContractFieldIR],
        hard_outputs: list[ContractFieldIR],
    ) -> WorkerSpecIR | None:
        """Build a WorkerSpecIR from candidate.

        Returns None only when the candidate lacks worker responsibility
        (no source spans, no task text / purpose, or non-worker boundary
        kind).  Missing contract is expressed via ``*_contract_status``
        fields rather than by rejecting the worker.
        """
        if not self._has_worker_responsibility(candidate):
            return None

        inputs = list(candidate.possible_inputs) if candidate.possible_inputs else []
        outputs = list(candidate.possible_outputs) if candidate.possible_outputs else []

        if not inputs:
            inputs = WorkerPlanMaterializer._match_hard_fact_contracts(candidate, hard_inputs)
        if not outputs:
            outputs = WorkerPlanMaterializer._match_hard_fact_contracts(candidate, hard_outputs)

        input_status = self._derive_contract_status(
            fields=inputs,
            candidate_status=getattr(candidate, "input_contract_status", "unknown"),
            source=getattr(candidate, "input_contract_status_source", None),
        )
        output_status = self._derive_contract_status(
            fields=outputs,
            candidate_status=getattr(candidate, "output_contract_status", "unknown"),
            source=getattr(candidate, "output_contract_status_source", None),
        )
        partial_reason = self._partial_contract_reason(input_status, output_status)

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
            input_contract_status=input_status,
            output_contract_status=output_status,
            partial_reason=partial_reason,
            boundary_kind=candidate.candidate_kind,
            decision_evidence=list(decision.evidence),
            reason=decision.reason,
        )

    def _recover_from_hard_facts(
        self,
        candidate: CandidateTaskUnitIR,
        decision: WorkerBoundaryDecisionIR,
        hard_inputs: list[ContractFieldIR],
        hard_outputs: list[ContractFieldIR],
    ) -> WorkerSpecIR | None:
        """Build a worker purely from hard facts when candidate IO is empty.

        Used when the IRS-compliant Stage 3.5a candidate has empty
        possible_inputs/possible_outputs but the adapter hard facts
        provide a complete contract.
        """
        matched_inputs = WorkerPlanMaterializer._match_hard_fact_contracts(candidate,hard_inputs)
        matched_outputs = WorkerPlanMaterializer._match_hard_fact_contracts(candidate,hard_outputs)
        if not matched_inputs or not matched_outputs:
            return None
        worker_id = self._worker_id_from_candidate(candidate.candidate_id)
        worker_name = self._worker_name_from_candidate(candidate)
        return WorkerSpecIR(
            worker_id=worker_id,
            worker_name=worker_name,
            kind="child",
            purpose=candidate.purpose or candidate.task_text,
            owned_span_ids=list(candidate.source_span_ids),
            input_contract=matched_inputs,
            output_contract=matched_outputs,
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

    @staticmethod
    def _contract_fields_backed(
        worker: WorkerSpecIR,
        candidate: CandidateTaskUnitIR,
        hard_inputs: list[ContractFieldIR],
        hard_outputs: list[ContractFieldIR],
    ) -> bool:
        """Return False only when non-empty contract fields are LLM-invented.

        Empty (unknown) fields are NOT treated as invented — contract
        incompleteness is handled via ``*_contract_status`` fields and
        IRS diagnostics, not by rejecting the worker.
        """
        hard_in_names: set[str] = {f.name for f in hard_inputs}
        hard_out_names: set[str] = {f.name for f in hard_outputs}

        if hard_inputs and worker.input_contract:
            if not all(f.name in hard_in_names for f in worker.input_contract):
                return False
        if hard_outputs and worker.output_contract:
            if not all(f.name in hard_out_names for f in worker.output_contract):
                return False
        return True

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
            InputBindingIR(
                f.name, f.name,
                f.required is not False,  # B1: None → True for handoff safety
            )
            for f in worker.input_contract
        ]
        output_bindings = [
            OutputBindingIR(
                f.name, f.name,
                f.required is not False,  # B1: None → True for handoff safety
                "set",
            )
            for f in worker.output_contract
        ]

        input_binding_status = (
            "known_present"
            if input_bindings
            else "known_empty"
            if worker.input_contract_status == "known_empty"
            else "unknown"
        )
        output_binding_status = (
            "known_present"
            if output_bindings
            else "known_empty"
            if worker.output_contract_status == "known_empty"
            else "unknown"
        )
        input_binding_status_source = (
            worker.input_contract_status_source
            if input_binding_status == "known_empty"
            else None
        )
        output_binding_status_source = (
            worker.output_contract_status_source
            if output_binding_status == "known_empty"
            else None
        )
        materialization_status = derive_handoff_materialization_status(
            input_bindings=input_bindings,
            output_bindings=output_bindings,
            input_status=input_binding_status,
            output_status=output_binding_status,
        )

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
            input_binding_status=input_binding_status,
            output_binding_status=output_binding_status,
            input_binding_status_source=input_binding_status_source,
            output_binding_status_source=output_binding_status_source,
            materialization_status=materialization_status,
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
                    sorted(unassigned, key=_span_sort_key)
                )

    # ---- Worker responsibility ---------------------------------------

    _WORKER_LIKE_KINDS: set[str] = {
        "explicit_delegation", "bounded_subtask",
        "integration_wrapper", "template_or_format_protocol",
    }

    @staticmethod
    def _has_worker_responsibility(candidate: CandidateTaskUnitIR) -> bool:
        return bool(
            candidate.source_span_ids
            and (candidate.task_text or candidate.purpose)
            and candidate.candidate_kind in WorkerPlanMaterializer._WORKER_LIKE_KINDS
        )

    @staticmethod
    def _derive_contract_status(
        *,
        fields: list[ContractFieldIR],
        candidate_status: str,
        source: str | None,
    ) -> str:
        from nl2spl.ir.worker_contract_status import derive_contract_status

        if fields:
            return "known_present"
        # Only pass declared_status for explicit declarations; "unknown"
        # is the normal partial-worker default and should be quiet.
        declared: str | None = None
        if candidate_status in {"known_present", "known_empty"}:
            declared = candidate_status
        return derive_contract_status(
            [], declared_status=declared, source=source,
        )

    @staticmethod
    def _partial_contract_reason(
        input_status: str, output_status: str,
    ) -> str | None:
        if input_status == "unknown" and output_status == "unknown":
            return "missing_input_and_output_contract"
        if input_status == "unknown":
            return "missing_input_contract"
        if output_status == "unknown":
            return "missing_output_contract"
        return None

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
