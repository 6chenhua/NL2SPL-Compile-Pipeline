from __future__ import annotations

from dataclasses import FrozenInstanceError, fields

import pytest

from nl2spl.compiler.spl_editing.drafting.model import (
    DraftPreview,
    FieldInference,
    InferenceTraceRecord,
    InferredRepairDraft,
    StoredRepairDraft,
    UserRepairInput,
)
from nl2spl.compiler.spl_editing.drafting.values import (
    ResponsibilityValue,
    assert_provider_scope,
)

PROVIDER_ID = "worker_delegation.define_child_worker.drafting.v1"


def _draft() -> InferredRepairDraft:
    return InferredRepairDraft(
        draft_id="draft_1",
        issue_id="issue_1",
        affordance_id="worker_promotion.resolve_contract",
        strategy_id="worker_delegation.complete_closure.v2",
        option_id="define_child_worker",
        fields=(
            FieldInference(
                field_id="responsibility",
                value=ResponsibilityValue(PROVIDER_ID, "Gather source evidence"),
                confidence="high",
                evidence_refs=("issue:issue_1",),
            ),
        ),
        clarification_questions=(),
        trace=(
            InferenceTraceRecord(
                field_id="responsibility",
                source="subject.summary",
                evidence_refs=("issue:issue_1",),
                decision="defaulted from worker promotion subject",
                confidence="high",
            ),
        ),
        draft_preview=DraftPreview(
            title="Create child worker",
            summary="Gather source evidence.",
            field_summaries=("Responsibility: Gather source evidence",),
        ),
    )


def test_dto_values_are_frozen_and_compare_by_value() -> None:
    draft = _draft()
    assert draft == _draft()
    with pytest.raises(FrozenInstanceError):
        draft.draft_id = "other"  # type: ignore[misc]


def test_user_input_has_two_explicit_acceptance_gates() -> None:
    names = {field.name for field in fields(UserRepairInput)}
    assert "draft_accepted" in names
    assert "materialized_preview_accepted" in names
    assert "confirmed" not in names
    assert "patch_payload" not in names
    assert "raw_ir" not in names
    assert "materialization_plan" not in names


def test_field_inference_rejects_raw_mapping_value() -> None:
    with pytest.raises(TypeError, match="typed RepairFieldValue"):
        FieldInference(
            field_id="responsibility",
            value={"text": "raw"},  # type: ignore[arg-type]
            confidence="high",
        )


def test_provider_scope_rejects_unrelated_provider_value() -> None:
    value = ResponsibilityValue("other.provider", "Gather source evidence")
    with pytest.raises(ValueError, match="other.provider"):
        assert_provider_scope(value, PROVIDER_ID)


def test_stored_draft_contains_no_overlay_or_evidence_authority_fields() -> None:
    names = {field.name for field in fields(StoredRepairDraft)}
    forbidden = {
        "overlay_event",
        "patched_snapshot",
        "repair_evidence",
        "evidence_packet",
        "patch_payload",
    }
    assert names.isdisjoint(forbidden)
    stored = StoredRepairDraft(
        draft_id="draft_1",
        session_id="session_1",
        artifact_snapshot_id="snapshot_1",
        overlay_version=0,
        issue_id="issue_1",
        option_id="define_child_worker",
        draft=_draft(),
        created_at="2026-07-04T00:00:00Z",
    )
    assert stored.draft == _draft()

