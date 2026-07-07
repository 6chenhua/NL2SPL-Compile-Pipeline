"""Session-scoped ephemeral storage for inferred repair drafts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime

from nl2spl.compiler.spl_editing.drafting.errors import RepairDraftingError
from nl2spl.compiler.spl_editing.drafting.model import (
    InferredRepairDraft,
    StoredRepairDraft,
)
from nl2spl.compiler.spl_editing.drafting.staleness import (
    DraftIdentity,
    check_staleness,
)


@dataclass(frozen=True)
class DraftStoreKey:
    session_id: str
    artifact_snapshot_id: str
    overlay_version: int
    draft_id: str

    @classmethod
    def from_stored(cls, draft: StoredRepairDraft) -> DraftStoreKey:
        return cls(
            session_id=draft.session_id,
            artifact_snapshot_id=draft.artifact_snapshot_id,
            overlay_version=draft.overlay_version,
            draft_id=draft.draft_id,
        )


class DraftCollisionError(RepairDraftingError):
    """Raised when a draft key would overwrite another draft."""


class DraftNotFoundError(RepairDraftingError):
    """Raised when a draft cannot be found."""


class RepairDraftStore:
    """In-memory draft store scoped to the current application process."""

    def __init__(self) -> None:
        self._drafts: dict[DraftStoreKey, StoredRepairDraft] = {}

    def put(
        self,
        draft: InferredRepairDraft,
        *,
        session_id: str,
        artifact_snapshot_id: str,
        overlay_version: int,
        created_at: str | None = None,
    ) -> StoredRepairDraft:
        stored = StoredRepairDraft(
            draft_id=draft.draft_id,
            session_id=session_id,
            artifact_snapshot_id=artifact_snapshot_id,
            overlay_version=overlay_version,
            issue_id=draft.issue_id,
            option_id=draft.option_id,
            draft=draft,
            created_at=created_at or datetime.now(UTC).isoformat(),
        )
        key = DraftStoreKey.from_stored(stored)
        if key in self._drafts:
            raise DraftCollisionError(f"Draft already exists for key {key}")
        self._drafts[key] = stored
        return stored

    def get(
        self,
        *,
        session_id: str,
        artifact_snapshot_id: str,
        overlay_version: int,
        draft_id: str,
    ) -> StoredRepairDraft:
        key = DraftStoreKey(session_id, artifact_snapshot_id, overlay_version, draft_id)
        try:
            return self._drafts[key]
        except KeyError as exc:
            raise DraftNotFoundError(f"Draft not found: {draft_id}") from exc

    def get_for_admission(
        self,
        *,
        draft_id: str,
        current: DraftIdentity,
    ) -> StoredRepairDraft:
        draft = self.get(
            session_id=current.session_id,
            artifact_snapshot_id=current.artifact_snapshot_id,
            overlay_version=current.overlay_version,
            draft_id=draft_id,
        )
        check_staleness(draft, current=current).require_fresh()
        return draft

    def clear_session(self, session_id: str) -> int:
        keys = [key for key in self._drafts if key.session_id == session_id]
        for key in keys:
            del self._drafts[key]
        return len(keys)

    def expire_before_overlay(self, *, session_id: str, overlay_version: int) -> int:
        keys = [
            key
            for key in self._drafts
            if key.session_id == session_id and key.overlay_version < overlay_version
        ]
        for key in keys:
            del self._drafts[key]
        return len(keys)

    def list_drafts(self) -> tuple[StoredRepairDraft, ...]:
        return tuple(self._drafts[key] for key in sorted(self._drafts, key=str))

    @staticmethod
    def with_overlay_version(draft: StoredRepairDraft, overlay_version: int) -> StoredRepairDraft:
        """Test helper for stale matrix construction without mutating the store."""

        return replace(draft, overlay_version=overlay_version)

