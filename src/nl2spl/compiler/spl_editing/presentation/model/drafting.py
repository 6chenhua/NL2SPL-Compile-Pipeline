"""Presentation DTOs for repair drafting interactions."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.drafting.model import DraftPreview, InferredRepairDraft


@dataclass(frozen=True)
class RepairDraftingCapabilityView:
    issue_id: str
    option_id: str
    revision_token: str
    status: str
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepairDraftCreationView:
    issue_id: str
    option_id: str
    revision_token: str
    status: str
    session_id: str | None = None
    draft_id: str | None = None
    draft: InferredRepairDraft | None = None
    draft_preview: DraftPreview | None = None
    reasons: tuple[str, ...] = ()

