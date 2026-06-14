"""Presentation DTO layer tests."""

from __future__ import annotations

import inspect
from dataclasses import replace
from pathlib import Path

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.compiler.spl_editing.core.model import EditableIssue
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation import (
    IssueCategory,
    PresentationQuality,
    RepairOptionAvailability,
    SPLEditingPresentationService,
)
from nl2spl.compiler.spl_editing.presentation.builders import (
    IssuePresentationBuilder,
)
from nl2spl.compiler.spl_editing.presentation.contract.invariants import (
    expected_can_fix,
)
from nl2spl.compiler.spl_editing.presentation.model.issue import RepairOptionView
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.worker_plan_ir import WorkerFlowPlanIR
from tests.spl_editing_stub_llm import StubSuggestionLLM


def _irs(
    construct_type: str = "EXCEPTION_FLOW",
    construct_id: str = "worker:worker_main.exception_flow:exc_1",
    slot_name: str = "handler_action",
) -> DiagnosticIRSRef:
    return DiagnosticIRSRef(
        construct_type=construct_type,
        construct_id=construct_id,
        slot_name=slot_name,
        construct_path=(),
    )


def _issue(
    *,
    issue_id: str = "diag_1",
    kind: str = "missing_handler",
    target_ref: str = "worker:worker_main.exception_flow:exc_1",
    irs_ref: DiagnosticIRSRef | None = None,
    related: tuple[str, ...] | None = None,
    repairability: str = "editable",
    message: str = "diagnostic message must not be parsed",
) -> EditableIssue:
    irs_ref = irs_ref or _irs()
    return EditableIssue(
        issue_id=issue_id,
        primary_diagnostic_id=issue_id,
        related_diagnostic_ids=related or (issue_id,),
        issue_group_id=None,
        kind=kind,
        target_ref=target_ref,
        irs_ref=irs_ref,
        missing_slot=irs_ref.slot_name,
        source_span_ids=(),
        message=message,
        authority="post_normalize_irs",
        affordance_ids=("affordance",),
        repairability=repairability,  # type: ignore[arg-type]
    )


def _diagnostic(
    diagnostic_id: str,
    *,
    kind: str = "missing_handler",
    irs_ref: DiagnosticIRSRef | None = None,
    target_ref: str = "worker:worker_main.exception_flow:exc_1",
    issue_group_id: str | None = None,
    issue_role: str = "primary",
) -> CompileDiagnostic:
    irs_ref = irs_ref or _irs()
    diagnostic = CompileDiagnostic(
        diagnostic_id=diagnostic_id,
        kind=kind,
        severity="warning",
        message="Message text is not a primary presentation fact",
        target_ref=target_ref,
        missing_slot=MissingSlot(
            slot_name=irs_ref.slot_name,
            required_for="complete",
            reason="missing",
        ),
    )
    diagnostic.metadata["irs_ref"] = irs_ref.to_dict()
    diagnostic.metadata["authority"] = "post_normalize_irs"
    diagnostic.metadata["repairability"] = "editable"
    diagnostic.metadata["issue_role"] = issue_role
    if issue_group_id:
        diagnostic.metadata["issue_group_id"] = issue_group_id
    return diagnostic


def _snapshot(
    *,
    compile_diagnostics: tuple[CompileDiagnostic, ...] = (),
    include_lane_artifacts: bool = True,
    condition_text: str | None = "Template unavailable",
) -> ArtifactSnapshot:
    worker_flow_plan = (
        WorkerFlowPlanIR(
            worker_flows={
                "worker_main": FlowStructureIR(
                    exception_flows=[
                        ExceptionFlow(
                            flow_id="exc_1",
                            condition_text=condition_text or "",
                            spans=[],
                        )
                    ]
                )
            }
        )
        if condition_text is not None
        else None
    )
    lane_value = object() if include_lane_artifacts else None
    return ArtifactSnapshot(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=0,
        worker_plan=lane_value,
        worker_flow_plan=worker_flow_plan if include_lane_artifacts else None,
        worker_block_plan=lane_value,
        worker_step_plan=lane_value,
        resources=lane_value,
        symbol_table=lane_value,
        compile_diagnostics=compile_diagnostics,
    )


def _builder() -> IssuePresentationBuilder:
    service = _build_default_service(suggestion_llm=StubSuggestionLLM())
    return IssuePresentationBuilder(catalog=service._catalog, runtime=service._runtime)


def test_can_fix_invariant_uses_available_repair_options() -> None:
    options = (
        RepairOptionView(
            label="Unavailable",
            description="x",
            availability=RepairOptionAvailability.REVIEW_ONLY,
        ),
        RepairOptionView(
            label="Available",
            description="x",
            availability=RepairOptionAvailability.AVAILABLE,
        ),
    )

    assert expected_can_fix(options) is True


def test_exception_title_uses_artifact_condition_not_diagnostic_message() -> None:
    issue = _issue(message="NEVER_USE_THIS_CONDITION")
    snapshot = _snapshot(compile_diagnostics=(_diagnostic(issue.issue_id),))
    card = _builder().build_card(
        display_id=1,
        issue=issue,
        snapshot=snapshot,
        diagnostics=snapshot.compile_diagnostics,
    )

    assert card.title == "Exception has no handler: Template unavailable"
    assert "NEVER_USE_THIS_CONDITION" not in card.title


