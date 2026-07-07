"""Unit tests for Stage 1 LLM segment parser."""

from __future__ import annotations

from nl2spl.pipeline.stages.stage1_segmentation.llm_segment_parser import LLMSegmentParser

def test_llm_segment_parser_valid_json() -> None:
    response = {
        "segments": [
            {
                "segment_text_exact": "If X, do Y.",
                "segmentation_kind": "guarded_action",
                "guard_text_exact": "X",
                "action_text_exact": "do Y",
                "source_packet_ids": ["p1"],
                "source_section_id": "sec_process",
                "boundary_confidence": "high",
                "continuation_repaired": False
            },
            {
                "segment_text_exact": "Then do Z.",
                "segmentation_kind": "atomic_action_candidate",
                "guard_text_exact": None,
                "action_text_exact": None,
                "source_packet_ids": ["p2"],
                "source_section_id": "sec_process",
                "boundary_confidence": "medium",
                "continuation_repaired": False
            }
        ]
    }

    segments = LLMSegmentParser.parse(response)
    assert len(segments) == 2

    s1 = segments[0]
    assert s1.segment_text_exact == "If X, do Y."
    assert s1.segmentation_kind == "guarded_action"
    assert s1.guard_text_exact == "X"
    assert s1.action_text_exact == "do Y"
    assert s1.source_packet_ids == ("p1",)
    assert s1.boundary_confidence == "high"
    assert s1.continuation_repaired is False

    s2 = segments[1]
    assert s2.segment_text_exact == "Then do Z."
    assert s2.segmentation_kind == "atomic_action_candidate"
    assert s2.guard_text_exact is None
    assert s2.action_text_exact is None
    assert s2.source_packet_ids == ("p2",)
    assert s2.boundary_confidence == "medium"
    assert s2.continuation_repaired is False

def test_llm_segment_parser_missing_required_fields() -> None:
    response = {
        "segments": [
            {
                # missing segment_text_exact
                "segmentation_kind": "guarded_action",
                "source_packet_ids": ["p1"]
            },
            {
                "segment_text_exact": "Valid",
                # missing segmentation_kind
                "source_packet_ids": ["p2"]
            }
        ]
    }
    segments = LLMSegmentParser.parse(response)
    assert len(segments) == 0
