from __future__ import annotations

from pathlib import Path

from nl2spl.compiler.spl_editing.demo import _build_default_service
from nl2spl.compiler.spl_editing.handlers.missing_handler.handler import (
    MissingHandlerRepairHandler,
)
from nl2spl.compiler.spl_editing.handlers.missing_output_producer.handler import (
    MissingOutputProducerHandler,
)
from nl2spl.compiler.spl_editing.interaction.model import (
    SubmitRepairDirectiveDraftRequest,
)
from nl2spl.compiler.spl_editing.presentation.service import (
    SPLEditingPresentationService,
)
from tests.spl_editing_stub_llm import StubSuggestionLLM

SNAPSHOT = Path("examples/output/demo/spl_editing_snapshot.json")


def _runtime():
    editing = _build_default_service(suggestion_llm=StubSuggestionLLM())
    run_id = editing.register_snapshot_file(SNAPSHOT)
    editing._snapshot_repository = None
    presentation = SPLEditingPresentationService(editing)
    snapshot = editing._get_snapshot(run_id)
    revision = f"{snapshot.compile_run_id}:{snapshot.snapshot_id}:{snapshot.overlay_version}"
    return editing, presentation, run_id, snapshot, revision


def _worker_issue(editing, run_id):
    return next(
        item
        for item in editing.list_issue_inventory(run_id).editable
        if item.irs_ref.construct_type == "WORKER_PROMOTION"
    )


def test_rd0_current_define_child_form_first_exposes_technical_fields() -> None:
    editing, presentation, run_id, _snapshot, revision = _runtime()
    issue = _worker_issue(editing, run_id)

    interaction = presentation.get_repair_interaction(
        run_id, issue.issue_id, "define_child_worker", revision
    )

    assert interaction.interaction_kind == "structured_with_notes"
    field_ids = {field.field_id for field in interaction.fields}
    assert {
        "placement_ref",
        "invocation_timing",
        "result_usage",
        "returned_results",
        "input_refs",
    }.issubset(field_ids)
    assert interaction.input_readiness == "input_required"


def test_rd0_current_define_child_worker_e2e_still_lane_b_accepted() -> None:
    editing, presentation, run_id, snapshot, revision = _runtime()
    issue = _worker_issue(editing, run_id)
    interaction = presentation.get_repair_interaction(
        run_id, issue.issue_id, "define_child_worker", revision
    )
    input_ref = next(
        option.value
        for field in interaction.fields
        if field.field_id == "input_refs"
        for option in field.options
        if option.label == "user_request"
    )
    request = SubmitRepairDirectiveDraftRequest(
        run_id=run_id,
        issue_id=issue.issue_id,
        strategy_id="worker_delegation.complete_closure.v2",
        option_id="define_child_worker",
        contract_id="worker_delegation.define_child_worker.v1",
        contract_version="1",
        revision_token=revision,
            field_values={
                "child_business_logic": (
                    "Gather approved source evidence using user_request; "
                    "return delegated evidence."
                ),
                "delegated_responsibility": "Gather approved source evidence",
            "invocation_timing": "append",
            "result_usage": (
                {
                    "output_local_id": "evidence",
                    "create_parent_local_temporary": "yes",
                },
            ),
        },
        selected_ref_ids={"input_refs": (input_ref,)},
        new_fact_declarations=(
            {
                "local_id": "evidence",
                "display_name": "delegated evidence",
                "semantic_description": "Evidence returned by the child worker",
                "data_type_hint": "text",
            },
        ),
    )

    submitted = presentation.submit_repair_directive_draft(request)
    assert submitted.input_readiness == "input_complete"
    handle = presentation.preview_repair_directive(submitted.normalized_directive_id)
    session, verification = presentation.apply_repair_preview(
        submitted.normalized_directive_id, handle.preview.preview_id
    )

    assert verification.accepted is True
    assert verification.lane == "B"
    assert issue.primary_diagnostic_id in verification.resolved_diagnostic_ids
    patched = editing._snapshots.get(
        run_id, snapshot.snapshot_id, overlay_version=session.overlay_version
    )
    assert patched.overlay_version == snapshot.overlay_version + 1


def test_rd0_existing_missing_handler_and_output_handlers_remain_available() -> None:
    editing, _presentation, _run_id, _snapshot, _revision = _runtime()

    handler_ids = set(editing._runtime.handlers.list_keys())
    assert "missing_handler" in handler_ids
    assert "missing_output_producer" in handler_ids
    assert isinstance(
        editing._runtime.handlers.get("missing_handler"),
        MissingHandlerRepairHandler,
    )
    assert isinstance(
        editing._runtime.handlers.get("missing_output_producer"),
        MissingOutputProducerHandler,
    )


def test_rd0_manifest_records_no_drafting_provider_path_at_baseline() -> None:
    manifest = Path("artifacts/reviews/repair_drafting/RD0/manifest.json").read_text(
        encoding="utf-8"
    )
    assert '"drafting_subsystem_introduced": false' in manifest
