"""Unit tests for Stage 1 Segmentation Config."""

from __future__ import annotations

from nl2spl.pipeline.stages.stage1_segmentation.config import Stage1SegmentationConfig


def test_stage1_segmentation_config_defaults() -> None:
    config = Stage1SegmentationConfig()
    assert config.mode == "legacy_packet_passthrough"
    assert config.max_retries == 2
    assert config.require_full_coverage is True
    assert config.emit_sidecar is True
    assert config.require_validator_pass is True
    assert config.fail_closed_on_invalid_llm_output is True
