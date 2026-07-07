from __future__ import annotations

import copy
from dataclasses import dataclass, replace
from pathlib import Path

import pytest

from nl2spl.compiler.spl_editing.demo import _build_default_service
from nl2spl.compiler.spl_editing.drafting.admission.errors import DraftAdmissionError
from nl2spl.compiler.spl_editing.drafting.model import UserRepairFieldValue, UserRepairInput
from nl2spl.compiler.spl_editing.drafting.providers.worker_delegation import (
    WorkerDelegationInferenceProvider,
)
from nl2spl.compiler.spl_editing.drafting.values import (
    BusinessLogicValue,
    ExplicitNoneValue,
    NewOutputDraftValue,
    ResponsibilityValue,
    SelectedInputRefsValue,
)
from nl2spl.compiler.spl_editing.interaction.model import SubmitRepairDirectiveDraftRequest
from nl2spl.compiler.spl_editing.patches.define_child_worker_closure.verifier import (
    DefineChildWorkerClosureVerifier,
)
from nl2spl.compiler.spl_editing.presentation.service import SPLEditingPresentationService
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef, SelectableRefSet
from tests.spl_editing_stub_llm import StubSuggestionLLM

SNAPSHOT = Path("examples/output/demo/spl_editing_snapshot.json")


@dataclass(frozen=True)
class _ProviderIssue:
    issue_id: str = "issue_1"


@dataclass(frozen=True)
class _ProviderTarget:
    target_ref: str = "worker_promotion:cand_source_gathering"
    worker_id: str = "worker_main"
    canonical_name: str = "cand_source_gathering"


@dataclass(frozen=True)
class _ProviderEntry:
    affordance_id: str = "worker_promotion.resolve_contract"


@dataclass(frozen=True)
class _ProviderOption:
    strategy_id: str = "worker_delegation.complete_closure.v2"
    option_id: str = "define_child_worker"


@dataclass(frozen=True)
class _ProviderContext:
    metadata: dict


def _runtime():
    editing = _build_default_service(suggestion_llm=StubSuggestionLLM())
    run_id = editing.register_snapshot_file(SNAPSHOT)
    editing._snapshot_repository = None
    presentation = SPLEditingPresentationService(editing)
    issue = next(
        item
        for item in editing.list_issue_inventory(run_id).editable
        if item.irs_ref.construct_type == "WORKER_PROMOTION"
    )
    snapshot = editing._get_snapshot(run_id)
    revision = f"{snapshot.compile_run_id}:{snapshot.snapshot_id}:{snapshot.overlay_version}"
    return editing, presentation, run_id, issue, snapshot, revision


def _worker_context(presentation, run_id, issue):
    return presentation._worker_delegation_context(
        run_id,
        issue.issue_id,
        "define_child_worker",
    )


def _valid_input_ref(presentation, run_id, issue) -> str:
    _issue, _snapshot, _entry, _option, _target, _context, _subject, refset = (
        _worker_context(presentation, run_id, issue)
    )
    return next(
        ref.ref_id
        for ref in refset.refs
        if ref.ref_role == "selectable_input"
        and ref.ref_kind == "worker_input"
        and ref.canonical_name == "user_request"
    )


def _submit_bad_directive(presentation, run_id, issue, revision, *, selected, values):
    request = SubmitRepairDirectiveDraftRequest(
        run_id,
        issue.issue_id,
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        "worker_delegation.define_child_worker.v1",
        "1",
        revision,
        values,
        selected,
        (
            {
                "local_id": "evidence",
                "display_name": "delegated evidence",
                "semantic_description": "Evidence returned by the child worker",
                "data_type_hint": "text",
            },
        ),
    )
    return presentation.submit_repair_directive_draft(request)


def _valid_values() -> dict[str, object]:
    return {
        "delegated_responsibility": "Gather source evidence",
        "invocation_timing": "append",
        "result_usage": (
            {
                "output_local_id": "evidence",
                "create_parent_local_temporary": "yes",
            },
        ),
    }


def _draft_first_accept(presentation, run_id, issue, revision):
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
    accepted = presentation.accept_repair_draft(
        run_id=run_id,
        issue_id=issue.issue_id,
        option_id="define_child_worker",
        session_id=creation.session_id,
        draft_id=creation.draft_id,
        revision_token=revision,
        user_input=_accepted_defaults(creation.draft, creation.draft_id),
    )
    return creation, accepted


