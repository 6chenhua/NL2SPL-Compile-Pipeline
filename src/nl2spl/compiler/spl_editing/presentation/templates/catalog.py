"""Facade for presentation display copy."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.presentation.templates.confirmation_copy import (
    will_do,
    will_not_do,
)
from nl2spl.compiler.spl_editing.presentation.templates.issue_copy import (
    category_label,
    impact_text,
    issue_title,
    what_detected_text,
    why_it_matters_text,
)
from nl2spl.compiler.spl_editing.presentation.templates.repair_option_copy import (
    option_label,
    patch_description,
    patch_label,
)
from nl2spl.compiler.spl_editing.presentation.templates.suggestion_copy import (
    expected_effects,
)
from nl2spl.compiler.spl_editing.presentation.templates.unavailable_reasons import (
    unavailable_reason,
)
from nl2spl.compiler.spl_editing.presentation.templates.verification_copy import (
    authority_summary,
)

__all__ = [
    "authority_summary",
    "category_label",
    "expected_effects",
    "impact_text",
    "issue_title",
    "option_label",
    "patch_description",
    "patch_label",
    "unavailable_reason",
    "what_detected_text",
    "why_it_matters_text",
    "will_do",
    "will_not_do",
]
