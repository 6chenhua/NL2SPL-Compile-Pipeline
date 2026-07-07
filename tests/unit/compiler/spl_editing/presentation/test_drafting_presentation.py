from __future__ import annotations

import inspect
from pathlib import Path

from nl2spl.compiler.spl_editing.demo import _build_default_service
from nl2spl.compiler.spl_editing.drafting.model import UserRepairInput
from nl2spl.compiler.spl_editing.interaction.model import SubmitRepairDirectiveDraftRequest
from nl2spl.compiler.spl_editing.presentation.service import SPLEditingPresentationService
from tests.spl_editing_stub_llm import StubSuggestionLLM

SNAPSHOT = Path("examples/output/demo/spl_editing_snapshot.json")


def _runtime():
    editing = _build_default_service(suggestion_llm=StubSuggestionLLM())
    run_id = editing.register_snapshot_file(SNAPSHOT)
    editing._snapshot_repository = None
    presentation = SPLEditingPresentationService(editing)
    snapshot = editing._get_snapshot(run_id)
    revision = f"{snapshot.compile_run_id}:{snapshot.snapshot_id}:{snapshot.overlay_version}"
    issue = next(
        item
        for item in editing.list_issue_inventory(run_id).editable
        if item.irs_ref.construct_type == "WORKER_PROMOTION"
    )
    return editing, presentation, run_id, issue, snapshot, revision


def test_no_provider_shows_drafting_unavailable_without_losing_existing_path() -> None:
    _editing, presentation, run_id, issue, _snapshot, revision = _runtime()

    capability = presentation.get_repair_drafting_capability(
        run_id,
        issue.issue_id,
        "keep_in_main_flow",
        revision,
    )
    assert capability.status == "drafting_unavailable"
    assert capability.reasons == ("no provider",)

    presentation.get_repair_interaction(
        run_id,
        issue.issue_id,
        "keep_in_main_flow",
        revision,
    )
    request = SubmitRepairDirectiveDraftRequest(
        run_id=run_id,
        issue_id=issue.issue_id,
        strategy_id="worker_delegation.complete_closure.v2",
        option_id="keep_in_main_flow",
        contract_id="worker_delegation.keep_in_main_flow.v1",
        contract_version="1",
        revision_token=revision,
        field_values={"task_selection": "source gathering"},
        selected_ref_ids={},
        new_fact_declarations=(),
    )
    submitted = presentation.submit_repair_directive_draft(request)
    assert submitted.input_readiness == "input_complete"


def test_create_repair_draft_rejects_stale_revision() -> None:
    _editing, presentation, run_id, issue, _snapshot, revision = _runtime()
    stale = revision.rsplit(":", 1)[0] + ":99"

    result = presentation.create_repair_draft(
        run_id=run_id,
        issue_id=issue.issue_id,
        option_id="define_child_worker",
        revision_token=stale,
        user_input=UserRepairInput(input_mode="free_text", free_text="Gather evidence"),
    )

    assert result.status == "stale_revision"
    assert result.draft_id is None


def test_non_editable_issue_cannot_create_draft() -> None:
    _editing, presentation, run_id, _issue, _snapshot, revision = _runtime()
    non_editable = next(
        item for item in presentation._editing.list_issue_inventory(run_id).deferred
    )

    result = presentation.create_repair_draft(
        run_id=run_id,
        issue_id=non_editable.issue_id,
        option_id="define_child_worker",
        revision_token=revision,
        user_input=UserRepairInput(input_mode="none"),
    )

    assert result.status == "non_editable_issue"


def test_drafting_api_uses_stable_ids_not_display_index() -> None:
    signature = inspect.signature(SPLEditingPresentationService.create_repair_draft)
    assert "issue_id" in signature.parameters
    assert "option_id" in signature.parameters
    assert "draft_id" not in signature.parameters
    assert "option_index" not in signature.parameters
    assert "display_id" not in signature.parameters
