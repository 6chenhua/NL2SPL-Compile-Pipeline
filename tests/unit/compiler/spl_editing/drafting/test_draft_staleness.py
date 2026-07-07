from __future__ import annotations

from dataclasses import replace

import pytest

from nl2spl.compiler.spl_editing.drafting.model import DraftPreview, InferredRepairDraft
from nl2spl.compiler.spl_editing.drafting.staleness import (
    DraftIdentity,
    StaleRepairDraftError,
    check_staleness,
)
from nl2spl.compiler.spl_editing.drafting.store import RepairDraftStore


def _stored():
    store = RepairDraftStore()
    return store.put(
        InferredRepairDraft(
            draft_id="draft_1",
            issue_id="issue_1",
            affordance_id="worker_promotion.resolve_contract",
            strategy_id="worker_delegation.complete_closure.v2",
            option_id="define_child_worker",
            fields=(),
            clarification_questions=(),
            trace=(),
            draft_preview=DraftPreview("Create child worker", "Gather evidence."),
        ),
        session_id="session_1",
        artifact_snapshot_id="snapshot_1",
        overlay_version=0,
        created_at="2026-07-04T00:00:00Z",
    )


def _identity(**kwargs) -> DraftIdentity:
    data = {
        "session_id": "session_1",
        "artifact_snapshot_id": "snapshot_1",
        "overlay_version": 0,
        "issue_id": "issue_1",
        "option_id": "define_child_worker",
        "schema_version": "repair_drafting.v1",
    }
    data.update(kwargs)
    return DraftIdentity(**data)


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    (
        ("session_id", "other_session", "session_id mismatch"),
        ("artifact_snapshot_id", "other_snapshot", "artifact_snapshot_id mismatch"),
        ("overlay_version", 1, "overlay_version mismatch"),
        ("issue_id", "other_issue", "issue_id mismatch"),
        ("option_id", "keep_in_main_flow", "option_id mismatch"),
        ("schema_version", "other_schema", "draft schema version mismatch"),
    ),
)
def test_stale_negative_matrix(field_name: str, value, reason: str) -> None:
    result = check_staleness(_stored(), current=_identity(**{field_name: value}))
    assert result.stale is True
    assert reason in result.reasons


def test_matching_identity_is_fresh() -> None:
    result = check_staleness(_stored(), current=_identity())
    assert result.stale is False
    assert result.reasons == ()


def test_stale_draft_cannot_enter_admission_lookup() -> None:
    store = RepairDraftStore()
    draft = _stored()
    store.put(
        draft.draft,
        session_id=draft.session_id,
        artifact_snapshot_id=draft.artifact_snapshot_id,
        overlay_version=draft.overlay_version,
        created_at=draft.created_at,
    )

    with pytest.raises(StaleRepairDraftError, match="issue_id mismatch"):
        stale = replace(draft, issue_id="other_issue")
        check_staleness(stale, current=_identity()).require_fresh()

