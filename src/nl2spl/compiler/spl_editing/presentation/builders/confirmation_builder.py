"""Apply confirmation presentation builder."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import RepairSuggestion
from nl2spl.compiler.spl_editing.presentation.model.confirmation import (
    ApplyConfirmationView,
)
from nl2spl.compiler.spl_editing.presentation.templates.confirmation_copy import (
    will_do,
    will_not_do,
)


def build_apply_confirmation(
    suggestion: RepairSuggestion,
) -> ApplyConfirmationView:
    patch = suggestion.patch
    return ApplyConfirmationView(
        suggestion_id=suggestion.suggestion_id,
        title=suggestion.title,
        will_do=will_do(patch.patch_type, patch.verification_lane),
        will_not_do=will_not_do(),
        verification_lane=patch.verification_lane,
        requires_user_confirmation=True,
    )


__all__ = ["build_apply_confirmation"]
