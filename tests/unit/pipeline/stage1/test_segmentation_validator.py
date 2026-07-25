"""Unit tests for Stage 1 Segmentation Validator."""

from __future__ import annotations

from nl2spl.canonical import CanonicalCompileInput, SemanticPacket
from nl2spl.pipeline.stages.stage1_segmentation import (
    LLMSpanSegment,
    Stage1SegmentationValidator,
)
from nl2spl.pipeline.stages.stage1_segmentation.diagnostics import (
    COVERAGE_GAP,
    GUARD_ACTION_NOT_SUBSTRING,
    GUARDED_ACTION_MISSING_ELEMENTS,
)
from nl2spl.pipeline.stages.stage1_segmentation.source_buffer import SourceSectionReconstructor


def _prepare_buffers():
    packet1 = SemanticPacket(
        packet_id="p1",
        source_section_id="reusable_process",
        packet_type="process_step",
        text="When enough required information is available",
        modality="hard_fact",
    )
    packet2 = SemanticPacket(
        packet_id="p2",
        source_section_id="reusable_process",
        packet_type="process_step",
        text="produce a draft.",
        modality="hard_fact",
    )
    canonical_input = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0.0",
        raw_text="raw text",
        semantic_packets=[packet1, packet2],
    )
    reconstructor = SourceSectionReconstructor()
    return reconstructor.reconstruct(canonical_input)

def test_validator_accepts_valid_proposals() -> None:
    source_buffers = _prepare_buffers()
    validator = Stage1SegmentationValidator()

    # Valid guarded_action proposal (no comma, matches normalized source exactly)
    proposals = [
        LLMSpanSegment(
            segment_text_exact="When enough required information is available produce a draft.",
            segmentation_kind="guarded_action",
            guard_text_exact="enough required information is available",
            action_text_exact="produce a draft",
            source_packet_ids=("p1", "p2"),
            source_section_id="reusable_process",
        )
    ]

    records, diagnostics, warnings = validator.validate(proposals, source_buffers)
    assert len(diagnostics) == 0
    assert len(records) == 1
    assert records[0].span_text == "When enough required information is available produce a draft."
    assert records[0].validation_status == "validated"

def test_validator_rejects_paraphrase() -> None:
    source_buffers = _prepare_buffers()
    validator = Stage1SegmentationValidator()

    # Paraphrased proposal (changed "produce" to "create")
    proposals = [
        LLMSpanSegment(
            segment_text_exact="When enough required information is available produce a draft.",
            segmentation_kind="guarded_action",
            guard_text_exact="enough required information is available",
            action_text_exact="create a draft",  # Action is not a substring
            source_packet_ids=("p1", "p2"),
            source_section_id="reusable_process",
        )
    ]

    records, diagnostics, warnings = validator.validate(proposals, source_buffers)
    assert len(records) == 0
    assert len(diagnostics) == 1
    assert diagnostics[0].kind == GUARD_ACTION_NOT_SUBSTRING

def test_validator_rejects_coverage_gap() -> None:
    source_buffers = _prepare_buffers()
    validator = Stage1SegmentationValidator()

    # Proposal covers only packet 1, leaving packet 2 uncovered
    proposals = [
        LLMSpanSegment(
            segment_text_exact="When enough required information is available",
            segmentation_kind="atomic_action_candidate",
            source_packet_ids=("p1",),
            source_section_id="reusable_process",
        )
    ]

    records, diagnostics, warnings = validator.validate(proposals, source_buffers)
    assert len(records) == 0
    assert len(diagnostics) == 1
    assert diagnostics[0].kind == COVERAGE_GAP

def test_validator_rejects_missing_guard_action_elements() -> None:
    source_buffers = _prepare_buffers()
    validator = Stage1SegmentationValidator()

    # Missing guard_text_exact for guarded_action kind
    proposals = [
        LLMSpanSegment(
            segment_text_exact="When enough required information is available produce a draft.",
            segmentation_kind="guarded_action",
            guard_text_exact=None,
            action_text_exact="produce a draft",
            source_packet_ids=("p1", "p2"),
            source_section_id="reusable_process",
        )
    ]

    records, diagnostics, warnings = validator.validate(proposals, source_buffers)
    assert len(records) == 0
    assert len(diagnostics) == 1
    assert diagnostics[0].kind == GUARDED_ACTION_MISSING_ELEMENTS