def _accepted_defaults(draft, draft_id: str) -> UserRepairInput:
    fields = {field.field_id: field.value for field in draft.fields}
    task = fields["child_task"]
    inputs = fields["child_inputs"]
    output = fields["child_output"]
    logic = fields["child_business_logic"]
    assert isinstance(task, ResponsibilityValue)
    assert isinstance(output, NewOutputDraftValue)
    assert isinstance(logic, BusinessLogicValue)
    input_refs = ()
    if isinstance(inputs, SelectedInputRefsValue):
        input_refs = inputs.ref_ids
    else:
        assert isinstance(inputs, ExplicitNoneValue)
    return UserRepairInput(
        input_mode="structured_form",
        field_values=(
            UserRepairFieldValue("child_task", task.text, "accepted_default"),
            UserRepairFieldValue("child_inputs", input_refs, "accepted_default"),
            UserRepairFieldValue("child_output", output.display_name, "accepted_default"),
            UserRepairFieldValue("child_business_logic", logic.text, "accepted_default"),
        ),
        accepted_draft_id=draft_id,
        draft_accepted=True,
    )


def test_admission_negative_cases_reject_before_overlay() -> None:
    editing, presentation, run_id, issue, before, revision = _runtime()
    valid_ref = _valid_input_ref(presentation, run_id, issue)
    cases = {
        "unknown_ref": (
            {"input_refs": ("unknown-ref",)},
            _valid_values(),
        ),
        "raw_variable_name": (
            {"input_refs": ("user_request",)},
            _valid_values(),
        ),
        "free_text_placement_id": (
            {"input_refs": (valid_ref,), "placement_ref": ("step_1",)},
            {**_valid_values(), "invocation_timing": "before"},
        ),
    }

    for _name, (selected, values) in cases.items():
        result = _submit_bad_directive(
            presentation,
            run_id,
            issue,
            revision,
            selected=selected,
            values=values,
        )
        after = editing._get_snapshot(run_id)
        assert result.normalized_directive_id is None
        assert result.input_readiness != "input_complete"
        assert after.overlay_version == before.overlay_version
        assert issue.primary_diagnostic_id in {
            item.primary_diagnostic_id
            for item in editing.list_issue_inventory(run_id).editable
        }


def test_stale_draft_and_missing_materialized_preview_acceptance_are_rejected() -> None:
    editing, presentation, run_id, issue, before, revision = _runtime()
    stale = revision.rsplit(":", 1)[0] + ":99"

    stale_creation = presentation.create_repair_draft(
        run_id=run_id,
        issue_id=issue.issue_id,
        option_id="define_child_worker",
        revision_token=stale,
        user_input=UserRepairInput(input_mode="free_text", free_text="Gather evidence"),
    )
    assert stale_creation.status == "stale_revision"
    assert editing._get_snapshot(run_id).overlay_version == before.overlay_version

    _creation, accepted = _draft_first_accept(presentation, run_id, issue, revision)
    handle = presentation.create_materialized_preview_from_draft(
        accepted.normalized_directive_id
    )
    with pytest.raises(DraftAdmissionError, match="materialized_preview_accepted"):
        presentation.accept_materialized_preview(
            directive_id=accepted.normalized_directive_id,
            preview_id=handle.preview.preview_id,
            user_input=UserRepairInput(input_mode="none", draft_accepted=True),
        )
    assert editing._get_snapshot(run_id).overlay_version == before.overlay_version


def test_provider_policy_negative_cases_do_not_create_actionable_bindings() -> None:
    provider = WorkerDelegationInferenceProvider()
    refset = SelectableRefSet(
        "set_1",
        "issue_1",
        "snapshot_1",
        "worker_main",
        (
            SelectableRef(
                "ref:input:user_request",
                "worker_input",
                "selectable_input",
                "user_request",
                "user_request",
                worker_id="worker_main",
            ),
            SelectableRef(
                "ref:target:source_evidence",
                "required_output",
                "target_output",
                "source_evidence",
                "source_evidence",
                worker_id="worker_main",
            ),
        ),
        "worker_delegation",
    )
    context = provider.build_context(
        issue=_ProviderIssue(),
        target=_ProviderTarget(),
        catalog_entry=_ProviderEntry(),
        option=_ProviderOption(),
        snapshot=object(),
        repair_context=_ProviderContext(
            metadata={
                "candidate_task_candidates": (
                    "source gathering",
                    "template matching",
                ),
                "candidate_source_span_ids": ("api:s31", "s32"),
            }
        ),
        refset=refset,
        subject=None,
    )

    draft = provider.infer(context=context, user_input=UserRepairInput(input_mode="none"))

    responsibility = next(field for field in draft.fields if field.field_id == "child_task")
    binding = next(field for field in draft.fields if field.field_id == "result_binding")
    assert responsibility.value is None
    assert any(question.field_id == "child_task" for question in draft.clarification_questions)
    assert binding.value is None
    assert binding.confidence == "blocked"
    assert all(
        "api:s31" not in evidence
        for record in draft.trace
        for evidence in record.evidence_refs
    )


