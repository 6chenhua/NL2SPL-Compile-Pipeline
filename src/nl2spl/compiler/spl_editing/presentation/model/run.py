"""Run presentation DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.compiler.spl_editing.presentation.model.advanced import (
    RunAdvancedDetails,
)
from nl2spl.compiler.spl_editing.presentation.model.issue import (
    IssueCategorySummary,
)


@dataclass(frozen=True)
class RunPresentationView:
    run_id: str
    run_label: str
    snapshot_id: str
    overlay_version: int
    snapshot_status: str
    editable: bool
    issue_count: int
    issue_summary: tuple[IssueCategorySummary, ...] = ()
    advanced: RunAdvancedDetails = field(default_factory=RunAdvancedDetails)


__all__ = ["RunPresentationView"]
