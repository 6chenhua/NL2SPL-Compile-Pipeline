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
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    InvokeLocationHintIR,
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
