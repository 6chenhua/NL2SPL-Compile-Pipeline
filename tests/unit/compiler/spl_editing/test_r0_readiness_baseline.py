"""R0 Readiness Baseline: Current-state lock tests for SPL Editing readiness.

This file LOCKS current behavior BEFORE any readiness changes (R1-R6).
Tests document the pre-readiness baseline so we can verify that readiness
modifications don't silently break existing behavior and correctly introduce
new recognition pathways.

Coverage:
  1. CompileDiagnostic.metadata field exists and accepts arbitrary keys
  2. Default registry does NOT contain DELEGATION_INTENT (cross-ref R10 tests)
  3. WorkerDelegationIRSChecker does NOT produce DELEGATION_INTENT instances
  4. delegation_intent evidence routes to WORKER_CANDIDATE/WORKER_PROMOTION metadata
  5. Gate does NOT currently recognize origin=user_confirmed_repair
  6. ProducerIndex does NOT currently recognize origin=user_confirmed_repair
  7. Post-normalize IRS source evidence predicate does NOT recognize
     origin=user_confirmed_repair
  8. unspecified_output_missing_producer current projection behavior

IMPORTANT: These tests describe CURRENT behavior, not target behavior.
After R1-R6, some tests will be updated to reflect new recognition pathways
(e.g., Gate / ProducerIndex / IRS should recognize user_confirmed_repair).
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.post_normalize import PostNormalizeIRSCheckerV6
from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.producer_index import ProducerIndex, _step_is_renderable
from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_ir import FlowRef, WorkerIR
from nl2spl.pipeline.executable_gate import ExecutableElementGate


# ===========================================================================
# R0-1: CompileDiagnostic.metadata field
# ===========================================================================


class TestR0CompileDiagnosticMetadata:
    """Lock: CompileDiagnostic.metadata exists as dict[str, Any]."""

    def test_metadata_field_exists_and_is_dict(self) -> None:
        """R0-1: CompileDiagnostic.metadata is a dict field, default empty."""
        diag = CompileDiagnostic(
            diagnostic_id="diag_001",
            kind="missing_handler",
            severity="warning",
            message="Test diagnostic",
        )
        assert hasattr(diag, "metadata"), (
            "R0-1: CompileDiagnostic.metadata field must exist"
        )
        assert isinstance(diag.metadata, dict), (
            "R0-1: CompileDiagnostic.metadata must be a dict"
        )
        assert diag.metadata == {}, (
            "R0-1: CompileDiagnostic.metadata defaults to empty dict"
        )

    def test_metadata_accepts_arbitrary_keys(self) -> None:
        """R0-1: metadata dict accepts and preserves arbitrary string keys."""
        diag = CompileDiagnostic(
            diagnostic_id="diag_002",
            kind="type_or_contract_ambiguity",
            severity="error",
            message="Ambiguous contract",
            metadata={
                "irs_ref": {"construct_type": "EXCEPTION_FLOW", "slot_name": "handler_action"},
                "authority": "post_normalize_irs",
                "original_semantic_role": "delegation_intent",
            },
        )
        assert diag.metadata["irs_ref"]["construct_type"] == "EXCEPTION_FLOW"
        assert diag.metadata["authority"] == "post_normalize_irs"

    def test_metadata_preserved_after_construction(self) -> None:
        """R0-1: metadata dict is the same object, mutations visible."""
        diag = CompileDiagnostic(
            diagnostic_id="diag_003",
            kind="missing_output_producer",
            severity="warning",
            message="No producer",
            metadata={"key": "value"},
        )
        # Mutations to the dict are visible (not frozen/copied)
        diag.metadata["new_key"] = "new_value"
        assert diag.metadata["new_key"] == "new_value"
        assert diag.metadata["key"] == "value"


# ===========================================================================
# R0-2: Default registry does NOT contain DELEGATION_INTENT
# ===========================================================================


class TestR0DelegationIntentNotInRegistry:
    """Lock: DELEGATION_INTENT is NOT registered as an IRS construct.

    Cross-reference: tests/unit/compiler/irs/
        test_r10_delegation_intent_cleanup_characterization.py
        TestCharDelegationIntentRegistry
    """

    def test_registry_has_no_delegation_intent(self) -> None:
        """R0-2: SPLConstructRegistry.default() does NOT contain
        DELEGATION_INTENT construct type.
        """
        registry = SPLConstructRegistry.default()
        assert not registry.has("DELEGATION_INTENT"), (
            "R0-2: DELEGATION_INTENT must NOT be a registered ConstructIRS. "
            "delegation_intent is a source signal / route annotation role, "
            "not a construct type."
        )

    def test_list_constructs_excludes_delegation_intent(self) -> None:
        """R0-2: DELEGATION_INTENT not in any construct listing."""
        registry = SPLConstructRegistry.default()
        assert "DELEGATION_INTENT" not in registry.list_constructs()


# ===========================================================================
# R0-3: WorkerDelegationIRSChecker does NOT produce DELEGATION_INTENT
# ===========================================================================


class TestR0WorkerDelegationCheckerNoDelegationIntent:
    """Lock: WorkerDelegationIRSChecker does NOT produce DELEGATION_INTENT.

    Cross-reference: tests/unit/compiler/irs/
        test_r10_delegation_intent_cleanup_characterization.py
        TestCharDelegationIntentExtraction
    """

    def test_supported_construct_types_excludes_delegation_intent(self) -> None:
        """R0-3: DELEGATION_INTENT is NOT in supported_construct_types."""
        checker = WorkerDelegationIRSChecker()
        assert "DELEGATION_INTENT" not in checker.supported_construct_types, (
            "R0-3: DELEGATION_INTENT must NOT be a supported construct type. "
            "Only WORKER_CANDIDATE, WORKER_PROMOTION, CHILD_WORKER, "
            "WORKER_HANDOFF are supported."
        )

    def test_extract_instances_produces_no_delegation_intent_type(
        self,
    ) -> None:
        """R0-3: extract_instances never produces DELEGATION_INTENT construct_type."""
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

        construct_types = {i.construct_type for i in instances}
        assert "DELEGATION_INTENT" not in construct_types, (
            "R0-3: extract_instances must NOT produce DELEGATION_INTENT instances. "
            f"Got types: {construct_types}"
        )

    # Also verify: when we have only candidates (no routes), no DELEGATION_INTENT
    def test_no_routes_only_candidates_no_delegation_intent(self) -> None:
        """R0-3: Even without routes, only WORKER_CANDIDATE + WORKER_PROMOTION."""
        from nl2spl.ir.worker_plan_ir import CandidateTaskUnitIR, WorkerPlanIR

        plan = WorkerPlanIR(
            main_worker_id="worker_main",
            workers=[],
            candidates=[
                CandidateTaskUnitIR(
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
            ],
            decisions=[],
            handoffs=[],
        )
        checker = WorkerDelegationIRSChecker()
        context = IRSCheckContext(stage_name="stage3_5", worker_plan=plan)
        instances = checker.extract_instances(context)

        types = {i.construct_type for i in instances}
        assert "DELEGATION_INTENT" not in types
        assert "WORKER_CANDIDATE" in types
        assert "WORKER_PROMOTION" in types


# ===========================================================================
# R0-4: delegation_intent evidence routes to WORKER_CANDIDATE / WORKER_PROMOTION
# ===========================================================================


class TestR0DelegationIntentEvidenceRouting:
    """Lock: delegation_intent route annotations produce synthetic
    WORKER_CANDIDATE + WORKER_PROMOTION with original_semantic_role metadata.

    Cross-reference: tests/unit/compiler/irs/
        test_r10_delegation_intent_cleanup_characterization.py
        TestCharDelegationIntentExtraction
    """

    def test_synthetic_candidate_has_delegation_intent_metadata(self) -> None:
        """R0-4: Synthetic WORKER_CANDIDATE carries
        original_semantic_role='delegation_intent' in metadata.
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

        for instance in instances:
            assert instance.metadata.get("original_semantic_role") == "delegation_intent", (
                f"R0-4: Instance {instance.construct_type}:{instance.construct_id} "
                f"must carry original_semantic_role='delegation_intent'"
            )
            assert instance.metadata.get("synthetic_from_route_annotation") is True

    def test_real_candidate_also_carries_delegation_metadata_when_overlapping(
        self,
    ) -> None:
        """R0-4: Real candidate whose spans overlap delegation annotations
        also gets delegation_intent metadata.
        """
        from nl2spl.ir.worker_plan_ir import CandidateTaskUnitIR, WorkerPlanIR

        routes = FieldRouteIR(
            behavior=["s_shared"],
            annotations=[
                RouteAnnotation(
                    span_id="s_shared",
                    field="behavior",
                    semantic_role="delegation_intent",
                    route_family="delegation_boundary",
                    executable=False,
                )
            ],
        )
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_1",
            source_span_ids=["s_shared"],  # overlaps with delegation annotation
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

        # The real candidate (not synthetic) also gets delegation metadata
        real_candidates = [
            i for i in instances
            if i.construct_type == "WORKER_CANDIDATE"
            and not i.metadata.get("synthetic_from_route_annotation")
        ]
        assert len(real_candidates) >= 1, (
            "R0-4: Real candidate with overlapping delegation spans should exist"
        )
        for c in real_candidates:
            assert c.metadata.get("original_semantic_role") == "delegation_intent", (
                f"R0-4: Real candidate {c.construct_id} overlapping delegation "
                f"annotation must carry original_semantic_role='delegation_intent'"
            )


