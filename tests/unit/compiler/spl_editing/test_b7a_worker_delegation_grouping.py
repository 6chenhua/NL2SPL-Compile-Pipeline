"""B7a: Worker/delegation issue grouping proof."""

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogBuilder
from nl2spl.compiler.spl_editing.issues.extractor import EditableIssueExtractor
from nl2spl.compiler.spl_editing.issues.promoter import WorkerDelegationPromoter
from nl2spl.ir.diagnostics import CompileDiagnostic


def _diag(diag_id: str, slot: str, role: str = "primary") -> CompileDiagnostic:
    d = CompileDiagnostic(
        diagnostic_id=diag_id, kind="type_or_contract_ambiguity",
        severity="warning", message=f"Missing {slot}",
        target_ref="worker_promotion:cand_1",
        source_span_ids=["s1"], blocks_rendering=False, blocks_completion=True,
        missing_slot=MissingSlot(slot_name=slot, required_for="complete",
                                  reason=f"missing {slot}", source_span_ids=["s1"]),
    )
    d.metadata["irs_ref"] = {
        "construct_type": "WORKER_PROMOTION",
        "construct_id": "worker_promotion:cand_1",
        "slot_name": slot, "construct_path": [],
        "source_authority": "stage_local_irs",
    }
    d.metadata["authority"] = "stage_local_irs"
    d.metadata["original_semantic_role"] = "delegation_intent"
    d.metadata["promotion_status"] = "blocked"
    return d


def test_worker_promotion_grouped_as_one_issue() -> None:
    """B7a: 4 WORKER_PROMOTION slots → 1 editable issue after promotion."""
    diags = [
        _diag(f"diag_{i}", slot, "primary" if i == 0 else "alias")
        for i, slot in enumerate([
            "promotion_input_contract",
            "promotion_output_contract",
            "promotion_invocation_point",
            "promotion_result_handoff",
        ])
    ]
    promoter = WorkerDelegationPromoter()
    promoted = promoter.annotate(diags)
    catalog = RepairCatalogBuilder.from_construct_registry(
        SPLConstructRegistry.default())
    issues = EditableIssueExtractor(catalog).extract(promoted)
    assert len(issues) == 1
    assert issues[0].kind == "type_or_contract_ambiguity"
    assert len(issues[0].related_diagnostic_ids) == 4
    assert issues[0].repairability == "editable"
    assert "worker_promotion.resolve_contract" in issues[0].affordance_ids
