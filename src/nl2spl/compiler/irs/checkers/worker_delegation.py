"""IRS v6 Worker/Delegation Checker — first v6-style checker implementation.

R4 implementation:
    - Extracts WORKER_CANDIDATE, WORKER_PROMOTION, CHILD_WORKER, WORKER_HANDOFF instances
    - Checks satisfaction based on structured IR fields only
    - Does not call LLM or parse raw NL
    - Does not modify WorkerPlanIR
    - Does not generate new workers or handoffs
    - Uses diagnostic_kind for missing slots

R10 Phase 1:
    - DELEGATION_INTENT removed as IRS construct; delegation_intent annotations
      are evidence routed into WORKER_CANDIDATE / WORKER_PROMOTION instead.
    - Annotations not covered by any candidate produce synthetic candidate-only
      WORKER_CANDIDATE / WORKER_PROMOTION instances flagged with
      metadata.synthetic_from_route_annotation=True.
"""

from __future__ import annotations

from nl2spl.compiler.construct_registry import (
    ConstructIRS,
    ConstructSatisfactionReport,
    SlotSatisfaction,
)
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.graph import ConstructEdge
from nl2spl.compiler.irs.instance import ConstructInstance
from nl2spl.ir.worker_contract_status import (
    binding_side_satisfied,
    contract_side_satisfied,
)


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

        worker_plan = context.worker_plan

        # Collect delegation_intent route annotations as evidence.
        # They are NOT registered as DELEGATION_INTENT construct instances.
        # Instead, they are routed into WORKER_CANDIDATE / WORKER_PROMOTION.
        delegation_annotations: list = []
        if context.routes is not None:
            delegation_annotations = context.routes.get_annotations_by_role(
                "delegation_intent"
            )
        delegation_span_ids = {ann.span_id for ann in delegation_annotations}
        # Track which delegation spans have been covered by existing candidates
        covered_delegation_spans: set[str] = set()

        # ------------------------------------------------------------------
        # Extract WORKER_CANDIDATE / WORKER_PROMOTION from WorkerPlanIR
        # candidates.  Delegation-intent route annotations that overlap with
        # a candidate's source spans are attached as evidence.
        # ------------------------------------------------------------------
        if worker_plan is not None:
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
                if candidate.candidate_kind not in worker_candidate_kinds:
                    continue

                # Merge delegation annotation spans into source_span_ids
                candidate_spans = list(candidate.source_span_ids)
                delegation_hits = delegation_span_ids & set(candidate_spans)
                covered_delegation_spans |= delegation_hits

                candidate_metadata: dict = {"candidate_ir": candidate}
                promotion_metadata: dict = {"candidate_ir": candidate}

                # Attach delegation evidence when annotations overlap.
                # Only merge the spans that actually hit this candidate,
                # not every delegation annotation span in the system.
                if delegation_hits:
                    candidate_spans = list(
                        set(candidate_spans) | delegation_hits
                    )
                    delegation_meta = {
                        "original_semantic_role": "delegation_intent",
                        "original_route_annotation_ids": sorted(delegation_hits),
                        "original_source_span_ids": sorted(delegation_hits),
                    }
                    candidate_metadata.update(delegation_meta)
                    promotion_metadata.update(delegation_meta)

                instances.append(ConstructInstance(
                    construct_id=f"worker_candidate:{candidate.candidate_id}",
                    construct_type="WORKER_CANDIDATE",
                    materialized=False,
                    source_demanded=True,
                    candidate_only=True,
                    ir_ref=candidate,
                    source_span_ids=candidate_spans,
                    construct_path=("worker_plan", "candidates", candidate.candidate_id),
                    metadata=candidate_metadata,
                ))

                instances.append(ConstructInstance(
                    construct_id=f"worker_promotion:{candidate.candidate_id}",
                    construct_type="WORKER_PROMOTION",
                    materialized=False,
                    source_demanded=True,
                    candidate_only=True,
                    ir_ref=candidate,
                    source_span_ids=candidate_spans,
                    construct_path=("worker_plan", "promotion", candidate.candidate_id),
                    metadata=promotion_metadata,
                ))

        # ------------------------------------------------------------------
        # Synthetic WORKER_CANDIDATE / WORKER_PROMOTION for delegation_intent
        # annotations not covered by any WorkerPlanIR candidate.
        # These are candidate-only analysis instances flagged with
        # metadata.synthetic_from_route_annotation=True.
        # ------------------------------------------------------------------
        uncovered_spans = delegation_span_ids - covered_delegation_spans
        if uncovered_spans:
            from nl2spl.ir.worker_plan_ir import CandidateTaskUnitIR

            for ann in delegation_annotations:
                if ann.span_id not in uncovered_spans:
                    continue

                synthetic_id = f"del_{ann.span_id}"
                synthetic_candidate = CandidateTaskUnitIR(
                    candidate_id=synthetic_id,
                    source_span_ids=[ann.span_id],
                    task_text="",
                    purpose="",
                    candidate_kind="explicit_delegation",
                    possible_inputs=[],
                    possible_outputs=[],
                    signals=["delegation"],
                    risks=[
                        "no_clear_input_contract",
                        "no_clear_output_contract",
                    ],
                )
                synthetic_metadata = {
                    "candidate_ir": synthetic_candidate,
                    "synthetic_from_route_annotation": True,
                    "original_semantic_role": "delegation_intent",
                    "original_route_annotation_id": ann.span_id,
                    "original_source_span_ids": [ann.span_id],
                    "annotation": ann,
                }

                instances.append(ConstructInstance(
                    construct_id=f"worker_candidate:{synthetic_id}",
                    construct_type="WORKER_CANDIDATE",
                    materialized=False,
                    source_demanded=True,
                    candidate_only=True,
                    ir_ref=synthetic_candidate,
                    source_span_ids=[ann.span_id],
                    construct_path=("routes", "annotations", ann.span_id),
                    metadata=dict(synthetic_metadata),
                ))
                instances.append(ConstructInstance(
                    construct_id=f"worker_promotion:{synthetic_id}",
                    construct_type="WORKER_PROMOTION",
                    materialized=False,
                    source_demanded=True,
                    candidate_only=True,
                    ir_ref=synthetic_candidate,
                    source_span_ids=[ann.span_id],
                    construct_path=("routes", "annotations", ann.span_id),
                    metadata=dict(synthetic_metadata),
                ))

        # Extract CHILD_WORKER from materialized workers and
        # WORKER_HANDOFF from handoffs. Both require WorkerPlanIR.
        if worker_plan is not None:
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
            if not handoff.to_worker:
                return False
            return any(
                w.worker_id == handoff.to_worker
                for w in worker_plan.workers
            )
        elif handoff.mode == "api_call":
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
        report_metadata: dict = {
            "candidate_id": candidate.candidate_id,
            "candidate_kind": candidate.candidate_kind,
            "candidate_status": "identified",
        }
        for key in (
            "original_semantic_role",
            "original_route_annotation_id",
            "original_route_annotation_ids",
            "original_source_span_ids",
            "synthetic_from_route_annotation",
        ):
            if key in instance.metadata:
                report_metadata[key] = instance.metadata[key]

        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=slots,
            completeness=completeness,
            renderable=False,
            source_span_ids=list(candidate.source_span_ids),
            construct_path=instance.construct_path,
            frontier_status="leaf",
            metadata=report_metadata,
        )

    @staticmethod
    def _promotion_contract_side_satisfied(
        *,
        fields: list,
        status: str,
        risks: list[str],
        missing_risk: str,
    ) -> bool:
        if status == "known_empty":
            return True
        return contract_side_satisfied(fields, status) and missing_risk not in risks

    def _check_worker_promotion(
        self,
        instance: ConstructInstance,
        irs: ConstructIRS,
        context: IRSCheckContext,
    ) -> ConstructSatisfactionReport:
        """Check WORKER_PROMOTION satisfaction.

        Promotion is ready when all slots are satisfied:
            - promotion_input_contract: possible_inputs or known_empty.
            - promotion_output_contract: possible_outputs or known_empty.
            - promotion_invocation_point: accepted decision and handoff evidence.
            - promotion_result_handoff: output bindings or known_empty.
        """
        candidate = instance.metadata["candidate_ir"]
        slots: list[SlotSatisfaction] = []
        missing_slot_names: list[str] = []

        # Check promotion_input_contract
        input_contract_satisfied = self._promotion_contract_side_satisfied(
            fields=candidate.possible_inputs,
            status=candidate.input_contract_status,
            risks=candidate.risks,
            missing_risk="no_clear_input_contract",
        )
        slot_spec = irs.get_slot("promotion_input_contract")
        slots.append(SlotSatisfaction(
            slot_name="promotion_input_contract",
            status="satisfied" if input_contract_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if input_contract_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not input_contract_satisfied else None,
            diagnostic_blocks_rendering=False,
            explanation=(
                "Input contract satisfied" if input_contract_satisfied
                else "Missing clear input contract"
            ),
        ))
        if not input_contract_satisfied:
            missing_slot_names.append("promotion_input_contract")

        # Check promotion_output_contract
        output_contract_satisfied = self._promotion_contract_side_satisfied(
            fields=candidate.possible_outputs,
            status=candidate.output_contract_status,
            risks=candidate.risks,
            missing_risk="no_clear_output_contract",
        )
        slot_spec = irs.get_slot("promotion_output_contract")
        slots.append(SlotSatisfaction(
            slot_name="promotion_output_contract",
            status="satisfied" if output_contract_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if output_contract_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not output_contract_satisfied else None,
            diagnostic_blocks_rendering=False,
            explanation=(
                "Output contract satisfied" if output_contract_satisfied
                else "Missing clear output contract"
            ),
        ))
        if not output_contract_satisfied:
            missing_slot_names.append("promotion_output_contract")

        # Check promotion_invocation_point
        # Requires: accepted decision (or synthetic delegation) + matching
        # handoff with invoke hint.
        is_synthetic = instance.metadata.get("synthetic_from_route_annotation", False)
        invocation_point_satisfied = False
        if context.worker_plan:
            # Check for accepted extract_child_worker decision.
            # Synthetic instances (from bare delegation annotations) skip
            # the decision requirement — the handoff match is sufficient.
            has_accepted_decision = any(
                d.candidate_id == candidate.candidate_id
                and d.decision == "extract_child_worker"
                for d in context.worker_plan.decisions
            )
            # Check for matching handoff with invocation hint
            # Must have real invoke_location_hint with structural fields
            matching_handoffs = self._matching_handoffs_for_candidate(
                candidate,
                context.worker_plan,
            )
            has_handoff_with_hint = any(
                h.invoke_location_hint
                and (
                    h.invoke_location_hint.after_span_id
                    or h.invoke_location_hint.before_span_id
                    or h.invoke_location_hint.block_hint != "unknown"
                )
                for h in matching_handoffs
            )
            invocation_point_satisfied = (
                has_accepted_decision or is_synthetic
            ) and has_handoff_with_hint

        slot_spec = irs.get_slot("promotion_invocation_point")
        slots.append(SlotSatisfaction(
            slot_name="promotion_invocation_point",
            status="satisfied" if invocation_point_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if invocation_point_satisfied else None,
            diagnostic_kind=(
                slot_spec.missing_diagnostic
                if not invocation_point_satisfied
                else None
            ),
            diagnostic_blocks_rendering=False,
            explanation=(
                "Invocation point identified with accepted decision and "
                "matching handoff with invoke hint"
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
            matching_handoffs = self._matching_handoffs_for_candidate(
                candidate,
                context.worker_plan,
            )
            result_handoff_satisfied = any(
                binding_side_satisfied(
                    h.output_bindings,
                    h.output_binding_status,
                )
                for h in matching_handoffs
            )

        slot_spec = irs.get_slot("promotion_result_handoff")
        slots.append(SlotSatisfaction(
            slot_name="promotion_result_handoff",
            status="satisfied" if result_handoff_satisfied else "missing",
            source_span_ids=list(candidate.source_span_ids),
            relation="direct" if result_handoff_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not result_handoff_satisfied else None,
            diagnostic_blocks_rendering=False,
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
                source_span_ids=list(candidate.source_span_ids),
                metadata={
                    "candidate_id": candidate.candidate_id,
                    "edge_source": "worker_plan",
                },
            )
        ]

        # Add blocked_by edges for each missing slot
        if not all_satisfied:
            for slot_name in missing_slot_names:
                related_edges.append(ConstructEdge(
                    from_id=instance.construct_id,
                    to_id=(
                        f"missing_slot:{candidate.candidate_id}"
                        f":{slot_name}"
                    ),
                    edge_type="blocked_by",
                    source_span_ids=list(candidate.source_span_ids),
                    metadata={
                        "missing_slot": slot_name,
                        "candidate_id": candidate.candidate_id,
                        "edge_source": "worker_plan",
                    },
                ))

        # WORKER_PROMOTION is not renderable (analysis construct)
        report_metadata: dict = {
            "promotion_status": promotion_status,
            "promotion_candidate_id": candidate.candidate_id,
            "promotion_missing_slots": missing_slot_names,
        }
        # Propagate delegation provenance from instance metadata so
        # DiagnosticProjector / selective promotion can use it (Phase 4).
        for key in (
            "original_semantic_role",
            "original_route_annotation_id",
            "original_route_annotation_ids",
            "original_source_span_ids",
            "synthetic_from_route_annotation",
        ):
            if key in instance.metadata:
                report_metadata[key] = instance.metadata[key]

        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=slots,
            completeness=completeness,
            renderable=False,
            source_span_ids=list(candidate.source_span_ids),
            construct_path=instance.construct_path,
            frontier_status="cutline_blocked" if not all_satisfied else "leaf",
            cutline_reason="missing_promotion_contract" if not all_satisfied else None,
            related_edges=related_edges,
            metadata=report_metadata,
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

        # Check responsibility.  A partial child worker skeleton is meaningful
        # when it has an auditable responsibility signal, even if contract or
        # invocation slots are still incomplete.
        responsibility_satisfied = bool(
            worker.purpose.strip()
            or worker.reason.strip()
            or worker.owned_span_ids
        )
        slots.append(SlotSatisfaction(
            slot_name="responsibility",
            status="satisfied" if responsibility_satisfied else "missing",
            source_span_ids=list(worker.owned_span_ids),
            relation="direct" if responsibility_satisfied else None,
        ))

        # Check input_contract
        input_contract_satisfied = contract_side_satisfied(
            worker.input_contract,
            worker.input_contract_status,
        )
        slot_spec = irs.get_slot("input_contract")
        slots.append(SlotSatisfaction(
            slot_name="input_contract",
            status="satisfied" if input_contract_satisfied else "missing",
            source_span_ids=list(worker.owned_span_ids),
            relation="direct" if input_contract_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not input_contract_satisfied else None,
        ))

        # Check output_contract
        output_contract_satisfied = contract_side_satisfied(
            worker.output_contract,
            worker.output_contract_status,
        )
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
                    if binding_side_satisfied(
                        handoff.output_bindings,
                        handoff.output_binding_status,
                    ):
                        result_handoff_satisfied = True

        slot_spec = irs.get_slot("invocation_point")
        slots.append(SlotSatisfaction(
            slot_name="invocation_point",
            status="satisfied" if invocation_point_satisfied else "missing",
            source_span_ids=list(worker.owned_span_ids),
            relation="direct" if invocation_point_satisfied else None,
            diagnostic_kind=(
                slot_spec.missing_diagnostic
                if not invocation_point_satisfied
                else None
            ),
        ))

        slot_spec = irs.get_slot("result_handoff")
        slots.append(SlotSatisfaction(
            slot_name="result_handoff",
            status="satisfied" if result_handoff_satisfied else "missing",
            source_span_ids=list(worker.owned_span_ids),
            relation="direct" if result_handoff_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not result_handoff_satisfied else None,
        ))

        # Determine completeness and frontier
        # Read required-for-partial from IRS spec, not hardcoded
        required_for_partial_names = {
            slot_spec.slot_name
            for slot_spec in irs.slots
            if slot_spec.required_for_partial
        }
        partial_slots_missing = any(
            s.status != "satisfied"
            for s in slots
            if s.slot_name in required_for_partial_names
        )
        all_satisfied = all(s.status == "satisfied" for s in slots)

        if all_satisfied:
            completeness = "complete"
            frontier = "leaf"
            cutline = None
        elif partial_slots_missing:
            completeness = "blocked"
            frontier = "cutline_blocked"
            cutline = "missing_required_for_partial"
        else:
            completeness = "partial"
            frontier = "leaf"
            cutline = None

        return ConstructSatisfactionReport(
            construct_id=instance.construct_id,
            construct_type=instance.construct_type,
            slots=slots,
            completeness=completeness,
            renderable=(
                all_satisfied
                or (irs.partial_rendering_allowed and not partial_slots_missing)
            ),
            source_span_ids=list(worker.owned_span_ids),
            construct_path=instance.construct_path,
            frontier_status=frontier,
            cutline_reason=cutline,
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
        input_bindings_satisfied = binding_side_satisfied(
            handoff.input_bindings,
            handoff.input_binding_status,
        )
        slot_spec = irs.get_slot("input_bindings")
        slots.append(SlotSatisfaction(
            slot_name="input_bindings",
            status="satisfied" if input_bindings_satisfied else "missing",
            source_span_ids=handoff_source_spans,
            relation="direct" if input_bindings_satisfied else None,
            diagnostic_kind=slot_spec.missing_diagnostic if not input_bindings_satisfied else None,
        ))

        # Check output_bindings
        output_bindings_satisfied = binding_side_satisfied(
            handoff.output_bindings,
            handoff.output_binding_status,
        )
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
                edge_type="handoff_to",
                source_span_ids=list(handoff_source_spans),
                metadata={
                    "handoff_id": handoff.handoff_id,
                    "target_worker_id": handoff.to_worker,
                    "edge_source": "worker_plan",
                },
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
