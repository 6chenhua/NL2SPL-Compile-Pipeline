"""Data models for Stage 1 Segmentation payload and sidecar."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from nl2spl.ir.diagnostics import CompileDiagnostic


@dataclass(frozen=True)
class LLMSpanSegment:
    """Raw span segmentation output from LLM."""
    segment_text_exact: str
    segmentation_kind: Literal[
        "atomic_text_unit",
        "atomic_action_candidate",
        "guarded_action",
        "continuation_repaired",
        "ambiguous_boundary",
    ]
    guard_text_exact: str | None = None
    action_text_exact: str | None = None
    source_packet_ids: tuple[str, ...] = ()
    source_section_id: str | None = None
    char_start: int | None = None
    char_end: int | None = None
    boundary_confidence: Literal["high", "medium", "low"] = "medium"
    continuation_repaired: bool = False

@dataclass(frozen=True)
class SpanSegmentationRecord:
    """Authoritative, validated span segmentation record."""
    span_id: str
    segmentation_kind: Literal[
        "atomic_text_unit",
        "atomic_action_candidate",
        "guarded_action",
        "continuation_repaired",
        "ambiguous_boundary",
    ]
    span_text: str
    guard_text_exact: str | None
    action_text_exact: str | None
    parent_packet_ids: tuple[str, ...]
    source_section_id: str
    char_start: int
    char_end: int
    boundary_confidence: Literal["high", "medium", "low"]
    continuation_repaired: bool
    validation_status: Literal["validated", "repaired_by_validator", "ambiguous"]
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize record to dict."""
        return {
            "span_id": self.span_id,
            "segmentation_kind": self.segmentation_kind,
            "span_text": self.span_text,
            "guard_text_exact": self.guard_text_exact,
            "action_text_exact": self.action_text_exact,
            "parent_packet_ids": list(self.parent_packet_ids),
            "source_section_id": self.source_section_id,
            "char_start": self.char_start,
            "char_end": self.char_end,
            "boundary_confidence": self.boundary_confidence,
            "continuation_repaired": self.continuation_repaired,
            "validation_status": self.validation_status,
            "metadata": dict(self.metadata),
        }

@dataclass(frozen=True)
class Stage1SegmentationPayload:
    """Stage 1 segmentation payload for snapshots/checkpoints."""
    records: tuple[SpanSegmentationRecord, ...]
    diagnostics: tuple[CompileDiagnostic, ...]
    warnings: tuple[str, ...]
    source_buffers: Mapping[str, Any]  # dict representation of source buffers
