"""Deterministic validator for Stage 1 Span Segmentation proposals."""

from __future__ import annotations

import re
from typing import Literal

from nl2spl.ir.diagnostics import CompileDiagnostic
from nl2spl.pipeline.stages.stage1_segmentation.diagnostics import (
    COVERAGE_GAP,
    FABRICATED_PACKET_IDS,
    GUARD_ACTION_NOT_SUBSTRING,
    GUARDED_ACTION_MISSING_ELEMENTS,
    INVALID_KIND,
    PARAPHRASE_REJECTED,
    make_diagnostic,
)
from nl2spl.pipeline.stages.stage1_segmentation.segmentation_payload import (
    LLMSpanSegment,
    SpanSegmentationRecord,
)
from nl2spl.pipeline.stages.stage1_segmentation.source_buffer import SectionSourceBuffer


class Stage1SegmentationValidator:
    """Validator serving as the P0 correctness authority for Stage 1 LLM segmentation."""

    VALID_KINDS = {
        "atomic_text_unit",
        "atomic_action_candidate",
        "guarded_action",
        "continuation_repaired",
        "ambiguous_boundary",
    }

    @staticmethod
    def _match_with_whitespace_drift(source_text: str, segment_text: str, start_idx: int) -> tuple[int, int] | None:
        """Find the next occurrence of segment_text in source_text starting from start_idx, with whitespace tolerance."""
        norm_seg = " ".join(segment_text.split())
        words = [re.escape(w) for w in norm_seg.split() if w]
        if not words:
            return None
        pattern = r'\s*'.join(words)
        match = re.search(pattern, source_text[start_idx:])
        if match:
            char_start = start_idx + match.start()
            char_end = start_idx + match.end()
            return char_start, char_end
        return None

    def validate(
        self,
        proposals: list[LLMSpanSegment],
        source_buffers: dict[str, SectionSourceBuffer],
    ) -> tuple[list[SpanSegmentationRecord], list[CompileDiagnostic], list[str]]:
        """Validate proposed segments against the authoritative source buffers.

        Args:
            proposals: List of proposed segments from LLM
            source_buffers: Reconstructed source buffers by section ID

        Returns:
            Tuple of:
              - list of validated SpanSegmentationRecord objects
              - list of CompileDiagnostic objects (errors)
              - list of warning strings
        """
        validated_records: list[SpanSegmentationRecord] = []
        diagnostics: list[CompileDiagnostic] = []
        warnings: list[str] = []

        # Group proposals by section
        proposals_by_section: dict[str, list[LLMSpanSegment]] = {}
        for prop in proposals:
            sec_id = prop.source_section_id or "unknown"
            proposals_by_section.setdefault(sec_id, []).append(prop)

        span_counter = 1

        for section_id, sec_proposals in proposals_by_section.items():
            buffer = source_buffers.get(section_id)
            if not buffer:
                # No source buffer for this section
                msg = f"No source buffer found for section '{section_id}'."
                diagnostics.append(make_diagnostic("stage1_segmentation_missing_buffer", msg, section_id))
                continue

            normalized_text = buffer.normalized_text
            current_search_index = 0
            section_records: list[SpanSegmentationRecord] = []
            section_failed = False

            for prop in sec_proposals:
                # 1. Validate kind
                if prop.segmentation_kind not in self.VALID_KINDS:
                    msg = f"Invalid segmentation kind '{prop.segmentation_kind}'."
                    diagnostics.append(make_diagnostic(INVALID_KIND, msg, section_id))
                    section_failed = True
                    break

                # 2. String matching with whitespace drift tolerance (reject paraphrase)
                match = self._match_with_whitespace_drift(normalized_text, prop.segment_text_exact, current_search_index)
                if not match:
                    # Not found sequentially
                    msg = f"Paraphrase or out-of-order text detected: '{prop.segment_text_exact[:50]}...'"
                    diagnostics.append(make_diagnostic(PARAPHRASE_REJECTED, msg, section_id))
                    section_failed = True
                    break

                char_start, char_end = match
                current_search_index = char_end
                matched_span_text = normalized_text[char_start:char_end]

                # 3. Guard/Action element validation
                if prop.segmentation_kind in ("guarded_action", "continuation_repaired"):
                    if not prop.guard_text_exact or not prop.action_text_exact:
                        msg = f"guarded_action segment is missing guard_text_exact or action_text_exact: '{prop.segment_text_exact[:50]}...'"
                        diagnostics.append(make_diagnostic(GUARDED_ACTION_MISSING_ELEMENTS, msg, section_id))
                        section_failed = True
                        break

                    # Check that guard and action exist in segment_text_exact (with whitespace tolerance)
                    norm_guard = " ".join(prop.guard_text_exact.split())
                    norm_action = " ".join(prop.action_text_exact.split())
                    norm_seg = " ".join(prop.segment_text_exact.split())
                    if norm_guard not in norm_seg or norm_action not in norm_seg:
                        msg = f"Guard or action text is not a substring of segment text: '{prop.segment_text_exact[:50]}...'"
                        diagnostics.append(make_diagnostic(GUARD_ACTION_NOT_SUBSTRING, msg, section_id))
                        section_failed = True
                        break

                # 4. Provenance verification (authoritative recomputation & mismatch policy)
                authoritative_packet_ids = buffer.get_parent_packet_ids(char_start, char_end)
                llm_packet_ids = prop.source_packet_ids

                # Compare
                auth_set = set(authoritative_packet_ids)
                llm_set = set(llm_packet_ids)

                validation_status: Literal[
                    "validated",
                    "repaired_by_validator",
                    "ambiguous",
                ] = "validated"

                if not auth_set:
                    # Recomputation failed
                    msg = f"No authoritative packets cover the range [{char_start}, {char_end}]."
                    diagnostics.append(make_diagnostic(FABRICATED_PACKET_IDS, msg, section_id))
                    section_failed = True
                    break
                elif not llm_set.intersection(auth_set):
                    # Completely disjoint! Fabricated. Reject.
                    msg = f"Fabricated or disjoint packet IDs: LLM declared {list(llm_set)}, authoritative is {list(auth_set)}."
                    diagnostics.append(make_diagnostic(FABRICATED_PACKET_IDS, msg, section_id))
                    section_failed = True
                    break
                elif llm_set != auth_set:
                    # Mismatch but overlaps. Repair to authoritative ones.
                    validation_status = "repaired_by_validator"

                # 5. Create record
                record = SpanSegmentationRecord(
                    span_id=f"s{span_counter}",
                    segmentation_kind=prop.segmentation_kind,
                    span_text=matched_span_text,
                    guard_text_exact=prop.guard_text_exact,
                    action_text_exact=prop.action_text_exact,
                    parent_packet_ids=authoritative_packet_ids,
                    source_section_id=section_id,
                    char_start=char_start,
                    char_end=char_end,
                    boundary_confidence=prop.boundary_confidence,
                    continuation_repaired=prop.continuation_repaired,
                    validation_status=validation_status,
                )
                section_records.append(record)
                span_counter += 1

            if section_failed:
                continue

            # 6. Check full coverage of substantive source text
            last_end = 0
            for record in section_records:
                gap_text = normalized_text[last_end:record.char_start]
                if any(c.isalnum() for c in gap_text):
                    msg = f"Coverage gap detected in section '{section_id}' before span {record.span_id}: '{gap_text[:30]}'."
                    diagnostics.append(make_diagnostic(COVERAGE_GAP, msg, section_id))
                    section_failed = True
                    break
                last_end = record.char_end

            if not section_failed:
                tail_gap = normalized_text[last_end:]
                if any(c.isalnum() for c in tail_gap):
                    msg = f"Coverage gap detected at the end of section '{section_id}': '{tail_gap[:30]}'."
                    diagnostics.append(make_diagnostic(COVERAGE_GAP, msg, section_id))
                    section_failed = True

            if not section_failed:
                validated_records.extend(section_records)

        return validated_records, diagnostics, warnings
