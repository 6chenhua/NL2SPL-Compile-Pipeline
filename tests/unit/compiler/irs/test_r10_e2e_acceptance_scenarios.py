"""R10 E2E Acceptance Scenarios — Section 12 of the implementation plan.

These tests verify the full chain from route annotation through IRS checker,
DiagnosticProjector, orchestrator selective promotion, and feedback report
rendering — ensuring the DELEGATION_INTENT cleanup meets all acceptance
criteria end-to-end.

Scenario coverage:
  1. Delegation intent without contract → type_or_contract_ambiguity
  2. Delegation intent with complete handoff → no ambiguity
  3. Source signal preservation → source_span_ids + feedback provenance
  4. Stage-local diagnostics remain selective
  5. Registry cleanup — DELEGATION_INTENT removed
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.feedback_report_renderer import render_feedback_report
from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.compiler.irs.registry import IRSCheckerRegistry
from nl2spl.compiler.irs.result_store import IRSResultStore, IRSStageResult
from nl2spl.compiler.irs.runner import IRSRunner
from nl2spl.ir.diagnostics import CompileDiagnostic, TraceRecord
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
from nl2spl.pipeline.orchestrator import PipelineOrchestrator


# =============================================================================
# Helpers
# =============================================================================


def _make_runner() -> IRSRunner:
    checker_registry = IRSCheckerRegistry()
    checker_registry.register(WorkerDelegationIRSChecker())
    return IRSRunner(
        registry=checker_registry,
        construct_registry=SPLConstructRegistry.default(),
        projector=DiagnosticProjector(),
    )


def _delegation_routes(span_id: str = "s_delegate") -> FieldRouteIR:
    return FieldRouteIR(
        behavior=[span_id],
        annotations=[
            RouteAnnotation(
                span_id=span_id,
                field="behavior",
                semantic_role="delegation_intent",
                route_family="delegation_boundary",
                executable=False,
                source_section_id="sec_delegation_policy",
                source_packet_id="pkt_delegate",
            )
        ],
    )


# =============================================================================
# Scenario 1: Delegation intent without contract
# =============================================================================


class TestScenario1DelegationWithoutContract:
    """Section 12.1: Delegation intent without contract → type_or_contract_ambiguity"""

    def test_produces_type_or_contract_ambiguity(self) -> None:
        """Confirmed delegation_intent with no handoff contract produces
        type_or_contract_ambiguity via IRS projection."""
        routes = _delegation_routes()
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        diags = [
            d for d in result.diagnostics
            if d.kind == "type_or_contract_ambiguity"
        ]
        assert len(diags) >= 1

    def test_diagnostic_id_has_irs_prefix(self) -> None:
        """Diagnostic ID starts with 'irs_'."""
        routes = _delegation_routes()
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        for d in result.diagnostics:
            if d.kind == "type_or_contract_ambiguity":
                assert d.diagnostic_id.startswith("irs_")

    def test_target_ref_is_worker_promotion_not_delegation_intent(self) -> None:
        """Target ref is worker_promotion:*, NOT delegation_intent:*."""
        routes = _delegation_routes()
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        ambiguity_diags = [
            d for d in result.diagnostics
            if d.kind == "type_or_contract_ambiguity"
        ]
        assert len(ambiguity_diags) >= 1

        for d in ambiguity_diags:
            assert (d.target_ref or "").startswith("worker_promotion:"), (
                f"Expected worker_promotion:* target_ref, got {d.target_ref!r}"
            )
            assert not (d.target_ref or "").startswith("delegation_intent:"), (
                f"delegation_intent:* target_ref must not appear, got {d.target_ref!r}"
            )

    def test_blocks_completion_true_blocks_rendering_false(self) -> None:
        """blocks_completion=True, blocks_rendering=False."""
        routes = _delegation_routes()
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        ambiguity_diags = [
            d for d in result.diagnostics
            if d.kind == "type_or_contract_ambiguity"
        ]
        assert len(ambiguity_diags) >= 1

        for d in ambiguity_diags:
            assert d.blocks_completion is True, (
                f"blocks_completion must be True for {d.diagnostic_id}"
            )
            assert d.blocks_rendering is False, (
                f"blocks_rendering must be False for {d.diagnostic_id}"
            )

    def test_diagnostic_has_source_span_ids(self) -> None:
        """Diagnostic preserves original delegation source_span_ids."""
        routes = _delegation_routes()
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        ambiguity_diags = [
            d for d in result.diagnostics
            if d.kind == "type_or_contract_ambiguity"
        ]
        for d in ambiguity_diags:
            assert "s_delegate" in d.source_span_ids, (
                f"source_span_ids must contain 's_delegate', got {d.source_span_ids}"
            )

    def test_report_carries_delegation_metadata(self) -> None:
        """ConstructSatisfactionReport metadata includes delegation provenance."""
        routes = _delegation_routes()
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        promotion_reports = [
            r for r in result.reports
            if r.construct_type == "WORKER_PROMOTION"
        ]
        assert len(promotion_reports) >= 1

        for report in promotion_reports:
            if report.metadata.get("synthetic_from_route_annotation"):
                assert report.metadata["original_semantic_role"] == "delegation_intent"
                assert "s_delegate" in report.metadata.get(
                    "original_source_span_ids", []
                )

    def test_no_delegation_intent_construct_in_results(self) -> None:
        """No DELEGATION_INTENT construct type in reports or diagnostics."""
        routes = _delegation_routes()
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

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


# =============================================================================
# Scenario 2: Delegation intent with complete handoff
# =============================================================================


class TestScenario2DelegationWithCompleteHandoff:
    """Section 12.2: Delegation intent with complete handoff → no ambiguity"""

    def _complete_handoff_plan(self) -> WorkerPlanIR:
        return WorkerPlanIR(
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

    def test_no_delegation_ambiguity_produced(self) -> None:
        """Complete handoff → no type_or_contract_ambiguity with
        delegation_intent:* target_ref."""
        routes = _delegation_routes()
        plan = self._complete_handoff_plan()

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        delegation_diags = [
            d for d in result.diagnostics
            if (d.target_ref or "").startswith("delegation_intent:")
        ]
        assert len(delegation_diags) == 0

    def test_no_delegation_intent_report(self) -> None:
        """No DELEGATION_INTENT report in results."""
        routes = _delegation_routes()
        plan = self._complete_handoff_plan()

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        delegation_reports = [
            r for r in result.reports
            if r.construct_type == "DELEGATION_INTENT"
        ]
        assert len(delegation_reports) == 0

    def test_promotion_invocation_and_result_handoff_satisfied(self) -> None:
        """The synthetic WORKER_PROMOTION has invocation_point and
        result_handoff satisfied because the handoff matches."""
        routes = _delegation_routes()
        plan = self._complete_handoff_plan()

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        promotion_reports = [
            r for r in result.reports
            if r.construct_type == "WORKER_PROMOTION"
        ]
        assert len(promotion_reports) >= 1

        for report in promotion_reports:
            inv_slot = next(
                (s for s in report.slots
                 if s.slot_name == "promotion_invocation_point"),
                None,
            )
            res_slot = next(
                (s for s in report.slots
                 if s.slot_name == "promotion_result_handoff"),
                None,
            )
            if inv_slot:
                assert inv_slot.status == "satisfied", (
                    "invocation_point should be satisfied when handoff matches"
                )
            if res_slot:
                assert res_slot.status == "satisfied", (
                    "result_handoff should be satisfied when handoff has output_bindings"
                )


# =============================================================================
# Scenario 3: Source signal preservation
# =============================================================================


class TestScenario3SourceSignalPreservation:
    """Section 12.3: Source signal preservation through the full chain"""

    def test_diagnostic_metadata_has_delegation_provenance(self) -> None:
        """Projected diagnostic metadata includes original_semantic_role."""
        routes = _delegation_routes()
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        ambiguity_diags = [
            d for d in result.diagnostics
            if d.kind == "type_or_contract_ambiguity"
        ]
        for d in ambiguity_diags:
            assert d.metadata.get("original_semantic_role") == "delegation_intent", (
                f"Diagnostic {d.diagnostic_id} missing original_semantic_role "
                f"in metadata: {d.metadata}"
            )

    def test_feedback_shows_source_signal_section(self) -> None:
        """Feedback report shows 'Source Signals' section with
        source_signal:delegation_intent: prefix."""
        trace = TraceRecord(
            target_ref="source_signal:delegation_intent:source_gathering",
            source_span_ids=["s_del_1"],
            source_section_id="sec_delegation_policy",
            relation="inferred",
            explanation="Delegation intent 'source_gathering': text",
        )

        report = render_feedback_report(
            spl_text="// SPL",
            traces=[trace],
        )

        assert "### Source Signals" in report
        assert "source_signal:delegation_intent:source_gathering" in report

    def test_feedback_does_not_show_delegation_intent_as_construct_target(self) -> None:
        """Feedback report does NOT display delegation_intent:* as a
        construct/diagnostic host target."""
        trace = TraceRecord(
            target_ref="source_signal:delegation_intent:source_gathering",
            source_span_ids=["s_del_1"],
            relation="inferred",
            explanation="Delegation intent 'source_gathering': text",
        )

        report = render_feedback_report(
            spl_text="// SPL",
            traces=[trace],
        )

        assert "### Delegation Intents" not in report, (
            "R10: 'Delegation Intents' section must not appear"
        )
        # The bare prefix should not appear as a construct target
        assert "delegation_intent:source_gathering" not in report or (
            "source_signal:delegation_intent:source_gathering" in report
        )

    def test_report_metadata_preserves_original_source_spans(self) -> None:
        """ConstructSatisfactionReport preserves original source_span_ids."""
        routes = _delegation_routes()
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        for report in result.reports:
            if report.metadata.get("synthetic_from_route_annotation"):
                original_spans = report.metadata.get("original_source_span_ids", [])
                assert "s_delegate" in original_spans, (
                    f"original_source_span_ids must contain delegation span"
                )


# =============================================================================
# Scenario 4: Stage-local diagnostics remain selective
# =============================================================================


class TestScenario4SelectivePromotion:
    """Section 12.4: Only delegation-sourced diagnostics are promoted"""

    def test_delegation_sourced_diagnostics_are_promoted(self) -> None:
        """Delegation-sourced worker_promotion:* diagnostics are promoted."""
        routes = _delegation_routes()
        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", routes=routes, worker_plan=plan),
        )

        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=tuple(result.diagnostics),
        ))
        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) >= 1, (
            "Delegation-sourced diagnostics must be promoted"
        )
        for d in promoted:
            assert d.kind == "type_or_contract_ambiguity"
            assert (d.target_ref or "").startswith("worker_promotion:")
            assert d.metadata.get("original_semantic_role") == "delegation_intent"

    def test_non_delegation_promotion_diagnostics_not_promoted(self) -> None:
        """WORKER_PROMOTION diagnostics without delegation provenance
        are NOT promoted."""
        candidate = CandidateTaskUnitIR(
            candidate_id="cand_nodel",
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
            candidates=[candidate],
        )

        result = _make_runner().run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", worker_plan=plan),
        )

        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=tuple(result.diagnostics),
        ))
        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) == 0, (
            "Non-delegation-sourced diagnostics must NOT be promoted"
        )

    def test_old_delegation_intent_prefix_not_promoted(self) -> None:
        """Diagnostics with delegation_intent:* target_ref (if any existed)
        would NOT be promoted — the old filter is removed."""
        # Manually construct a diagnostic with the OLD format to prove
        # the new orchestrator filter rejects it.
        from nl2spl.compiler.compile_result import MissingSlot

        old_format_diag = CompileDiagnostic(
            diagnostic_id="irs_old001",
            kind="type_or_contract_ambiguity",
            severity="error",
            message="Old format diagnostic",
            target_ref="delegation_intent:s_old",
            source_span_ids=["s_old"],
            missing_slot=MissingSlot(
                slot_name="handoff_contract",
                required_for="complete",
                reason="Missing handoff contract",
            ),
            blocks_rendering=False,
            blocks_completion=True,
        )
        # Would need delegation provenance to be promoted
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=(old_format_diag,),
        ))
        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) == 0, (
            "Old delegation_intent:* target_ref is NOT promoted under new filter"
        )


# =============================================================================
# Scenario 5: Registry cleanup
# =============================================================================


class TestScenario5RegistryCleanup:
    """Section 12.5: DELEGATION_INTENT removed, worker constructs remain"""

    def test_delegation_intent_not_in_registry(self) -> None:
        """DELEGATION_INTENT is not in SPLConstructRegistry."""
        registry = SPLConstructRegistry.default()
        assert not registry.has("DELEGATION_INTENT")

    def test_worker_constructs_still_exist(self) -> None:
        """WORKER_CANDIDATE, WORKER_PROMOTION, WORKER_HANDOFF still exist."""
        registry = SPLConstructRegistry.default()
        assert registry.has("WORKER_CANDIDATE")
        assert registry.has("WORKER_PROMOTION")
        assert registry.has("WORKER_HANDOFF")
        assert registry.has("CHILD_WORKER")

    def test_construct_list_has_no_delegation_intent(self) -> None:
        """list_constructs() does not include DELEGATION_INTENT."""
        registry = SPLConstructRegistry.default()
        constructs = registry.list_constructs()
        assert "DELEGATION_INTENT" not in constructs

    def test_semantic_role_delegation_intent_still_exists(self) -> None:
        """semantic_role='delegation_intent' still exists as route annotation."""
        ann = RouteAnnotation(
            span_id="s_test",
            field="behavior",
            semantic_role="delegation_intent",
            route_family="delegation_boundary",
            executable=False,
        )
        assert ann.semantic_role == "delegation_intent"
