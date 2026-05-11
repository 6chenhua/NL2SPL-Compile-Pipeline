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
    source_section_id: str | None = None
    source_packet_id: str | None = None

    def __post_init__(self) -> None:
        """Validate span_id format."""
        if not self.span_id.startswith("s"):
            raise ValueError(f"span_id must start with 's', got: {self.span_id}")

    def to_dict(self) -> dict[str, object]:
        """Serialize span while omitting absent adapter provenance."""
        data: dict[str, object] = {
            "span_id": self.span_id,
            "text": self.text,
            "ambiguity": {
                "is_ambiguous": self.ambiguity.is_ambiguous,
                "reasons": self.ambiguity.reasons,
                "needs_split": self.ambiguity.needs_split,
            },
        }
        if self.source_section_id is not None:
            data["source_section_id"] = self.source_section_id
        if self.source_packet_id is not None:
            data["source_packet_id"] = self.source_packet_id
        return data
