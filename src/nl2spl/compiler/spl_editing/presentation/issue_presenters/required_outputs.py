"""Required output issue presenter."""

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


class RequiredOutputPresenter:
    """Presentation projection for required outputs without producers."""

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
        return IssueCardView(
            display_id=display_id,
            issue_id=issue.issue_id,
            category=IssueCategory.REQUIRED_OUTPUTS,
            title=issue_title(
                IssueCategory.REQUIRED_OUTPUTS,
                output_name=context.output_name,
            ),
            impact=impact_text(IssueCategory.REQUIRED_OUTPUTS),
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
        missing = (context.output_name,) if context.output_name else ("producer",)
        return IssueDetailPresentationView(
            issue_id=issue.issue_id,
            title=issue_title(
                IssueCategory.REQUIRED_OUTPUTS,
                output_name=context.output_name,
            ),
            what_was_detected=what_detected_text(IssueCategory.REQUIRED_OUTPUTS),
            missing_items=missing,
            why_it_matters=why_it_matters_text(IssueCategory.REQUIRED_OUTPUTS),
            available_repairs=repair_options,
            suggested_resolution=suggested_resolution,
            source_context=context.source_excerpt,
            presentation_quality=context.quality,
            advanced=advanced,
        )


__all__ = ["RequiredOutputPresenter"]
