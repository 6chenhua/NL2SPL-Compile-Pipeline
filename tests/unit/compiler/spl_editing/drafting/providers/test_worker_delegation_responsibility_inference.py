from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.drafting.admission.bridge import DraftAdmissionBridge
from nl2spl.compiler.spl_editing.drafting.model import UserRepairInput
from nl2spl.compiler.spl_editing.drafting.providers.worker_delegation import (
    WorkerDelegationInferenceProvider,
)
from nl2spl.compiler.spl_editing.drafting.staleness import DraftIdentity
from nl2spl.compiler.spl_editing.drafting.store import RepairDraftStore
from nl2spl.compiler.spl_editing.drafting.values import ResponsibilityValue
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef, SelectableRefSet
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR


@dataclass(frozen=True)
class _Issue:
    issue_id: str = "issue_1"


@dataclass(frozen=True)
class _Target:
    target_ref: str = "worker_promotion:cand_source_gathering"
    worker_id: str = "worker_main"
    canonical_name: str = "cand_source_gathering"


@dataclass(frozen=True)
class _Entry:
    affordance_id: str = "worker_promotion.resolve_contract"


@dataclass(frozen=True)
class _Option:
    strategy_id: str = "worker_delegation.complete_closure.v2"
    option_id: str = "define_child_worker"


@dataclass(frozen=True)
class _Context:
    metadata: dict


@dataclass(frozen=True)
class _Subject:
    summary: str | None


def _refset() -> SelectableRefSet:
    return SelectableRefSet(
        "set_1",
        "issue_1",
        "snapshot_1",
        "worker_main",
        (
            SelectableRef(
                "ref:input:user_request",
                "variable",
                "selectable_input",
                "user_request",
                "user_request",
                type_hint="text",
            ),
            SelectableRef(
                "ref:binding:source_evidence",
                "variable",
                "binding_target",
                "source_evidence",
                "source_evidence",
                type_hint="text",
            ),
        ),
        "worker_delegation",
    )


def _draft(
    *,
    metadata: dict,
    user_input: UserRepairInput | None = None,
    subject_summary: str | None = None,
):
    provider = WorkerDelegationInferenceProvider()
    context = provider.build_context(
        issue=_Issue(),
        target=_Target(),
        catalog_entry=_Entry(),
        option=_Option(),
        snapshot=object(),
        repair_context=_Context(metadata=metadata),
        refset=_refset(),
        subject=_Subject(subject_summary) if subject_summary is not None else None,
    )
    return provider.infer(
        context=context,
        user_input=user_input or UserRepairInput(input_mode="none"),
    )


def _responsibility_field_and_trace(draft):
    field = next(field for field in draft.fields if field.field_id == "responsibility")
    trace = next(
        record for record in draft.trace if record.field_id == "responsibility"
    )
    return field, trace


def test_free_text_responsibility_uses_user_intent_evidence() -> None:
    draft = _draft(
        metadata={
            "candidate_task_summary": "Gather source evidence",
            "candidate_source_span_ids": ("s31",),
        },
        user_input=UserRepairInput(
            input_mode="free_text",
            free_text="Gather approved source evidence",
        ),
    )

    field, trace = _responsibility_field_and_trace(draft)

    assert isinstance(field.value, ResponsibilityValue)
    assert field.value.text == "Gather approved source evidence"
    assert field.evidence_refs == ("user_input:free_text",)
    assert trace.source == "user_input.free_text"
    assert trace.evidence_refs == ("user_input:free_text",)


def test_source_backed_single_candidate_uses_source_span_evidence() -> None:
    draft = _draft(
        metadata={
            "candidate_task_summary": "Gather approved source evidence",
            "candidate_source_span_ids": ("s31", "api:s32"),
        },
    )

    field, trace = _responsibility_field_and_trace(draft)

    assert isinstance(field.value, ResponsibilityValue)
    assert field.value.text == "Gather approved source evidence"
    assert field.evidence_refs == ("s31",)
    assert trace.evidence_refs == ("s31",)
    assert "api:s32" not in field.evidence_refs


def test_multi_candidate_responsibility_requires_clarification() -> None:
    draft = _draft(
        metadata={
            "candidate_task_candidates": (
                "Gather source evidence",
                "Template matching",
            ),
            "candidate_source_span_ids": ("s31",),
        },
    )

    field = next(field for field in draft.fields if field.field_id == "responsibility")

    assert field.value is None
    assert field.confidence == "blocked"
    assert draft.clarification_questions
    assert tuple(option.value for option in draft.clarification_questions[0].options) == (
        "Gather source evidence",
        "Template matching",
    )


def test_ambiguous_source_gathering_or_template_matching_does_not_default_both() -> None:
    draft = _draft(
        metadata={
            "candidate_task_summary": "source gathering or template matching",
            "candidate_source_span_ids": ("s31",),
        },
    )

    field = next(field for field in draft.fields if field.field_id == "responsibility")

    assert field.value is None
    assert field.confidence == "blocked"
    assert draft.clarification_questions
    assert tuple(option.value for option in draft.clarification_questions[0].options) == (
        "source gathering",
        "template matching",
    )


def test_subject_summary_fallback_drives_responsibility_clarification_options() -> None:
    draft = _draft(
        metadata={"candidate_source_span_ids": ("s31",)},
        subject_summary=(
            "Optional delegated subtasks such as source gathering or template matching "
            "may be used if bounded"
        ),
    )

    field = next(field for field in draft.fields if field.field_id == "responsibility")

    assert field.value is None
    assert field.confidence == "blocked"
    assert tuple(option.value for option in draft.clarification_questions[0].options) == (
        "source gathering",
        "template matching",
    )


def test_blocked_responsibility_cannot_enter_admission_directive() -> None:
    draft = _draft(metadata={"candidate_source_span_ids": ()})
    stored = RepairDraftStore().put(
        draft,
        session_id="session_1",
        artifact_snapshot_id="snapshot_1",
        overlay_version=0,
        created_at="2026-07-04T00:00:00Z",
    )

    result = DraftAdmissionBridge().admit_worker_delegation(
        stored=stored,
        user_input=UserRepairInput(input_mode="none", draft_accepted=True),
        current=DraftIdentity(
            "session_1",
            "snapshot_1",
            0,
            "issue_1",
            "define_child_worker",
        ),
        option=_Option(),
        target=_Target(),
        snapshot=ArtifactSnapshot(
            "snapshot_1",
            "run_1",
            0,
            worker_step_plan=WorkerStepPlanIR("worker_main", {"worker_main": []}),
        ),
        refset=_refset(),
        provider_id=WorkerDelegationInferenceProvider.provider_id,
        contract_id="worker_delegation.define_child_worker.v1",
        contract_version="1",
        revision_token="run_1:snapshot_1:0",
    )

    assert result.input_readiness in {"input_required", "input_invalid"}
    assert result.directive_id is None
    assert any("confirmed semantic fields required" in error.message for error in result.errors)
