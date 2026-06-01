"""IRS v6 Worker/Delegation Checker — first v6-style checker implementation.

R4 implementation:
    - Extracts WORKER_CANDIDATE, WORKER_PROMOTION, CHILD_WORKER, WORKER_HANDOFF instances
    - Checks satisfaction based on structured IR fields only
    - Does not call LLM or parse raw NL
    - Does not modify WorkerPlanIR
    - Does not generate new workers or handoffs
    - Uses diagnostic_kind for missing slots
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import (
    ConstructIRS,
    ConstructSatisfactionReport,
    SlotSatisfaction,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.graph import ConstructEdge, ConstructEdgeType
from nl2spl.compiler.irs.instance import ConstructInstance


class WorkerDelegationIRSChecker:
    """IRS v6 checker for worker/delegation constructs.
    
    Supported constructs:
        - WORKER_CANDIDATE: Identified task boundary candidates
        - WORKER_PROMOTION: Promotion readiness assessment
        - CHILD_WORKER: Materialized child workers
        - WORKER_HANDOFF: Materialized worker handoffs
    
    Design principles:
        - Only consumes structured IR fields
        - Does not infer semantics from text
        - Does not modify context or IR
        - Does not generate new constructs
        - Uses diagnostic_kind for missing slots
    """
    
    checker_id = "worker_delegation"
    supported_construct_types = (
        "WORKER_CANDIDATE",
        "WORKER_PROMOTION",
        "CHILD_WORKER",
        "WORKER_HANDOFF",
    )
    supported_stages = ("stage3_5", "stage3_5_worker_boundary")
    
    def extract_instances(self, context: IRSCheckContext) -> list[ConstructInstance]:
        """Extract worker/delegation construct instances from context.
        
        Args:
            context: Pipeline context with worker_plan
        
        Returns:
            List of construct instances to check
        """
        instances: list[ConstructInstance] = []
        
        # No worker_plan means no instances
        if context.worker_plan is None:
            return instances
        
        worker_plan = context.worker_plan
        
        # Extract WORKER_CANDIDATE and WORKER_PROMOTION from candidates
        # Only process worker/delegation boundary candidates, not constraint/exception/alternative/api_call
        worker_candidate_kinds = {
            "explicit_delegation",
            "bounded_subtask",
            "integration_wrapper",
            "complex_control_extraction",
            "loop_body_worker",
            "failure_recovery_protocol",
            "template_or_format_protocol",
        }
        
        for candidate in worker_plan.candidates:
            # Skip non-worker candidates
            if candidate.candidate_kind not in worker_candidate_kinds:
                continue
            
            # WORKER_CANDIDATE instance
            candidate_instance = ConstructInstance(
                construct_id=f"worker_candidate:{candidate.candidate_id}",
                construct_type="WORKER_CANDIDATE",
                materialized=False,
                source_demanded=True,
                candidate_only=True,
                ir_ref=candidate,
                source_span_ids=list(candidate.source_span_ids),
                construct_path=("worker_plan", "candidates", candidate.candidate_id),
                metadata={"candidate_ir": candidate},
            )
            instances.append(candidate_instance)
            
            # WORKER_PROMOTION instance
            promotion_instance = ConstructInstance(
                construct_id=f"worker_promotion:{candidate.candidate_id}",
                construct_type="WORKER_PROMOTION",
                materialized=False,
                source_demanded=True,
                candidate_only=True,
                ir_ref=candidate,
                source_span_ids=list(candidate.source_span_ids),
                construct_path=("worker_plan", "promotion", candidate.candidate_id),
                metadata={"candidate_ir": candidate},
            )
            instances.append(promotion_instance)
        
        # Extract CHILD_WORKER from materialized workers
        for worker in worker_plan.workers:
            if worker.kind in {"child", "api_adapter"}:
                worker_instance = ConstructInstance(
                    construct_id=f"child_worker:{worker.worker_id}",
                    construct_type="CHILD_WORKER",
                    materialized=True,
                    source_demanded=True,
                    candidate_only=False,
                    ir_ref=worker,
                    source_span_ids=list(worker.owned_span_ids),
                    construct_path=("worker_plan", "workers", worker.worker_id),
                    metadata={"worker_ir": worker},
                )
                instances.append(worker_instance)
        
        # Extract WORKER_HANDOFF from handoffs
        for handoff in worker_plan.handoffs:
            # Collect source spans from invoke_location_hint if available
            handoff_source_spans = []
            if handoff.invoke_location_hint:
                if handoff.invoke_location_hint.after_span_id:
                    handoff_source_spans.append(handoff.invoke_location_hint.after_span_id)
                if handoff.invoke_location_hint.before_span_id:
                    handoff_source_spans.append(handoff.invoke_location_hint.before_span_id)
            
            handoff_instance = ConstructInstance(
                construct_id=f"worker_handoff:{handoff.handoff_id}",
                construct_type="WORKER_HANDOFF",
                materialized=True,
                source_demanded=True,
                candidate_only=False,
                ir_ref=handoff,
                source_span_ids=handoff_source_spans,
                construct_path=("worker_plan", "handoffs", handoff.handoff_id),
                metadata={"handoff_ir": handoff},
            )
            instances.append(handoff_instance)
        
        return instances
    
    def check_instance(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Check IRS satisfaction for a construct instance.
        
        Args:
            instance: Construct instance to check
            irs: Information requirements spec
            context: Pipeline context (for cross-construct queries)
        
        Returns:
            Satisfaction report with slot-level evidence
        """
        if instance.construct_type == "WORKER_CANDIDATE":
            return self._check_worker_candidate(instance, irs, context)
        elif instance.construct_type == "WORKER_PROMOTION":
            return self._check_worker_promotion(instance, irs, context)
        elif instance.construct_type == "CHILD_WORKER":
            return self._check_child_worker(instance, irs, context)
        elif instance.construct_type == "WORKER_HANDOFF":
            return self._check_worker_handoff(instance, irs, context)
        else:
            raise ValueError(f"Unsupported construct type: {instance.construct_type}")
    
    def _matching_handoffs_for_candidate(self, candidate, worker_plan):
        """Find handoffs that structurally match the given candidate.
        
        Matching criteria (in order of preference):
        1. Handoff invoke hint spans overlap with candidate source spans
        2. Handoff target worker owned spans overlap with candidate source spans
        3. Unambiguous fallback: single accepted candidate + single invoke handoff
        
        All matching handoffs must have valid targets (existing worker or valid API ref).
        
        Args:
            candidate: CandidateTaskUnitIR
            worker_plan: WorkerPlanIR
        
        Returns:
            List of matching WorkerHandoffIR with valid targets
        """
        if not worker_plan:
            return []
        
        matching = []
        candidate_spans = set(candidate.source_span_ids)
        
        for handoff in worker_plan.handoffs:
            if handoff.mode != "invoke":
                continue
            
            # Skip handoffs without valid targets
            if not self._handoff_has_valid_target(handoff, worker_plan):
                continue
            
            # Check invoke hint span overlap
            if handoff.invoke_location_hint:
                hint_spans = set()
                if handoff.invoke_location_hint.after_span_id:
                    hint_spans.add(handoff.invoke_location_hint.after_span_id)
                if handoff.invoke_location_hint.before_span_id:
                    hint_spans.add(handoff.invoke_location_hint.before_span_id)
                
                if hint_spans & candidate_spans:
                    matching.append(handoff)
                    continue
            
            # Check target worker owned spans overlap
            if handoff.to_worker:
                target_worker = next(
                    (w for w in worker_plan.workers if w.worker_id == handoff.to_worker),
                    None
                )
                if target_worker:
                    worker_spans = set(target_worker.owned_span_ids)
                    if worker_spans & candidate_spans:
                        matching.append(handoff)
                        continue
        
        # Unambiguous fallback: single accepted candidate + single invoke handoff with valid target
        if not matching:
            accepted_candidates = [
                d.candidate_id for d in worker_plan.decisions
                if d.decision == "extract_child_worker"
            ]
            invoke_handoffs = [
                h for h in worker_plan.handoffs 
                if h.mode == "invoke" and self._handoff_has_valid_target(h, worker_plan)
            ]
            
            if (len(accepted_candidates) == 1 
                and accepted_candidates[0] == candidate.candidate_id
                and len(invoke_handoffs) == 1):
                matching.append(invoke_handoffs[0])
        
        return matching
    
    def _handoff_has_valid_target(self, handoff, worker_plan):
        """Check if handoff has a valid target.
        
        Args:
            handoff: WorkerHandoffIR
            worker_plan: WorkerPlanIR
        
        Returns:
            bool: True if target is valid
        """
        if handoff.mode == "invoke":
            # For invoke mode, to_worker must exist in worker_plan.workers
            if not handoff.to_worker:
                return False
            return any(
                w.worker_id == handoff.to_worker
                for w in worker_plan.workers
            )
        elif handoff.mode == "api_call":
            # For api_call mode, api_ref must be non-empty
            return bool(handoff.api_ref)
        return False
    
    def _check_worker_candidate(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Check WORKER_CANDIDATE satisfaction.
        
        A candidate is complete when:
            - responsibility: purpose or task_text is non-empty
            - delegation_signal: signals non-empty or candidate_kind != "not_a_worker"
            - source_evidence: source_span_ids non-empty
        """
        candidate = instance.metadata["candidate_ir"]
        slots: list[SlotSatisfaction] = []
        
        # Check responsibility
        responsibility_satisfied = bool(candidate.purpose or candidate.task_text)
        slots.append(SlotSatisfaction(
            slot_name="responsibility",
            status="satisfied" if responsibility_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if responsibility_satisfied else None,
        ))
        
        # Check delegation_signal
        delegation_signal_satisfied = bool(
            candidate.signals or candidate.candidate_kind != "not_a_worker"
        )
        slots.append(SlotSatisfaction(
            slot_name="delegation_signal",
            status="satisfied" if delegation_signal_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if delegation_signal_satisfied else None,
        ))
        
        # Check source_evidence
        source_evidence_satisfied = bool(candidate.source_span_ids)
        slots.append(SlotSatisfaction(
            slot_name="source_evidence",
            status="satisfied" if source_evidence_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if source_evidence_satisfied else None,
        ))
        
        # Determine completeness
        all_satisfied = all(s.status == "satisfied" for s in slots)
        completeness = "complete" if all_satisfied else "partial"
        
        # WORKER_CANDIDATE is not renderable (analysis construct)
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=slots,
            completeness=completeness,
            renderable=False,
            source_span_ids=list(candidate.source_span_ids),
            construct_path=instance.construct_path,
            frontier_status="leaf",
            metadata={
                "candidate_id": candidate.candidate_id,
                "candidate_kind": candidate.candidate_kind,
                "candidate_status": "identified",
            },
        )
    
    def _check_worker_promotion(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Check WORKER_PROMOTION satisfaction.
        
        Promotion is ready when all slots are satisfied:
            - promotion_input_contract: possible_inputs non-empty, no no_clear_input_contract risk
            - promotion_output_contract: possible_outputs non-empty, no no_clear_output_contract risk
            - promotion_invocation_point: no no_parent_invocation_point risk, has handoff evidence
            - promotion_result_handoff: no unclear_result_handoff risk, has handoff with output_bindings
        """
        candidate = instance.metadata["candidate_ir"]
        slots: list[SlotSatisfaction] = []
        missing_slot_names: list[str] = []
        
        # Check promotion_input_contract
        input_contract_satisfied = (
            bool(candidate.possible_inputs)
            and "no_clear_input_contract" not in candidate.risks
        )
        slot_spec = irs.get_slot("promotion_input_contract")
        slots.append(SlotSatisfaction(
            slot_name="promotion_input_contract",
            status="satisfied" if input_contract_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if input_contract_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not input_contract_satisfied else None,
            explanation=(
                "Input contract satisfied" if input_contract_satisfied
                else "Missing clear input contract"
            ),
        ))
        if not input_contract_satisfied:
            missing_slot_names.append("promotion_input_contract")
        
        # Check promotion_output_contract
        output_contract_satisfied = (
            bool(candidate.possible_outputs)
            and "no_clear_output_contract" not in candidate.risks
        )
        slot_spec = irs.get_slot("promotion_output_contract")
        slots.append(SlotSatisfaction(
            slot_name="promotion_output_contract",
            status="satisfied" if output_contract_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if output_contract_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not output_contract_satisfied else None,
            explanation=(
                "Output contract satisfied" if output_contract_satisfied
                else "Missing clear output contract"
            ),
        ))
        if not output_contract_satisfied:
            missing_slot_names.append("promotion_output_contract")
        
        # Check promotion_invocation_point
        # Requires: accepted decision + matching handoff with invoke hint
        invocation_point_satisfied = False
        if context.worker_plan:
            # Check for accepted extract_child_worker decision
            has_accepted_decision = any(
                d.candidate_id == candidate.candidate_id
                and d.decision == "extract_child_worker"
                for d in context.worker_plan.decisions
            )
            # Check for matching handoff with invocation hint
            # Must have real invoke_location_hint with structural fields
            matching_handoffs = self._matching_handoffs_for_candidate(candidate, context.worker_plan)
            has_handoff_with_hint = any(
                h.invoke_location_hint
                and (
                    h.invoke_location_hint.after_span_id
                    or h.invoke_location_hint.before_span_id
                    or h.invoke_location_hint.block_hint != "unknown"
                )
                for h in matching_handoffs
            )
            invocation_point_satisfied = has_accepted_decision and has_handoff_with_hint
        
        slot_spec = irs.get_slot("promotion_invocation_point")
        slots.append(SlotSatisfaction(
            slot_name="promotion_invocation_point",
            status="satisfied" if invocation_point_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if invocation_point_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not invocation_point_satisfied else None,
            explanation=(
                "Invocation point identified with accepted decision and matching handoff with invoke hint"
                if invocation_point_satisfied
                else "Missing accepted decision or matching handoff with invocation hint"
            ),
        ))
        if not invocation_point_satisfied:
            missing_slot_names.append("promotion_invocation_point")
        
        # Check promotion_result_handoff
        # Requires: matching handoff with non-empty output_bindings
        result_handoff_satisfied = False
        if context.worker_plan:
            matching_handoffs = self._matching_handoffs_for_candidate(candidate, context.worker_plan)
            result_handoff_satisfied = any(
                h.output_bindings
                for h in matching_handoffs
            )
        
        slot_spec = irs.get_slot("promotion_result_handoff")
        slots.append(SlotSatisfaction(
            slot_name="promotion_result_handoff",
            status="satisfied" if result_handoff_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if result_handoff_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not result_handoff_satisfied else None,
            explanation=(
                "Result handoff with output bindings found"
                if result_handoff_satisfied
                else "Missing matching handoff with output bindings"
            ),
        ))
        if not result_handoff_satisfied:
            missing_slot_names.append("promotion_result_handoff")
        
        # Determine completeness and promotion status
        all_satisfied = all(s.status == "satisfied" for s in slots)
        completeness = "complete" if all_satisfied else "partial"
        promotion_status = "ready" if all_satisfied else "blocked"
        
        # Build related edges (candidate -> promotion)
        related_edges = [
            ConstructEdge(
                from_id=f"worker_candidate:{candidate.candidate_id}",
                to_id=instance.construct_id,
                edge_type="promotes_to",
            )
        ]
        
        # WORKER_PROMOTION is not renderable (analysis construct)
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=slots,
            completeness=completeness,
            renderable=False,
            source_span_ids=list(candidate.source_span_ids),
            construct_path=instance.construct_path,
            frontier_status="cutline_partial" if not all_satisfied else "leaf",
            cutline_reason="promotion_blocked" if not all_satisfied else None,
            related_edges=related_edges,
            metadata={
                "promotion_status": promotion_status,
                "promotion_candidate_id": candidate.candidate_id,
                "promotion_missing_slots": missing_slot_names,
            },
        )
    
    def _check_child_worker(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Check CHILD_WORKER satisfaction.
        
        A child worker is complete when:
            - responsibility: purpose is non-empty
            - input_contract: input_contract is non-empty
            - output_contract: output_contract is non-empty
            - invocation_point: exists handoff from main/parent to this worker
            - result_handoff: matching handoff has output_bindings
        """
        worker = instance.metadata["worker_ir"]
        slots: list[SlotSatisfaction] = []
        
        # Check responsibility
        responsibility_satisfied = bool(worker.purpose)
        slots.append(SlotSatisfaction(
            slot_name="responsibility",
            status="satisfied" if responsibility_satisfied else "missing",
            source_span_ids=list(worker.owned_span_ids),
            relation="direct" if responsibility_satisfied else None,
        ))
        
        # Check input_contract
        input_contract_satisfied = bool(worker.input_contract)
        slot_spec = irs.get_slot("input_contract")
        slots.append(SlotSatisfaction(
            slot_name="input_contract",
            status="satisfied" if input_contract_satisfied else "missing",
            source_span_ids=list(worker.owned_span_ids),
            relation="direct" if input_contract_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not input_contract_satisfied else None,
        ))
        
        # Check output_contract
        output_contract_satisfied = bool(worker.output_contract)
        slot_spec = irs.get_slot("output_contract")
        slots.append(SlotSatisfaction(
            slot_name="output_contract",
            status="satisfied" if output_contract_satisfied else "missing",
            source_span_ids=list(worker.owned_span_ids),
            relation="direct" if output_contract_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not output_contract_satisfied else None,
        ))
        
        # Check invocation_point and result_handoff by looking for handoffs
        worker_plan = context.worker_plan
        invocation_point_satisfied = False
        result_handoff_satisfied = False
        
        if worker_plan:
            for handoff in worker_plan.handoffs:
                if handoff.mode == "invoke" and handoff.to_worker == worker.worker_id:
                    invocation_point_satisfied = True
                    if handoff.output_bindings:
                        result_handoff_satisfied = True
        
        slot_spec = irs.get_slot("invocation_point")
        slots.append(SlotSatisfaction(
            slot_name="invocation_point",
            status="satisfied" if invocation_point_satisfied else "missing",
            source_span_ids=list(worker.owned_span_ids),
            relation="direct" if invocation_point_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not invocation_point_satisfied else None,
        ))
        
        slot_spec = irs.get_slot("result_handoff")
        slots.append(SlotSatisfaction(
            slot_name="result_handoff",
            status="satisfied" if result_handoff_satisfied else "missing",
            source_span_ids=list(worker.owned_span_ids),
            relation="direct" if result_handoff_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not result_handoff_satisfied else None,
        ))
        
        # Determine completeness
        all_satisfied = all(s.status == "satisfied" for s in slots)
        completeness = "complete" if all_satisfied else "partial"
        
        # CHILD_WORKER report does not determine final renderability
        # That's the responsibility of Gate/ProducerIndex
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=slots,
            completeness=completeness,
            renderable=all_satisfied,
            source_span_ids=list(worker.owned_span_ids),
            construct_path=instance.construct_path,
            frontier_status="leaf",
            metadata={
                "worker_id": worker.worker_id,
                "worker_kind": worker.kind,
            },
        )
    
    def _check_worker_handoff(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Check WORKER_HANDOFF satisfaction.
        
        A handoff is complete when:
            - from_worker: from_worker is non-empty and exists in worker_plan
            - target: to_worker (invoke mode) or api_ref (api_call mode) is non-empty
            - input_bindings: input_bindings is non-empty
            - output_bindings: output_bindings is non-empty
            - invocation_site: invoke_location_hint has structural fields
        """
        handoff = instance.metadata["handoff_ir"]
        slots: list[SlotSatisfaction] = []
        
        # Check from_worker
        from_worker_satisfied = False
        handoff_source_spans = list(instance.source_span_ids) if instance.source_span_ids else []
        if handoff.from_worker and context.worker_plan:
            from_worker_satisfied = any(
                w.worker_id == handoff.from_worker
                for w in context.worker_plan.workers
            )
        slot_spec = irs.get_slot("from_worker")
        slots.append(SlotSatisfaction(
            slot_name="from_worker",
            status="satisfied" if from_worker_satisfied else "missing",
            source_span_ids=handoff_source_spans,
            relation="direct" if from_worker_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not from_worker_satisfied else None,
        ))
        
        # Check target
        target_satisfied = False
        if handoff.mode == "invoke":
            # For invoke mode, to_worker must exist in worker_plan
            if handoff.to_worker and context.worker_plan:
                target_satisfied = any(
                    w.worker_id == handoff.to_worker
                    for w in context.worker_plan.workers
                )
        elif handoff.mode == "api_call":
            target_satisfied = bool(handoff.api_ref)
        slot_spec = irs.get_slot("target")
        slots.append(SlotSatisfaction(
            slot_name="target",
            status="satisfied" if target_satisfied else "missing",
            source_span_ids=handoff_source_spans,
            relation="direct" if target_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not target_satisfied else None,
        ))
        
        # Check input_bindings
        input_bindings_satisfied = bool(handoff.input_bindings)
        slot_spec = irs.get_slot("input_bindings")
        slots.append(SlotSatisfaction(
            slot_name="input_bindings",
            status="satisfied" if input_bindings_satisfied else "missing",
            source_span_ids=handoff_source_spans,
            relation="direct" if input_bindings_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not input_bindings_satisfied else None,
        ))
        
        # Check output_bindings
        output_bindings_satisfied = bool(handoff.output_bindings)
        slot_spec = irs.get_slot("output_bindings")
        slots.append(SlotSatisfaction(
            slot_name="output_bindings",
            status="satisfied" if output_bindings_satisfied else "missing",
            source_span_ids=handoff_source_spans,
            relation="direct" if output_bindings_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not output_bindings_satisfied else None,
        ))
        
        # Check invocation_site
        # Only use invoke_location_hint structural fields or condition_text
        # Do NOT use ordering (required Literal) as evidence
        invocation_site_satisfied = False
        if handoff.invoke_location_hint:
            hint = handoff.invoke_location_hint
            invocation_site_satisfied = bool(
                hint.after_span_id
                or hint.before_span_id
                or hint.block_hint != "unknown"
            )
        # Also check condition_text (but not ordering)
        if not invocation_site_satisfied:
            invocation_site_satisfied = bool(handoff.condition_text)
        slot_spec = irs.get_slot("invocation_site")
        slots.append(SlotSatisfaction(
            slot_name="invocation_site",
            status="satisfied" if invocation_site_satisfied else "missing",
            source_span_ids=handoff_source_spans,
            relation="direct" if invocation_site_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not invocation_site_satisfied else None,
        ))
        
        # Determine completeness
        all_satisfied = all(s.status == "satisfied" for s in slots)
        completeness = "complete" if all_satisfied else "partial"
        
        # Build related edges (handoff -> target worker)
        # Only add edge if target is valid
        related_edges: list[ConstructEdge] = []
        if target_satisfied and handoff.mode == "invoke" and handoff.to_worker:
            related_edges.append(ConstructEdge(
                from_id=instance.construct_id,
                to_id=f"child_worker:{handoff.to_worker}",
                edge_type="invokes",
            ))
        
        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=slots,
            completeness=completeness,
            renderable=False,  # Handoff is not a renderable SPL construct
            source_span_ids=handoff_source_spans,
            construct_path=instance.construct_path,
            frontier_status="leaf",
            related_edges=related_edges,
            metadata={
                "handoff_id": handoff.handoff_id,
                "handoff_mode": handoff.mode,
                "from_worker": handoff.from_worker,
                "to_worker": handoff.to_worker if handoff.mode == "invoke" else None,
                "api_ref": handoff.api_ref if handoff.mode == "api_call" else None,
            },
        )
