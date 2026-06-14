"""SPL Editing presentation projection layer."""

from nl2spl.compiler.spl_editing.presentation.contract import (
    IssueCategory,
    IssueSectionKey,
    IssueSectionKind,
    PresentationMode,
    PresentationQuality,
    RepairOptionAvailability,
)
from nl2spl.compiler.spl_editing.presentation.model import (
    ApplyConfirmationView,
    IssueAdvancedDetails,
    IssueCardView,
    IssueCategorySummary,
    IssueDetailPresentationView,
    IssueListPresentationView,
    IssueSectionView,
    RepairOptionView,
    RunAdvancedDetails,
    RunPresentationView,
    SuggestionPresentationView,
    VerificationPresentationView,
)
from nl2spl.compiler.spl_editing.presentation.service import (
    SPLEditingPresentationService,
)

__all__ = [
    "ApplyConfirmationView",
    "IssueAdvancedDetails",
    "IssueCardView",
    "IssueCategory",
    "IssueCategorySummary",
    "IssueDetailPresentationView",
    "IssueListPresentationView",
    "IssueSectionKey",
    "IssueSectionKind",
    "IssueSectionView",
    "PresentationMode",
    "PresentationQuality",
    "RepairOptionAvailability",
    "RepairOptionView",
    "RunAdvancedDetails",
    "RunPresentationView",
    "SuggestionPresentationView",
    "SPLEditingPresentationService",
    "VerificationPresentationView",
]
