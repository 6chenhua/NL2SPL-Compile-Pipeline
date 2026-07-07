"""Parser for raw LLM segmentation JSON output."""

from __future__ import annotations

from typing import Any
from nl2spl.pipeline.stages.stage1_segmentation.segmentation_payload import LLMSpanSegment

class LLMSegmentParser:
    """Parses raw LLM segmentation response dictionary into LLMSpanSegment structures."""

    @staticmethod
    def parse(response_dict: dict[str, Any]) -> list[LLMSpanSegment]:
        """Parse raw response dict.

        Args:
            response_dict: Dictionary parsed from LLM JSON response

        Returns:
            List of parsed LLMSpanSegment objects
        """
        segments_data = response_dict.get("segments", [])
        segments: list[LLMSpanSegment] = []

        for item in segments_data:
            segment_text_exact = item.get("segment_text_exact")
            segmentation_kind = item.get("segmentation_kind")

            if not segment_text_exact or not segmentation_kind:
                continue

            # Ensure packet ids is a tuple
            source_packet_ids = item.get("source_packet_ids") or item.get("parent_packet_ids") or ()
            if isinstance(source_packet_ids, list):
                source_packet_ids = tuple(source_packet_ids)
            elif isinstance(source_packet_ids, str):
                source_packet_ids = (source_packet_ids,)
            else:
                source_packet_ids = tuple(source_packet_ids)

            segments.append(
                LLMSpanSegment(
                    segment_text_exact=str(segment_text_exact),
                    segmentation_kind=segmentation_kind,
                    guard_text_exact=item.get("guard_text_exact"),
                    action_text_exact=item.get("action_text_exact"),
                    source_packet_ids=source_packet_ids,
                    source_section_id=item.get("source_section_id"),
                    char_start=item.get("char_start"),
                    char_end=item.get("char_end"),
                    boundary_confidence=item.get("boundary_confidence", "medium"),
                    continuation_repaired=bool(item.get("continuation_repaired", False)),
                )
            )

        return segments
