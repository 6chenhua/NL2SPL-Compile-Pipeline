"""Tests for productized diagnostic consolidation."""

from __future__ import annotations

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.diagnostic_consolidator import (
    DiagnosticConsolidationInput,
    DiagnosticConsolidator,
    diagnostic_dedup_key,
)
from nl2spl.compiler.irs.diagnostic_authority_adapter import (
    diagnostic_authority_from_irs_store,
)
from nl2spl.compiler.irs.result_store import IRSResultStore, IRSStageResult
from nl2spl.ir.diagnostics import CompileDiagnostic


def _diag(
    diagnostic_id: str,
    *,
    kind: str = "type_or_contract_ambiguity",
    target_ref: str = "target:one",
    slot: str | None = None,
    spans: list[str] | None = None,
) -> CompileDiagnostic:
    return CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind=kind,
        severity="warning",
        message=f"message {diagnostic_id}",
        target_ref=target_ref,
        source_span_ids=list(spans or ["s1"]),
        missing_slot=(
            MissingSlot(
                slot_name=slot,
                required_for="complete",
                reason=f"missing {slot}",
                source_span_ids=list(spans or ["s1"]),
            )
            if slot
            else None
        ),
        blocks_completion=True,
    )


def test_dedup_key_includes_missing_slot() -> None:
    a = _diag("a", slot="condition")
    b = _diag("b", slot="handler_action")

    assert diagnostic_dedup_key(a) != diagnostic_dedup_key(b)


def test_post_normalize_suppresses_duplicate_stage_local() -> None:
    post = _diag("post", slot="handler_action")
    stage = _diag("stage", slot="handler_action")
    store = IRSResultStore()
    store.put_stage_result(
        IRSStageResult(stage_name="stage4", diagnostics=(stage,))
    )

    result = DiagnosticConsolidator().consolidate(
        DiagnosticConsolidationInput(
            stage_local_authority=diagnostic_authority_from_irs_store(store),
            post_normalize_diagnostics=[post],
        )
    )

    assert [d.diagnostic_id for d in result.final_diagnostics] == ["post"]
    assert [d.diagnostic_id for d in result.suppressed_stage_local_diagnostics] == [
        "stage"
    ]


def test_different_missing_slots_are_not_merged() -> None:
    post = _diag("post", slot="condition")
    gate = _diag("gate", slot="handler_action")

    result = DiagnosticConsolidator().consolidate(
        DiagnosticConsolidationInput(
            post_normalize_diagnostics=[post],
            gate_diagnostics=[gate],
        )
    )

    assert {d.diagnostic_id for d in result.final_diagnostics} == {"post", "gate"}


def test_gate_diagnostic_preserved_over_later_duplicates() -> None:
    gate = _diag("gate", slot="source_evidence")
    conflict_duplicate = _diag("conflict", slot="source_evidence")

    result = DiagnosticConsolidator().consolidate(
        DiagnosticConsolidationInput(
            gate_diagnostics=[gate],
            conflict_diagnostics=[conflict_duplicate],
        )
    )

    assert [d.diagnostic_id for d in result.final_diagnostics] == ["gate"]


def test_stage_local_unique_default_suppressed() -> None:
    stage = _diag("stage_unique", slot="promotion_input_contract")
    store = IRSResultStore()
    store.put_stage_result(
        IRSStageResult(stage_name="stage3_5", diagnostics=(stage,))
    )

    result = DiagnosticConsolidator().consolidate(
        DiagnosticConsolidationInput(
            stage_local_authority=diagnostic_authority_from_irs_store(store)
        )
    )

    assert result.final_diagnostics == []
    assert [d.diagnostic_id for d in result.suppressed_stage_local_diagnostics] == [
        "stage_unique"
    ]


def test_stage_local_unique_can_be_included_by_policy() -> None:
    stage = _diag("stage_unique", slot="promotion_input_contract")
    store = IRSResultStore()
    store.put_stage_result(
        IRSStageResult(stage_name="stage3_5", diagnostics=(stage,))
    )

    result = DiagnosticConsolidator().consolidate(
        DiagnosticConsolidationInput(
            stage_local_authority=diagnostic_authority_from_irs_store(store),
            include_stage_local_diagnostics=True,
        )
    )

    assert [d.diagnostic_id for d in result.final_diagnostics] == ["stage_unique"]
    assert result.suppressed_stage_local_diagnostics == []


def test_diagnostic_order_is_deterministic_by_authority_group() -> None:
    result = DiagnosticConsolidator().consolidate(
        DiagnosticConsolidationInput(
            stage2_diagnostics=[_diag("stage2")],
            stage7_diagnostics=[_diag("stage7", target_ref="target:stage7")],
            post_normalize_diagnostics=[_diag("post", target_ref="target:post")],
            gate_diagnostics=[_diag("gate", target_ref="target:gate")],
            provenance_diagnostics=[_diag("prov", target_ref="target:prov")],
            irs_promoted_diagnostics=[_diag("irs_deleg", target_ref="target:deleg")],
            conflict_diagnostics=[_diag("conf", target_ref="target:conf")],
        )
    )

    assert [d.diagnostic_id for d in result.final_diagnostics] == [
        "post",
        "gate",
        "prov",
        "stage2",
        "irs_deleg",
        "conf",
        "stage7",
    ]


def test_consolidator_does_not_mutate_input_diagnostic() -> None:
    diagnostic = _diag("d1", slot="handler_action")
    original_spans = list(diagnostic.source_span_ids)

    DiagnosticConsolidator().consolidate(
        DiagnosticConsolidationInput(post_normalize_diagnostics=[diagnostic])
    )

    assert diagnostic.source_span_ids == original_spans
    assert diagnostic.missing_slot is not None
    assert diagnostic.missing_slot.slot_name == "handler_action"
