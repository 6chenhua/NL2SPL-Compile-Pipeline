"""Staleness checks for ephemeral repair drafts."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.constants import DRAFT_SCHEMA_VERSION
from nl2spl.compiler.spl_editing.drafting.errors import RepairDraftingError
from nl2spl.compiler.spl_editing.drafting.model import StoredRepairDraft


@dataclass(frozen=True)
class DraftIdentity:
    session_id: str
    artifact_snapshot_id: str
    overlay_version: int
    issue_id: str
    option_id: str
    schema_version: str = DRAFT_SCHEMA_VERSION


@dataclass(frozen=True)
class DraftStalenessResult:
    stale: bool
    reasons: tuple[str, ...] = ()

    def require_fresh(self) -> None:
        if self.stale:
            raise StaleRepairDraftError("; ".join(self.reasons))


class StaleRepairDraftError(RepairDraftingError):
    """Raised when an old draft attempts to enter Admission."""


def check_staleness(
    draft: StoredRepairDraft,
    *,
    current: DraftIdentity,
) -> DraftStalenessResult:
    reasons: list[str] = []
    if draft.session_id != current.session_id:
        reasons.append("session_id mismatch")
    if draft.artifact_snapshot_id != current.artifact_snapshot_id:
        reasons.append("artifact_snapshot_id mismatch")
    if draft.overlay_version != current.overlay_version:
        reasons.append("overlay_version mismatch")
    if draft.issue_id != current.issue_id:
        reasons.append("issue_id mismatch")
    if draft.option_id != current.option_id:
        reasons.append("option_id mismatch")
    if draft.schema_version != current.schema_version:
        reasons.append("draft schema version mismatch")
    return DraftStalenessResult(stale=bool(reasons), reasons=tuple(reasons))


def require_fresh_draft(draft: StoredRepairDraft, *, current: DraftIdentity) -> None:
    check_staleness(draft, current=current).require_fresh()

