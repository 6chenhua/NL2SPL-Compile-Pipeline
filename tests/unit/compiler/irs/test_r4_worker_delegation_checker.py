"""R4 Worker/Delegation Checker Tests

Tests for the first v6-style checker implementation.

Test coverage:
    - Registry contains WORKER_PROMOTION and WORKER_HANDOFF
    - No worker_plan returns no reports
    - Candidate extraction produces WORKER_CANDIDATE + WORKER_PROMOTION
    - Candidate complete does not mean promotion ready
    - Incomplete delegation promotion is blocked
    - Missing contracts create diagnostic_kind slots
    - Complete promotion has promotion_status=ready
    - Materialized child worker produces CHILD_WORKER report
    - Materialized handoff produces WORKER_HANDOFF report
    - Checker does not mutate WorkerPlanIR
    - Runner + projector produces CompileDiagnostic
    - Related edges express relationships
"""

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.compiler.irs.registry import IRSCheckerRegistry
from nl2spl.compiler.irs.runner import IRSRunner
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    InputBindingIR,
    InvokeLocationHintIR,
    OutputBindingIR,
    WorkerHandoffIR,
    WorkerPlanIR,
    WorkerSpecIR,
)


# ===========================================================================
# Registry Tests
# ===========================================================================


class TestR4ConstructRegistry:
    """Test that WORKER_PROMOTION and WORKER_HANDOFF are registered"""

    def test_registry_contains_worker_promotion(self):
        """WORKER_PROMOTION construct spec exists"""
        registry = SPLConstructRegistry.default()
        assert registry.has("WORKER_PROMOTION")
        
        irs = registry.get("WORKER_PROMOTION")
        assert irs.construct_type == "WORKER_PROMOTION"
        assert len(irs.slots) == 4
        assert irs.get_slot("promotion_input_contract") is not None
        assert irs.get_slot("promotion_output_contract") is not None
        assert irs.get_slot("promotion_invocation_point") is not None
        assert irs.get_slot("promotion_result_handoff") is not None

    def test_registry_contains_worker_handoff(self):
        """WORKER_HANDOFF construct spec exists"""
        registry = SPLConstructRegistry.default()
        assert registry.has("WORKER_HANDOFF")
        
        irs = registry.get("WORKER_HANDOFF")
        assert irs.construct_type == "WORKER_HANDOFF"
        assert len(irs.slots) == 5
        assert irs.get_slot("from_worker") is not None
        assert irs.get_slot("target") is not None
        assert irs.get_slot("input_bindings") is not None
        assert irs.get_slot("output_bindings") is not None
        assert irs.get_slot("invocation_site") is not None

    def test_worker_candidate_updated_description(self):
        """WORKER_CANDIDATE description clarifies candidate vs promotion"""
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_CANDIDATE")
        
        # Should mention candidate boundary, not promotion
        assert "candidate" in irs.description.lower()
        assert "boundary" in irs.description.lower()
        
        # Slots should be about candidate identification, not promotion
        assert irs.get_slot("responsibility") is not None
        assert irs.get_slot("delegation_signal") is not None
        assert irs.get_slot("source_evidence") is not None

    def test_registry_no_longer_has_delegation_intent(self):
        """R10 Phase 5: DELEGATION_INTENT removed from ConstructRegistry."""
        registry = SPLConstructRegistry.default()
        assert not registry.has("DELEGATION_INTENT"), (
            "R10 Phase 5: DELEGATION_INTENT construct removed from registry"
        )


# ===========================================================================
# Checker Extraction Tests
# ===========================================================================


class TestR4CheckerExtraction:
    """Test instance extraction from WorkerPlanIR"""

    def test_no_worker_plan_returns_empty(self):
        """No worker_plan in context returns no instances"""
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=None)
        
        instances = checker.extract_instances(context)
        assert instances == []

    def test_candidate_extraction_produces_candidate_and_promotion(self):
        """Each candidate produces WORKER_CANDIDATE + WORKER_PROMOTION instances"""
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[
                CandidateTaskUnitIR(
                    candidate_id="cand_1",
                    source_span_ids=["s1"],
                    task_text="Draft document",
                    purpose="Drafting",
                    candidate_kind="explicit_delegation",
                    possible_inputs=[],
                    possible_outputs=[],
                    signals=["delegation"],
                    risks=[],
                )
            ],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        instances = checker.extract_instances(context)
        
        assert len(instances) == 2
        
        candidate_instances = [i for i in instances if i.construct_type == "WORKER_CANDIDATE"]
        promotion_instances = [i for i in instances if i.construct_type == "WORKER_PROMOTION"]
        
        assert len(candidate_instances) == 1
        assert len(promotion_instances) == 1
        
        assert candidate_instances[0].construct_id == "worker_candidate:cand_1"
        assert candidate_instances[0].materialized is False
        assert candidate_instances[0].source_demanded is True
        assert candidate_instances[0].candidate_only is True
        
        assert promotion_instances[0].construct_id == "worker_promotion:cand_1"
        assert promotion_instances[0].materialized is False
        assert promotion_instances[0].source_demanded is True
        assert promotion_instances[0].candidate_only is True

    def test_child_worker_extraction(self):
        """Materialized child workers produce CHILD_WORKER instances"""
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_child",
                    worker_name="Child",
                    kind="child",
                    purpose="Child worker",
                    owned_span_ids=["s2"],
                    input_contract=[],
                    output_contract=[],
                    depends_on=[],
                    constraints=[],
                    boundary_kind="child_worker",
                    decision_evidence=[],
                    reason="",
                )
            ],
            candidates=[],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        instances = checker.extract_instances(context)
        
        assert len(instances) == 1
        assert instances[0].construct_type == "CHILD_WORKER"
        assert instances[0].construct_id == "child_worker:worker_child"
        assert instances[0].materialized is True

    def test_handoff_extraction(self):
        """Materialized handoffs produce WORKER_HANDOFF instances"""
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[],
            decisions=[],
            handoffs=[
                WorkerHandoffIR(
                    handoff_id="handoff_1",
                    from_worker="worker_main",
                    to_worker="worker_child",
                    api_ref=None,
                    mode="invoke",
                    condition_text=None,
                    ordering="after",
                    input_bindings=[],
                    output_bindings=[],
                )
            ],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        instances = checker.extract_instances(context)
        
        assert len(instances) == 1
        assert instances[0].construct_type == "WORKER_HANDOFF"
        assert instances[0].construct_id == "worker_handoff:handoff_1"
        assert instances[0].materialized is True

    def test_delegation_intent_extraction_from_routes(self):
        """R10 Phase 1: Route delegation annotations now produce synthetic
        WORKER_CANDIDATE + WORKER_PROMOTION instances — no DELEGATION_INTENT."""
        routes = FieldRouteIR(
            behavior=["s_delegate"],
            annotations=[
                RouteAnnotation(
                    span_id="s_delegate",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                )
            ],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", routes=routes)

        instances = checker.extract_instances(context)

        # R10: produces WORKER_CANDIDATE + WORKER_PROMOTION (not DELEGATION_INTENT)
        assert len(instances) == 2
        types = {i.construct_type for i in instances}
        assert types == {"WORKER_CANDIDATE", "WORKER_PROMOTION"}
        assert all("del_s_delegate" in i.construct_id for i in instances)
        # All instances must be flagged as synthetic
        for i in instances:
            assert i.metadata.get("synthetic_from_route_annotation") is True
            assert i.metadata.get("original_semantic_role") == "delegation_intent"


class TestR4DelegationIntentIRS:
    """Route-level delegation intent diagnostics come from IRS projection."""

    def _runner(self) -> IRSRunner:
        registry = IRSCheckerRegistry()
        registry.register(WorkerDelegationIRSChecker())
        return IRSRunner(
            registry=registry,
            construct_registry=SPLConstructRegistry.default(),
            projector=DiagnosticProjector(),
        )

    def _routes(self) -> FieldRouteIR:
        return FieldRouteIR(
            behavior=["s_delegate"],
            annotations=[
                RouteAnnotation(
                    span_id="s_delegate",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                    source_section_id="sec_delegation_policy",
                    source_packet_id="pkt_delegate",
                )
            ],
        )

    def test_missing_handoff_contract_projects_irs_diagnostic(self):
        """R10 Phase 1: Missing delegation contract — WORKER_PROMOTION
        missing slots produce type_or_contract_ambiguity via IRS projection.

        Precise assertions: exact diagnostic count, exact slot names,
        correct target_ref, correct source spans, correct metadata.
        """
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])
        result = self._runner().run_stage(
            "stage3_5",
            IRSCheckContext(
                stage_name="stage3_5",
                routes=self._routes(),
                worker_plan=plan,
            ),
        )

        # R10: diagnostics target worker_promotion:del_s_delegate (synthetic)
        expected_target = "worker_promotion:del_s_delegate"
        diags = [
            d for d in result.diagnostics
            if d.target_ref == expected_target
            and d.kind == "type_or_contract_ambiguity"
        ]
        # All 4 promotion slots missing → exactly 4 diagnostics
        assert len(diags) == 4, (
            f"Expected exactly 4 ambiguity diagnostics for {expected_target}, "
            f"got {len(diags)}: {[(d.target_ref, d.missing_slot.slot_name if d.missing_slot else None) for d in diags]}"
        )
        slot_names = {d.missing_slot.slot_name for d in diags}
        assert slot_names == {
            "promotion_input_contract",
            "promotion_output_contract",
            "promotion_invocation_point",
            "promotion_result_handoff",
        }, f"Unexpected slot names: {slot_names}"

        for diag in diags:
            assert diag.diagnostic_id.startswith("irs_")
            assert diag.kind == "type_or_contract_ambiguity"
            assert "s_delegate" in diag.source_span_ids
            assert diag.missing_slot is not None

        # Verify no DELEGATION_INTENT reports or diagnostics exist
        delegation_reports = [
            r for r in result.reports
            if r.construct_type == "DELEGATION_INTENT"
        ]
        assert len(delegation_reports) == 0
        delegation_diags = [
            d for d in result.diagnostics
            if (d.target_ref or "").startswith("delegation_intent:")
        ]
        assert len(delegation_diags) == 0

        # Verify the report carries delegation provenance metadata
        promotion_reports = [
            r for r in result.reports
            if r.construct_id == expected_target
        ]
        assert len(promotion_reports) == 1
        report = promotion_reports[0]
        assert report.metadata.get("synthetic_from_route_annotation") is True
        assert report.metadata.get("original_semantic_role") == "delegation_intent"
        assert report.metadata.get("original_source_span_ids") == ["s_delegate"]

    def test_valid_handoff_contract_suppresses_delegation_intent_diagnostic(self):
        """R10 Phase 1: A valid invoke handoff covering the span
        satisfies WORKER_PROMOTION invocation/result-handoff slots.
        No DELEGATION_INTENT construct exists anymore."""
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="MainWorker",
                    kind="main",
                    purpose="Main",
                    boundary_kind="main_worker",
                ),
                WorkerSpecIR(
                    worker_id="worker_child",
                    worker_name="ChildWorker",
                    kind="child",
                    purpose="Child",
                    boundary_kind="child_worker",
                ),
            ],
            handoffs=[
                WorkerHandoffIR(
                    handoff_id="handoff_1",
                    from_worker="worker_main",
                    to_worker="worker_child",
                    api_ref=None,
                    mode="invoke",
                    condition_text=None,
                    ordering="after",
                    input_bindings=[
                        InputBindingIR(
                            parent_variable="request",
                            child_input="request",
                            required=True,
                        )
                    ],
                    output_bindings=[
                        OutputBindingIR(
                            child_output="result",
                            parent_variable="result",
                            required=True,
                            merge_strategy="set",
                        )
                    ],
                    invoke_location_hint=InvokeLocationHintIR(
                        flow_kind="main",
                        flow_id=None,
                        after_span_id="s_delegate",
                        before_span_id=None,
                        block_hint="sequential",
                    ),
                )
            ],
        )

        result = self._runner().run_stage(
            "stage3_5",
            IRSCheckContext(
                stage_name="stage3_5",
                routes=self._routes(),
                worker_plan=plan,
            ),
        )

        # R10: No DELEGATION_INTENT constructs or diagnostics
        assert all(
            not (d.target_ref or "").startswith("delegation_intent:")
            for d in result.diagnostics
        )
        delegation_reports = [
            r for r in result.reports
            if r.construct_type == "DELEGATION_INTENT"
        ]
        assert len(delegation_reports) == 0

        # Synthetic WORKER_PROMOTION exists for the delegation span.
        # The matching handoff satisfies invocation_point + result_handoff.
        promotion_reports = [
            r for r in result.reports
            if r.construct_type == "WORKER_PROMOTION"
            and "del_s_delegate" in r.construct_id
        ]
        assert len(promotion_reports) == 1
        promotion = promotion_reports[0]

        # invocation_point: satisfied (handoff hint spans overlap)
        inv_slot = next(
            s for s in promotion.slots
            if s.slot_name == "promotion_invocation_point"
        )
        assert inv_slot.status == "satisfied", (
            f"Expected invocation_point satisfied, got {inv_slot.status}"
        )

        # result_handoff: satisfied (handoff has output_bindings)
        res_slot = next(
            s for s in promotion.slots
            if s.slot_name == "promotion_result_handoff"
        )
        assert res_slot.status == "satisfied", (
            f"Expected result_handoff satisfied, got {res_slot.status}"
        )

        # Note: input/output contract slots are still missing because the
        # synthetic candidate (from bare route annotation) has no contracts.
        # This is expected — Phase 2 will refine signal preservation.


