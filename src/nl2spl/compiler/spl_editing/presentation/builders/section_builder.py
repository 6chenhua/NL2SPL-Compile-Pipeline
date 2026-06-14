"""Issue section builder."""

from __future__ import annotations

from collections import Counter

from nl2spl.compiler.spl_editing.presentation.contract.categories import (
    IssueCategory,
)
from nl2spl.compiler.spl_editing.presentation.contract.sections import (
    IssueSectionKey,
    IssueSectionKind,
)
from nl2spl.compiler.spl_editing.presentation.model.issue import (
    IssueCardView,
    IssueCategorySummary,
)
from nl2spl.compiler.spl_editing.presentation.model.sections import (
    IssueSectionView,
)
from nl2spl.compiler.spl_editing.presentation.templates.issue_copy import (
    category_label,
)


def build_sections(
    cards: tuple[IssueCardView, ...],
    *,
    include_developer: bool = False,
) -> tuple[IssueSectionView, ...]:
    editable = tuple(
        c
        for c in cards
        if c.repairability == "editable"
        and c.category != IssueCategory.DEVELOPER_DIAGNOSTIC
    )
    review = tuple(
        c
        for c in cards
        if c.repairability != "editable" and c.category != IssueCategory.DEVELOPER_DIAGNOSTIC
    )
    developer = tuple(c for c in cards if c.category == IssueCategory.DEVELOPER_DIAGNOSTIC)

    sections = [
        IssueSectionView(
            section_key=IssueSectionKey.EDITABLE_ISSUES,
            label="Editable issues",
            section_kind=IssueSectionKind.EDITABLE,
            items=editable,
        ),
        IssueSectionView(
            section_key=IssueSectionKey.REVIEW_NEEDED,
            label="Review needed",
            section_kind=IssueSectionKind.REVIEW_NEEDED,
            items=review,
            visible_by_default=bool(review),
        ),
    ]
    if include_developer:
        sections.append(
            IssueSectionView(
                section_key=IssueSectionKey.DEVELOPER_DIAGNOSTICS,
                label="Developer diagnostics",
                section_kind=IssueSectionKind.DEVELOPER_DIAGNOSTICS,
                items=developer,
                visible_by_default=False,
            )
        )
    return tuple(sections)


def summarize_cards(cards: tuple[IssueCardView, ...]) -> tuple[IssueCategorySummary, ...]:
    counts = Counter(c.category for c in cards if c.category != IssueCategory.DEVELOPER_DIAGNOSTIC)
    return tuple(
        IssueCategorySummary(category=category, label=category_label(category), count=count)
        for category, count in sorted(counts.items(), key=lambda item: item[0].value)
    )


__all__ = ["build_sections", "summarize_cards"]
