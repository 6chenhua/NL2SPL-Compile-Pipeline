"""Expected-correct API placeholder inventory and presentation behavior."""

from __future__ import annotations

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.feedback_report_renderer import _grouped_diag_items
from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation import SPLEditingPresentationService
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from tests.spl_editing_stub_llm import StubSuggestionLLM


def _api_deferred(slot_name: str) -> CompileDiagnostic:
    diagnostic = CompileDiagnostic(
        diagnostic_id=f"diag_api_{slot_name}",
        kind="deferred_api_contract_validation",
        severity="info",
        message="API contract validation is deferred downstream.",
        target_ref="api:ApprovedSourceRecipesAPI",
        missing_slot=MissingSlot(
            slot_name=slot_name,
            required_for="downstream_api_validation",
            reason="Authoritative API contract is not available to NL2SPL.",
        ),
        blocks_rendering=False,
        blocks_completion=False,
    )
    diagnostic.metadata["irs_ref"] = DiagnosticIRSRef(
        construct_type="API_DECLARATION",
        construct_id="api:ApprovedSourceRecipesAPI",
        slot_name=slot_name,
    ).to_dict()
    diagnostic.metadata["authority"] = "post_normalize_irs"
    diagnostic.metadata["repairability"] = "review_only"
    diagnostic.metadata["presentation_disposition"] = "deferred_validation"
    diagnostic.metadata["validation_authority"] = "downstream_spl_compiler"
    diagnostic.metadata["api_contract_validation_status"] = "pending"
    diagnostic.metadata["issue_group_id"] = (
        "api_contract_deferred:ApprovedSourceRecipesAPI"
    )
    diagnostic.metadata["issue_role"] = "primary" if slot_name == "functions" else "alias"
    return diagnostic


def test_expected_correct_api_placeholder_inventory_and_presentation() -> None:
    diagnostics = [_api_deferred("functions"), _api_deferred("openapi_schema")]
    snapshot = ArtifactSnapshot(
        snapshot_id="snap_api",
        compile_run_id="run_api",
        overlay_version=0,
        compile_diagnostics=tuple(diagnostics),
    )

    service = _build_default_service(suggestion_llm=StubSuggestionLLM())
    service.register_compile_result(snapshot)
    inventory = service.list_issue_inventory(snapshot.compile_run_id)
    presentation = SPLEditingPresentationService(service)
    issue_list = presentation.list_issue_presentations(snapshot.compile_run_id)

    assert inventory.editable == ()
    assert len(inventory.deferred) == 1
    assert inventory.deferred[0].repairability == "review_only"
    assert inventory.deferred[0].disposition == "deferred_validation"
    assert _grouped_diag_items(diagnostics) == [diagnostics]

    editable_section = next(
        section
        for section in issue_list.sections
        if section.section_key.value == "editable_issues"
    )
    deferred_section = next(
        section
        for section in issue_list.sections
        if section.section_key.value == "deferred_validation"
    )
    assert editable_section.items == ()
    assert len(deferred_section.items) == 1
    assert deferred_section.items[0].can_fix is False
    assert deferred_section.items[0].category.value == "api_contract_review"
