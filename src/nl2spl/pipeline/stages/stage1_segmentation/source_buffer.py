"""Source reconstruction and offset mapping for Stage 1."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from nl2spl.canonical import CanonicalCompileInput, SemanticPacket

@dataclass(frozen=True)
class SourcePacketRange:
    """Character range of a packet within the normalized section text."""
    packet_id: str
    source_section_id: str
    normalized_char_start: int
    normalized_char_end: int
    original_char_start: int | None = None
    original_char_end: int | None = None

@dataclass(frozen=True)
class SourceNormalizationMap:
    """Map normalized offsets back to original packet boundaries."""
    # Placeholders or simple mapping can be extended later if needed.
    pass

@dataclass(frozen=True)
class SectionSourceBuffer:
    """Reconstructed, normalized source text for a single section."""
    source_section_id: str
    normalized_text: str
    packet_ranges: tuple[SourcePacketRange, ...]
    normalization_map: SourceNormalizationMap = field(default_factory=SourceNormalizationMap)

    def get_parent_packet_ids(self, start: int, end: int) -> tuple[str, ...]:
        """Find all parent packet IDs that contribute to the given range in normalized_text."""
        parent_ids: list[str] = []
        for pr in self.packet_ranges:
            # Check overlap between [start, end] and [pr.normalized_char_start, pr.normalized_char_end]
            if max(start, pr.normalized_char_start) < min(end, pr.normalized_char_end):
                parent_ids.append(pr.packet_id)
        # If no strict overlap (e.g. empty match or boundary), fallback to point containment
        if not parent_ids:
            for pr in self.packet_ranges:
                if pr.normalized_char_start <= start <= pr.normalized_char_end:
                    parent_ids.append(pr.packet_id)
        return tuple(parent_ids)

class SourceSectionReconstructor:
    """Reconstructs SectionSourceBuffer from canonical input semantic packets."""

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize line breaks and multiple spaces."""
        # Replace newlines/carriage returns with space
        text = text.replace("\r\n", " ").replace("\n", " ")
        # Reduce multiple spaces to single space
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    def reconstruct(self, canonical_input: CanonicalCompileInput) -> dict[str, SectionSourceBuffer]:
        """Group semantic packets by section and reconstruct source buffers."""
        packets_by_section: dict[str, list[SemanticPacket]] = {}
        for pkt in canonical_input.semantic_packets:
            packets_by_section.setdefault(pkt.source_section_id, []).append(pkt)

        buffers: dict[str, SectionSourceBuffer] = {}
        for section_id, pkts in packets_by_section.items():
            normalized_texts: list[str] = []
            ranges: list[SourcePacketRange] = []
            current_offset = 0

            for pkt in pkts:
                norm_text = self._normalize_text(pkt.text)
                if not norm_text:
                    continue

                if normalized_texts:
                    # Add a space between packets
                    normalized_texts.append(" ")
                    current_offset += 1

                start = current_offset
                end = start + len(norm_text)
                normalized_texts.append(norm_text)
                current_offset = end

                ranges.append(
                    SourcePacketRange(
                        packet_id=pkt.packet_id,
                        source_section_id=section_id,
                        normalized_char_start=start,
                        normalized_char_end=end,
                    )
                )

            buffers[section_id] = SectionSourceBuffer(
                source_section_id=section_id,
                normalized_text="".join(normalized_texts),
                packet_ranges=tuple(ranges),
            )

        return buffers