# ===========================================================================
# Candidate Checking Tests
# ===========================================================================


class TestR4CandidateChecking:
    """Test WORKER_CANDIDATE report generation"""

    def test_complete_candidate_report(self):
        """Complete candidate has all slots satisfied"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Draft document",
            purpose="Drafting",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=[],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_CANDIDATE")
        
        instances = checker.extract_instances(context)
        candidate_instance = [i for i in instances if i.construct_type == "WORKER_CANDIDATE"][0]
        
        report = checker.check_instance(candidate_instance, irs, context)
        
        assert report.construct_type == "WORKER_CANDIDATE"
        assert report.completeness == "complete"
        assert report.renderable is False
        assert report.frontier_status == "leaf"
        assert report.metadata["candidate_status"] == "identified"
        
        # All slots satisfied
        assert len(report.slots) == 3
        assert all(s.status == "satisfied" for s in report.slots)

    def test_candidate_complete_does_not_mean_promotion_ready(self):
        """Candidate can be complete while promotion is blocked"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Draft document",
            purpose="Drafting",
            candidate_kind="explicit_delegation",
            possible_inputs=[],  # Empty - promotion will be blocked
            possible_outputs=[],  # Empty - promotion will be blocked
            signals=["delegation"],
            risks=["no_clear_input_contract", "no_clear_output_contract"],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        
        instances = checker.extract_instances(context)
        candidate_instance = [i for i in instances if i.construct_type == "WORKER_CANDIDATE"][0]
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        candidate_report = checker.check_instance(
            candidate_instance, registry.get("WORKER_CANDIDATE"), context
        )
        promotion_report = checker.check_instance(
            promotion_instance, registry.get("WORKER_PROMOTION"), context
        )
        
        # Candidate is complete
        assert candidate_report.completeness == "complete"
        
        # But promotion is blocked
        assert promotion_report.completeness == "partial"
        assert promotion_report.metadata["promotion_status"] == "blocked"
        assert "promotion_input_contract" in promotion_report.metadata["promotion_missing_slots"]
        assert "promotion_output_contract" in promotion_report.metadata["promotion_missing_slots"]


# ===========================================================================
# Promotion Checking Tests
# ===========================================================================


