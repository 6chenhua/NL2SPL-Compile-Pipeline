"""Text utility methods for Stage 11 SPLRenderer."""

from __future__ import annotations

import re


class TextUtilsMixin:
    """Mixin class containing text utility methods for SPLRenderer."""

    def _render_condition(self, text: str) -> str:
        """Render a condition without redundant trigger words."""
        condition = self._strip_terminal_punctuation(self._clean_text(text))
        condition = re.sub(r"^(if|when)\s+", "", condition, flags=re.IGNORECASE)
        return condition or "condition"

    def _strip_leading_condition_clause(self, text: str) -> str:
        """Remove a leading natural-language condition from a command."""
        return re.sub(
            r"^(if|when|unless)\s+[^,]+,\s*",
            "",
            text,
            flags=re.IGNORECASE,
        )

    def _strip_trailing_condition_clause(self, text: str, condition_text: str) -> str:
        """Remove a trailing condition already represented by a block."""
        condition_key = self._condition_key(condition_text)
        for keyword in ("if", "when", "unless"):
            pattern = rf"\s+{keyword}\s+(.+)$"
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match and self._condition_key(match.group(1)) == condition_key:
                return text[: match.start()]
        return text

    def _condition_key(self, text: str) -> str:
        """Normalize condition text for duplicate detection."""
        key = self._strip_terminal_punctuation(self._clean_text(text)).lower()
        key = re.sub(r"^(if|when)\s+", "", key)
        return re.sub(r"[^a-z0-9_]+", " ", key).strip()

    def _clean_text(self, text: str) -> str:
        """Collapse whitespace in free text."""
        return " ".join(str(text).strip().split())

    def _strip_terminal_punctuation(self, text: str) -> str:
        """Remove punctuation that reads badly before RESULT/RESPONSE."""
        return text.rstrip(" .")

    def _capitalize_first(self, text: str) -> str:
        """Capitalize the first character of a command description."""
        if not text:
            return text
        return text[0].upper() + text[1:]

    def _quote_text(self, text: str) -> str:
        """Escape free text for quoted SPL descriptions."""
        return self._clean_text(text).replace('"', '\\"')
