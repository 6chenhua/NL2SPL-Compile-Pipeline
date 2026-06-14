"""Exception handling issue presenter."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import EditableIssue
from nl2spl.compiler.spl_editing.presentation.contract.categories import (
    IssueCategory,
)
from nl2spl.compiler.spl_editing.presentation.issue_presenters.base import (
    can_fix,
    fix_label_for,
)
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
from nl2spl.compiler.spl_editing.presentation.templates.issue_copy import (
    impact_text,
    issue_title,
    what_detected_text,
    why_it_matters_text,
)


class ExceptionHandlingPresenter:
    """Presentation projection for missing exception handlers."""

    def build_card(
        self,
        *,
        display_id: int,
        issue: EditableIssue,
        context: DisplayContext,
        repair_options: tuple[RepairOptionView, ...],
        suggested_resolution: str | None,
        advanced: IssueAdvancedDetails,
    ) -> IssueCardView:
        title = issue_title(
            IssueCategory.EXCEPTION_HANDLING,
            condition_text=context.condition_text,
        )
        return IssueCardView(
            display_id=display_id,
            issue_id=issue.issue_id,
            category=IssueCategory.EXCEPTION_HANDLING,
            title=title,
            impact=impact_text(IssueCategory.EXCEPTION_HANDLING),
            fix_label=fix_label_for(repair_options),
            suggested_resolution=suggested_resolution,
            source_excerpt=context.source_excerpt,
            repairability=issue.repairability,
            can_fix=can_fix(repair_options),
            presentation_quality=context.quality,
            advanced=advanced,
        )

    def build_detail(
        self,
        *,
        issue: EditableIssue,
        context: DisplayContext,
        repair_options: tuple[RepairOptionView, ...],
        suggested_resolution: str | None,
        advanced: IssueAdvancedDetails,
    ) -> IssueDetailPresentationView:
        title = issue_title(
            IssueCategory.EXCEPTION_HANDLING,
            condition_text=context.condition_text,
        )
        return IssueDetailPresentationView(
            issue_id=issue.issue_id,
            title=title,
            what_was_detected=what_detected_text(IssueCategory.EXCEPTION_HANDLING),
            missing_items=("handler action",),
            why_it_matters=why_it_matters_text(IssueCategory.EXCEPTION_HANDLING),
            available_repairs=repair_options,
            suggested_resolution=suggested_resolution,
            source_context=context.source_excerpt,
            presentation_quality=context.quality,
            advanced=advanced,
        )


__all__ = ["ExceptionHandlingPresenter"]