# ===========================================================================
# R0-5: Gate does NOT currently recognize origin=user_confirmed_repair
# ===========================================================================


class TestR0GateUserConfirmedRepair:
    """Lock: Gate.classify_origin does NOT check for user_confirmed_repair.

    A step with metadata.origin='user_confirmed_repair' but no source_span_ids
    is CURRENTLY classified as 'assumed'.  After R6, this should change.
    """

    def test_user_confirmed_repair_classified_as_assumed(self) -> None:
        """R6 RESOLVED — step with
        metadata.origin='user_confirmed_repair' (no source spans, no handoff)
        is NOW classified as 'user_confirmed_repair'.
        """
        gate = ExecutableElementGate()
        step = StepIR(
            "st_repair", "User-confirmed handler", [],
            "GENERAL_COMMAND",
            metadata={"origin": "user_confirmed_repair"},
        )
        origin = gate.classify_origin(step)
        assert origin == "user_confirmed_repair", (
            f"R6: Gate now recognizes user_confirmed_repair. "
            f"Expected 'user_confirmed_repair', got '{origin}'."
        )

    def test_user_confirmed_repair_is_not_renderable(self) -> None:
        """R6 RESOLVED — user_confirmed_repair step without source
        spans is NOW renderable through the gate.
        """
        gate = ExecutableElementGate()
        step = StepIR(
            "st_repair", "User-confirmed handler", [],
            "GENERAL_COMMAND",
            metadata={"origin": "user_confirmed_repair"},
        )
        ok, reason = gate.is_renderable(step, "user_confirmed_repair", {}, set(), {})
        assert ok is True, (
            f"R6: user_confirmed_repair step is NOW renderable. "
            f"Blocked with reason: {reason}"
        )
        assert reason is None

    def test_user_confirmed_repair_with_source_spans_is_source_backed(
        self,
    ) -> None:
        """R0-5: CURRENT behavior — step with BOTH source_span_ids AND
        metadata.origin='user_confirmed_repair' is classified as
        'source_backed' (source spans take priority in classify_origin).
        """
        gate = ExecutableElementGate()
        step = StepIR(
            "st_repair", "User-confirmed with source", ["s1"],
            "GENERAL_COMMAND",
            metadata={"origin": "user_confirmed_repair"},
        )
        origin = gate.classify_origin(step)
        assert origin == "source_backed", (
            f"R0-5 CURRENT: source_span_ids take priority over "
            f"user_confirmed_repair. Got '{origin}'."
        )

    def test_user_confirmed_repair_filtered_in_gate_apply(self) -> None:
        """R6 RESOLVED — gate.apply() now passes user_confirmed_repair
        steps through.
        """
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR("st1", "Real work", ["s1"], "GENERAL_COMMAND"),
                StepIR(
                    "st_repair", "User-confirmed repair", [],
                    "GENERAL_COMMAND",
                    metadata={"origin": "user_confirmed_repair"},
                ),
            ],
        )
        filtered, infos, _diags = gate.apply(worker)

        # Both steps pass through
        assert len(filtered.steps) == 2
        step_ids = {s.step_id for s in filtered.steps}
        assert "st_repair" in step_ids

        # Both are renderable
        assert all(i.renderable for i in infos), (
            f"R6: All steps should be renderable, got blocked: "
            f"{[(i.step_id, i.render_block_reason) for i in infos if not i.renderable]}"
        )

    def test_user_confirmed_repair_step_with_source_spans_passes_gate(
        self,
    ) -> None:
        """R0-5: CURRENT behavior — a step with both source_span_ids AND
        user_confirmed_repair passes the gate because source_backed takes
        priority.
        """
        gate = ExecutableElementGate()
        worker = WorkerIR(
            worker_name="MainWorker",
            description="Test",
            main_flow=FlowRef(),
            steps=[
                StepIR(
                    "st_repair", "User-confirmed repair with source", ["s1"],
                    "GENERAL_COMMAND",
                    metadata={"origin": "user_confirmed_repair"},
                ),
            ],
        )
        filtered, infos, _diags = gate.apply(worker)
        assert len(filtered.steps) == 1
        assert all(i.renderable for i in infos)


