"""Worker delegation issue presenter."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import EditableIssue, UserFacingIssue
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

_DEFAULT_MISSING = (
    "input contract",
    "output contract",
    "invocation point",
    "result handoff",
)


class WorkerDelegationPresenter:
    """Presentation projection for worker delegation contract gaps."""

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
        missing = context.missing_items or _DEFAULT_MISSING
        subject = context.subject
        title = _subject_title(subject)
        return IssueCardView(
            display_id=display_id,
            issue_id=issue.issue_id,
            category=IssueCategory.WORKER_DELEGATION,
            title=title,
            impact=impact_text(IssueCategory.WORKER_DELEGATION),
            fix_label=fix_label_for(repair_options),
            suggested_resolution=suggested_resolution,
            source_excerpt=context.source_excerpt,
            missing_items=missing,
            repairability=issue.repairability,
            can_fix=can_fix(repair_options),
            presentation_quality=context.quality,
            advanced=advanced,
        )

    def build_detail(
        self,
        *,
        issue: EditableIssue | UserFacingIssue,
        context: DisplayContext,
        repair_options: tuple[RepairOptionView, ...],
        suggested_resolution: str | None,
        advanced: IssueAdvancedDetails,
    ) -> IssueDetailPresentationView:
        missing = context.missing_items or _DEFAULT_MISSING
        subject = context.subject
        title = _subject_title(subject)
        detected = (
            f"The delegation intent for {subject.summary} is incomplete."
            if subject is not None and subject.summary
            else what_detected_text(IssueCategory.WORKER_DELEGATION)
        )
        return IssueDetailPresentationView(
            issue_id=issue.issue_id,
            title=title,
            what_was_detected=detected,
            missing_items=missing,
            why_it_matters=why_it_matters_text(IssueCategory.WORKER_DELEGATION),
            available_repairs=repair_options,
            suggested_resolution=suggested_resolution,
            source_context=context.source_excerpt,
            presentation_quality=context.quality,
            advanced=advanced,
        )


def _subject_title(subject) -> str:
    if subject is None:
        return issue_title(IssueCategory.WORKER_DELEGATION)
    if subject.subject_kind == "worker" and subject.display_name:
        return f"Child worker definition is incomplete: {subject.display_name}"
    if subject.summary:
        summary = " ".join(subject.summary.split())
        if len(summary) > 120:
            summary = summary[:117].rstrip() + "..."
        return f"Potential child-worker responsibility is incomplete: {summary}"
    return issue_title(IssueCategory.WORKER_DELEGATION)


__all__ = ["WorkerDelegationPresenter"]
