"""Suggestion presentation builder."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import RepairSuggestion
from nl2spl.compiler.spl_editing.presentation.model.suggestion import (
    SuggestionPresentationView,
)
from nl2spl.compiler.spl_editing.presentation.templates.suggestion_copy import (
    expected_effects,
)


def build_suggestion_presentation(
    suggestion: RepairSuggestion,
) -> SuggestionPresentationView:
    effects = suggestion.expected_effect or expected_effects(
        suggestion.patch.patch_type,
    )
    return SuggestionPresentationView(
        suggestion_id=suggestion.suggestion_id,
        title=suggestion.title,
        explanation=suggestion.explanation,
        expected_effect=effects,
        risks=suggestion.risks,
        preview=suggestion.spl_preview,
        patch_type=suggestion.patch.patch_type,
    )


def build_suggestion_presentations(
    suggestions: tuple[RepairSuggestion, ...],
) -> tuple[SuggestionPresentationView, ...]:
    return tuple(build_suggestion_presentation(s) for s in suggestions)


__all__ = ["build_suggestion_presentation", "build_suggestion_presentations"]
