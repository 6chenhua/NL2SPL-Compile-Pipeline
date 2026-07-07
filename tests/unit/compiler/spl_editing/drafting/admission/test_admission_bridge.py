from __future__ import annotations

from dataclasses import dataclass

import pytest

from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.drafting.admission.bridge import (
    DraftAdmissionBridge,
    require_materialized_preview_acceptance,
)
from nl2spl.compiler.spl_editing.drafting.admission.errors import DraftAdmissionError
from nl2spl.compiler.spl_editing.drafting.model import (
    DraftPreview,
    FieldInference,
    InferredRepairDraft,
    UserRepairFieldValue,
    UserRepairInput,
)
from nl2spl.compiler.spl_editing.drafting.staleness import DraftIdentity
from nl2spl.compiler.spl_editing.drafting.store import RepairDraftStore
from nl2spl.compiler.spl_editing.drafting.values import (
    BusinessLogicValue,
    NewOutputDraftValue,
    PlacementIntentValue,
    ResponsibilityValue,
    ResultBindingValue,
    SelectedInputRefsValue,
)
from nl2spl.compiler.spl_editing.selectable_refs.model import SelectableRef, SelectableRefSet
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR

PROVIDER_ID = "worker_delegation.define_child_worker.drafting.v1"


@dataclass(frozen=True)
class _Option:
    strategy_id: str = "worker_delegation.complete_closure.v2"
    option_id: str = "define_child_worker"


@dataclass(frozen=True)
class _Target:
    target_ref: str = "worker_promotion:cand_1"


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
                scope="worker",
                type_hint="text",
            ),
            SelectableRef(
                "ref:placement:step_1",
                "existing_step",
                "placement_anchor",
                "step_1",
                "Collect request",
                scope="worker",
            ),
        ),
        "worker_delegation",
    )


def _stored(*, input_ref: str = "ref:input:user_request", provider_id: str = PROVIDER_ID):
    draft = InferredRepairDraft(
        "draft_1",
        "issue_1",
        "worker_promotion.resolve_contract",
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        (
            FieldInference(
                "child_task",
                ResponsibilityValue(provider_id, "Gather source evidence"),
                "high",
            ),
            FieldInference(
                "child_inputs",
                SelectedInputRefsValue(provider_id, (input_ref,)),
                "high",
            ),
            FieldInference(
                "child_output",
                NewOutputDraftValue(
                    provider_id,
                    "evidence",
                    "delegated evidence",
                    "Evidence returned by child worker",
                    "text",
                ),
                "medium",
            ),
            FieldInference(
                "child_business_logic",
                BusinessLogicValue(
                    provider_id,
                    "Gather source evidence using user_request; return delegated evidence.",
                ),
                "medium",
            ),
            FieldInference("placement", PlacementIntentValue(provider_id, "append"), "medium"),
            FieldInference(
                "result_binding",
                ResultBindingValue(
                    provider_id,
                    "evidence",
                    create_parent_local_temporary=True,
                ),
                "medium",
            ),
        ),
        (),
        (),
        DraftPreview("Create child worker", "Gather evidence."),
    )
    return RepairDraftStore().put(
        draft,
        session_id="session_1",
        artifact_snapshot_id="snapshot_1",
        overlay_version=0,
        created_at="2026-07-04T00:00:00Z",
    )


def _admit(stored=None, user_input=None):
    stored = stored or _stored()
    return DraftAdmissionBridge().admit_worker_delegation(
        stored=stored,
        user_input=user_input or _accepted_defaults(stored),
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
        provider_id=PROVIDER_ID,
        contract_id="worker_delegation.define_child_worker.v1",
        contract_version="1",
        revision_token="run_1:snapshot_1:0",
    )


def _accepted_defaults(stored) -> UserRepairInput:
    input_ref = next(
        field.value.ref_ids[0]
        for field in stored.draft.fields
        if isinstance(field.value, SelectedInputRefsValue)
    )
    return UserRepairInput(
        input_mode="structured_form",
        field_values=(
            UserRepairFieldValue("child_task", "Gather source evidence", "accepted_default"),
            UserRepairFieldValue(
                "child_inputs",
                (input_ref,),
                "accepted_default",
            ),
            UserRepairFieldValue("child_output", "delegated evidence", "accepted_default"),
            UserRepairFieldValue(
                "child_business_logic",
                "Gather source evidence using user_request; return delegated evidence.",
                "accepted_default",
            ),
        ),
        draft_accepted=True,
    )


def test_valid_typed_draft_enters_existing_directive() -> None:
    result = _admit()
    assert result.input_readiness == "input_complete"
    assert result.directive_id is not None
    assert result.directive.delegated_responsibility == "Gather source evidence"


def test_draft_accepted_false_cannot_enter_materialized_preview() -> None:
    result = _admit(user_input=UserRepairInput(input_mode="none", draft_accepted=False))
    assert result.input_readiness == "input_invalid"
    assert "draft_accepted" in result.errors[0].message


def test_field_confirmations_are_required_before_admission() -> None:
    result = _admit(user_input=UserRepairInput(input_mode="none", draft_accepted=True))
    assert result.input_readiness == "input_invalid"
    assert "confirmed semantic fields required" in result.errors[0].message


def test_unrelated_provider_value_rejected() -> None:
    result = _admit(stored=_stored(provider_id="other.provider"))
    assert result.input_readiness == "input_invalid"
    assert "other.provider" in result.errors[0].message


def test_unknown_selected_ref_rejected_before_materialization() -> None:
    result = _admit(stored=_stored(input_ref="unknown_ref"))
    assert result.input_readiness == "input_invalid"
    assert any(error.code == "invalid_ref_id" for error in result.errors)


def test_free_text_cannot_fill_required_structured_fields() -> None:
    draft = InferredRepairDraft(
        "draft_1",
        "issue_1",
        "worker_promotion.resolve_contract",
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        (),
        (),
        (),
        DraftPreview("Create child worker", "Gather evidence."),
    )
    stored = RepairDraftStore().put(
        draft,
        session_id="session_1",
        artifact_snapshot_id="snapshot_1",
        overlay_version=0,
    )
    result = _admit(
        stored=stored,
        user_input=UserRepairInput(
            input_mode="free_text",
            free_text="Gather evidence",
            draft_accepted=True,
        ),
    )
    assert result.input_readiness == "input_invalid"


def test_materialized_preview_acceptance_gate_blocks_apply() -> None:
    with pytest.raises(DraftAdmissionError, match="materialized_preview_accepted"):
        require_materialized_preview_acceptance(
            UserRepairInput(input_mode="none", materialized_preview_accepted=False)
        )
