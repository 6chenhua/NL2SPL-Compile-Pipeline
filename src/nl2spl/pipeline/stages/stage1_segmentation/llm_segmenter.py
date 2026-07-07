"""LLM segmenter for Stage 1 Span Segmentation."""

from __future__ import annotations

from typing import Any

from nl2spl.canonical import CanonicalCompileInput
from nl2spl.llm.client import LLMClient
from nl2spl.llm.prompts import load_prompt
from nl2spl.pipeline.stages.stage1_segmentation.llm_segment_parser import (
    LLMSegmentParser,
)
from nl2spl.pipeline.stages.stage1_segmentation.segmentation_payload import (
    LLMSpanSegment,
)
from nl2spl.pipeline.stages.stage1_segmentation.source_buffer import (
    SectionSourceBuffer,
    SourceSectionReconstructor,
)


class LLMSourceConstrainedSegmenter:
    """Invokes LLM to propose semantic span segmentations for each section."""

    def __init__(self, client: LLMClient) -> None:
        """Initialize segmenter.

        Args:
            client: LLM client for invoking LLM APIs
        """
        self.client = client
        self.reconstructor = SourceSectionReconstructor()

    def segment(
        self,
        canonical_input: CanonicalCompileInput,
        source_buffers: dict[str, SectionSourceBuffer],
        validation_feedback: str | None = None,
    ) -> list[LLMSpanSegment]:
        """Run LLM span segmentation on the canonical input.

        Args:
            canonical_input: The canonical input to segment
            source_buffers: Reconstructed source buffers for each section

        Returns:
            List of proposed LLMSpanSegment objects
        """
        all_proposals: list[LLMSpanSegment] = []
        system_prompt = load_prompt("stage1_source_constrained")
        user_template = load_prompt("stage1_source_constrained_user")

        # Group packets by section to format the prompt
        packets_by_section: dict[str, list[Any]] = {}
        for pkt in canonical_input.semantic_packets:
            packets_by_section.setdefault(pkt.source_section_id, []).append(pkt)

        for section_id, pkts in packets_by_section.items():
            if not pkts:
                continue

            # Format the packets for the user prompt
            packets_text = "\n".join(f"[{pkt.packet_id}] {pkt.text}" for pkt in pkts)
            user_prompt = (
                user_template
                .replace("{section_id}", section_id)
                .replace("{packets}", packets_text)
            )
            if validation_feedback:
                user_prompt += (
                    "\n\nPrevious output was rejected by the deterministic "
                    "validator. Correct the segmentation and return JSON only.\n"
                    f"Validator feedback:\n{validation_feedback}\n"
                    "Reminder: copy exact source substrings, including commas "
                    "and punctuation. Do not paraphrase."
                )

            # Call LLM
            response_dict = self.client.call_json(
                stage_name="stage1_source_constrained",
                system_prompt=system_prompt,
                user_prompt=user_prompt,
            )

            # Parse proposals
            proposals = LLMSegmentParser.parse(response_dict)

            # Populate section ID if missing from LLM response
            refined_proposals = []
            for prop in proposals:
                # Set source_section_id to the authoritative section we queried
                refined_prop = LLMSpanSegment(
                    segment_text_exact=prop.segment_text_exact,
                    segmentation_kind=prop.segmentation_kind,
                    guard_text_exact=prop.guard_text_exact,
                    action_text_exact=prop.action_text_exact,
                    source_packet_ids=prop.source_packet_ids,
                    source_section_id=section_id,  # force correct section
                    char_start=prop.char_start,
                    char_end=prop.char_end,
                    boundary_confidence=prop.boundary_confidence,
                    continuation_repaired=prop.continuation_repaired,
                )
                refined_proposals.append(refined_prop)

            all_proposals.extend(refined_proposals)

        return all_proposals
