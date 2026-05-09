"""SpanIR - Text span with ambiguity markers."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AmbiguityInfo:
    """Ambiguity information for a span."""

    is_ambiguous: bool = False
    reasons: list[str] = field(default_factory=list)
    needs_split: bool = False


@dataclass
class SpanIR:
    """Text span with ambiguity markers.

    Attributes:
        span_id: Unique identifier (format: s{N})
        text: Original text content
        ambiguity: Ambiguity information
    """

    span_id: str
    text: str
    ambiguity: AmbiguityInfo = field(default_factory=AmbiguityInfo)

    def __post_init__(self) -> None:
        """Validate span_id format."""
        if not self.span_id.startswith("s"):
            raise ValueError(f"span_id must start with 's', got: {self.span_id}")
