from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.drafting.model import (
    DraftPreview,
    InferredRepairDraft,
)
from nl2spl.compiler.spl_editing.drafting.store import (
    DraftCollisionError,
    DraftNotFoundError,
    RepairDraftStore,
)


def _draft(draft_id: str = "draft_1") -> InferredRepairDraft:
    return InferredRepairDraft(
        draft_id=draft_id,
        issue_id="issue_1",
        affordance_id="worker_promotion.resolve_contract",
        strategy_id="worker_delegation.complete_closure.v2",
        option_id="define_child_worker",
        fields=(),
        clarification_questions=(),
        trace=(),
        draft_preview=DraftPreview("Create child worker", "Gather evidence."),
    )


def test_same_session_snapshot_overlay_can_read_draft() -> None:
    store = RepairDraftStore()
    stored = store.put(
        _draft(),
        session_id="session_1",
        artifact_snapshot_id="snapshot_1",
        overlay_version=0,
        created_at="2026-07-04T00:00:00Z",
    )

    assert store.get(
        session_id="session_1",
        artifact_snapshot_id="snapshot_1",
        overlay_version=0,
        draft_id="draft_1",
    ) == stored


def test_draft_id_collision_fails_fast() -> None:
    store = RepairDraftStore()
    store.put(
        _draft(),
        session_id="session_1",
        artifact_snapshot_id="snapshot_1",
        overlay_version=0,
    )
    with pytest.raises(DraftCollisionError):
        store.put(
            _draft(),
            session_id="session_1",
            artifact_snapshot_id="snapshot_1",
            overlay_version=0,
        )


def test_different_overlay_is_not_same_store_key() -> None:
    store = RepairDraftStore()
    store.put(
        _draft(),
        session_id="session_1",
        artifact_snapshot_id="snapshot_1",
        overlay_version=0,
    )

    with pytest.raises(DraftNotFoundError):
        store.get(
            session_id="session_1",
            artifact_snapshot_id="snapshot_1",
            overlay_version=1,
            draft_id="draft_1",
        )


def test_clear_and_expire_do_not_create_artifact_side_effects() -> None:
    store = RepairDraftStore()
    store.put(
        _draft("draft_1"),
        session_id="session_1",
        artifact_snapshot_id="snap",
        overlay_version=0,
    )
    store.put(
        _draft("draft_2"),
        session_id="session_1",
        artifact_snapshot_id="snap",
        overlay_version=1,
    )
    assert store.expire_before_overlay(session_id="session_1", overlay_version=1) == 1
    assert [draft.draft_id for draft in store.list_drafts()] == ["draft_2"]
    assert store.clear_session("session_1") == 1
    assert store.list_drafts() == ()