def test_missing_condition_degrades_without_showing_compiler_id_or_message() -> None:
    issue = _issue(message="NEVER_USE_THIS_CONDITION")
    snapshot = _snapshot(
        compile_diagnostics=(_diagnostic(issue.issue_id),),
        condition_text=None,
    )
    card = _builder().build_card(
        display_id=1,
        issue=issue,
        snapshot=snapshot,
        diagnostics=snapshot.compile_diagnostics,
    )

    assert card.title == "Exception has no handler"
    assert "exc_1" not in card.title
    assert "NEVER_USE_THIS_CONDITION" not in card.title
    assert card.presentation_quality == PresentationQuality.DEGRADED


def test_worker_promotion_related_slots_become_one_delegation_issue() -> None:
    slots = (
        "promotion_input_contract",
        "promotion_output_contract",
        "promotion_invocation_point",
        "promotion_result_handoff",
    )
    diagnostics = tuple(
        _diagnostic(
            f"diag_{idx}",
            kind="type_or_contract_ambiguity",
            irs_ref=_irs(
                construct_type="WORKER_PROMOTION",
                construct_id="worker_promotion:del_s30",
                slot_name=slot,
            ),
            target_ref="worker_promotion:del_s30",
            issue_group_id="grp_1",
            issue_role="primary" if idx == 0 else "related",
        )
        for idx, slot in enumerate(slots)
    )
    issue = _issue(
        issue_id="diag_0",
        kind="type_or_contract_ambiguity",
        target_ref="worker_promotion:del_s30",
        irs_ref=_irs(
            construct_type="WORKER_PROMOTION",
            construct_id="worker_promotion:del_s30",
            slot_name="promotion_input_contract",
        ),
        related=tuple(d.diagnostic_id for d in diagnostics),
    )
    snapshot = _snapshot(compile_diagnostics=diagnostics)

    card = _builder().build_card(
        display_id=1,
        issue=issue,
        snapshot=snapshot,
        diagnostics=snapshot.compile_diagnostics,
    )

    assert card.category == IssueCategory.WORKER_DELEGATION
    assert card.title == "Worker delegation is underspecified"
    assert card.missing_items == (
        "input contract",
        "output contract",
        "invocation point",
        "result handoff",
    )


def test_issue_list_is_sectioned_and_review_only_is_separate() -> None:
    editable = _issue(issue_id="editable")
    review = _issue(issue_id="review", repairability="review_only")
    snapshot = _snapshot()

    issue_list = _builder().build_list(
        run_id="run_1",
        snapshot=snapshot,
        issues=(editable, review),
    )

    assert [section.label for section in issue_list.sections] == [
        "Editable issues",
        "Review needed",
    ]
    assert issue_list.sections[0].items[0].issue_id == "editable"
    assert issue_list.sections[1].items[0].issue_id == "review"


def test_snapshot_capability_gap_marks_option_unavailable() -> None:
    issue = _issue()
    snapshot = _snapshot(include_lane_artifacts=False)

    card = _builder().build_card(
        display_id=1,
        issue=issue,
        snapshot=snapshot,
        diagnostics=(),
    )

    assert card.can_fix is False


def test_suggested_resolution_does_not_make_option_available() -> None:
    issue = _issue(message="x")
    issue = replace(issue, suggested_resolution="Add a handler step.")
    snapshot = _snapshot(include_lane_artifacts=False)

    card = _builder().build_card(
        display_id=1,
        issue=issue,
        snapshot=snapshot,
        diagnostics=(),
    )

    assert card.suggested_resolution == "Add a handler step."
    assert card.can_fix is False


def test_presentation_service_returns_dtos_from_core_service() -> None:
    service = _build_default_service(suggestion_llm=StubSuggestionLLM())
    diagnostic = _diagnostic("diag_1")
    service.register_artifact_snapshot(_snapshot(compile_diagnostics=(diagnostic,)))
    presentation = SPLEditingPresentationService(service)

    run_view = presentation.get_run_presentation("run_1")
    issue_list = presentation.list_issue_presentations("run_1")

    assert run_view.snapshot_id == "snap_1"
    assert issue_list.sections[0].items
    assert issue_list.sections[0].items[0].title.startswith("Exception has no handler")


def test_presentation_service_lists_registered_runs() -> None:
    service = _build_default_service(suggestion_llm=StubSuggestionLLM())
    service.register_artifact_snapshot(_snapshot())
    presentation = SPLEditingPresentationService(service)

    runs = presentation.list_run_presentations()

    assert len(runs) == 1
    assert runs[0].run_id == "run_1"


def test_demo_cli_consumes_presentation_api_not_raw_diagnostics() -> None:
    path = Path("examples/output/spl_editing_demo/run_demo.py")
    source = path.read_text(encoding="utf-8")

    assert "SPLEditingPresentationService" in source
    assert "IRS diagnostics" not in source
    assert "DiagnosticIRSRef" not in source
    assert "CompileDiagnostic" not in source
    assert "RepairCatalog" not in source


def test_model_and_template_boundaries() -> None:
    model_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/nl2spl/compiler/spl_editing/presentation/model").glob("*.py")
    )
    template_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("src/nl2spl/compiler/spl_editing/presentation/templates").glob("*.py")
    )

    assert "CompileDiagnostic" not in model_sources
    assert "import RepairCatalog" not in template_sources
    assert "from nl2spl.compiler.spl_editing.core.catalog" not in template_sources
    assert "supported_patch_types" not in template_sources
    assert "handler_id" not in template_sources


def test_presentation_resolvers_do_not_parse_diagnostic_message() -> None:
    import nl2spl.compiler.spl_editing.presentation.resolvers.display_context as dc
    import nl2spl.compiler.spl_editing.presentation.resolvers.source_excerpt as se

    source = inspect.getsource(dc) + inspect.getsource(se)
    assert ".message" not in source
    assert "regex" not in source.lower()


