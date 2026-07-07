from __future__ import annotations

from pathlib import Path

from nl2spl.compiler.spl_editing.demo import _build_default_service
from nl2spl.compiler.spl_editing.drafting.model import UserRepairFieldValue, UserRepairInput
from nl2spl.compiler.spl_editing.drafting.values import (
    BusinessLogicValue,
    NewOutputDraftValue,
    ResponsibilityValue,
    SelectedInputRefsValue,
)
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


def _assert_typed_preview_boundary(handle) -> None:
    typed_artifact = handle.preview.typed_artifact
    assert typed_artifact is not None
    roles = {node.role for node in typed_artifact.construct_nodes}
    assert {"child_worker", "child_command", "worker_handoff", "parent_invoke"}.issubset(
        roles
    )
    rendered = handle.preview.rendered_preview
    assert "COMMAND-X" not in rendered
    assert "USING " not in rendered
    assert "ChildWorker_" not in rendered
    assert "WorkerIR(" not in rendered
    assert "StepIR(" not in rendered


def test_define_child_worker_draft_first_lane_b_e2e() -> None:
    editing, presentation, run_id, issue, base, revision = _runtime()
    assert _has_approved_source_recipes_call(base.worker_step_plan.main_worker_steps)

    creation = presentation.create_repair_draft(
        run_id=run_id,
        issue_id=issue.issue_id,
        option_id="define_child_worker",
        revision_token=revision,
        user_input=UserRepairInput(
            input_mode="free_text",
            free_text="Gather approved source evidence",
            selected_option_id="define_child_worker",
        ),
    )
    assert creation.status == "draft_created"
    assert creation.draft_id is not None
    assert creation.draft_preview is not None
    assert creation.draft.clarification_questions == ()
    assert {field.field_id for field in creation.draft.fields}.issuperset(
        {
            "child_task",
            "child_inputs",
            "child_output",
            "child_business_logic",
            "placement",
            "result_binding",
        }
    )
    assert all(field.confidence in {"high", "medium"} for field in creation.draft.fields)
    assert creation.draft.trace
    assert all(field.evidence_refs for field in creation.draft.fields)
    assert all(record.evidence_refs for record in creation.draft.trace)
    assert {record.field_id for record in creation.draft.trace} == {
        field.field_id for field in creation.draft.fields
    }
    responsibility = next(
        field for field in creation.draft.fields if field.field_id == "child_task"
    )
    responsibility_trace = next(
        record for record in creation.draft.trace if record.field_id == "child_task"
    )
    assert responsibility.evidence_refs == ("user_input:free_text",)
    assert responsibility_trace.evidence_refs == ("user_input:free_text",)

    accepted = presentation.accept_repair_draft(
        run_id=run_id,
        issue_id=issue.issue_id,
        option_id="define_child_worker",
        session_id=creation.session_id,
        draft_id=creation.draft_id,
        revision_token=revision,
        user_input=_accepted_defaults(creation.draft, creation.draft_id),
    )
    assert accepted.input_readiness == "input_complete"
    assert accepted.normalized_directive_id is not None

    handle = presentation.create_materialized_preview_from_draft(
        accepted.normalized_directive_id
    )
    _assert_typed_preview_boundary(handle)
    session, verification = presentation.accept_materialized_preview(
        directive_id=accepted.normalized_directive_id,
        preview_id=handle.preview.preview_id,
        user_input=UserRepairInput(
            input_mode="none",
            accepted_draft_id=creation.draft_id,
            draft_accepted=True,
            materialized_preview_accepted=True,
        ),
    )

    assert verification.accepted is True
    assert verification.lane == "B"
    assert issue.primary_diagnostic_id in verification.resolved_diagnostic_ids
    patched = editing._snapshots.get(
        run_id,
        base.snapshot_id,
        overlay_version=session.overlay_version,
    )
    marker = patched.promotion_resolution_markers[0]
    assert marker.resolution_kind == "defined_child_worker"
    assert _has_approved_source_recipes_call(patched.worker_step_plan.main_worker_steps)
    rendered = editing._verifier._lane_b.replay(patched).rendered_spl
    assert "CALL ApprovedSourceRecipesAPI" in rendered


def test_draft_first_does_not_require_user_technical_fields() -> None:
    _editing, presentation, run_id, issue, _base, revision = _runtime()
    creation = presentation.create_repair_draft(
        run_id=run_id,
        issue_id=issue.issue_id,
        option_id="define_child_worker",
        revision_token=revision,
        user_input=UserRepairInput(input_mode="free_text", free_text="Gather evidence"),
    )

    assert creation.status == "draft_created"
    assert creation.draft is not None
    user_supplied = {field.field_id for field in creation.draft.fields}
    assert "placement_ref" not in user_supplied
    assert "handoff_binding" not in user_supplied
    assert "invoke_output" not in user_supplied


def _accepted_defaults(draft, draft_id: str) -> UserRepairInput:
    fields = {field.field_id: field.value for field in draft.fields}
    task = fields["child_task"]
    inputs = fields["child_inputs"]
    output = fields["child_output"]
    logic = fields["child_business_logic"]
    assert isinstance(task, ResponsibilityValue)
    assert isinstance(inputs, SelectedInputRefsValue)
    assert isinstance(output, NewOutputDraftValue)
    assert isinstance(logic, BusinessLogicValue)
    return UserRepairInput(
        input_mode="structured_form",
        field_values=(
            UserRepairFieldValue("child_task", task.text, "accepted_default"),
            UserRepairFieldValue("child_inputs", inputs.ref_ids, "accepted_default"),
            UserRepairFieldValue("child_output", output.display_name, "accepted_default"),
            UserRepairFieldValue("child_business_logic", logic.text, "accepted_default"),
        ),
        accepted_draft_id=draft_id,
        draft_accepted=True,
    )


def _has_approved_source_recipes_call(steps) -> bool:
    return any(
        step.command_type == "CALL_API"
        and step.integration_ref == "ApprovedSourceRecipesAPI"
        for step in steps
    )