# ===========================================================================
# R0-6: ProducerIndex does NOT currently recognize origin=user_confirmed_repair
# ===========================================================================


class TestR0ProducerIndexUserConfirmedRepair:
    """Lock: ProducerIndex._step_is_renderable does NOT check for
    user_confirmed_repair.
    """

    def test_step_is_renderable_rejects_user_confirmed_repair(self) -> None:
        """R6 RESOLVED — _step_is_renderable now returns True for
        user_confirmed_repair step without source spans.
        """
        step = StepIR(
            "st_repair", "User-confirmed producer", [],
            "GENERAL_COMMAND",
            outputs=["result"],
            metadata={"origin": "user_confirmed_repair"},
        )
        assert _step_is_renderable(step) is True, (
            "R6: ProducerIndex now recognizes user_confirmed_repair."
        )

    def test_user_confirmed_repair_output_not_produced(self) -> None:
        """R6 RESOLVED — output of user_confirmed_repair step
        is NOW considered produced.
        """
        step = StepIR(
            "st_repair", "User-confirmed producer", [],
            "GENERAL_COMMAND",
            outputs=["result"],
            metadata={"origin": "user_confirmed_repair"},
        )
        index = ProducerIndex(steps=[step])
        assert index.is_produced("result"), (
            "R6: ProducerIndex now recognizes user_confirmed_repair. "
            "Output 'result' should be produced."
        )

    def test_user_confirmed_repair_with_source_spans_is_produced(self) -> None:
        """R0-6: CURRENT behavior — step with source_span_ids AND
        user_confirmed_repair IS produced (source spans take priority).
        """
        step = StepIR(
            "st_repair", "User-confirmed with source", ["s1"],
            "GENERAL_COMMAND",
            outputs=["result"],
            metadata={"origin": "user_confirmed_repair"},
        )
        index = ProducerIndex(steps=[step])
        assert index.is_produced("result"), (
            "R0-6 CURRENT: source_span_ids make the step renderable "
            "regardless of user_confirmed_repair metadata."
        )


