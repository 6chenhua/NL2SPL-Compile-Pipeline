"""Sectioned issue list presentation DTOs."""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.spl_editing.presentation.contract.sections import (
    IssueSectionKey,
    IssueSectionKind,
)
from nl2spl.compiler.spl_editing.presentation.model.issue import (
    IssueCardView,
    IssueCategorySummary,
)


@dataclass(frozen=True)
class IssueSectionView:
    section_key: IssueSectionKey
    label: str
    section_kind: IssueSectionKind
    items: tuple[IssueCardView, ...] = ()
    visible_by_default: bool = True


@dataclass(frozen=True)
class IssueListPresentationView:
    run_id: str
    snapshot_id: str
    sections: tuple[IssueSectionView, ...] = ()
    summary: tuple[IssueCategorySummary, ...] = ()


__all__ = ["IssueListPresentationView", "IssueSectionView"]
