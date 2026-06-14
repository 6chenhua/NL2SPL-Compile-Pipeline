"""Developer-only diagnostic presenter."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.presentation.issue_presenters.generic import (
    GenericIssuePresenter,
)


class DeveloperOnlyPresenter(GenericIssuePresenter):
    """Projection for diagnostics hidden from default user issue lists."""


__all__ = ["DeveloperOnlyPresenter"]
