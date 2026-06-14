"""Stable presentation contract symbols."""

from nl2spl.compiler.spl_editing.presentation.contract.availability import (
    RepairOptionAvailability,
)
from nl2spl.compiler.spl_editing.presentation.contract.categories import (
    IssueCategory,
)
from nl2spl.compiler.spl_editing.presentation.contract.invariants import (
    assert_can_fix_invariant,
    expected_can_fix,
    has_available_repair_option,
)
from nl2spl.compiler.spl_editing.presentation.contract.modes import (
    PresentationMode,
)
from nl2spl.compiler.spl_editing.presentation.contract.quality import (
    PresentationQuality,
)
from nl2spl.compiler.spl_editing.presentation.contract.sections import (
    IssueSectionKey,
    IssueSectionKind,
)

__all__ = [
    "IssueCategory",
    "IssueSectionKey",
    "IssueSectionKind",
    "PresentationMode",
    "PresentationQuality",
    "RepairOptionAvailability",
    "assert_can_fix_invariant",
    "expected_can_fix",
    "has_available_repair_option",
]
