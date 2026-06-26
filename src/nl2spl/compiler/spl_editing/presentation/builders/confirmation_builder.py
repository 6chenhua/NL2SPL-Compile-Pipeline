"""Apply confirmation presentation builder.

R6: Accepts an optional ``confirmation_context`` to populate
materialization-aware fields (target construct, selected refs, plan, lane).
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from nl2spl.compiler.spl_editing.core.model import RepairSuggestion
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent
from nl2spl.compiler.spl_editing.presentation.model.confirmation import (
    ApplyConfirmationView,
    ConfirmationRefItem,
)
from nl2spl.compiler.spl_editing.presentation.templates.confirmation_copy import (
    will_do,
    will_not_do,
)


def build_apply_confirmation(
    suggestion: RepairSuggestion,
    confirmation_context: Any | None = None,
) -> ApplyConfirmationView:
    """Build an ``ApplyConfirmationView`` from a suggestion.

    When *confirmation_context* is provided (R6 materialization path),
    the view is enriched with the sealed target construct, selected
    references, intent summary, plan id, and verification lane.
    """
    patch = suggestion.patch
    view = ApplyConfirmationView(
        suggestion_id=suggestion.suggestion_id,
        title=suggestion.title,
        will_do=will_do(patch.patch_type, patch.verification_lane),
        will_not_do=will_not_do(),
        verification_lane=patch.verification_lane,
        requires_user_confirmation=True,
    )

    if confirmation_context is not None:
        intent = suggestion.patch.payload
        if isinstance(intent, ConstructRepairIntent):
            view = replace(
                view,
                target_construct=(
                    f"{confirmation_context.catalog_entry.construct_type}"
                    f".{confirmation_context.catalog_entry.slot_name}"
                ),
                target_name=confirmation_context.target.canonical_name or "",
                selected_refs=tuple(
                    ConfirmationRefItem(
                        ref_id=r.ref.ref_id,
                        display_label=r.ref.display_label,
                        ref_kind=r.ref.ref_kind,
                        ref_role=r.ref.ref_role,
                    )
                    for r in confirmation_context.resolved_refs
                ),
                intent_summary=intent.intent_summary,
                materialization_plan_id=intent.materialization_plan_id or "",
            )

    return view


__all__ = ["build_apply_confirmation"]
