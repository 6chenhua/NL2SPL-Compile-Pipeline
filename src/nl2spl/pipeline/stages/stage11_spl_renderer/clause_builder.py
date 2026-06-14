"""Clause building methods for Stage 11 SPLRenderer."""

from __future__ import annotations


class ClauseBuilderMixin:
    """Mixin class containing clause building methods for SPLRenderer."""

    def _canonical_command_text(
        self,
        text: str,
        condition_text: str | None = None,
    ) -> str:
        """Rewrite extracted step text into a clean command description."""
        description = self._clean_text(text) or "Perform the step"
        condition = self._clean_text(condition_text or "")

        description = self._strip_leading_condition_clause(description)
        if condition:
            description = self._strip_trailing_condition_clause(description, condition)
            if self._condition_key(description) == self._condition_key(condition):
                description = "Evaluate whether the condition holds"

        return self._capitalize_first(self._strip_terminal_punctuation(description))

    def _description_with_refs(self, text: str, inputs: list[str]) -> str:
        """Append variable references to a command description."""
        description = self._strip_terminal_punctuation(
            self._clean_text(text) or "Perform the step"
        )
        refs = self._refs(inputs)
        missing_refs = [ref for ref in refs if ref not in description]
        if missing_refs:
            description = f"{description} based on {self._join_refs(missing_refs)}"
        return description

    def _with_clause(self, inputs: list[str]) -> str:
        """Render an invocation WITH clause."""
        refs = self._refs(inputs)
        if not refs:
            return ""
        return f" WITH {', '.join(refs)}"

    def _result_clause(self, keyword: str, outputs: list[str]) -> str:
        """Render declared outputs as a command result clause."""
        if not outputs:
            return ""

        results: list[str] = []
        for output in outputs:
            if not output:
                continue
            results.append(self._result_item(output))
            self._produced_variables.add(output)

        if not results:
            return ""
        return f" {keyword} {', '.join(results)} SET"

    def _result_item(self, output: str) -> str:
        """Render one output binding in a result list."""
        if output not in self._produced_variables:
            data_type = self._result_data_types.get(output, "text")
            return f"{output}: {self._format_data_type(data_type)}"
        return f"<REF>{output}</REF>"

    def _refs(self, names: list[str]) -> list[str]:
        """Render variable names as SPL REF tags."""
        return [f"<REF>{name}</REF>" for name in names if name]

    def _join_refs(self, refs: list[str]) -> str:
        """Join REF tags into readable text."""
        if len(refs) <= 1:
            return "".join(refs)
        if len(refs) == 2:
            return f"{refs[0]} and {refs[1]}"
        return f"{', '.join(refs[:-1])}, and {refs[-1]}"
