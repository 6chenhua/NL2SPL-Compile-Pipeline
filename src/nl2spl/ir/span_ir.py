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
    """Text span with ambiguity markers and provenance.

    Attributes:
        span_id: Unique identifier (format: s{N}; sub-spans use suffix s{N}a, s{N}b)
        text: Original text content (structural markers stripped)
        ambiguity: Ambiguity information
        source_section_id: Structured section ID from canonical adapter
                           (e.g. "sec_task_family")
        source_packet_id: Structured packet ID from canonical adapter
        section_context: Natural-language section title for LLM-path spans
                         (e.g. "Policies", "Inputs for Each Run").
                         Mutually exclusive in practice with source_section_id;
                         both may be None for top-level content.
        is_placeholder: True when span represents an absent/empty value
                        (e.g. "None" after stripping "Optional:").
    """

    span_id: str
    text: str
    ambiguity: AmbiguityInfo = field(default_factory=AmbiguityInfo)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    section_context: str | None = None
    is_placeholder: bool = False

    guard_text_exact: str | None = None
    action_text_exact: str | None = None
    segmentation_kind: str | None = None

    def __post_init__(self) -> None:
        """Validate span_id format.

        Empty string is allowed as a temporary placeholder during pre-processing.
        The pipeline's execute() will reassign all IDs before returning.
        """
        if self.span_id and not self.span_id.startswith("s"):
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
        if self.section_context is not None:
            data["section_context"] = self.section_context
        if self.is_placeholder:
            data["is_placeholder"] = True
        if self.guard_text_exact is not None:
            data["guard_text_exact"] = self.guard_text_exact
        if self.action_text_exact is not None:
            data["action_text_exact"] = self.action_text_exact
        if self.segmentation_kind is not None:
            data["segmentation_kind"] = self.segmentation_kind
        return data
