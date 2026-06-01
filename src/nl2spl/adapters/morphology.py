from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class MorphologyProfile:
    """Represents the pure morphological shape of a text input."""
    has_headings: bool
    has_colon_sections: bool
    has_lists: bool
    has_tables: bool
    has_markdown_blocks: bool
    has_key_value_blocks: bool

    @property
    def is_highly_structured(self) -> bool:
        """Return True if the text exhibits structural section markers."""
        return self.has_headings or self.has_colon_sections or self.has_key_value_blocks


class ShapeGrammar:
    """Shared regular expressions for morphological structure."""
    
    # Markdown headings (e.g., "# Title")
    MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+\S")
    
    # Colon-delimited section heading (for example, "Heading:").
    # \uff1a is the Unicode FULLWIDTH COLON (U+FF1A) used in CJK text.
    # Keeping it as an escape avoids encoding issues across platforms.
    COLON_HEADING = re.compile(r"^[^:\uff1a\n]{1,120}[:\uff1a]$")
    
    # Key-value section line (for example, "Key: Value").
    KEY_VALUE = re.compile(r"^[^:\uff1a\n]{1,120}[:\uff1a]\s*\S")
    
    # List items (- or * or 1.)
    LIST_ITEM = re.compile(r"^[-*]\s+\S|^\d+\.\s+\S")
    
    # Table-like structure (e.g., | Header |)
    TABLE_ROW = re.compile(r"^\|.*\|$")

    @classmethod
    def is_heading(cls, line: str) -> bool:
        """True if the line is a markdown heading or a colon heading."""
        line_stripped = line.strip()
        return bool(cls.MARKDOWN_HEADING.match(line_stripped) or cls.COLON_HEADING.match(line_stripped))


class StructuralShapeDetector:
    """Pure morphology detector. Contains NO domain semantic terms."""

    @staticmethod
    def detect(text: str) -> MorphologyProfile:
        lines = text.split("\n")

        has_headings = False
        has_colon_sections = False
        has_lists = False
        has_tables = False
        has_markdown_blocks = False
        has_key_value_blocks = False

        in_code_block = False
        for line in lines:
            line_stripped = line.strip()

            if line_stripped.startswith("```"):
                in_code_block = not in_code_block
                has_markdown_blocks = True
                continue

            if in_code_block:
                continue

            if ShapeGrammar.MARKDOWN_HEADING.match(line_stripped):
                has_headings = True

            if ShapeGrammar.COLON_HEADING.match(line_stripped):
                has_colon_sections = True

            if ShapeGrammar.KEY_VALUE.match(line_stripped):
                has_key_value_blocks = True

            if ShapeGrammar.LIST_ITEM.match(line_stripped):
                has_lists = True

            if ShapeGrammar.TABLE_ROW.match(line_stripped):
                has_tables = True

        return MorphologyProfile(
            has_headings=has_headings,
            has_colon_sections=has_colon_sections,
            has_lists=has_lists,
            has_tables=has_tables,
            has_markdown_blocks=has_markdown_blocks,
            has_key_value_blocks=has_key_value_blocks,
        )
