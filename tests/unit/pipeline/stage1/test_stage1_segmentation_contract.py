"""Unit tests checking the segmenter and configuration contract for Stage 1."""

from __future__ import annotations

from unittest.mock import MagicMock

from nl2spl.canonical import CanonicalCompileInput, SemanticPacket
from nl2spl.config import PipelineConfig, Stage1SegmentationConfig
from nl2spl.pipeline.stages.stage1_segmentation import (
    LLMSourceConstrainedSegmenter,
    SourceSectionReconstructor,
)
from nl2spl.pipeline.stages.stage1_segmentation.diagnostics import PARAPHRASE_REJECTED
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer


def test_llm_segmenter_sends_correct_prompts_and_parses_response() -> None:
    # 1. Setup mock client
    mock_client = MagicMock()
    mock_client.call_json.return_value = {
        "segments": [
            {
                "segment_text_exact": (
                    "When enough required information is available produce a draft."
                ),
                "segmentation_kind": "guarded_action",
                "guard_text_exact": "enough required information is available",
                "action_text_exact": "produce a draft",
                "source_packet_ids": ["p16", "p17"],
                "source_section_id": "reusable_process",
                "boundary_confidence": "high",
                "continuation_repaired": True,
            }
        ]
    }

    # 2. Setup inputs
    packet1 = SemanticPacket(
        packet_id="p16",
        source_section_id="reusable_process",
        packet_type="process_step",
        text="When enough required information is available",
        modality="hard_fact",
    )
    packet2 = SemanticPacket(
        packet_id="p17",
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

    # 3. Run segmenter
    reconstructor = SourceSectionReconstructor()
    source_buffers = reconstructor.reconstruct(canonical_input)

    segmenter = LLMSourceConstrainedSegmenter(mock_client)
    proposals = segmenter.segment(canonical_input, source_buffers)

    # 4. Verify results and client calls
    assert len(proposals) == 1
    p0 = proposals[0]
    assert (
        p0.segment_text_exact
        == "When enough required information is available produce a draft."
    )
    assert p0.segmentation_kind == "guarded_action"
    assert p0.guard_text_exact == "enough required information is available"
    assert p0.action_text_exact == "produce a draft"
    assert p0.source_packet_ids == ("p16", "p17")
    assert p0.source_section_id == "reusable_process"
    assert p0.continuation_repaired is True

    # Check LLM client was called once for the section
    mock_client.call_json.assert_called_once()
    kwargs = mock_client.call_json.call_args.kwargs
    assert kwargs["stage_name"] == "stage1_source_constrained"
    assert "reusable_process" in kwargs["user_prompt"]


def test_active_segmentation_rejects_invalid_llm_output_and_falls_back() -> None:
    mock_client = MagicMock()
    mock_client.call_json.return_value = {
        "segments": [
            {
                "segment_text_exact": "Create a final draft.",
                "segmentation_kind": "atomic_action_candidate",
                "guard_text_exact": None,
                "action_text_exact": None,
                "source_packet_ids": ["p16"],
                "source_section_id": "reusable_process",
                "boundary_confidence": "high",
                "continuation_repaired": False,
            }
        ]
    }
    config = PipelineConfig(
        stage1=Stage1SegmentationConfig(mode="llm_source_constrained")
    )
    canonical_input = CanonicalCompileInput(
        source_schema="structural_nl",
        schema_version="1.0.0",
        raw_text="When enough required information is available",
        semantic_packets=[
            SemanticPacket(
                packet_id="p16",
                source_section_id="reusable_process",
                packet_type="process_step",
                text="When enough required information is available",
                modality="hard_fact",
            )
        ],
    )

    slicer = SpanSlicer(config, mock_client)
    spans = slicer.execute(canonical_input)

    assert [span.text for span in spans] == [
        "When enough required information is available"
    ]
    assert [record.to_dict() for record in slicer.validated_records] == []
    assert any(
        diagnostic.kind == PARAPHRASE_REJECTED
        for diagnostic in slicer.stage1_segmentation_diagnostics
    )
