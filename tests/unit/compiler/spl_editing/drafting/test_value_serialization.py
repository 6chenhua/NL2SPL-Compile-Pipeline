from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.drafting.model import (
    DraftPreview,
    FieldInference,
    InferenceTraceRecord,
    InferredRepairDraft,
    StoredRepairDraft,
    UserRepairFieldValue,
    UserRepairInput,
)
from nl2spl.compiler.spl_editing.drafting.serialization import (
    inferred_draft_from_json_text,
    stored_draft_from_json_text,
    to_json_text,
    user_input_from_json_text,
)
from nl2spl.compiler.spl_editing.drafting.values import (
    NewOutputDraftValue,
    PlacementIntentValue,
    ResponsibilityValue,
    ResultBindingValue,
    SelectedInputRefsValue,
)

PROVIDER_ID = "worker_delegation.define_child_worker.drafting.v1"


def _draft() -> InferredRepairDraft:
    fields = (
        FieldInference(
            "responsibility",
            ResponsibilityValue(PROVIDER_ID, "Gather source evidence"),
            "high",
            ("subject:worker_promotion",),
        ),
        FieldInference(
            "input_refs",
            SelectedInputRefsValue(PROVIDER_ID, ("ref:user_request",)),
            "high",
            ("refset:selectable",),
        ),
        FieldInference(
            "output",
            NewOutputDraftValue(
                PROVIDER_ID,
                "evidence",
                "delegated evidence",
                "Evidence returned by the child worker",
                "text",
            ),
            "medium",
            ("subject:worker_promotion",),
        ),
        FieldInference(
            "placement",
            PlacementIntentValue(PROVIDER_ID, "append"),
            "medium",
            ("placement:default",),
        ),
        FieldInference(
            "result_binding",
            ResultBindingValue(
                PROVIDER_ID,
                "evidence",
                create_parent_local_temporary=True,
            ),
            "medium",
            ("producer:required_output",),
        ),
    )
    return InferredRepairDraft(
        "draft_1",
        "issue_1",
        "worker_promotion.resolve_contract",
        "worker_delegation.complete_closure.v2",
        "define_child_worker",
        fields,
        (),
        (
            InferenceTraceRecord(
                "responsibility",
                "subject.summary",
                ("subject:worker_promotion",),
                "defaulted from promotion subject",
                "high",
            ),
        ),
        DraftPreview(
            "Create child worker",
            "Gather source evidence.",
            ("Use input ref:user_request",),
        ),
    )


def test_user_input_round_trips_as_stable_json() -> None:
    value = UserRepairInput(
        input_mode="mixed",
        free_text="Gather the approved evidence",
        field_values=(UserRepairFieldValue("responsibility", "Gather evidence"),),
        selected_option_id="define_child_worker",
        draft_accepted=True,
    )
    text = to_json_text(value)
    assert user_input_from_json_text(text) == value
    assert to_json_text(user_input_from_json_text(text)) == text


def test_inferred_draft_round_trips_with_typed_values() -> None:
    draft = _draft()
    text = to_json_text(draft)
    assert inferred_draft_from_json_text(text) == draft
    assert to_json_text(inferred_draft_from_json_text(text)) == text


def test_stored_draft_round_trips_without_persistent_authority() -> None:
    stored = StoredRepairDraft(
        "draft_1",
        "session_1",
        "snapshot_1",
        0,
        "issue_1",
        "define_child_worker",
        _draft(),
        "2026-07-04T00:00:00Z",
    )
    text = to_json_text(stored)
    assert "overlay_event" not in text
    assert "repair_evidence" not in text
    assert stored_draft_from_json_text(text) == stored


def test_raw_object_value_cannot_round_trip_as_repair_field_value() -> None:
    with pytest.raises(TypeError, match="typed RepairFieldValue"):
        FieldInference(
            "bad",
            object(),  # type: ignore[arg-type]
            "high",
        )
