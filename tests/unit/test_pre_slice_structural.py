"""Unit tests for Phase 2: deterministic pre-slicing (_pre_slice_structural)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from nl2spl.ir.span_ir import SpanIR
from nl2spl.pipeline.stages.stage1_span_slicer import SpanSlicer


class TestPreSliceStructural:
    """Tests for _pre_slice_structural() method."""

    # =========================================================================
    # L2-F1: Header/Bullet/Ordered pattern recognition (≥3 test cases each)
    # =========================================================================

    # ---- test_header_stripping ----

    def test_header_stripping_level1_exact_match_organizational(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-a: Level-1 whitelist organizational headers produce no span."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "## Task Family\n- Newsletter\n- Announcement"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        # "Task Family" is organizational → no span for it
        header_spans = [s for s in pre_slices if s.text == "Task Family"]
        assert len(header_spans) == 0
        # But the bullet items should be captured
        bulletin_spans = [s for s in pre_slices if s.text in ("Newsletter", "Announcement")]
        assert len(bulletin_spans) == 2

    def test_header_stripping_level2_keyword_match(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-b: Level-2 keyword pattern match strips organizational header."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "## Inputs\n- Topic\n- Audience"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        # "Inputs" matches keyword pattern → no span
        header_spans = [s for s in pre_slices if s.text == "Inputs"]
        assert len(header_spans) == 0
        # Bullet items should still be captured
        assert len([s for s in pre_slices if s.text in ("Topic", "Audience")]) == 2

    def test_header_stripping_semantic_header_kept(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-c: Non-organizational headers become spans."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "## Executive Summary\nThis is important."

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        # "Executive Summary" is semantic → should be a span
        header_spans = [s for s in pre_slices if s.text == "Executive Summary"]
        assert len(header_spans) == 1

    def test_header_stripping_multiple_levels(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-d: Different markdown header levels all handled."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "# Title\n## Policies\n### Subsection\n#### Detail"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        # "Title", "Subsection", "Detail" are semantic; "Policies" is organizational
        texts = [s.text for s in pre_slices]
        assert "Title" in texts
        assert "Subsection" in texts
        assert "Detail" in texts
        assert "Policies" not in texts

    # ---- test_bullet_slicing ----

    def test_bullet_slicing_dash_marker(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-e: Dash (-) bullet marker stripped."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "- Item A\n- Item B\n- Item C"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        texts = [s.text for s in pre_slices]
        assert texts == ["Item A", "Item B", "Item C"]

    def test_bullet_slicing_asterisk_marker(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-f: Asterisk (*) bullet marker stripped."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "* First\n* Second\n* Third"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        texts = [s.text for s in pre_slices]
        assert texts == ["First", "Second", "Third"]

    def test_bullet_slicing_plus_marker(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-g: Plus (+) bullet marker stripped."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "+ Alpha\n+ Beta\n+ Gamma"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        texts = [s.text for s in pre_slices]
        assert texts == ["Alpha", "Beta", "Gamma"]

    def test_bullet_slicing_empty_item(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-h: Empty bullet item handled gracefully."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "- \n- Real Item"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        texts = [s.text for s in pre_slices]
        assert "Real Item" in texts

    # ---- test_ordered_slicing ----

    def test_ordered_slicing_basic(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-i: Ordered list number prefix stripped."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "1. First step\n2. Second step\n3. Third step"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        texts = [s.text for s in pre_slices]
        assert texts == ["First step", "Second step", "Third step"]

    def test_ordered_slicing_double_digits(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-j: Double-digit numbers in ordered list handled."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "10. Step ten\n11. Step eleven"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        texts = [s.text for s in pre_slices]
        assert "Step ten" in texts
        assert "Step eleven" in texts

    def test_ordered_slicing_with_punctuation(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F1-k: Ordered items with internal punctuation preserved."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "1. Review the document, then sign it.\n2. Send confirmation."

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        texts = [s.text for s in pre_slices]
        assert "Review the document, then sign it." in texts
        assert "Send confirmation." in texts

    # =========================================================================
    # L2-F2: Residual blocks retain [Section: ...] prefix
    # =========================================================================

    def test_residual_blocks_have_section_prefix(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F2: Residual blocks are prefixed with section context."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "## Policies\nSome residual paragraph about policies."

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        # "Policies" is organizational → no span, but residual should reference it
        assert len(pre_slices) == 0
        assert len(residual) == 1
        assert residual[0].startswith("[Section: Policies]\n")
        assert "Some residual paragraph about policies." in residual[0]

    # =========================================================================
    # L2-F3: Multiline Label content goes to residual_blocks
    # =========================================================================

    def test_multiline_label_goes_to_residual(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F3: **Label:** with content on next line goes to residual."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "**Description:**\nThis is a long description\nthat spans multiple lines."

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        # Same-line label content extraction would be empty for multiline
        # The content lines should go to residual
        assert len(residual) >= 1
        # The residual block should contain the content (label line itself excluded)
        residual_text = "\n".join(residual)
        assert "This is a long description" in residual_text

    # =========================================================================
    # L2-F4: span_id renumbering produces continuous s1–sN
    # =========================================================================

    def test_span_id_renumbering(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F4: After pre-slicing, span_ids are empty; after execute(), continuous s1–sN."""
        mock_client.call_json.return_value = {
            "spans": [{"span_id": "x1", "text": "Residual span."}]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "- Pre-sliced item\n\nSome residual paragraph."

        spans = slicer.execute(raw_text)

        # Verify continuous numbering
        ids = [s.span_id for s in spans]
        expected = [f"s{i+1}" for i in range(len(spans))]
        assert ids == expected

    # =========================================================================
    # L2-F5: Coverage warning below 90%
    # =========================================================================

    def test_coverage_warning_below_90(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F5: Coverage 80-90% produces warning diagnostic."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        # 8 unique tokens in raw_text
        raw_text = "Alice Bob Charlie David Eve Frank Grace Henry"
        # Span covers 7 of 8 tokens (= 87.5% → warning)
        all_spans = [
            SpanIR(span_id="s1", text="Alice Bob Charlie David Eve Frank Grace"),
        ]

        diagnostics = slicer._validate_coverage(raw_text, all_spans)

        # Should produce exactly one warning diagnostic
        assert len(diagnostics) == 1
        assert diagnostics[0]["severity"] == "warning"
        assert 0.80 <= diagnostics[0]["coverage"] < 0.90

    # =========================================================================
    # L2-F7: Preprocess exception → fallback to full LLM path
    # =========================================================================

    def test_preprocess_exception_fallback(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F7: When _pre_slice_structural raises, falls back to full LLM."""
        mock_client.call_json.return_value = {
            "spans": [{"span_id": "s1", "text": "LLM fallback span."}]
        }
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "- Item\n\nSome text."

        # Mock _pre_slice_structural to raise
        original_method = slicer._pre_slice_structural
        slicer._pre_slice_structural = lambda x: (_ for _ in ()).throw(RuntimeError("Preprocess error"))

        try:
            spans = slicer.execute(raw_text)

            # Fallback to LLM should produce spans
            assert len(spans) >= 1
            assert spans[0].span_id == "s1"  # Continuous numbering from 1
        finally:
            slicer._pre_slice_structural = original_method

    # =========================================================================
    # L2-F8: _is_organizational two-level detection
    # =========================================================================

    def test_is_organizational_exact_match(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F8-a: Exact whitelist match returns True."""
        from nl2spl.pipeline.stages.stage1_span_slicer import _is_organizational

        assert _is_organizational("task family") is True
        assert _is_organizational("policies") is True
        assert _is_organizational("inputs for each run") is True

    def test_is_organizational_keyword_match(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F8-b: Keyword pattern match returns True."""
        from nl2spl.pipeline.stages.stage1_span_slicer import _is_organizational

        assert _is_organizational("inputs") is True
        assert _is_organizational("outputs") is True
        assert _is_organizational("process") is True
        assert _is_organizational("constraints") is True

    def test_is_organizational_non_match(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F8-c: Non-organizational title returns False."""
        from nl2spl.pipeline.stages.stage1_span_slicer import _is_organizational

        assert _is_organizational("Executive Summary") is False
        assert _is_organizational("Background") is False
        assert _is_organizational("Conclusion") is False

    # =========================================================================
    # L2-F9: LLM residual failure → skip block, compilation continues
    # =========================================================================

    def test_llm_residual_failure_skips_block(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F9: When LLM fails on one block, that block is skipped, others continue."""
        # First call fails, second succeeds
        mock_client.call_json.side_effect = [
            RuntimeError("LLM error"),
            {"spans": [{"span_id": "x1", "text": "Second block span."}]},
        ]
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "## Policies\nResidual paragraph one.\n\n## Process\nResidual paragraph two."

        spans = slicer.execute(raw_text)

        # Only the second block's span should appear
        texts = [s.text for s in spans]
        assert "Second block span." in texts
        # First block's content should not appear (it was skipped)

    # =========================================================================
    # L2-F10: Coverage error below 80%
    # =========================================================================

    def test_coverage_error_below_80(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-F10: Coverage < 80% produces error diagnostic."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        # Create text with many unique tokens
        raw_text = "Apple banana cherry date elderberry fig grape honeydew kiwi lemon mango nectarine orange papaya quince raspberry strawberry tangerine ugli vanilla watermelon xigua yellowfruit zucchini"
        # Spans that cover very few tokens
        all_spans = [
            SpanIR(span_id="s1", text="Apple"),
        ]

        diagnostics = slicer._validate_coverage(raw_text, all_spans)

        # Should produce exactly one error diagnostic
        assert len(diagnostics) == 1
        assert diagnostics[0]["severity"] == "error"
        assert diagnostics[0]["coverage"] < 0.80

    # =========================================================================
    # L2-R2: Canonical path unchanged (does not go through preprocessing)
    # =========================================================================

    def test_canonical_path_unchanged(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """L2-R2: When canonical_input is provided, _pre_slice_structural is NOT called."""
        from nl2spl.canonical.compile_input import CanonicalCompileInput

        slicer = SpanSlicer(pipeline_config, mock_client)

        canonical_input = CanonicalCompileInput(
            raw_text="Some raw text",
            source_schema="structural_nl",
            schema_version="1.0",
        )

        # Mock _pre_slice_structural to raise if called
        def should_not_be_called(text: str):
            raise AssertionError("_pre_slice_structural should NOT be called for canonical path")

        original_method = slicer._pre_slice_structural
        slicer._pre_slice_structural = should_not_be_called

        try:
            # This should NOT call _pre_slice_structural
            spans = slicer.execute(canonical_input)

            # Should produce spans via canonical path
            assert isinstance(spans, list)
        finally:
            slicer._pre_slice_structural = original_method


class TestPlaceholderDetection:
    """Tests for placeholder detection (is_placeholder field)."""

    def test_placeholder_none_lowercase(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Detect 'none' as a placeholder value."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "- none\n- Real Item"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        texts = {s.text: s for s in pre_slices}
        assert "none" in texts
        assert texts["none"].is_placeholder is True
        assert texts["Real Item"].is_placeholder is False

    def test_placeholder_na(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """Detect 'n/a' as a placeholder value."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "**Priority:** n/a"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        assert len(pre_slices) == 1
        assert pre_slices[0].text == "n/a"
        assert pre_slices[0].is_placeholder is True


class TestSectionContextTracking:
    """Tests for section_context field propagation."""

    def test_section_context_from_organizational_header(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """section_context is set from organizational header."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "## Policies\n- No external data\n- Cite all sources"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        assert len(pre_slices) == 2
        assert pre_slices[0].section_context == "Policies"
        assert pre_slices[1].section_context == "Policies"

    def test_section_context_updates_on_new_header(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """section_context updates when entering a new organizational section."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        # Use organizational headers (whitelist) so they set section_context
        raw_text = "## Policies\n- No external data\n\n## Delegation Policy\n- Drafting"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        # Two bullet items only (organizational headers NOT produced as spans)
        assert len(pre_slices) == 2
        # First item in "Policies" section
        assert pre_slices[0].text == "No external data"
        assert pre_slices[0].section_context == "Policies"
        # Second item in "Delegation Policy" section
        assert pre_slices[1].text == "Drafting"
        assert pre_slices[1].section_context == "Delegation Policy"

    def test_section_context_none_for_top_level(self, pipeline_config: MagicMock, mock_client: MagicMock) -> None:
        """section_context is None for top-level content."""
        slicer = SpanSlicer(pipeline_config, mock_client)
        raw_text = "- Top level item\n- Another item"

        pre_slices, residual = slicer._pre_slice_structural(raw_text)

        assert len(pre_slices) == 2
        assert pre_slices[0].section_context is None
        assert pre_slices[1].section_context is None