def test_closure_verifier_rejects_orphan_child_handoff_and_invoke() -> None:
    editing, presentation, run_id, issue, base, revision = _runtime()
    _creation, accepted = _draft_first_accept(presentation, run_id, issue, revision)
    handle = presentation.create_materialized_preview_from_draft(
        accepted.normalized_directive_id
    )
    session, verification = presentation.accept_materialized_preview(
        directive_id=accepted.normalized_directive_id,
        preview_id=handle.preview.preview_id,
        user_input=UserRepairInput(
            input_mode="none",
            draft_accepted=True,
            materialized_preview_accepted=True,
        ),
    )
    assert verification.accepted
    valid = editing._snapshots.get(
        run_id,
        base.snapshot_id,
        overlay_version=session.overlay_version,
    )
    patch = next(reversed(editing._applied_patches.values()))
    artifacts = editing._verifier._lane_b.replay(valid)
    marker = valid.promotion_resolution_markers[0]
    child_id = next(
        ref.removeprefix("worker:")
        for ref in marker.materialized_construct_refs
        if ref.startswith("worker:")
    )
    handoff = next(item for item in valid.worker_plan.handoffs if item.to_worker == child_id)

    orphan_child = replace(
        valid,
        worker_plan=replace(
            valid.worker_plan,
            workers=tuple(
                worker for worker in valid.worker_plan.workers if worker.worker_id != child_id
            ),
        ),
    )
    orphan_handoff = copy.deepcopy(valid)
    orphan_handoff.worker_step_plan.worker_steps[valid.worker_plan.main_worker_id] = [
        step
        for step in orphan_handoff.worker_step_plan.main_worker_steps
        if step.handoff_id != handoff.handoff_id
    ]
    orphan_invoke = copy.deepcopy(valid)
    orphan_invoke.worker_plan.handoffs = [
        item for item in orphan_invoke.worker_plan.handoffs if item.handoff_id != handoff.handoff_id
    ]

    verifier = DefineChildWorkerClosureVerifier()
    assert verifier.verify(patch, base, orphan_child, artifacts)
    assert verifier.verify(patch, base, orphan_handoff, artifacts)
    assert verifier.verify(patch, base, orphan_invoke, artifacts)


def test_accepted_case_lane_b_has_no_new_blocking_or_output_diagnostics() -> None:
    editing, presentation, run_id, issue, base, revision = _runtime()
    before_diagnostics = {
        diagnostic.diagnostic_id
        for diagnostic in base.compile_diagnostics
        if diagnostic.kind in {"missing_output_producer", "type_or_contract_ambiguity"}
    }
    _creation, accepted = _draft_first_accept(presentation, run_id, issue, revision)
    handle = presentation.create_materialized_preview_from_draft(
        accepted.normalized_directive_id
    )
    session, verification = presentation.accept_materialized_preview(
        directive_id=accepted.normalized_directive_id,
        preview_id=handle.preview.preview_id,
        user_input=UserRepairInput(
            input_mode="none",
            draft_accepted=True,
            materialized_preview_accepted=True,
        ),
    )
    patched = editing._snapshots.get(
        run_id,
        base.snapshot_id,
        overlay_version=session.overlay_version,
    )
    after_diagnostics = {
        diagnostic.diagnostic_id
        for diagnostic in patched.compile_diagnostics
        if diagnostic.kind in {"missing_output_producer", "type_or_contract_ambiguity"}
    }

    assert verification.accepted is True
    assert verification.lane == "B"
    assert issue.primary_diagnostic_id in verification.resolved_diagnostic_ids
    assert not verification.new_blocking_diagnostic_ids
    assert after_diagnostics <= before_diagnostics
