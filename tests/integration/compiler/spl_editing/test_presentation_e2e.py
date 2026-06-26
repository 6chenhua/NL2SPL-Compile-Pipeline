"""End-to-end presentation + suggestion verification.

Validates the SPL Editing flow through the presentation API:
  run list -> issue list -> issue detail -> suggestions -> confirmation DTOs

Covers valid LLM output, malformed LLM fail-fast behavior, unsupported
patch type propagation, and presentation boundary invariants.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.compile_result import MissingSlot
from nl2spl.compiler.spl_editing.cli import _build_default_service
from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    UnsupportedPatchTypeError,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation import (
    IssueCategory,
    SPLEditingPresentationService,
)
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef
from nl2spl.ir.flow_structure_ir import ExceptionFlow, FlowStructureIR
from nl2spl.ir.worker_plan_ir import (
    WorkerFlowPlanIR,
    WorkerPlanIR,
    WorkerSpecIR,
)
from tests.spl_editing_stub_llm import StubSuggestionLLM

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _exception_diagnostic() -> CompileDiagnostic:
    d = CompileDiagnostic(
        "diag_exc",
        "missing_handler",
        "warning",
        "Exception flow has no handler.",
        target_ref="worker:w_main.exception_flow:exc_1",
        missing_slot=MissingSlot("handler_action", "complete", "missing"),
    )
    d.metadata["irs_ref"] = DiagnosticIRSRef(
        construct_type="EXCEPTION_FLOW",
        construct_id="worker:w_main.exception_flow:exc_1",
        slot_name="handler_action",
        construct_path=(),
    ).to_dict()
    d.metadata["authority"] = "post_normalize_irs"
    d.metadata["repairability"] = "editable"
    d.metadata["issue_role"] = "primary"
    return d


def _exception_snapshot() -> ArtifactSnapshot:
    return ArtifactSnapshot(
        snapshot_id="snap_e2e",
        compile_run_id="run_e2e",
        overlay_version=0,
        worker_plan=object(),
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={
                "w_main": FlowStructureIR(
                    exception_flows=[
                        ExceptionFlow(
                            flow_id="exc_1",
                            condition_text="Template unavailable",
                            spans=[],
                        )
                    ]
                )
            }
        ),
        worker_block_plan=object(),
        worker_step_plan=object(),
        resources=object(),
        symbol_table=object(),
        compile_diagnostics=(_exception_diagnostic(),),
    )


def _promotion_diagnostics() -> tuple[CompileDiagnostic, ...]:
    slots = (
        "promotion_input_contract",
        "promotion_output_contract",
        "promotion_invocation_point",
        "promotion_result_handoff",
    )
    result: list[CompileDiagnostic] = []
    for idx, slot in enumerate(slots):
        d = CompileDiagnostic(
            f"diag_promo_{idx}",
            "type_or_contract_ambiguity",
            "warning",
            f"Ambiguity in {slot}.",
            target_ref="worker_promotion:del_s30",
            missing_slot=MissingSlot(slot, "complete", "missing"),
        )
        d.metadata["irs_ref"] = DiagnosticIRSRef(
            construct_type="WORKER_PROMOTION",
            construct_id="worker_promotion:del_s30",
            slot_name=slot,
            construct_path=(),
        ).to_dict()
        d.metadata["authority"] = "post_normalize_irs"
        d.metadata["repairability"] = "editable"
        d.metadata["issue_group_id"] = "grp_promo"
        d.metadata["issue_role"] = "primary" if idx == 0 else "related"
        result.append(d)
    return tuple(result)


def _promotion_snapshot() -> ArtifactSnapshot:
    worker_plan = WorkerPlanIR(
        main_worker_id="w_main",
        workers=[
            WorkerSpecIR(
                worker_id="w_main",
                worker_name="main",
                kind="main",
                purpose="Main worker",
            ),
        ],
        handoffs=(),
    )
    return ArtifactSnapshot(
        snapshot_id="snap_promo",
        compile_run_id="run_promo",
        overlay_version=0,
        worker_plan=worker_plan,
        worker_flow_plan=object(),
        worker_block_plan=object(),
        worker_step_plan=object(),
        resources=object(),
        symbol_table=object(),
        agent_profile=None,
        compile_diagnostics=_promotion_diagnostics(),
    )


# ---------------------------------------------------------------------------
# E2E: Run list + issue list + detail — valid LLM
# ---------------------------------------------------------------------------


class TestE2EExceptionHandlingValidLLM:
    """Presentation DTO flow: exception issue with valid LLM output."""

    def test_presentation_flow_with_valid_llm(self) -> None:
        llm = StubSuggestionLLM()
        svc = _build_default_service(suggestion_llm=llm)
        svc.register_artifact_snapshot(_exception_snapshot())
        pres = SPLEditingPresentationService(svc)

        # Run list
        runs = pres.list_run_presentations()
        assert len(runs) == 1
        assert runs[0].run_id == "run_e2e"
        assert runs[0].issue_count >= 1

        # Issue list — sectioned, editable
        issue_list = pres.list_issue_presentations("run_e2e")
        assert len(issue_list.sections) >= 1
        assert issue_list.sections[0].section_key.value == "editable_issues"
        cards = issue_list.sections[0].items
        assert len(cards) == 1
        card = cards[0]
        assert card.category == IssueCategory.EXCEPTION_HANDLING
        assert card.title == "Exception has no handler: Template unavailable"
        assert card.can_fix is True

        # Issue detail — repair options from catalog
        detail = pres.get_issue_detail_presentation("run_e2e", card.issue_id)
        assert detail.title == card.title
        assert len(detail.available_repairs) >= 1
        assert detail.available_repairs[0].label == "Add handler step"

        # Choose a repair option (demo flow: select option, then generate)
        option = detail.available_repairs[0]
        assert option.patch_types == ("AddExceptionHandlerStep",)

        issue = pres.issue_by_id("run_e2e", card.issue_id)
        session = svc.create_session("run_e2e", issue)
        suggestions = svc.generate_suggestions(
            session.session_id,
            selected_patch_types=option.patch_types,
        )
        assert len(suggestions) == 1
        assert suggestions[0].title == "Stub suggestion 1"
        assert suggestions[0].patch.patch_type == "AddExceptionHandlerStep"
        # All suggestions must be the selected patch type
        assert all(s.patch.patch_type in option.patch_types for s in suggestions)

        # Suggestion presentation DTOs
        sug_views = pres.present_suggestions(suggestions)
        assert len(sug_views) == 1
        assert sug_views[0].title == "Stub suggestion 1"
        assert len(sug_views[0].expected_effect) >= 1

        # Apply confirmation presentation DTO
        confirmation = pres.present_apply_confirmation(suggestions[0])
        assert confirmation.verification_lane == "B"
        assert "Apply typed patch" in confirmation.will_do[0]
        assert "Modify final SPL text directly" in confirmation.will_not_do[0]


# ---------------------------------------------------------------------------
# E2E: LLM failure is surfaced
# ---------------------------------------------------------------------------


class TestE2ELLMFailure:
    """LLM returns malformed JSON; handlers surface the error."""

    def test_exception_handler_malformed_llm_raises(self) -> None:
        """MissingHandler: malformed LLM output raises."""
        llm = StubSuggestionLLM(
            fixed_response={
                "patch_type": "AddExceptionHandlerStep",
                "title": "T",
                # missing "explanation" -> PatchValidationError
            }
        )
        svc = _build_default_service(suggestion_llm=llm)
        svc.register_artifact_snapshot(_exception_snapshot())
        pres = SPLEditingPresentationService(svc)

        issue_list = pres.list_issue_presentations("run_e2e")
        issue = pres.issue_by_id("run_e2e", issue_list.sections[0].items[0].issue_id)
        session = svc.create_session("run_e2e", issue)
        with pytest.raises(PatchValidationError, match="LLM did not produce"):
            svc.generate_suggestions(session.session_id)

    def test_worker_delegation_malformed_llm_raises(self) -> None:
        """TypeOrContractAmbiguity: malformed LLM is surfaced."""
        llm = StubSuggestionLLM(fixed_response={"not": "valid"})
        svc = _build_default_service(suggestion_llm=llm)
        svc.register_artifact_snapshot(_promotion_snapshot())
        pres = SPLEditingPresentationService(svc)

        # 4 related slots -> 1 grouped issue
        issue_list = pres.list_issue_presentations("run_promo")
        editable = next(s for s in issue_list.sections if s.section_key.value == "editable_issues")
        cards = editable.items
        assert len(cards) == 1
        assert cards[0].category == IssueCategory.WORKER_DELEGATION
        assert cards[0].title == "Worker delegation is underspecified"
        assert len(cards[0].missing_items) == 4

        # Malformed LLM output is surfaced instead of hidden.
        issue = pres.issue_by_id("run_promo", cards[0].issue_id)
        session = svc.create_session("run_promo", issue)
        with pytest.raises(PatchValidationError, match="LLM did not produce"):
            svc.generate_suggestions(session.session_id)


# ---------------------------------------------------------------------------
# E2E: Worker delegation — selected_patch_types returns multiple same-type suggestions
# ---------------------------------------------------------------------------


class TestE2EWorkerDelegationSelectedPatchTypes:
    """Worker delegation: choose a repair option, get multiple suggestions of that type."""

    def test_selected_patch_type_returns_multiple_suggestions(self) -> None:
        """Select one patch type → multiple concrete suggestions of that type."""
        llm = StubSuggestionLLM()
        svc = _build_default_service(suggestion_llm=llm)
        svc.register_artifact_snapshot(_promotion_snapshot())
        pres = SPLEditingPresentationService(svc)

        issue_list = pres.list_issue_presentations("run_promo")
        editable = next(s for s in issue_list.sections if s.section_key.value == "editable_issues")
        card = editable.items[0]

        # Verify available repair options
        detail = pres.get_issue_detail_presentation("run_promo", card.issue_id)
        assert len(detail.available_repairs) >= 2

        # Choose the "Convert to main-flow step" option (index 1; index 0 is
        # CreateWorkerHandoffContract which requires a child worker in context).
        convert_option = detail.available_repairs[1]
        assert convert_option.patch_types == ("ConvertDelegationIntentToMainFlowStep",)

        issue = pres.issue_by_id("run_promo", card.issue_id)
        session = svc.create_session("run_promo", issue)
        suggestions = svc.generate_suggestions(
            session.session_id,
            selected_patch_types=convert_option.patch_types,
        )
        assert len(suggestions) == 1
        assert all(
            s.patch.patch_type == "ConvertDelegationIntentToMainFlowStep" for s in suggestions
        ), (
            f"All suggestions must be 'ConvertDelegationIntentToMainFlowStep', "
            f"got {[s.patch.patch_type for s in suggestions]}"
        )


# ---------------------------------------------------------------------------
# E2E: Presentation DTO boundary — no raw diagnostic leak
# ---------------------------------------------------------------------------


class TestE2EPresentationBoundary:
    """Presentation DTOs never expose raw diagnostic IDs in default view."""

    def test_default_titles_are_user_readable(self) -> None:
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        svc.register_artifact_snapshot(_exception_snapshot())
        pres = SPLEditingPresentationService(svc)

        issue_list = pres.list_issue_presentations("run_e2e")
        card = issue_list.sections[0].items[0]

        assert card.title != "diag_exc"
        assert card.title.startswith("Exception has no handler")
        assert "EXCEPTION_FLOW" not in card.title
        assert "exc_1" not in card.title

    def test_advanced_details_hold_raw_ids(self) -> None:
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        svc.register_artifact_snapshot(_exception_snapshot())
        pres = SPLEditingPresentationService(svc)

        issue_list = pres.list_issue_presentations("run_e2e")
        card = issue_list.sections[0].items[0]
        assert card.advanced is not None
        assert card.advanced.primary_diagnostic_id == "diag_exc"

    def test_developer_section_hidden_by_default(self) -> None:
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        svc.register_artifact_snapshot(_exception_snapshot())
        pres = SPLEditingPresentationService(svc)

        issue_list = pres.list_issue_presentations("run_e2e")
        assert all(s.section_key.value != "developer_diagnostics" for s in issue_list.sections)

    def test_developer_mode_shows_developer_diagnostics(self) -> None:
        svc = _build_default_service(suggestion_llm=StubSuggestionLLM())
        svc.register_artifact_snapshot(_exception_snapshot())
        pres = SPLEditingPresentationService(svc)

        issue_list = pres.list_issue_presentations("run_e2e", include_developer=True)
        assert "developer_diagnostics" in {s.section_key.value for s in issue_list.sections}


# ---------------------------------------------------------------------------
# E2E: UnsupportedPatchTypeError still propagates (not swallowed by fallback)
# ---------------------------------------------------------------------------


class TestE2EUnsupportedPatchTypePropagation:
    """LLM returning an unsupported patch type must raise, not fallback."""

    def test_unsupported_type_propagates(self) -> None:
        llm = StubSuggestionLLM(
            fixed_response={
                "patch_type": "WrongType",
                "title": "Bad",
                "explanation": "Bad",
                "payload": {},
            }
        )
        svc = _build_default_service(suggestion_llm=llm)
        svc.register_artifact_snapshot(_exception_snapshot())

        issue_list = svc.list_editable_issues("run_e2e")
        session = svc.create_session("run_e2e", issue_list[0])

        with pytest.raises(UnsupportedPatchTypeError):
            svc.generate_suggestions(session.session_id)
