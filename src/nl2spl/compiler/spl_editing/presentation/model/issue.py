"""Issue presentation DTOs."""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.compiler.spl_editing.presentation.contract.availability import (
    RepairOptionAvailability,
)
from nl2spl.compiler.spl_editing.presentation.contract.categories import (
    IssueCategory,
)
from nl2spl.compiler.spl_editing.presentation.contract.invariants import (
    assert_can_fix_invariant,
)
from nl2spl.compiler.spl_editing.presentation.contract.quality import (
    PresentationQuality,
)
from nl2spl.compiler.spl_editing.presentation.model.advanced import (
    IssueAdvancedDetails,
)


@dataclass(frozen=True)
class IssueCategorySummary:
    category: IssueCategory
    label: str
    count: int


@dataclass(frozen=True)
class RepairOptionView:
    label: str
    description: str
    option_id: str | None = None
    strategy_id: str | None = None
    interaction_contract_id: str | None = None
    interaction_summary: str | None = None
    patch_types: tuple[str, ...] = ()
    verification_lane: str = ""
    availability: RepairOptionAvailability = RepairOptionAvailability.AVAILABLE
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class IssueCardView:
    display_id: int
    issue_id: str
    category: IssueCategory
    title: str
    impact: str
    fix_label: str
    suggested_resolution: str | None = None
    source_excerpt: str | None = None
    missing_items: tuple[str, ...] = ()
    repairability: str = "editable"
    can_fix: bool = False
    presentation_quality: PresentationQuality = PresentationQuality.COMPLETE
    advanced: IssueAdvancedDetails | None = None


@dataclass(frozen=True)
class IssueDetailPresentationView:
    issue_id: str
    title: str
    what_was_detected: str
    missing_items: tuple[str, ...]
    why_it_matters: str
    available_repairs: tuple[RepairOptionView, ...]
    suggested_resolution: str | None = None
    source_context: str | None = None
    presentation_quality: PresentationQuality = PresentationQuality.COMPLETE
    advanced: IssueAdvancedDetails = field(
        default_factory=lambda: IssueAdvancedDetails(primary_diagnostic_id="")
    )

    def __post_init__(self) -> None:
        can_fix = any(
            option.availability == RepairOptionAvailability.AVAILABLE
            for option in self.available_repairs
        )
        assert_can_fix_invariant(
            can_fix=can_fix,
            options=self.available_repairs,
        )


__all__ = [
    "IssueCardView",
    "IssueCategorySummary",
    "IssueDetailPresentationView",
    "RepairOptionView",
]
