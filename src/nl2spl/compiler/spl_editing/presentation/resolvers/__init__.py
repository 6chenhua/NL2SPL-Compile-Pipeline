"""Presentation resolver exports."""

from nl2spl.compiler.spl_editing.presentation.resolvers.advanced_details import (
    build_advanced_details,
)
from nl2spl.compiler.spl_editing.presentation.resolvers.display_context import (
    DisplayContext,
    build_display_context,
    category_for_issue,
)
from nl2spl.compiler.spl_editing.presentation.resolvers.issue_subject import issue_subject_for
from nl2spl.compiler.spl_editing.presentation.resolvers.repair_options import (
    repair_options_for_issue,
)
from nl2spl.compiler.spl_editing.presentation.resolvers.source_excerpt import (
    source_excerpt_for_issue,
)
from nl2spl.compiler.spl_editing.presentation.resolvers.suggested_resolution import (
    suggested_resolution_for_issue,
)

__all__ = [
    "DisplayContext",
    "build_advanced_details",
    "build_display_context",
    "issue_subject_for",
    "category_for_issue",
    "repair_options_for_issue",
    "source_excerpt_for_issue",
    "suggested_resolution_for_issue",
]
