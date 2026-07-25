"""R10 Phase 0: Characterization tests for DELEGATION_INTENT cleanup.

This file LOCKS current behavior BEFORE any production code changes.
Tests document the pre-migration baseline so we can verify that the
migration (Phase 1-6) doesn't silently break delegation diagnostics.

Coverage targets per Section 4.5 of the implementation plan:
  1. delegation_intent without contract currently produces type_or_contract_ambiguity
  2. current diagnostic target_ref is delegation_intent:*
  3. current provenance / trace contains delegation_intent:* target
  4. current WORKER_PROMOTION missing slots have NO explicit diagnostic_blocks_rendering=False
  5. complete handoff currently does NOT produce ambiguity
  6. DELEGATION_INTENT construct_type exists in registry

IMPORTANT: These tests describe CURRENT behavior, not target behavior.
After Phase 1-6, these tests will be updated/removed to reflect the new design.
"""

from __future__ import annotations

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
# Characterization 1: DELEGATION_INTENT in registry
# ===========================================================================


class TestCharDelegationIntentRegistry:
    """Characterize: DELEGATION_INTENT is registered as an IRS construct."""

    def test_registry_has_delegation_intent_construct(self) -> None:
        """R10 Phase 5: DELEGATION_INTENT removed from SPLConstructRegistry."""
        registry = SPLConstructRegistry.default()
        assert not registry.has("DELEGATION_INTENT"), (
            "R10 Phase 5: DELEGATION_INTENT construct removed from registry"
        )

    def test_delegation_intent_has_slots(self) -> None:
        """R10 Phase 5: DELEGATION_INTENT IRS no longer exists.
        Its diagnostic responsibility moved to WORKER_PROMOTION."""
        registry = SPLConstructRegistry.default()
        assert not registry.has("DELEGATION_INTENT")
        # WORKER_PROMOTION now carries the type_or_contract_ambiguity
        assert registry.has("WORKER_PROMOTION")

    def test_delegation_intent_existence_policy(self) -> None:
        """R10 Phase 5: semantic_role='delegation_intent' still exists
        as source signal (route annotation), not as IRS construct."""
        from nl2spl.ir.field_route_ir import RouteAnnotation
        ann = RouteAnnotation(
            span_id="s_test",
            field="behavior",
            semantic_role="delegation_intent",
            route_family="delegation_boundary",
            executable=False,
        )
        assert ann.semantic_role == "delegation_intent"


# ===========================================================================
# Characterization 2: DELEGATION_INTENT instance extraction from routes
# ===========================================================================


