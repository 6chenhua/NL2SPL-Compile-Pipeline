"""StructuredTextIR — representation for structured/raw/json text in IR constructs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

StructuredTextFormat = Literal[
    "json_object",
    "structured_text",
    "raw_text",
    "empty_placeholder",
]


@dataclass
class StructuredTextIR:
    """Structured text IR representation.

    Attributes:
        format: Text format type (json_object, structured_text, raw_text, empty_placeholder)
        canonical_text: Canonical text string representation
        parsed_value: Optional parsed structured value (e.g. dict or list)
    """

    format: StructuredTextFormat
    canonical_text: str
    parsed_value: Any | None = None
