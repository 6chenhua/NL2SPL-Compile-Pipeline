"""Issue family presenter protocol."""

from __future__ import annotations

from typing import Protocol

from nl2spl.compiler.spl_editing.core.model import EditableIssue, UserFacingIssue
from nl2spl.compiler.spl_editing.presentation.model.advanced import (
    IssueAdvancedDetails,
)
from nl2spl.compiler.spl_editing.presentation.model.issue import (
    IssueCardView,
    IssueDetailPresentationView,
    RepairOptionView,
)
from nl2spl.compiler.spl_editing.presentation.resolvers.display_context import (
    DisplayContext,
)


class IssueFamilyPresenter(Protocol):
    """Build user-facing card and detail views for one issue family."""

    def build_card(
        self,
        *,
        display_id: int,
        issue: EditableIssue | UserFacingIssue,
        context: DisplayContext,
        repair_options: tuple[RepairOptionView, ...],
        suggested_resolution: str | None,
        advanced: IssueAdvancedDetails,
    ) -> IssueCardView:
        """Project an editable issue into a list card."""

    def build_detail(
        self,
        *,
        issue: EditableIssue | UserFacingIssue,
        context: DisplayContext,
        repair_options: tuple[RepairOptionView, ...],
        suggested_resolution: str | None,
        advanced: IssueAdvancedDetails,
    ) -> IssueDetailPresentationView:
        """Project an editable issue into a detail view."""


def fix_label_for(options: tuple[RepairOptionView, ...]) -> str:
    labels = tuple(o.label for o in options if o.patch_types)
    if not labels:
        return "Review issue"
    return " / ".join(dict.fromkeys(labels))


def can_fix(options: tuple[RepairOptionView, ...]) -> bool:
    from nl2spl.compiler.spl_editing.presentation.contract.availability import (
        RepairOptionAvailability,
    )

    return any(o.availability == RepairOptionAvailability.AVAILABLE for o in options)


__all__ = ["IssueFamilyPresenter", "can_fix", "fix_label_for"]