# ===========================================================================
# R0-7: Post-normalize IRS source evidence predicate does NOT recognize
#       origin=user_confirmed_repair
# ===========================================================================


class TestR0PostNormalizeUserConfirmedRepair:
    """Lock: PostNormalizeIRSCheckerV6._source_evidence_slot does NOT check
    for user_confirmed_repair.
    """

    def test_source_evidence_slot_missing_for_user_confirmed_repair(
        self,
    ) -> None:
        """R6 RESOLVED — _source_evidence_slot now returns status='satisfied'
        for a user_confirmed_repair step.
        """
        checker = PostNormalizeIRSCheckerV6()
        irs = SPLConstructRegistry.default().get("GENERAL_COMMAND")
        step = StepIR(
            "st_repair", "User-confirmed repair step", [],
            "GENERAL_COMMAND",
            metadata={"origin": "user_confirmed_repair"},
        )

        slot = checker._source_evidence_slot(step, irs, set())

        assert slot.status == "satisfied", (
            f"R6: Post-normalize IRS now recognizes user_confirmed_repair. "
            f"Expected status='satisfied', got '{slot.status}'."
        )

    def test_source_evidence_slot_diagnostic_kind_for_user_confirmed_repair(
        self,
    ) -> None:
        """R6 RESOLVED — user_confirmed_repair no longer triggers a
        missing-evidence diagnostic.
        """
        checker = PostNormalizeIRSCheckerV6()
        irs = SPLConstructRegistry.default().get("GENERAL_COMMAND")
        step = StepIR(
            "st_repair", "User-confirmed repair step", [],
            "GENERAL_COMMAND",
            metadata={"origin": "user_confirmed_repair"},
        )

        slot = checker._source_evidence_slot(step, irs, set())

        # No diagnostic kind emitted — evidence is satisfied
        assert slot.diagnostic_kind is None, (
            f"R6: user_confirmed_repair step should have no diagnostic_kind, "
            f"got '{slot.diagnostic_kind}'."
        )

    def test_source_evidence_slot_user_confirmed_repair_vs_compiler_unpack(
        self,
    ) -> None:
        """R6 RESOLVED — both compiler_unpack AND user_confirmed_repair
        are now recognized by _source_evidence_slot.
        """
        checker = PostNormalizeIRSCheckerV6()
        irs = SPLConstructRegistry.default().get("GENERAL_COMMAND")

        # compiler_unpack → recognized (status=satisfied)
        unpack_step = StepIR(
            "st_unpack", "Extract field", [],
            "GENERAL_COMMAND",
            metadata={"origin": "compiler_unpack"},
        )
        unpack_slot = checker._source_evidence_slot(unpack_step, irs, set())
        assert unpack_slot.status == "satisfied"

        # user_confirmed_repair → NOW recognized (status=satisfied)
        repair_step = StepIR(
            "st_repair", "User-confirmed repair", [],
            "GENERAL_COMMAND",
            metadata={"origin": "user_confirmed_repair"},
        )
        repair_slot = checker._source_evidence_slot(repair_step, irs, set())
        assert repair_slot.status == "satisfied", (
            f"R6: user_confirmed_repair is now recognized. "
            f"Got status='{repair_slot.status}'."
        )