class TestR4PromotionChecking:
    """Test WORKER_PROMOTION report generation"""

    def test_incomplete_delegation_promotion_is_blocked(self):
        """Incomplete delegation produces blocked promotion report"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_draft",
            source_span_ids=["s2"],
            task_text="Draft using templates",
            purpose="Drafting can be delegated",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["explicit_delegation"],
            risks=["no_clear_input_contract", "no_clear_output_contract"],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        
        instances = checker.extract_instances(context)
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        report = checker.check_instance(promotion_instance, irs, context)
        
        assert report.construct_type == "WORKER_PROMOTION"
        assert report.completeness == "partial"
        assert report.renderable is False
        assert report.frontier_status == "cutline_blocked"
        assert report.cutline_reason == "missing_promotion_contract"
        assert report.metadata["promotion_status"] == "blocked"
        assert report.metadata["promotion_candidate_id"] == "cand_draft"
        
        # Check missing slots have diagnostic_kind
        missing_slots = [s for s in report.slots if s.status == "missing"]
        assert len(missing_slots) > 0
        for slot in missing_slots:
            assert slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_missing_input_contract_creates_diagnostic_kind(self):
        """Missing input contract slot has diagnostic_kind"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],  # Missing
            possible_outputs=["output1"],
            signals=["delegation"],
            risks=["no_clear_input_contract"],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        
        instances = checker.extract_instances(context)
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        report = checker.check_instance(promotion_instance, irs, context)
        
        input_slot = next(s for s in report.slots if s.slot_name == "promotion_input_contract")
        assert input_slot.status == "missing"
        assert input_slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_missing_output_contract_creates_diagnostic_kind(self):
        """Missing output contract slot has diagnostic_kind"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=["input1"],
            possible_outputs=[],  # Missing
            signals=["delegation"],
            risks=["no_clear_output_contract"],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        
        instances = checker.extract_instances(context)
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        report = checker.check_instance(promotion_instance, irs, context)
        
        output_slot = next(s for s in report.slots if s.slot_name == "promotion_output_contract")
        assert output_slot.status == "missing"
        assert output_slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_missing_invocation_point_creates_diagnostic_kind(self):
        """Missing invocation point slot has diagnostic_kind"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=["input1"],
            possible_outputs=["output1"],
            signals=["delegation"],
            risks=["no_parent_invocation_point"],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        
        instances = checker.extract_instances(context)
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        report = checker.check_instance(promotion_instance, irs, context)
        
        invocation_slot = next(
            s for s in report.slots if s.slot_name == "promotion_invocation_point"
        )
        assert invocation_slot.status == "missing"
        assert invocation_slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_missing_result_handoff_creates_diagnostic_kind(self):
        """Missing result handoff slot has diagnostic_kind"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=["input1"],
            possible_outputs=["output1"],
            signals=["delegation"],
            risks=["unclear_result_handoff"],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        
        instances = checker.extract_instances(context)
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        report = checker.check_instance(promotion_instance, irs, context)
        
        handoff_slot = next(
            s for s in report.slots if s.slot_name == "promotion_result_handoff"
        )
        assert handoff_slot.status == "missing"
        assert handoff_slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_promotion_without_handoff_is_blocked(self):
        """Promotion without handoff evidence is blocked (negative test)"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=["input1"],
            possible_outputs=["output1"],
            signals=["delegation"],
            risks=[],  # No risks, but no handoff evidence either
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],  # No handoffs - promotion should be blocked
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        
        instances = checker.extract_instances(context)
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        report = checker.check_instance(promotion_instance, irs, context)
        
        # Without handoff evidence, promotion should be blocked
        assert report.completeness == "partial"
        assert report.metadata["promotion_status"] == "blocked"
        assert "promotion_invocation_point" in report.metadata["promotion_missing_slots"]
        assert "promotion_result_handoff" in report.metadata["promotion_missing_slots"]
        assert report.frontier_status == "cutline_blocked"
        assert report.cutline_reason == "missing_promotion_contract"

    def test_complete_promotion_with_all_evidence_is_ready(self):
        """Complete promotion with decision, child worker, handoff, and bindings is ready"""
        from nl2spl.ir.worker_plan_ir import WorkerBoundaryDecisionIR
        
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=["input1"],
            possible_outputs=["output1"],
            signals=["delegation"],
            risks=[],
        )
        
        child_worker = WorkerSpecIR(
            worker_id="worker_child",
            worker_name="Child",
            kind="child",
            purpose="Child worker",
            owned_span_ids=["s2"],
            input_contract=[{"name": "input1", "type": "string"}],
            output_contract=[{"name": "output1", "type": "string"}],
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        
        decision = WorkerBoundaryDecisionIR(
            candidate_id="cand_1",
            decision="extract_child_worker",
            boundary_strength="strong",
            boundary_kind="child_worker",
            rejection_reason=None,
            reason="Extracted as child worker",
        )
        
        handoff = WorkerHandoffIR(
            handoff_id="handoff_1",
            from_worker="worker_main",
            to_worker="worker_child",
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[{"from": "x", "to": "input1"}],
            output_bindings=[{"from": "output1", "to": "y"}],
            invoke_location_hint=InvokeLocationHintIR(
                flow_kind="main",
                flow_id=None,
                after_span_id="s1",
                before_span_id=None,
                block_hint="sequential",
            ),
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[child_worker],
            candidates=[candidate],
            decisions=[decision],
            handoffs=[handoff],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        
        instances = checker.extract_instances(context)
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        report = checker.check_instance(promotion_instance, irs, context)
        
        # With all evidence, promotion should be ready
        assert report.completeness == "complete"
        assert report.metadata["promotion_status"] == "ready"
        assert report.metadata["promotion_missing_slots"] == []
        assert report.frontier_status == "leaf"
        assert report.cutline_reason is None


# ===========================================================================
# Child Worker and Handoff Tests
# ===========================================================================


class TestR4ChildWorkerAndHandoff:
    """Test CHILD_WORKER and WORKER_HANDOFF reports"""

    def test_materialized_child_worker_produces_report(self):
        """Materialized child worker produces CHILD_WORKER report"""
        worker = WorkerSpecIR(
            worker_id="worker_child",
            worker_name="Child",
            kind="child",
            purpose="Child worker purpose",
            owned_span_ids=["s2"],
            input_contract=[{"name": "input1", "type": "string"}],
            output_contract=[{"name": "output1", "type": "string"}],
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        
        handoff = WorkerHandoffIR(
            handoff_id="handoff_1",
            from_worker="worker_main",
            to_worker="worker_child",
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[{"from": "x", "to": "input1"}],
            output_bindings=[{"from": "output1", "to": "y"}],
            invoke_location_hint=InvokeLocationHintIR(
                flow_kind="main",
                flow_id=None,
                after_span_id="s1",
                before_span_id=None,
                block_hint="sequential",
            ),
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[worker],
            candidates=[],
            decisions=[],
            handoffs=[handoff],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("CHILD_WORKER")
        
        instances = checker.extract_instances(context)
        worker_instance = [i for i in instances if i.construct_type == "CHILD_WORKER"][0]
        
        report = checker.check_instance(worker_instance, irs, context)
        
        assert report.construct_type == "CHILD_WORKER"
        assert report.completeness == "complete"
        assert report.renderable is True
        assert all(s.status == "satisfied" for s in report.slots)

    def test_child_worker_missing_contract_is_blocked(self):
        """CHILD_WORKER missing input/output contract → blocked / cutline_blocked."""
        worker = WorkerSpecIR(
            worker_id="worker_child",
            worker_name="Child",
            kind="child",
            purpose="Child worker purpose",
            owned_span_ids=["s2"],
            input_contract=[],  # missing
            output_contract=[],  # missing
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[worker],
            candidates=[],
            handoffs=[],
            decisions=[],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        irs = SPLConstructRegistry.default().get("CHILD_WORKER")
        instances = checker.extract_instances(context)
        child = [i for i in instances if i.construct_type == "CHILD_WORKER"][0]
        report = checker.check_instance(child, irs, context)

        assert report.completeness == "blocked"
        assert report.frontier_status == "cutline_blocked"
        assert report.cutline_reason == "missing_required_for_partial"
        assert report.renderable is False
        # input/output slots have diagnostic_kind
        for slot in report.slots:
            if slot.slot_name in ("input_contract", "output_contract"):
                assert slot.status == "missing"
                assert slot.diagnostic_kind == "type_or_contract_ambiguity"

    def test_child_worker_missing_only_invocation_is_partial(self):
        """CHILD_WORKER with contracts but missing invocation → partial / leaf."""
        worker = WorkerSpecIR(
            worker_id="worker_child",
            worker_name="Child",
            kind="child",
            purpose="Child worker purpose",
            owned_span_ids=["s2"],
            input_contract=[{"name": "x", "type": "string"}],
            output_contract=[{"name": "y", "type": "string"}],
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[worker],
            candidates=[],
            handoffs=[],  # no handoff → invocation_point/result_handoff missing
            decisions=[],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        irs = SPLConstructRegistry.default().get("CHILD_WORKER")
        instances = checker.extract_instances(context)
        child = [i for i in instances if i.construct_type == "CHILD_WORKER"][0]
        report = checker.check_instance(child, irs, context)

        assert report.completeness == "partial"
        assert report.frontier_status == "leaf"
        assert report.cutline_reason is None
        # input/output slots are satisfied
        for slot in report.slots:
            if slot.slot_name in ("input_contract", "output_contract"):
                assert slot.status == "satisfied"

    def test_child_worker_frontier_reads_from_irs_spec(self):
        """Checker reads required_for_partial from IRS spec, not hardcoded.

        If invocation_point were required_for_partial in the spec,
        a child worker missing invocation would be blocked, not partial.
        This test locks that the checker uses irs.slots, not a hardcoded set.
        """
        from nl2spl.compiler.construct_registry import (
            ConstructIRS,
            SlotSpec,
            SPLConstructRegistry,
        )

        # Build a custom registry where invocation_point is required_for_partial
        custom_registry = SPLConstructRegistry()
        custom_registry.register(ConstructIRS(
            construct_type="CHILD_WORKER",
            existence_policy="source_signal_required",
            source_signals=[],
            partial_rendering_allowed=False,
            slots=[
                SlotSpec(
                    slot_name="responsibility",
                    required_for_partial=True,
                    required_for_complete=True,
                ),
                SlotSpec(
                    slot_name="input_contract",
                    required_for_partial=True,
                    required_for_complete=True,
                    renderable_without=False,
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="output_contract",
                    required_for_partial=True,
                    required_for_complete=True,
                    renderable_without=False,
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="invocation_point",
                    required_for_partial=True,  # override: now required for partial
                    required_for_complete=True,
                    renderable_without=False,
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
                SlotSpec(
                    slot_name="result_handoff",
                    required_for_complete=True,
                    renderable_without=False,
                    missing_diagnostic="type_or_contract_ambiguity",
                ),
            ],
        ))

        worker = WorkerSpecIR(
            worker_id="worker_child",
            worker_name="Child",
            kind="child",
            purpose="Child worker purpose",
            owned_span_ids=["s2"],
            input_contract=[{"name": "x", "type": "string"}],
            output_contract=[{"name": "y", "type": "string"}],
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        plan = WorkerPlanIR(
            main_worker_id="main",
            workers=[worker],
            candidates=[],
            handoffs=[],  # invocation_point/result_handoff missing
            decisions=[],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        irs = custom_registry.get("CHILD_WORKER")
        instances = checker.extract_instances(context)
        child = [i for i in instances if i.construct_type == "CHILD_WORKER"][0]
        report = checker.check_instance(child, irs, context)

        # With invocation_point required_for_partial=True, missing it → blocked
        assert report.completeness == "blocked"
        assert report.frontier_status == "cutline_blocked"
        assert report.cutline_reason == "missing_required_for_partial"

    def test_materialized_handoff_produces_report(self):
        """Materialized handoff produces WORKER_HANDOFF report"""
        worker_main = WorkerSpecIR(
            worker_id="worker_main",
            worker_name="Main",
            kind="main",
            purpose="Main worker",
            owned_span_ids=["s1"],
            input_contract=[],
            output_contract=[],
            depends_on=[],
            constraints=[],
            boundary_kind="main_worker",
            decision_evidence=[],
            reason="",
        )
        
        worker_child = WorkerSpecIR(
            worker_id="worker_child",
            worker_name="Child",
            kind="child",
            purpose="Child worker",
            owned_span_ids=["s2"],
            input_contract=[{"name": "input1", "type": "string"}],
            output_contract=[{"name": "output1", "type": "string"}],
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        
        handoff = WorkerHandoffIR(
            handoff_id="handoff_1",
            from_worker="worker_main",
            to_worker="worker_child",
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[{"from": "x", "to": "input1"}],
            output_bindings=[{"from": "output1", "to": "y"}],
            invoke_location_hint=InvokeLocationHintIR(
                flow_kind="main",
                flow_id=None,
                after_span_id="s1",
                before_span_id=None,
                block_hint="sequential",
            ),
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[worker_main, worker_child],  # Include both workers
            candidates=[],
            decisions=[],
            handoffs=[handoff],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_HANDOFF")
        
        instances = checker.extract_instances(context)
        handoff_instance = [i for i in instances if i.construct_type == "WORKER_HANDOFF"][0]
        
        report = checker.check_instance(handoff_instance, irs, context)
        
        assert report.construct_type == "WORKER_HANDOFF"
        assert report.completeness == "complete"
        assert report.renderable is False  # Handoff is not renderable
        assert all(s.status == "satisfied" for s in report.slots)

    def test_handoff_missing_bindings_produces_diagnostic_slots(self):
        """Handoff missing bindings and invocation site produces slots with diagnostic_kind"""
        worker_main = WorkerSpecIR(
            worker_id="worker_main",
            worker_name="Main",
            kind="main",
            purpose="Main worker",
            owned_span_ids=["s1"],
            input_contract=[],
            output_contract=[],
            depends_on=[],
            constraints=[],
            boundary_kind="main_worker",
            decision_evidence=[],
            reason="",
        )
        
        worker_child = WorkerSpecIR(
            worker_id="worker_child",
            worker_name="Child",
            kind="child",
            purpose="Child worker",
            owned_span_ids=["s2"],
            input_contract=[],
            output_contract=[],
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        
        handoff = WorkerHandoffIR(
            handoff_id="handoff_1",
            from_worker="worker_main",
            to_worker="worker_child",
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="before",  # ordering alone is not sufficient for invocation_site
            input_bindings=[],  # Missing
            output_bindings=[],  # Missing
            invoke_location_hint=None,  # Missing - invocation_site will be missing
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[worker_main, worker_child],
            candidates=[],
            decisions=[],
            handoffs=[handoff],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_HANDOFF")
        
        instances = checker.extract_instances(context)
        handoff_instance = [i for i in instances if i.construct_type == "WORKER_HANDOFF"][0]
        
        report = checker.check_instance(handoff_instance, irs, context)
        
        assert report.completeness == "partial"
        
        missing_slots = [s for s in report.slots if s.status == "missing"]
        # Should have: input_bindings, output_bindings, invocation_site (ordering alone not sufficient)
        assert len(missing_slots) >= 3
        
        for slot in missing_slots:
            assert slot.diagnostic_kind == "type_or_contract_ambiguity"


# ===========================================================================
# Immutability and Edge Tests
# ===========================================================================


class TestR4CheckerBehavior:
    """Test checker behavior constraints"""

    def test_checker_does_not_mutate_worker_plan(self):
        """Checker does not modify WorkerPlanIR"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=["no_clear_input_contract"],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        # Capture original state
        original_candidates_count = len(plan.candidates)
        original_workers_count = len(plan.workers)
        original_handoffs_count = len(plan.handoffs)
        original_candidate_id = plan.candidates[0].candidate_id
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        
        instances = checker.extract_instances(context)
        for instance in instances:
            irs = registry.get(instance.construct_type)
            checker.check_instance(instance, irs, context)
        
        # Verify no mutation
        assert len(plan.candidates) == original_candidates_count
        assert len(plan.workers) == original_workers_count
        assert len(plan.handoffs) == original_handoffs_count
        assert plan.candidates[0].candidate_id == original_candidate_id

    def test_related_edges_express_candidate_to_promotion(self):
        """Related edges express candidate -> promotion relationship"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=["no_clear_input_contract"],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        
        instances = checker.extract_instances(context)
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        report = checker.check_instance(promotion_instance, irs, context)
        
        # R8.2: promotes_to + blocked_by edges for each missing slot
        promotes = [e for e in report.related_edges if e.edge_type == "promotes_to"]
        assert len(promotes) == 1
        assert promotes[0].from_id == "worker_candidate:cand_1"
        assert promotes[0].to_id == "worker_promotion:cand_1"
        # promotes_to edge carries source_span_ids
        assert promotes[0].source_span_ids == ["s1"]
        # blocked_by edges for missing slots
        blocked_by = [e for e in report.related_edges if e.edge_type == "blocked_by"]
        assert len(blocked_by) >= 1

    def test_related_edges_express_handoff_to_worker(self):
        """Related edges express handoff -> worker relationship when target exists"""
        worker_main = WorkerSpecIR(
            worker_id="worker_main",
            worker_name="Main",
            kind="main",
            purpose="Main worker",
            owned_span_ids=["s1"],
            input_contract=[],
            output_contract=[],
            depends_on=[],
            constraints=[],
            boundary_kind="main_worker",
            decision_evidence=[],
            reason="",
        )
        
        worker_child = WorkerSpecIR(
            worker_id="worker_child",
            worker_name="Child",
            kind="child",
            purpose="Child worker",
            owned_span_ids=["s2"],
            input_contract=[{"name": "input1", "type": "string"}],
            output_contract=[{"name": "output1", "type": "string"}],
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        
        handoff = WorkerHandoffIR(
            handoff_id="handoff_1",
            from_worker="worker_main",
            to_worker="worker_child",
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[{"from": "x", "to": "input1"}],
            output_bindings=[{"from": "output1", "to": "y"}],
            invoke_location_hint=InvokeLocationHintIR(
                flow_kind="main",
                flow_id=None,
                after_span_id="s1",
                before_span_id=None,
                block_hint="sequential",
            ),
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[worker_main, worker_child],  # Include child worker
            candidates=[],
            decisions=[],
            handoffs=[handoff],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_HANDOFF")
        
        instances = checker.extract_instances(context)
        handoff_instance = [i for i in instances if i.construct_type == "WORKER_HANDOFF"][0]
        
        report = checker.check_instance(handoff_instance, irs, context)
        
        assert len(report.related_edges) == 1
        edge = report.related_edges[0]
        assert edge.from_id == "worker_handoff:handoff_1"
        assert edge.to_id == "child_worker:worker_child"
        assert edge.edge_type == "handoff_to"

    def test_candidate_instance_preserves_source_provenance(self):
        """Candidate instances preserve ir_ref, source_span_ids, construct_path"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1", "s2"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=[],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        
        instances = checker.extract_instances(context)
        candidate_instance = [i for i in instances if i.construct_type == "WORKER_CANDIDATE"][0]
        
        # Verify source provenance
        assert candidate_instance.ir_ref is candidate
        assert candidate_instance.source_span_ids == ["s1", "s2"]
        assert candidate_instance.construct_path == ("worker_plan", "candidates", "cand_1")

    def test_promotion_instance_preserves_source_provenance(self):
        """Promotion instances preserve ir_ref, source_span_ids, construct_path"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1", "s2"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=[],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        
        instances = checker.extract_instances(context)
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        # Verify source provenance
        assert promotion_instance.ir_ref is candidate
        assert promotion_instance.source_span_ids == ["s1", "s2"]
        assert promotion_instance.construct_path == ("worker_plan", "promotion", "cand_1")

    def test_child_worker_instance_preserves_source_provenance(self):
        """Child worker instances preserve ir_ref, source_span_ids, construct_path"""
        worker = WorkerSpecIR(
            worker_id="worker_child",
            worker_name="Child",
            kind="child",
            purpose="Child worker",
            owned_span_ids=["s3", "s4"],
            input_contract=[],
            output_contract=[],
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[worker],
            candidates=[],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        
        instances = checker.extract_instances(context)
        worker_instance = [i for i in instances if i.construct_type == "CHILD_WORKER"][0]
        
        # Verify source provenance
        assert worker_instance.ir_ref is worker
        assert worker_instance.source_span_ids == ["s3", "s4"]
        assert worker_instance.construct_path == ("worker_plan", "workers", "worker_child")

    def test_handoff_instance_preserves_source_provenance(self):
        """Handoff instances preserve ir_ref, source_span_ids from invoke_location_hint, construct_path"""
        handoff = WorkerHandoffIR(
            handoff_id="handoff_1",
            from_worker="worker_main",
            to_worker="worker_child",
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[],
            output_bindings=[],
            invoke_location_hint=InvokeLocationHintIR(
                flow_kind="main",
                flow_id=None,
                after_span_id="s5",
                before_span_id="s6",
                block_hint="sequential",
            ),
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[],
            decisions=[],
            handoffs=[handoff],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        
        instances = checker.extract_instances(context)
        handoff_instance = [i for i in instances if i.construct_type == "WORKER_HANDOFF"][0]
        
        # Verify source provenance
        assert handoff_instance.ir_ref is handoff
        assert "s5" in handoff_instance.source_span_ids
        assert "s6" in handoff_instance.source_span_ids
        assert handoff_instance.construct_path == ("worker_plan", "handoffs", "handoff_1")

    def test_multiple_candidates_handoff_does_not_cross_wire(self):
        """Multiple candidates: handoff only matches the correct candidate, not others"""
        from nl2spl.ir.worker_plan_ir import WorkerBoundaryDecisionIR
        
        # Two candidates with different source spans
        candidate_a = CandidateTaskUnitIR(
            candidate_id="cand_a",
            source_span_ids=["s1", "s2"],
            task_text="Task A",
            purpose="Purpose A",
            candidate_kind="explicit_delegation",
            possible_inputs=["input1"],
            possible_outputs=["output1"],
            signals=["delegation"],
            risks=[],
        )
        
        candidate_b = CandidateTaskUnitIR(
            candidate_id="cand_b",
            source_span_ids=["s5", "s6"],
            task_text="Task B",
            purpose="Purpose B",
            candidate_kind="explicit_delegation",
            possible_inputs=["input2"],
            possible_outputs=["output2"],
            signals=["delegation"],
            risks=[],
        )
        
        # Child worker for candidate_a with overlapping spans
        worker_a = WorkerSpecIR(
            worker_id="worker_a",
            worker_name="Worker A",
            kind="child",
            purpose="Worker A",
            owned_span_ids=["s1", "s2", "s3"],
            input_contract=[{"name": "input1", "type": "string"}],
            output_contract=[{"name": "output1", "type": "string"}],
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        
        # Decision for candidate_a only
        decision_a = WorkerBoundaryDecisionIR(
            candidate_id="cand_a",
            decision="extract_child_worker",
            boundary_strength="strong",
            boundary_kind="child_worker",
            rejection_reason=None,
            reason="Extracted as child worker",
        )
        
        decision_b = WorkerBoundaryDecisionIR(
            candidate_id="cand_b",
            decision="extract_child_worker",
            boundary_strength="strong",
            boundary_kind="child_worker",
            rejection_reason=None,
            reason="Extracted as child worker",
        )
        
        # Handoff that matches candidate_a (overlapping spans with worker_a)
        handoff_a = WorkerHandoffIR(
            handoff_id="handoff_a",
            from_worker="worker_main",
            to_worker="worker_a",
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[{"from": "x", "to": "input1"}],
            output_bindings=[{"from": "output1", "to": "y"}],
            invoke_location_hint=InvokeLocationHintIR(
                flow_kind="main",
                flow_id=None,
                after_span_id="s2",  # Overlaps with candidate_a
                before_span_id=None,
                block_hint="sequential",
            ),
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[worker_a],
            candidates=[candidate_a, candidate_b],
            decisions=[decision_a, decision_b],
            handoffs=[handoff_a],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        
        instances = checker.extract_instances(context)
        promotion_a = [i for i in instances if i.construct_id == "worker_promotion:cand_a"][0]
        promotion_b = [i for i in instances if i.construct_id == "worker_promotion:cand_b"][0]
        
        report_a = checker.check_instance(promotion_a, irs, context)
        report_b = checker.check_instance(promotion_b, irs, context)
        
        # candidate_a should be ready (has matching handoff)
        assert report_a.completeness == "complete"
        assert report_a.metadata["promotion_status"] == "ready"
        
        # candidate_b should be blocked (no matching handoff)
        assert report_b.completeness == "partial"
        assert report_b.metadata["promotion_status"] == "blocked"
        assert "promotion_invocation_point" in report_b.metadata["promotion_missing_slots"]
        assert "promotion_result_handoff" in report_b.metadata["promotion_missing_slots"]

    def test_report_inherits_construct_path_as_tuple(self):
        """Reports inherit construct_path from instance as tuple, not string"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=[],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        
        instances = checker.extract_instances(context)
        candidate_instance = [i for i in instances if i.construct_type == "WORKER_CANDIDATE"][0]
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        candidate_report = checker.check_instance(
            candidate_instance, registry.get("WORKER_CANDIDATE"), context
        )
        promotion_report = checker.check_instance(
            promotion_instance, registry.get("WORKER_PROMOTION"), context
        )
        
        # Verify construct_path is tuple, not string
        assert isinstance(candidate_report.construct_path, tuple)
        assert candidate_report.construct_path == ("worker_plan", "candidates", "cand_1")
        
        assert isinstance(promotion_report.construct_path, tuple)
        assert promotion_report.construct_path == ("worker_plan", "promotion", "cand_1")

    def test_handoff_report_preserves_source_spans(self):
        """Handoff report preserves source_span_ids from instance"""
        worker_main = WorkerSpecIR(
            worker_id="worker_main",
            worker_name="Main",
            kind="main",
            purpose="Main worker",
            owned_span_ids=["s1"],
            input_contract=[],
            output_contract=[],
            depends_on=[],
            constraints=[],
            boundary_kind="main_worker",
            decision_evidence=[],
            reason="",
        )
        
        worker_child = WorkerSpecIR(
            worker_id="worker_child",
            worker_name="Child",
            kind="child",
            purpose="Child worker",
            owned_span_ids=["s2"],
            input_contract=[{"name": "input1", "type": "string"}],
            output_contract=[{"name": "output1", "type": "string"}],
            depends_on=[],
            constraints=[],
            boundary_kind="child_worker",
            decision_evidence=[],
            reason="",
        )
        
        handoff = WorkerHandoffIR(
            handoff_id="handoff_1",
            from_worker="worker_main",
            to_worker="worker_child",
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[{"from": "x", "to": "input1"}],
            output_bindings=[{"from": "output1", "to": "y"}],
            invoke_location_hint=InvokeLocationHintIR(
                flow_kind="main",
                flow_id=None,
                after_span_id="s3",
                before_span_id="s4",
                block_hint="sequential",
            ),
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[worker_main, worker_child],
            candidates=[],
            decisions=[],
            handoffs=[handoff],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_HANDOFF")
        
        instances = checker.extract_instances(context)
        handoff_instance = [i for i in instances if i.construct_type == "WORKER_HANDOFF"][0]
        
        # Verify instance has source spans from invoke_location_hint
        assert "s3" in handoff_instance.source_span_ids
        assert "s4" in handoff_instance.source_span_ids
        
        report = checker.check_instance(handoff_instance, irs, context)
        
        # Verify report preserves source spans
        assert "s3" in report.source_span_ids
        assert "s4" in report.source_span_ids
        
        # Verify slots also use handoff source spans
        for slot in report.slots:
            if slot.status == "satisfied":
                assert "s3" in slot.source_span_ids or "s4" in slot.source_span_ids

    def test_promotion_blocked_when_handoff_target_worker_missing(self):
        """Promotion blocked when handoff exists but target worker doesn't exist"""
        from nl2spl.ir.worker_plan_ir import WorkerBoundaryDecisionIR
        
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1", "s2"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=["input1"],
            possible_outputs=["output1"],
            signals=["delegation"],
            risks=[],
        )
        
        decision = WorkerBoundaryDecisionIR(
            candidate_id="cand_1",
            decision="extract_child_worker",
            boundary_strength="strong",
            boundary_kind="child_worker",
            rejection_reason=None,
            reason="Extracted as child worker",
        )
        
        # Handoff points to non-existent worker_child
        handoff = WorkerHandoffIR(
            handoff_id="handoff_1",
            from_worker="worker_main",
            to_worker="worker_child",  # This worker doesn't exist
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[{"from": "x", "to": "input1"}],
            output_bindings=[{"from": "output1", "to": "y"}],
            invoke_location_hint=InvokeLocationHintIR(
                flow_kind="main",
                flow_id=None,
                after_span_id="s1",  # Overlaps with candidate
                before_span_id=None,
                block_hint="sequential",
            ),
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],  # No child worker materialized
            candidates=[candidate],
            decisions=[decision],
            handoffs=[handoff],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        
        instances = checker.extract_instances(context)
        promotion_instance = [i for i in instances if i.construct_type == "WORKER_PROMOTION"][0]
        
        report = checker.check_instance(promotion_instance, irs, context)
        
        # Without materialized child worker, promotion must be blocked
        assert report.completeness == "partial"
        assert report.metadata["promotion_status"] == "blocked"
        # Should be missing invocation_point and/or result_handoff
        assert (
            "promotion_invocation_point" in report.metadata["promotion_missing_slots"]
            or "promotion_result_handoff" in report.metadata["promotion_missing_slots"]
        )

    def test_handoff_no_edge_when_target_worker_missing(self):
        """Handoff doesn't create graph edge when target worker doesn't exist"""
        worker_main = WorkerSpecIR(
            worker_id="worker_main",
            worker_name="Main",
            kind="main",
            purpose="Main worker",
            owned_span_ids=["s1"],
            input_contract=[],
            output_contract=[],
            depends_on=[],
            constraints=[],
            boundary_kind="main_worker",
            decision_evidence=[],
            reason="",
        )
        
        # Handoff to non-existent worker
        handoff = WorkerHandoffIR(
            handoff_id="handoff_1",
            from_worker="worker_main",
            to_worker="worker_child",  # Doesn't exist
            api_ref=None,
            mode="invoke",
            condition_text=None,
            ordering="after",
            input_bindings=[{"from": "x", "to": "input1"}],
            output_bindings=[{"from": "output1", "to": "y"}],
            invoke_location_hint=InvokeLocationHintIR(
                flow_kind="main",
                flow_id=None,
                after_span_id="s1",
                before_span_id=None,
                block_hint="sequential",
            ),
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[worker_main],  # No child worker
            candidates=[],
            decisions=[],
            handoffs=[handoff],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_HANDOFF")
        
        instances = checker.extract_instances(context)
        handoff_instance = [i for i in instances if i.construct_type == "WORKER_HANDOFF"][0]
        
        report = checker.check_instance(handoff_instance, irs, context)
        
        # Target should be missing
        target_slot = next(s for s in report.slots if s.slot_name == "target")
        assert target_slot.status == "missing"
        
        # Should not create graph edge to non-existent worker
        assert len(report.related_edges) == 0

    def test_non_worker_candidate_not_promoted(self):
        """Non-worker candidates (constraint, exception, etc.) don't produce WORKER_PROMOTION"""
        constraint_candidate = CandidateTaskUnitIR(
            candidate_id="cand_constraint",
            source_span_ids=["s1"],
            task_text="Constraint task",
            purpose="Constraint",
            candidate_kind="constraint",  # Not a worker candidate
            possible_inputs=[],
            possible_outputs=[],
            signals=[],
            risks=[],
        )
        
        exception_candidate = CandidateTaskUnitIR(
            candidate_id="cand_exception",
            source_span_ids=["s2"],
            task_text="Exception task",
            purpose="Exception",
            candidate_kind="exception_flow",  # Not a worker candidate
            possible_inputs=[],
            possible_outputs=[],
            signals=[],
            risks=[],
        )
        
        worker_candidate = CandidateTaskUnitIR(
            candidate_id="cand_worker",
            source_span_ids=["s3"],
            task_text="Worker task",
            purpose="Worker",
            candidate_kind="explicit_delegation",  # Worker candidate
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=[],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[constraint_candidate, exception_candidate, worker_candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        
        instances = checker.extract_instances(context)
        
        # Should only extract instances for worker candidate
        candidate_instances = [i for i in instances if i.construct_type == "WORKER_CANDIDATE"]
        promotion_instances = [i for i in instances if i.construct_type == "WORKER_PROMOTION"]
        
        assert len(candidate_instances) == 1
        assert candidate_instances[0].construct_id == "worker_candidate:cand_worker"
        
        assert len(promotion_instances) == 1
        assert promotion_instances[0].construct_id == "worker_promotion:cand_worker"


# ===========================================================================
# Runner Integration Tests
# ===========================================================================


class TestR4RunnerIntegration:
    """Test IRSRunner + WorkerDelegationIRSChecker integration"""

    def test_runner_with_checker_produces_reports_and_diagnostics(self):
        """Runner + checker + projector produces reports and diagnostics"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_draft",
            source_span_ids=["s2"],
            task_text="Draft using templates",
            purpose="Drafting can be delegated",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["explicit_delegation"],
            risks=["no_clear_input_contract", "no_clear_output_contract"],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        # Setup runner with checker and projector
        checker_registry = IRSCheckerRegistry()
        checker = WorkerDelegationIRSChecker()
        checker_registry.register(checker)
        
        construct_registry = SPLConstructRegistry.default()
        projector = DiagnosticProjector()
        
        runner = IRSRunner(
            registry=checker_registry,
            construct_registry=construct_registry,
            projector=projector,
        )
        
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        result = runner.run_stage("stage3_5", context)
        
        # Verify reports
        assert len(result.reports) == 2  # WORKER_CANDIDATE + WORKER_PROMOTION
        
        candidate_reports = [r for r in result.reports if r.construct_type == "WORKER_CANDIDATE"]
        promotion_reports = [r for r in result.reports if r.construct_type == "WORKER_PROMOTION"]
        
        assert len(candidate_reports) == 1
        assert len(promotion_reports) == 1
        
        # Verify diagnostics
        assert len(result.diagnostics) > 0
        
        # All diagnostics should be type_or_contract_ambiguity
        for diagnostic in result.diagnostics:
            assert diagnostic.kind == "type_or_contract_ambiguity"
            assert diagnostic.missing_slot is not None
            assert diagnostic.missing_slot.slot_name in [
                "promotion_input_contract",
                "promotion_output_contract",
                "promotion_invocation_point",
                "promotion_result_handoff",
            ]

    def test_runner_without_worker_plan_returns_empty(self):
        """Runner with no worker_plan returns empty result"""
        checker_registry = IRSCheckerRegistry()
        checker = WorkerDelegationIRSChecker()
        checker_registry.register(checker)
        
        construct_registry = SPLConstructRegistry.default()
        projector = DiagnosticProjector()
        
        runner = IRSRunner(
            registry=checker_registry,
            construct_registry=construct_registry,
            projector=projector,
        )
        
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=None)
        result = runner.run_stage("stage3_5", context)
        
        assert len(result.reports) == 0
        assert len(result.diagnostics) == 0
        assert len(result.warnings) == 0

    def test_no_unknown_construct_warnings(self):
        """Runner does not produce unknown construct warnings for R4 constructs"""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=[],
        )
        
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        
        checker_registry = IRSCheckerRegistry()
        checker = WorkerDelegationIRSChecker()
        checker_registry.register(checker)
        
        construct_registry = SPLConstructRegistry.default()
        projector = DiagnosticProjector()
        
        runner = IRSRunner(
            registry=checker_registry,
            construct_registry=construct_registry,
            projector=projector,
        )
        
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        result = runner.run_stage("stage3_5", context)
        
        # No warnings about unknown construct types
        unknown_warnings = [
            w for w in result.warnings if "Unknown construct type" in w
        ]
        assert len(unknown_warnings) == 0


# ===========================================================================
# R10 Phase 1: Metadata propagation tests
# ===========================================================================


class TestR10MetadataPropagation:
    """Verify delegation provenance fields flow from instance → report."""

    def test_promotion_report_carries_delegation_metadata_from_instance(self):
        """ConstructSatisfactionReport.metadata includes
        original_semantic_role, original_source_span_ids,
        synthetic_from_route_annotation from ConstructInstance.metadata.
        """
        routes = FieldRouteIR(
            behavior=["s_delegate"],
            annotations=[
                RouteAnnotation(
                    span_id="s_delegate",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                )
            ],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", routes=routes)
        instances = checker.extract_instances(context)
        promotion_instance = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        report = checker.check_instance(promotion_instance, irs, context)

        # Report metadata MUST carry delegation provenance for Phase 4
        assert report.metadata.get("synthetic_from_route_annotation") is True
        assert report.metadata.get("original_semantic_role") == "delegation_intent"
        assert report.metadata.get("original_source_span_ids") == ["s_delegate"]

    def test_candidate_report_carries_delegation_metadata_from_instance(self):
        """WORKER_CANDIDATE report also propagates provenance metadata."""
        routes = FieldRouteIR(
            behavior=["s_delegate"],
            annotations=[
                RouteAnnotation(
                    span_id="s_delegate",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                )
            ],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", routes=routes)
        instances = checker.extract_instances(context)
        candidate_instance = [
            i for i in instances if i.construct_type == "WORKER_CANDIDATE"
        ][0]
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_CANDIDATE")
        report = checker.check_instance(candidate_instance, irs, context)

        assert report.metadata.get("synthetic_from_route_annotation") is True
        assert report.metadata.get("original_semantic_role") == "delegation_intent"

    def test_real_candidate_report_has_no_synthetic_flag(self):
        """Real (non-synthetic) candidate report does NOT leak synthetic flag."""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=[],
        )
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        instances = checker.extract_instances(context)
        promotion_instance = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        report = checker.check_instance(promotion_instance, irs, context)

        assert report.metadata.get("synthetic_from_route_annotation") is None
        assert report.metadata.get("original_semantic_role") is None


# ===========================================================================
# R10 Phase 1: Correct span-per-candidate matching
# ===========================================================================


class TestR10DelegationSpanMatching:
    """Verify delegation annotation spans only merge into matching candidates."""

    def test_only_matching_delegation_span_merged_into_candidate(self):
        """Two delegation annotations, candidate covers only one.
        The candidate must only receive the matching span, not the other."""
        routes = FieldRouteIR(
            behavior=["s_delegate_a", "s_delegate_b"],
            annotations=[
                RouteAnnotation(
                    span_id="s_delegate_a",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s_delegate_b",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                ),
            ],
        )
        # Candidate only covers s_delegate_a
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s_delegate_a", "s_task"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=[],
        )
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(
            stage_name="stage3_5", routes=routes, worker_plan=plan
        )
        instances = checker.extract_instances(context)

        # Total: cand_1 candidate + promotion + del_s_delegate_b synth candidate + promotion = 4
        assert len(instances) == 4

        # Find the candidate instance
        cand_instances = [
            i for i in instances
            if i.construct_type == "WORKER_CANDIDATE"
            and i.construct_id == "worker_candidate:cand_1"
        ]
        assert len(cand_instances) == 1
        cand_instance = cand_instances[0]

        # Must have s_delegate_a merged in, but NOT s_delegate_b
        assert "s_delegate_a" in cand_instance.source_span_ids
        assert "s_delegate_b" not in cand_instance.source_span_ids, (
            "Bug: candidate received unrelated delegation span s_delegate_b"
        )
        assert cand_instance.metadata.get("original_semantic_role") == "delegation_intent"
        assert cand_instance.metadata.get("original_source_span_ids") == ["s_delegate_a"]

        # The uncovered span s_delegate_b must have its own synthetic candidate
        synth_instances = [
            i for i in instances
            if i.construct_type == "WORKER_CANDIDATE"
            and "del_s_delegate_b" in i.construct_id
        ]
        assert len(synth_instances) == 1
        synth = synth_instances[0]
        assert synth.metadata.get("synthetic_from_route_annotation") is True
        assert synth.source_span_ids == ["s_delegate_b"]

    def test_two_candidates_each_with_own_delegation_match(self):
        """Each candidate only gets its own matching delegation span."""
        routes = FieldRouteIR(
            behavior=["s_del_a", "s_del_b"],
            annotations=[
                RouteAnnotation(
                    span_id="s_del_a",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                ),
                RouteAnnotation(
                    span_id="s_del_b",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                ),
            ],
        )
        # Two candidates, each matching one delegation span
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[
                CandidateTaskUnitIR(
                    candidate_id="cand_a",
                    source_span_ids=["s_del_a"],
                    task_text="Task A",
                    purpose="Purpose A",
                    candidate_kind="explicit_delegation",
                    possible_inputs=[],
                    possible_outputs=[],
                    signals=["delegation"],
                    risks=[],
                ),
                CandidateTaskUnitIR(
                    candidate_id="cand_b",
                    source_span_ids=["s_del_b"],
                    task_text="Task B",
                    purpose="Purpose B",
                    candidate_kind="explicit_delegation",
                    possible_inputs=[],
                    possible_outputs=[],
                    signals=["delegation"],
                    risks=[],
                ),
            ],
            decisions=[],
            handoffs=[],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(
            stage_name="stage3_5", routes=routes, worker_plan=plan
        )
        instances = checker.extract_instances(context)

        # 2 real candidates × 2 types + 0 synthetic (both covered) = 4
        assert len(instances) == 4

        # cand_a has only s_del_a
        cand_a = [
            i for i in instances
            if i.construct_id == "worker_candidate:cand_a"
        ][0]
        assert "s_del_a" in cand_a.source_span_ids
        assert "s_del_b" not in cand_a.source_span_ids
        assert cand_a.metadata.get("original_source_span_ids") == ["s_del_a"]

        # cand_b has only s_del_b
        cand_b = [
            i for i in instances
            if i.construct_id == "worker_candidate:cand_b"
        ][0]
        assert "s_del_b" in cand_b.source_span_ids
        assert "s_del_a" not in cand_b.source_span_ids
        assert cand_b.metadata.get("original_source_span_ids") == ["s_del_b"]


# ===========================================================================
# R10 Phase 2B: Synthetic candidate acceptance tests
# ===========================================================================


class TestR10SyntheticCandidatePhase2B:
    """Phase 2B synthetic compatibility path acceptance.

    Synthetic candidates from bare route annotations must:
      - Be candidate_only, not materialized
      - Be non-renderable
      - Not generate materialized worker / handoff / invoke constructs
      - Carry synthetic_from_route_annotation=True
    """

    def _make_routes(self):
        return FieldRouteIR(
            behavior=["s_delegate"],
            annotations=[
                RouteAnnotation(
                    span_id="s_delegate",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                )
            ],
        )

    def test_synthetic_candidate_is_candidate_only(self):
        """Synthetic WORKER_CANDIDATE is candidate_only=True, materialized=False."""
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", routes=self._make_routes())
        instances = checker.extract_instances(context)

        for i in instances:
            assert i.candidate_only is True
            assert i.materialized is False

    def test_synthetic_promotion_is_not_renderable(self):
        """Synthetic WORKER_PROMOTION report is renderable=False."""
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", routes=self._make_routes())
        instances = checker.extract_instances(context)
        promotion_instance = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        report = checker.check_instance(promotion_instance, irs, context)

        assert report.renderable is False, (
            "Phase 2B: synthetic promotion must NOT be renderable"
        )

    def test_synthetic_instances_not_materialized_worker_or_handoff(self):
        """No CHILD_WORKER or WORKER_HANDOFF instances from bare annotation."""
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", routes=self._make_routes())
        instances = checker.extract_instances(context)

        types = {i.construct_type for i in instances}
        assert "CHILD_WORKER" not in types
        assert "WORKER_HANDOFF" not in types
        assert types == {"WORKER_CANDIDATE", "WORKER_PROMOTION"}

    def test_synthetic_promotion_slots_have_blocked_frontier(self):
        """Synthetic promotion (no contracts, no handoff) is cutline_blocked."""
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", routes=self._make_routes())
        instances = checker.extract_instances(context)
        promotion_instance = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        report = checker.check_instance(promotion_instance, irs, context)

        assert report.frontier_status == "cutline_blocked"
        assert report.cutline_reason == "missing_promotion_contract"
        assert report.metadata["promotion_status"] == "blocked"
        # All four slots missing
        missing = {s.slot_name for s in report.slots if s.status == "missing"}
        assert missing == {
            "promotion_input_contract",
            "promotion_output_contract",
            "promotion_invocation_point",
            "promotion_result_handoff",
        }

    def test_synthetic_does_not_bypass_planner_decision(self):
        """Synthetic promotion never reports promotion_status=ready
        without an actual planner decision. The invocation_point
        check may relax the accepted-decision requirement via
        has_accepted_decision or is_synthetic, but without a real
        handoff match it must still be blocked.
        """
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", routes=self._make_routes())
        instances = checker.extract_instances(context)
        promotion_instance = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        registry = SPLConstructRegistry.default()
        irs = registry.get("WORKER_PROMOTION")
        report = checker.check_instance(promotion_instance, irs, context)

        assert report.metadata["promotion_status"] == "blocked", (
            "Phase 2B: synthetic promotion without handoff match must be blocked"
        )

    def test_synthetic_with_handoff_but_no_decision_is_blocked(self):
        """P3 observation: synthetic with matching handoff hint but no
        accepted decision. invocation_point is satisfied (relaxed check),
        but promotion is still blocked because input/output contracts are
        missing on the synthetic candidate.
        """
        routes = self._make_routes()
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="Main",
                    kind="main",
                    purpose="Main",
                    boundary_kind="main_worker",
                ),
                WorkerSpecIR(
                    worker_id="worker_child",
                    worker_name="Child",
                    kind="child",
                    purpose="Child",
                    boundary_kind="child_worker",
                ),
            ],
            handoffs=[
                WorkerHandoffIR(
                    handoff_id="h1",
                    from_worker="worker_main",
                    to_worker="worker_child",
                    api_ref=None,
                    mode="invoke",
                    condition_text=None,
                    ordering="after",
                    input_bindings=[
                        InputBindingIR(
                            parent_variable="x", child_input="y", required=True,
                        )
                    ],
                    output_bindings=[
                        OutputBindingIR(
                            child_output="z", parent_variable="w",
                            required=True, merge_strategy="set",
                        )
                    ],
                    invoke_location_hint=InvokeLocationHintIR(
                        flow_kind="main",
                        flow_id=None,
                        after_span_id="s_delegate",
                        before_span_id=None,
                        block_hint="sequential",
                    ),
                )
            ],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(
            stage_name="stage3_5", routes=routes, worker_plan=plan,
        )
        instances = checker.extract_instances(context)
        promotion_instance = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        irs = SPLConstructRegistry.default().get("WORKER_PROMOTION")
        report = checker.check_instance(promotion_instance, irs, context)

        # invocation_point IS satisfied (synthetic relaxes decision check)
        inv_slot = next(
            s for s in report.slots
            if s.slot_name == "promotion_invocation_point"
        )
        assert inv_slot.status == "satisfied", (
            "Phase 2B: synthetic invocation_point is satisfied via "
            "handoff hint match (decision check relaxed)"
        )
        # result_handoff is also satisfied
        res_slot = next(
            s for s in report.slots
            if s.slot_name == "promotion_result_handoff"
        )
        assert res_slot.status == "satisfied"

        # But input/output contracts are missing → still blocked
        assert report.metadata["promotion_status"] == "blocked"
        assert "promotion_input_contract" in report.metadata["promotion_missing_slots"]
        assert "promotion_output_contract" in report.metadata["promotion_missing_slots"]


# ===========================================================================
# R10 Phase 2: Signal preservation — every delegation annotation is covered
# ===========================================================================


class TestR10DelegationSignalPreservation:
    """Phase 2: Every confirmed delegation_intent source signal must be
    represented by WORKER_CANDIDATE / WORKER_PROMOTION or explicit warning.

    Never: only TraceRecord, no candidate, no promotion, silent loss.
    """

    def test_single_annotation_produces_candidate_and_promotion(self):
        """One delegation annotation → one WORKER_CANDIDATE + one WORKER_PROMOTION."""
        routes = FieldRouteIR(
            behavior=["s_del"],
            annotations=[
                RouteAnnotation(
                    span_id="s_del",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                )
            ],
        )
        checker = WorkerDelegationIRSChecker()
        instances = checker.extract_instances(
            IRSCheckContext(stage_name="stage3_5", routes=routes)
        )
        types = {i.construct_type for i in instances}
        assert types == {"WORKER_CANDIDATE", "WORKER_PROMOTION"}
        assert len(instances) == 2

    def test_two_annotations_produce_two_pairs(self):
        """Two delegation annotations → 2×2 = 4 instances."""
        routes = FieldRouteIR(
            behavior=["s_a", "s_b"],
            annotations=[
                RouteAnnotation(
                    span_id="s_a", field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary", executable=False,
                ),
                RouteAnnotation(
                    span_id="s_b", field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary", executable=False,
                ),
            ],
        )
        checker = WorkerDelegationIRSChecker()
        instances = checker.extract_instances(
            IRSCheckContext(stage_name="stage3_5", routes=routes)
        )
        assert len(instances) == 4
        candidate_ids = {
            i.construct_id for i in instances
            if i.construct_type == "WORKER_CANDIDATE"
        }
        assert candidate_ids == {
            "worker_candidate:del_s_a",
            "worker_candidate:del_s_b",
        }

    def test_annotation_covered_by_candidate_not_duplicated(self):
        """Delegation annotation whose span is already in a candidate's
        source_span_ids does NOT create a duplicate synthetic instance."""
        routes = FieldRouteIR(
            behavior=["s_del"],
            annotations=[
                RouteAnnotation(
                    span_id="s_del", field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary", executable=False,
                )
            ],
        )
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s_del"],  # covers the delegation annotation
            task_text="Task", purpose="Purpose",
            candidate_kind="explicit_delegation",
        )
        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            candidates=[candidate],
        )
        checker = WorkerDelegationIRSChecker()
        instances = checker.extract_instances(
            IRSCheckContext(
                stage_name="stage3_5", routes=routes, worker_plan=plan,
            )
        )
        # Exactly 2 instances: cand_1 candidate + promotion (no synthetic!)
        assert len(instances) == 2
        ids = {i.construct_id for i in instances}
        assert ids == {
            "worker_candidate:cand_1",
            "worker_promotion:cand_1",
        }

    def test_zero_delegation_annotations_produces_no_synthetic(self):
        """No delegation annotations → only real candidates, no synthetic."""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task", purpose="Purpose",
            candidate_kind="explicit_delegation",
        )
        plan = WorkerPlanIR(
            main_worker_id="worker_main", candidates=[candidate],
        )
        checker = WorkerDelegationIRSChecker()
        instances = checker.extract_instances(
            IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        )
        assert len(instances) == 2
        for i in instances:
            assert i.metadata.get("synthetic_from_route_annotation") is None

    def test_signal_not_lost_even_with_empty_worker_plan(self):
        """Delegation annotation with empty worker_plan still produces
        synthetic candidate + promotion. No silent signal loss."""
        routes = FieldRouteIR(
            behavior=["s_del"],
            annotations=[
                RouteAnnotation(
                    span_id="s_del", field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary", executable=False,
                )
            ],
        )
        # WorkerPlanIR with no candidates, no workers — just a main_worker_id
        plan = WorkerPlanIR(main_worker_id="worker_main")
        checker = WorkerDelegationIRSChecker()
        instances = checker.extract_instances(
            IRSCheckContext(
                stage_name="stage3_5", routes=routes, worker_plan=plan,
            )
        )
        # Must have synthetic candidate + promotion
        assert len(instances) == 2
        assert all(
            i.metadata.get("synthetic_from_route_annotation") is True
            for i in instances
        )

    def test_each_covered_annotation_has_diagnostic_or_warning(self):
        """Every uncovered delegation annotation produces type_or_contract_ambiguity
        diagnostic via WORKER_PROMOTION IRS projection. No silent loss."""
        routes = FieldRouteIR(
            behavior=["s_del"],
            annotations=[
                RouteAnnotation(
                    span_id="s_del", field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary", executable=False,
                )
            ],
        )
        plan = WorkerPlanIR(main_worker_id="worker_main")
        checker_registry = IRSCheckerRegistry()
        checker_registry.register(WorkerDelegationIRSChecker())
        runner = IRSRunner(
            registry=checker_registry,
            construct_registry=SPLConstructRegistry.default(),
            projector=DiagnosticProjector(),
        )
        result = runner.run_stage(
            "stage3_5",
            IRSCheckContext(
                stage_name="stage3_5", routes=routes, worker_plan=plan,
            ),
        )

        # Must have at least one diagnostic from WORKER_PROMOTION
        diags = [
            d for d in result.diagnostics
            if d.kind == "type_or_contract_ambiguity"
            and (d.target_ref or "").startswith("worker_promotion:")
        ]
        assert len(diags) >= 1, (
            "Phase 2: delegation annotation must produce at least one "
            "type_or_contract_ambiguity diagnostic — signal not lost"
        )
        # The report must exist
        promotion_reports = [
            r for r in result.reports
            if r.construct_type == "WORKER_PROMOTION"
        ]
        assert len(promotion_reports) >= 1
        # All synthetic reports are non-renderable
        for r in promotion_reports:
            if r.metadata.get("synthetic_from_route_annotation"):
                assert r.renderable is False, (
                    "Phase 2B: synthetic report must not be renderable"
                )
