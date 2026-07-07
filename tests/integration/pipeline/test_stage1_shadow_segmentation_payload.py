"""Integration tests for Stage 1 Shadow Mode sidecar materialization and report generation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from nl2spl.config import LLMConfig, PipelineConfig, Stage1SegmentationConfig
from nl2spl.canonical import CanonicalCompileInput, SemanticPacket
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer

def test_stage1_shadow_mode_observability_and_checkpointing(tmp_path: Path) -> None:
    # 1. Setup config in shadow mode
    config = PipelineConfig(
        llm=LLMConfig(
            model="gpt-4o",
            max_tokens=4096,
            temperature=0.0,
            api_key="test-api-key",
        ),
        output_dir=tmp_path / "output",
        save_intermediate=True,
        log_level="DEBUG",
        max_retries=1,
    )
    # Enable shadow mode
    config.stage1 = Stage1SegmentationConfig(mode="llm_source_constrained_shadow")

    # 2. Setup inputs matching internal_comms process packets
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
        raw_text="dummy raw text",
        semantic_packets=[packet1, packet2],
    )

    # 3. Setup mock client to return valid segmentation proposal (repairing p16/p17 split)
    mock_client = MagicMock()
    mock_client.call_json.return_value = {
        "segments": [
            {
                "segment_text_exact": "When enough required information is available produce a draft.",
                "segmentation_kind": "guarded_action",
                "guard_text_exact": "enough required information is available",
                "action_text_exact": "produce a draft",
                "source_packet_ids": ["p16", "p17"],
                "source_section_id": "reusable_process",
                "boundary_confidence": "high",
                "continuation_repaired": True
            }
        ]
    }

    slicer = SpanSlicer(config, mock_client)
    spans = slicer.execute(canonical_input)

    # 4. Verify that legacy output was returned and NOT modified by shadow run
    assert len(spans) == 2
    assert spans[0].text == "When enough required information is available"
    assert spans[1].text == "produce a draft."

    # 5. Read the generated stage1 checkpoint file to verify shadow keys
    checkpoint_dir = config.run_dir
    checkpoint_file = checkpoint_dir / "stage1_span_slicer.json"
    assert checkpoint_file.exists(), "Checkpoint file must be persisted"

    checkpoint_data = json.loads(checkpoint_file.read_text(encoding="utf-8"))
    result_data = checkpoint_data.get("result", {})
    
    assert "stage1_shadow_segmentation_records" in result_data
    assert "stage1_shadow_segmentation_payload" in result_data
    assert "stage1_shadow_segmentation_report" in result_data
    assert "stage1_shadow_source_buffers" in result_data

    # 6. Verify shadow report details
    report = result_data["stage1_shadow_segmentation_report"]
    assert report["legacy_span_count"] == 2
    assert report["shadow_span_count"] == 1
    assert report["validator_failure_count"] == 0
    assert report["fallback_count"] == 0
    assert report["internal_comms_guarded_action_match"] is True
