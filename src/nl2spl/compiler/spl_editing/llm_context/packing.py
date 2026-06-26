"""ContextPacker — token budget control for prompt context (Phase L2).

Trims source excerpts, nearby steps, and candidate lists to stay
within configured token budgets.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.llm_context.model import StepSummary


class ContextPacker:
    """Control the size of context elements injected into the prompt."""

    def __init__(
        self,
        *,
        max_source_excerpt_chars: int = 500,
        max_nearby_steps: int = 5,
        max_candidate_refs: int = 10,
        max_variable_list: int = 30,
        max_previous_suggestions: int = 10,
    ) -> None:
        self.max_source_excerpt_chars = max_source_excerpt_chars
        self.max_nearby_steps = max_nearby_steps
        self.max_candidate_refs = max_candidate_refs
        self.max_variable_list = max_variable_list
        self.max_previous_suggestions = max_previous_suggestions

    def trim_excerpt(self, text: str | None) -> str | None:
        if not text:
            return None
        if len(text) <= self.max_source_excerpt_chars:
            return text
        return text[: self.max_source_excerpt_chars] + "…"

    def trim_nearby_steps(self, steps: tuple[StepSummary, ...]) -> tuple[StepSummary, ...]:
        return steps[: self.max_nearby_steps]

    def trim_variables(self, variables: tuple[str, ...]) -> tuple[str, ...]:
        return variables[: self.max_variable_list]

    def trim_previous(self, summaries: tuple[str, ...]) -> tuple[str, ...]:
        return summaries[: self.max_previous_suggestions]