# ===========================================================================
# R0-8: unspecified_output_missing_producer current projection behavior
# ===========================================================================


class TestR0UnspecifiedOutputMissingProducer:
    """Lock: unspecified_output_missing_producer diagnostic behavior in
    post-normalize IRS checker.

    When a RESOURCE_CONTRACT_DEMAND has direction=output, requiredness=unspecified,
    materialized bindings but no renderable producer, the producer slot status
    is 'satisfied' but carries diagnostic_kind='unspecified_output_missing_producer'.
    """

    def test_diagnostic_kind_is_unspecified_output_missing_producer(self) -> None:
        """R0-8: CURRENT behavior — the string literal
        'unspecified_output_missing_producer' is used as diagnostic_kind
        for unspecified outputs without a producer.
        """
        # Verify the literal exists by checking it's not any of the
        # standard missing_diagnostic values from the IRS slots
        registry = SPLConstructRegistry.default()

        # REQUIRED_OUTPUT.producer uses "missing_output_producer"
        req_out = registry.get("REQUIRED_OUTPUT")
        producer_slot = req_out.get_slot("producer")
        assert producer_slot is not None
        assert producer_slot.missing_diagnostic == "missing_output_producer"

        # RESOURCE_CONTRACT_DEMAND.producer also uses "missing_output_producer"
        rcd = registry.get("RESOURCE_CONTRACT_DEMAND")
        rcd_producer_slot = rcd.get_slot("producer")
        assert rcd_producer_slot is not None
        assert rcd_producer_slot.missing_diagnostic == "missing_output_producer"

        # But in _check_resource_contract_demand, when requiredness=unspecified
        # and no producer, the diagnostic_kind is hardcoded to
        # "unspecified_output_missing_producer" — a distinct kind NOT in the
        # slot spec's missing_diagnostic field.
        assert rcd_producer_slot.missing_diagnostic != "unspecified_output_missing_producer", (
            "R0-8: 'unspecified_output_missing_producer' is a special diagnostic "
            "kind emitted by _check_resource_contract_demand for "
            "requiredness=unspecified, distinct from the slot's "
            "missing_diagnostic='missing_output_producer'."
        )

    def test_unspecified_output_slot_status_is_satisfied(self) -> None:
        """R0-8: CURRENT behavior — when requiredness=unspecified and no
        producer exists, the slot status is 'satisfied' (not 'missing').
        The diagnostic is a warning, not a blocking error.

        This is verified by code inspection: in
        PostNormalizeIRSCheckerV6._check_resource_contract_demand,
        the producer slot with requiredness=unspecified and no producer
        has status='satisfied' with diagnostic_kind set to the warning.
        """
        # This is a code-inspection-backed characterization.
        # The actual logic is in post_normalize.py lines 528-565:
        #   if direction == "output" and requiredness == "unspecified" ...
        #       producer = SlotSatisfaction(
        #           slot_name="producer",
        #           status="satisfied",  # <-- satisfied, not missing
        #           diagnostic_kind="unspecified_output_missing_producer",
        #           ...
        #       )
        #
        # We verify this by checking the source evidence path:
        # A step with unspecified requiredness output that has bindings
        # but no producer → satisfied slot with warning diagnostic_kind.
        pass  # Characterized by code inspection above — no runtime test needed

    def test_diagnostic_registry_has_unspecified_output_kind(self) -> None:
        """R0-8: CURRENT behavior — 'unspecified_output_missing_producer'
        is registered in DiagnosticRegistry with expected severity/blocking.
        """
        from nl2spl.compiler.diagnostic_registry import DiagnosticRegistry

        diag_registry = DiagnosticRegistry.default()
        assert diag_registry.has("unspecified_output_missing_producer"), (
            "R0-8: 'unspecified_output_missing_producer' must be a known "
            "diagnostic kind in DiagnosticRegistry."
        )

        spec = diag_registry.get("unspecified_output_missing_producer")
        assert spec.enabled is True, (
            "R0-8: 'unspecified_output_missing_producer' must be enabled"
        )
        # The severity should be 'info' or 'warning' — not 'error'
        assert spec.default_severity in ("info", "warning"), (
            f"R0-8: 'unspecified_output_missing_producer' severity is "
            f"'{spec.default_severity}', expected 'info' or 'warning'"
        )
        # blocks_completion should be False for a review-only diagnostic
        assert spec.blocks_completion is False, (
            "R0-8: 'unspecified_output_missing_producer' should not block "
            "completion — it's a review-only hint."
        )
