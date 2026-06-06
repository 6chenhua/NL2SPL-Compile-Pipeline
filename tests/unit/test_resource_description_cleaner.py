"""Tests for Stage 6 resource description normalization."""

from __future__ import annotations

from nl2spl.pipeline.stages.stage6_resource_extractor.description_cleaner import (
    clean_resource_description,
)


def test_clean_resource_description_keeps_ascii_description() -> None:
    assert (
        clean_resource_description("allowed_evidence", "Allowed evidence from approved sources")
        == "Allowed evidence from approved sources"
    )


def test_clean_resource_description_replaces_non_ascii_description() -> None:
    assert clean_resource_description("clarifying_questions", "针对缺失输入提出的澄清问题") == (
        "Clarifying questions"
    )
