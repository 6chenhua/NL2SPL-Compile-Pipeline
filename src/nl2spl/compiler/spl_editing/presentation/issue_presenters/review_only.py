"""Review-only issue presenter."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.presentation.contract.categories import (
    IssueCategory,
)
from nl2spl.compiler.spl_editing.presentation.issue_presenters.generic import (
    GenericIssuePresenter,
)
from nl2spl.compiler.spl_editing.presentation.resolvers.display_context import (
    DisplayContext,
)


class ReviewOnlyPresenter(GenericIssuePresenter):
    """Generic presenter with review-only category override."""

    def _category(self, context: DisplayContext) -> IssueCategory:
        del context
        return IssueCategory.REVIEW_ONLY


__all__ = ["ReviewOnlyPresenter"]
