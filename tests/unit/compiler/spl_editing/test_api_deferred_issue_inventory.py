"""API deferred validation inventory and presentation tests."""

from __future__ import annotations

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.feedback_report_renderer import render_feedback_report
from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.compiler.spl_editing.core.model import EditableIssue
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation import (
    IssueCategory,
    SPLEditingPresentationService,
)
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from nl2spl.pipeline.orchestrator import PipelineOrchestrator
from tests.spl_editing_stub_llm import StubSuggestionLLM


def _api_deferred_diagnostic(
    diagnostic_id: str,
    slot_name: str,
) -> CompileDiagnostic:
    diagnostic = CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind="deferred_api_contract_validation",
        severity="info",
        message="API contract validation is deferred downstream.",
        target_ref="api:SearchAPI",
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
        construct_id="api:SearchAPI",
        slot_name=slot_name,
    ).to_dict()
    diagnostic.metadata["authority"] = "post_normalize_irs"
    diagnostic.metadata["repairability"] = "review_only"
    diagnostic.metadata["presentation_disposition"] = "deferred_validation"
    diagnostic.metadata["validation_authority"] = "downstream_spl_compiler"
    diagnostic.metadata["api_contract_validation_status"] = "pending"
    diagnostic.metadata["issue_group_id"] = "api_contract_deferred:SearchAPI"
    return diagnostic


def _snapshot(diagnostics: tuple[CompileDiagnostic, ...]) -> ArtifactSnapshot:
    return ArtifactSnapshot(
        snapshot_id="snap_api",
        compile_run_id="run_api",
        overlay_version=0,
        compile_diagnostics=diagnostics,
    )


def _service_with_api_deferred() -> tuple[SPLEditingPresentationService, str]:
    service = _build_default_service(suggestion_llm=StubSuggestionLLM())
    snapshot = _snapshot(
        (
            _api_deferred_diagnostic("diag_api_openapi", "openapi_schema"),
            _api_deferred_diagnostic("diag_api_functions", "functions"),
        )
    )
    service.register_artifact_snapshot(snapshot)
    return SPLEditingPresentationService(service), snapshot.compile_run_id


def test_api_deferred_validation_is_inventory_deferred_not_editable() -> None:
    presentation, run_id = _service_with_api_deferred()
    inventory = presentation._editing.list_issue_inventory(run_id)

    assert inventory.editable == ()
    assert len(inventory.deferred) == 1
    issue = inventory.deferred[0]
    assert not isinstance(issue, EditableIssue)
    assert issue.repairability == "review_only"
    assert issue.disposition == "deferred_validation"
    assert issue.validation_authority == "downstream_spl_compiler"
    assert set(issue.related_diagnostic_ids) == {
        "diag_api_openapi",
        "diag_api_functions",
    }


def test_api_deferred_validation_appears_in_presentation_without_fix_action() -> None:
    presentation, run_id = _service_with_api_deferred()

    run = presentation.get_run_presentation(run_id)
    issue_list = presentation.list_issue_presentations(run_id)
    deferred_section = next(
        section
        for section in issue_list.sections
        if section.section_key.value == "deferred_validation"
    )

    assert run.editable is False
    assert run.editable_issue_count == 0
    assert run.deferred_validation_count == 1
    assert issue_list.sections[0].section_key.value == "editable_issues"
    assert issue_list.sections[0].items == ()
    assert len(deferred_section.items) == 1
    card = deferred_section.items[0]
    assert card.category == IssueCategory.API_CONTRACT_REVIEW
    assert card.can_fix is False
    assert card.repairability == "review_only"
    assert card.title == "API contract validation is deferred"
    issue = presentation.issue_by_id(run_id, card.issue_id)
    assert issue.issue_id == card.issue_id
    assert issue.repairability == "review_only"


def test_orchestrator_annotator_keeps_api_deferred_review_only() -> None:
    diagnostics = [
        _api_deferred_diagnostic("diag_api_openapi", "openapi_schema"),
        _api_deferred_diagnostic("diag_api_functions", "functions"),
    ]
    for diagnostic in diagnostics:
        diagnostic.metadata.pop("repairability")
        diagnostic.metadata.pop("issue_role", None)

    PipelineOrchestrator._annotate_editable_diagnostics_for_snapshot_contract(diagnostics)

    assert {d.metadata["repairability"] for d in diagnostics} == {"review_only"}
    assert {d.metadata["issue_group_id"] for d in diagnostics} == {
        "api_contract_deferred:SearchAPI"
    }
    assert [
        d.diagnostic_id
        for d in sorted(diagnostics, key=lambda d: d.metadata["issue_role"])
        if d.metadata["issue_role"] == "primary"
    ] == ["diag_api_functions"]


def test_feedback_report_groups_api_deferred_validation_once() -> None:
    diagnostics = [
        _api_deferred_diagnostic("diag_api_openapi", "openapi_schema"),
        _api_deferred_diagnostic("diag_api_functions", "functions"),
    ]
    PipelineOrchestrator._annotate_editable_diagnostics_for_snapshot_contract(diagnostics)

    report = render_feedback_report(
        "DEFINE_APIS SearchAPI AS {};",
        completeness="complete",
        diagnostics=diagnostics,
    )

    assert "No completion-blocking diagnostic was emitted." in report
    assert "## 5. Deferred Validation" in report
    assert report.count("API contract validation deferred downstream.") == 1
    assert report.count("grouped:api:SearchAPI") == 1
    assert "Fix with AI" not in report
