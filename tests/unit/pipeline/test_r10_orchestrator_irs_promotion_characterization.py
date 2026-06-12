"""R10 Phase 0: Characterization tests for orchestrator IRS promotion logic.

This file LOCKS the current orchestrator behavior around delegation_intent:*
selective promotion. Tests document the pre-migration baseline.

Coverage targets per Section 4.5:
  1. current diagnostic passes through orchestrator selective promotion
  2. orchestrator uses target_ref.startswith("delegation_intent:")
  3. only stage3_5 DELEGATION_INTENT diagnostics are promoted
  4. include_stage_local_diagnostics_in_compile=False does NOT promote all
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.irs.checkers.worker_delegation import WorkerDelegationIRSChecker
from nl2spl.compiler.irs.context import IRSCheckContext
from nl2spl.compiler.irs.projector import DiagnosticProjector
from nl2spl.compiler.irs.registry import IRSCheckerRegistry
from nl2spl.compiler.irs.result_store import IRSResultStore, IRSStageResult
from nl2spl.compiler.irs.runner import IRSRunner
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.worker_plan_ir import (
    CandidateTaskUnitIR,
    WorkerPlanIR,
)
from nl2spl.pipeline.orchestrator import PipelineOrchestrator
from nl2spl.ir.diagnostics import CompileDiagnostic


# ===========================================================================
# Helpers
# ===========================================================================


def _make_delegation_sourced_diagnostic(
    target_ref: str = "worker_promotion:del_s_test",
    kind: str = "type_or_contract_ambiguity",
    source_span_ids: list[str] | None = None,
    with_metadata: bool = True,
) -> CompileDiagnostic:
    """Build a CompileDiagnostic matching the R10 Phase 4 projector output."""
    from nl2spl.compiler.compile_result import MissingSlot

    _spans = source_span_ids if source_span_ids is not None else ["s_test"]
    diag = CompileDiagnostic(
        diagnostic_id="irs_test001",
        kind=kind,
        severity="error",
        message=f"Test diagnostic for {target_ref}",
        target_ref=target_ref,
        source_span_ids=list(_spans),
        missing_slot=MissingSlot(
            slot_name="promotion_input_contract",
            required_for="complete",
            reason="Missing contract",
            source_span_ids=list(_spans),
        ),
        blocks_rendering=False,
        blocks_completion=True,
    )
    if with_metadata:
        diag.metadata["original_semantic_role"] = "delegation_intent"
        diag.metadata["original_source_span_ids"] = list(_spans)
        diag.metadata["synthetic_from_route_annotation"] = True
    return diag


def _make_non_delegation_diagnostic() -> CompileDiagnostic:
    """Build a CompileDiagnostic NOT sourced from delegation."""
    from nl2spl.compiler.compile_result import MissingSlot

    return CompileDiagnostic(
        diagnostic_id="irs_other001",
        kind="type_or_contract_ambiguity",
        severity="error",
        message="Some other diagnostic",
        target_ref="worker_promotion:cand_x",
        source_span_ids=["s_other"],
        missing_slot=MissingSlot(
            slot_name="promotion_input_contract",
            required_for="complete",
            reason="Missing contract",
            source_span_ids=["s_other"],
        ),
        blocks_rendering=True,
        blocks_completion=True,
    )


# ===========================================================================
# Phase 4: _promoted_irs_diagnostics — construct target + metadata filter
# ===========================================================================


class TestCharOrchestratorPromotedIRSDiagnostics:
    """R10 Phase 4: orchestrator promotes diagnostics by construct target
    + delegation metadata, NOT by delegation_intent:* target_ref."""

    def test_delegation_sourced_diagnostic_is_promoted(self) -> None:
        """R10 Phase 4: worker_promotion:* diagnostic with
        metadata.original_semantic_role="delegation_intent" IS promoted."""
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=(
                _make_delegation_sourced_diagnostic(
                    "worker_promotion:del_s_span1",
                ),
                _make_non_delegation_diagnostic(),
            ),
        ))

        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) == 1
        assert promoted[0].target_ref == "worker_promotion:del_s_span1"
        assert promoted[0].metadata.get("original_semantic_role") == "delegation_intent"

    def test_non_delegation_sourced_not_promoted(self) -> None:
        """R10 Phase 4: diagnostic without delegation metadata is NOT promoted."""
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=(_make_non_delegation_diagnostic(),),
        ))

        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) == 0

    def test_multiple_delegation_sourced_all_promoted(self) -> None:
        """R10 Phase 4: multiple delegation-sourced diagnostics all promoted."""
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=(
                _make_delegation_sourced_diagnostic("worker_promotion:del_a"),
                _make_delegation_sourced_diagnostic("worker_promotion:del_b"),
                _make_delegation_sourced_diagnostic("worker_promotion:del_c"),
            ),
        ))

        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) == 3

    def test_no_metadata_not_promoted(self) -> None:
        """R10 Phase 4: diagnostic with correct target but NO
        delegation metadata is NOT promoted."""
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=(
                _make_delegation_sourced_diagnostic(
                    "worker_promotion:cand_1",
                    with_metadata=False,  # No delegation provenance
                ),
            ),
        ))

        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) == 0

    def test_empty_source_span_ids_not_promoted(self) -> None:
        """R10 Phase 4: diagnostic with delegation metadata but empty
        source_span_ids is NOT promoted."""
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=(
                _make_delegation_sourced_diagnostic(
                    "worker_promotion:del_empty",
                    source_span_ids=[],
                ),
            ),
        ))

        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) == 0

    def test_wrong_target_prefix_not_promoted(self) -> None:
        """R10 Phase 4: delegation-sourced diagnostic with
        non-promotable target prefix is NOT promoted."""
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=(
                _make_delegation_sourced_diagnostic(
                    "exception_flow:exc_1",  # not in promotable prefixes
                ),
            ),
        ))

        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) == 0

    def test_empty_diagnostics_returns_empty(self) -> None:
        """Empty stage3_5 diagnostics → empty promoted list."""
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=(),
        ))
        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)
        assert promoted == []

    def test_no_stage3_5_result_returns_empty(self) -> None:
        """No stage3_5 result in store → empty promoted list."""
        store = IRSResultStore()
        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)
        assert promoted == []

    def test_diagnostics_from_other_stages_ignored(self) -> None:
        """Only stage3_5 diagnostics are considered."""
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=(
                _make_delegation_sourced_diagnostic("worker_promotion:del_3_5"),
            ),
        ))
        store.put_stage_result(IRSStageResult(
            stage_name="stage9_5",
            diagnostics=(
                _make_delegation_sourced_diagnostic("worker_promotion:del_9_5"),
            ),
        ))

        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) == 1
        assert promoted[0].target_ref == "worker_promotion:del_3_5"


# ===========================================================================
# Phase 4: Full IRS run → promoted diagnostics chain
# ===========================================================================


class TestCharFullIRSPromotionChain:
    """R10 Phase 4: end-to-end chain from IRS checker → store → promoted."""

    def test_irs_run_to_promoted_diagnostics_chain(self) -> None:
        """R10 Phase 4: delegation annotation → IRS worker_promotion:*
        diagnostics → orchestrator promotes via metadata filter."""
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

        plan = WorkerPlanIR(main_worker_id="worker_main", workers=[], handoffs=[])

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
                stage_name="stage3_5",
                routes=routes,
                worker_plan=plan,
            ),
        )

        # IRS produces worker_promotion:* diagnostics
        promotion_diags = [
            d for d in result.diagnostics
            if (d.target_ref or "").startswith("worker_promotion:")
        ]
        assert len(promotion_diags) >= 1

        # Verify projector metadata propagation
        for d in promotion_diags:
            assert d.metadata.get("original_semantic_role") == "delegation_intent", (
                "Phase 4A: projector must copy original_semantic_role to metadata"
            )

        # Store and promote
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=tuple(result.diagnostics),
        ))
        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) >= 1, (
            "Phase 4B: delegation-sourced worker_promotion:* diagnostics "
            "must be promoted to final diagnostics"
        )
        for d in promoted:
            assert (d.target_ref or "").startswith("worker_promotion:")
            assert d.kind == "type_or_contract_ambiguity"

    def test_candidate_without_delegation_route_not_promoted(self) -> None:
        """R10 Phase 4: WORKER_PROMOTION diagnostics from candidates
        WITHOUT delegation provenance are NOT promoted."""
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
            workers=[],
            candidates=[candidate],
            decisions=[],
            handoffs=[],
        )

        checker_registry = IRSCheckerRegistry()
        checker_registry.register(WorkerDelegationIRSChecker())
        runner = IRSRunner(
            registry=checker_registry,
            construct_registry=SPLConstructRegistry.default(),
            projector=DiagnosticProjector(),
        )
        result = runner.run_stage(
            "stage3_5",
            IRSCheckContext(stage_name="stage3_5", worker_plan=plan),
        )

        promotion_diags = [
            d for d in result.diagnostics
            if (d.target_ref or "").startswith("worker_promotion:")
        ]
        assert len(promotion_diags) > 0

        # No delegation provenance → not promoted
        store = IRSResultStore()
        store.put_stage_result(IRSStageResult(
            stage_name="stage3_5",
            diagnostics=tuple(result.diagnostics),
        ))
        promoted = PipelineOrchestrator._promoted_irs_diagnostics(store)

        assert len(promoted) == 0, (
            "Phase 4: candidate diagnostics without delegation provenance "
            "must NOT be promoted"
        )
