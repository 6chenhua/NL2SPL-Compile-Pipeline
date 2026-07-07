"""Unit tests for Stage 1 Segmentation Validator parent packet ID validation and repair."""

from __future__ import annotations

from nl2spl.canonical import CanonicalCompileInput, SemanticPacket
from nl2spl.pipeline.stages.stage1_segmentation.source_buffer import SourceSectionReconstructor
from nl2spl.pipeline.stages.stage1_segmentation import (
    LLMSpanSegment,
    Stage1SegmentationValidator,
)
from nl2spl.pipeline.stages.stage1_segmentation.diagnostics import FABRICATED_PACKET_IDS

def _prepare_multi_packet_buffers():
    p1 = SemanticPacket(
        packet_id="p1",
        source_section_id="reusable_process",
        packet_type="process_step",
        text="First query the database.",
        modality="hard_fact",
    )
    p2 = SemanticPacket(
        packet_id="p2",
        source_section_id="reusable_process",
        packet_type="process_step",
        text="Then check permission.",
        modality="hard_fact",
    )
    p3 = SemanticPacket(
        packet_id="p3",
        source_section_id="reusable_process",
        packet_type="process_step",
        text="Finally query DB.",
        modality="hard_fact",
    )
    canonical_input = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0.0",
        raw_text="raw text",
        semantic_packets=[p1, p2, p3],
    )
    reconstructor = SourceSectionReconstructor()
    return reconstructor.reconstruct(canonical_input)

def test_validator_repairs_omitted_adjacent_packet_ids() -> None:
    source_buffers = _prepare_multi_packet_buffers()
    validator = Stage1SegmentationValidator()

    # Proposal merges all 3 packets but only lists p1 and p3, omitting p2
    proposals = [
        LLMSpanSegment(
            segment_text_exact="First query the database. Then check permission. Finally query DB.",
            segmentation_kind="atomic_action_candidate",
            source_packet_ids=("p1", "p3"),
            source_section_id="reusable_process",
        )
    ]

    records, diagnostics, warnings = validator.validate(proposals, source_buffers)
    assert len(diagnostics) == 0
    assert len(records) == 1
    # Authoritative recomputation should repair and include p2
    assert records[0].parent_packet_ids == ("p1", "p2", "p3")
    assert records[0].validation_status == "repaired_by_validator"

def test_validator_rejects_disjoint_fabricated_packet_ids() -> None:
    source_buffers = _prepare_multi_packet_buffers()
    validator = Stage1SegmentationValidator()

    # Segment matches p1 but lists completely disjoint/fabricated p99
    proposals = [
        LLMSpanSegment(
            segment_text_exact="First query the database.",
            segmentation_kind="atomic_action_candidate",
            source_packet_ids=("p99",),
            source_section_id="reusable_process",
        ),
        # Must cover the rest of the text to avoid coverage gap rejection
        LLMSpanSegment(
            segment_text_exact="Then check permission. Finally query DB.",
            segmentation_kind="atomic_action_candidate",
            source_packet_ids=("p2", "p3"),
            source_section_id="reusable_process",
        )
    ]

    records, diagnostics, warnings = validator.validate(proposals, source_buffers)
    assert len(records) == 0
    assert len(diagnostics) == 1
    assert diagnostics[0].kind == FABRICATED_PACKET_IDS