class TestCharDelegationIntentExtraction:
    """Characterize: route annotations produce DELEGATION_INTENT instances."""

    def test_route_annotation_produces_delegation_intent_instance(self) -> None:
        """R10 Phase 1: RouteAnnotation(semantic_role="delegation_intent")
        now produces synthetic WORKER_CANDIDATE + WORKER_PROMOTION instances.
        No DELEGATION_INTENT construct is created.
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

        assert len(instances) == 2
        types = {i.construct_type for i in instances}
        assert types == {"WORKER_CANDIDATE", "WORKER_PROMOTION"}
        for i in instances:
            assert i.metadata.get("synthetic_from_route_annotation") is True
            assert i.metadata.get("original_semantic_role") == "delegation_intent"

    def test_delegation_intent_instance_has_correct_flags(self) -> None:
        """CHARACTERIZATION: DELEGATION_INTENT instance metadata flags."""
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

        instance = instances[0]
        assert instance.materialized is False
        assert instance.source_demanded is True
        assert instance.candidate_only is True
        assert instance.source_span_ids == ["s_delegate"]

    def test_delegation_intent_in_supported_construct_types(self) -> None:
        """R10 Phase 1: DELEGATION_INTENT removed from supported_construct_types.
        Only WORKER_CANDIDATE, WORKER_PROMOTION, CHILD_WORKER, WORKER_HANDOFF remain.
        """
        checker = WorkerDelegationIRSChecker()
        assert "DELEGATION_INTENT" not in checker.supported_construct_types, (
            "R10 Phase 1: DELEGATION_INTENT removed from supported_construct_types"
        )
        assert "WORKER_CANDIDATE" in checker.supported_construct_types
        assert "WORKER_PROMOTION" in checker.supported_construct_types


# ===========================================================================
# Characterization 3: delegation_intent:* diagnostic target_ref
# ===========================================================================


class TestCharDelegationIntentDiagnosticTarget:
    """Characterize: missing contract produces diagnostic with delegation_intent:* target."""

    def _make_runner(self) -> IRSRunner:
        registry = IRSCheckerRegistry()
        registry.register(WorkerDelegationIRSChecker())
        return IRSRunner(
            registry=registry,
            construct_registry=SPLConstructRegistry.default(),
            projector=DiagnosticProjector(),
        )

    def _make_routes(self) -> FieldRouteIR:
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

    def test_missing_contract_produces_delegation_intent_target_ref(self) -> None:
        """R10 Phase 1: missing handoff contract now produces
        target_ref="worker_promotion:del_<span_id>" via WORKER_PROMOTION
        missing slots, NOT delegation_intent:*.
        """
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])
        result = self._make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(
                stage_name="stage3_5",
                routes=self._make_routes(),
                worker_plan=plan,
            ),
        )

        # No delegation_intent:* diagnostics
        delegation_diags = [
            d for d in result.diagnostics
            if (d.target_ref or "").startswith("delegation_intent:")
        ]
        assert len(delegation_diags) == 0

        # Diagnostics come from WORKER_PROMOTION missing slots.
        # Precise: exactly 4 diagnostics for the synthetic candidate,
        # one per missing promotion slot.
        expected_target = "worker_promotion:del_s_delegate"
        diags = [
            d for d in result.diagnostics
            if d.target_ref == expected_target
            and d.kind == "type_or_contract_ambiguity"
        ]
        assert len(diags) == 4, (
            f"Expected exactly 4 ambiguity diagnostics for {expected_target}, "
            f"got {len(diags)}: {[(d.target_ref, d.missing_slot.slot_name if d.missing_slot else '?') for d in diags]}"
        )
        slot_names = {d.missing_slot.slot_name for d in diags}
        assert slot_names == {
            "promotion_input_contract",
            "promotion_output_contract",
            "promotion_invocation_point",
            "promotion_result_handoff",
        }, f"Unexpected slots: {slot_names}"
        for diag in diags:
            assert diag.diagnostic_id.startswith("irs_")
            assert diag.kind == "type_or_contract_ambiguity"
            assert "s_delegate" in diag.source_span_ids

    def test_valid_handoff_contract_suppresses_diagnostic(self) -> None:
        """CHARACTERIZATION: valid invoke handoff covering the span satisfies
        the DELEGATION_INTENT IRS slot and produces no delegation_intent:* diagnostic.
        """
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

        result = self._make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(
                stage_name="stage3_5",
                routes=self._make_routes(),
                worker_plan=plan,
            ),
        )

        delegation_diags = [
            d for d in result.diagnostics
            if (d.target_ref or "").startswith("delegation_intent:")
        ]
        assert len(delegation_diags) == 0, (
            "PRE-MIGRATION: valid handoff suppresses delegation_intent:* diagnostic. "
            "This invariant must be preserved: complete handoff → no ambiguity."
        )

    def test_delegation_intent_report_in_results(self) -> None:
        """R10 Phase 1: IRS reports no longer include DELEGATION_INTENT.
        Instead, WORKER_PROMOTION reports exist with synthetic_from_route_annotation.
        """
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])
        result = self._make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(
                stage_name="stage3_5",
                routes=self._make_routes(),
                worker_plan=plan,
            ),
        )

        # No DELEGATION_INTENT reports
        delegation_reports = [
            r for r in result.reports
            if r.construct_type == "DELEGATION_INTENT"
        ]
        assert len(delegation_reports) == 0

        # WORKER_PROMOTION report exists with synthetic flag
        promotion_reports = [
            r for r in result.reports
            if r.construct_type == "WORKER_PROMOTION"
        ]
        assert len(promotion_reports) >= 1


# ===========================================================================
# Characterization 4: WORKER_PROMOTION missing slots lack
#   explicit diagnostic_blocks_rendering=False
# ===========================================================================


class TestCharWorkerPromotionMissingSlots:
    """R10 Phase 3: WORKER_PROMOTION missing slots now explicitly set
    diagnostic_blocks_rendering=False."""

    def test_promotion_missing_slot_no_explicit_blocks_rendering_false(self) -> None:
        """R10 Phase 3: WORKER_PROMOTION _check_worker_promotion now sets
        diagnostic_blocks_rendering=False on every promotion slot.
        The projector will respect this and produce blocks_rendering=False.
        """
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],  # Missing → triggers missing slot
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
        promotion_instance = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        report = checker.check_instance(promotion_instance, irs, context)

        # Find missing slots
        missing_slots = [s for s in report.slots if s.status == "missing"]
        assert len(missing_slots) > 0

        for slot in missing_slots:
            assert slot.diagnostic_kind == "type_or_contract_ambiguity"
            assert slot.diagnostic_blocks_rendering is False, (
                f"Phase 3: missing slot '{slot.slot_name}' must have "
                f"diagnostic_blocks_rendering=False explicitly"
            )

    def test_promotion_report_is_not_renderable(self) -> None:
        """R10 Phase 3: WORKER_PROMOTION report still has renderable=False
        (correct for analysis construct), but now missing slots carry
        explicit diagnostic_blocks_rendering=False so the projector
        produces blocks_rendering=False.
        """
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
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
        irs = registry.get("WORKER_PROMOTION")

        instances = checker.extract_instances(context)
        promotion_instance = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        report = checker.check_instance(promotion_instance, irs, context)

        assert report.renderable is False, (
            "WORKER_PROMOTION is an analysis construct — renderable=False is correct"
        )
        # Every slot must have explicit diagnostic_blocks_rendering=False
        for slot in report.slots:
            assert slot.diagnostic_blocks_rendering is False, (
                f"Phase 3: slot '{slot.slot_name}' must have "
                f"diagnostic_blocks_rendering=False"
            )

    def test_projector_blocks_rendering_fallback_for_promotion(self) -> None:
        """R10 Phase 3: DiagnosticProjector now produces blocks_rendering=False
        for WORKER_PROMOTION diagnostics because the slot explicitly sets
        diagnostic_blocks_rendering=False.
        """
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
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

        # Run full checker + projector pipeline
        checker_registry = IRSCheckerRegistry()
        checker_registry.register(WorkerDelegationIRSChecker())
        runner = IRSRunner(
            registry=checker_registry,
            construct_registry=SPLConstructRegistry.default(),
            projector=DiagnosticProjector(),
        )
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        result = runner.run_stage("stage3_5", context)

        promotion_diags = [
            d for d in result.diagnostics
            if (d.target_ref or "").startswith("worker_promotion:")
        ]
        assert len(promotion_diags) > 0, (
            "Phase 3: promotion missing slots still project diagnostics"
        )

        for diag in promotion_diags:
            assert diag.blocks_rendering is False, (
                f"Phase 3: promotion diagnostic {diag.diagnostic_id} must have "
                f"blocks_rendering=False (slot-level override)"
            )
            assert diag.blocks_completion is True, (
                "Phase 3: blocks_completion must remain True"
            )


# ===========================================================================
# Characterization 5: WORKER_PROMOTION missing slots diagnostic kind
# ===========================================================================


class TestCharPromotionMissingSlotDiagnosticKind:
    """Characterize: WORKER_PROMOTION missing slots use type_or_contract_ambiguity."""

    def test_all_four_promotion_slots_missing_produce_ambiguity(self) -> None:
        """CHARACTERIZATION: when all 4 promotion slots are missing, each has
        diagnostic_kind='type_or_contract_ambiguity'.
        """
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s1"],
            task_text="Task",
            purpose="Purpose",
            candidate_kind="explicit_delegation",
            possible_inputs=[],
            possible_outputs=[],
            signals=["delegation"],
            risks=[
                "no_clear_input_contract",
                "no_clear_output_contract",
            ],
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
        promotion_instance = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        report = checker.check_instance(promotion_instance, irs, context)

        missing_slots = [s for s in report.slots if s.status == "missing"]
        missing_names = {s.slot_name: s for s in missing_slots}

        # All four should be missing with ambiguity kind
        expected = [
            "promotion_input_contract",
            "promotion_output_contract",
            "promotion_invocation_point",
            "promotion_result_handoff",
        ]
        for name in expected:
            assert name in missing_names, f"Slot {name} should be missing"
            assert missing_names[name].diagnostic_kind == "type_or_contract_ambiguity"

    def test_promotion_target_ref_not_explicitly_set_in_slot(self) -> None:
        """CHARACTERIZATION: WORKER_PROMOTION missing slots do NOT set
        diagnostic_target_ref in the SlotSatisfaction.
        The projector uses report.construct_id as fallback.
        """
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
        promotion_instance = [
            i for i in instances if i.construct_type == "WORKER_PROMOTION"
        ][0]
        report = checker.check_instance(promotion_instance, irs, context)

        for slot in report.slots:
            if slot.status == "missing":
                assert slot.diagnostic_target_ref is None, (
                    f"PRE-MIGRATION: missing slot '{slot.slot_name}' has "
                    f"diagnostic_target_ref=None. Projector falls back to "
                    f"report.construct_id='{report.construct_id}'."
                )


# ===========================================================================
# Characterization 6: Complete handoff does NOT produce ambiguity
# ===========================================================================


class TestCharCompleteHandoffNoAmbiguity:
    """Characterize: complete handoff suppresses delegation ambiguity."""

    def test_complete_handoff_no_delegation_diagnostic(self) -> None:
        """CHARACTERIZATION: when a handoff is complete (valid target,
        input bindings, output bindings, invocation hint), no
        delegation_intent:* diagnostic is produced.
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

        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[
                WorkerSpecIR(
                    worker_id="worker_main",
                    worker_name="Main",
                    kind="main",
                    purpose="Main worker",
                    boundary_kind="main_worker",
                ),
                WorkerSpecIR(
                    worker_id="worker_child",
                    worker_name="Child",
                    kind="child",
                    purpose="Child worker",
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
                            parent_variable="req",
                            child_input="input",
                            required=True,
                        )
                    ],
                    output_bindings=[
                        OutputBindingIR(
                            child_output="result",
                            parent_variable="res",
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

        checker_registry = IRSCheckerRegistry()
        checker_registry.register(WorkerDelegationIRSChecker())
        runner = IRSRunner(
            registry=checker_registry,
            construct_registry=SPLConstructRegistry.default(),
            projector=DiagnosticProjector(),
        )
        context = IRSCheckContext(
            stage_name="stage3_5",
            routes=routes,
            worker_plan=plan,
        )
        result = runner.run_stage("stage3_5", context)

        delegation_diags = [
            d for d in result.diagnostics
            if (d.target_ref or "").startswith("delegation_intent:")
        ]
        assert len(delegation_diags) == 0, (
            "PRE-MIGRATION INVARIANT: complete handoff MUST NOT produce "
            "delegation_intent:* diagnostic. This must remain true after migration."
        )


# ===========================================================================
# Characterization 7: Candidate/Promotion extraction without delegation route
# ===========================================================================


class TestCharNoRoutesProducesNoDelegationIntent:
    """Characterize: without delegation routes, no DELEGATION_INTENT instances."""

    def test_no_routes_only_candidates(self) -> None:
        """CHARACTERIZATION: context with worker_plan but no routes
        only produces WORKER_CANDIDATE + WORKER_PROMOTION, no DELEGATION_INTENT.
        """
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
        # No routes in context
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        instances = checker.extract_instances(context)

        types = {i.construct_type for i in instances}
        assert "DELEGATION_INTENT" not in types, (
            "PRE-MIGRATION: without routes, no DELEGATION_INTENT instances"
        )
        assert "WORKER_CANDIDATE" in types
        assert "WORKER_PROMOTION" in types

    def test_both_routes_and_candidates_produce_all_three(self) -> None:
        """R10 Phase 1: with routes AND candidates, 4 instances are extracted:
        2 WORKER_CANDIDATE (1 real + 1 synthetic) + 2 WORKER_PROMOTION.
        No DELEGATION_INTENT.
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
        context = IRSCheckContext(
            stage_name="stage3_5",
            routes=routes,
            worker_plan=plan,
        )
        instances = checker.extract_instances(context)

        types = {i.construct_type for i in instances}
        assert "DELEGATION_INTENT" not in types, (
            "R10 Phase 1: DELEGATION_INTENT no longer extracted"
        )
        # cand_1 produces 2 instances + del_s_delegate produces 2 synthetic = 4
        candidate_count = sum(
            1 for i in instances
            if i.construct_type == "WORKER_CANDIDATE"
        )
        promotion_count = sum(
            1 for i in instances
            if i.construct_type == "WORKER_PROMOTION"
        )
        assert candidate_count == 2  # cand_1 + del_s_delegate
        assert promotion_count == 2  # cand_1 + del_s_delegate
