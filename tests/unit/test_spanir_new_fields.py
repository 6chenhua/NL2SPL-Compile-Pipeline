"""Unit tests for new SpanIR fields: section_context and is_placeholder.

Covers:
- L3-F1: New fields default values (section_context=None, is_placeholder=False)
- L3-F5: to_dict() omits None/False fields
- L3-R2: Canonical path does not add new fields
- Backward compatibility with existing SpanIR usage
"""

from __future__ import annotations

from nl2spl.ir.span_ir import AmbiguityInfo, SpanIR


class TestSpanIRNewFields:
    """Tests for new SpanIR fields."""

    def test_spanir_default_section_context_is_none(self) -> None:
        """L3-F1-a: section_context defaults to None."""
        span = SpanIR(span_id="s1", text="hello world")
        assert span.section_context is None

    def test_spanir_default_is_placeholder_is_false(self) -> None:
        """L3-F1-b: is_placeholder defaults to False."""
        span = SpanIR(span_id="s1", text="hello world")
        assert span.is_placeholder is False

    def test_spanir_accepts_section_context(self) -> None:
        """SpanIR accepts section_context parameter."""
        span = SpanIR(
            span_id="s1",
            text="Draft message",
            section_context="Required Outputs",
        )
        assert span.section_context == "Required Outputs"

    def test_spanir_accepts_is_placeholder_true(self) -> None:
        """SpanIR accepts is_placeholder=True."""
        span = SpanIR(
            span_id="s1",
            text="None",
            is_placeholder=True,
        )
        assert span.is_placeholder is True

    def test_to_dict_omits_section_context_when_none(self) -> None:
        """L3-F5-a: to_dict() does not include section_context when None."""
        span = SpanIR(span_id="s1", text="hello")
        d = span.to_dict()
        assert "section_context" not in d

    def test_to_dict_includes_section_context_when_set(self) -> None:
        """L3-F5-b: to_dict() includes section_context when set."""
        span = SpanIR(span_id="s1", text="hello", section_context="Policies")
        d = span.to_dict()
        assert "section_context" in d
        assert d["section_context"] == "Policies"

    def test_to_dict_omits_is_placeholder_when_false(self) -> None:
        """L3-F5-c: to_dict() does not include is_placeholder when False."""
        span = SpanIR(span_id="s1", text="hello")
        d = span.to_dict()
        assert "is_placeholder" not in d

    def test_to_dict_includes_is_placeholder_when_true(self) -> None:
        """L3-F5-d: to_dict() includes is_placeholder when True."""
        span = SpanIR(span_id="s1", text="None", is_placeholder=True)
        d = span.to_dict()
        assert "is_placeholder" in d
        assert d["is_placeholder"] is True

    def test_to_dict_backward_compatible_fields(self) -> None:
        """L3-R2: Existing fields remain unchanged by new additions."""
        span = SpanIR(
            span_id="s5",
            text="Some content",
            ambiguity=AmbiguityInfo(is_ambiguous=True, reasons=["test"]),
            source_section_id="sec_policies",
            source_packet_id="pkt_001",
        )
        d = span.to_dict()
        assert d["span_id"] == "s5"
        assert d["text"] == "Some content"
        assert d["source_section_id"] == "sec_policies"
        assert d["source_packet_id"] == "pkt_001"
        assert d["ambiguity"]["is_ambiguous"] is True
        # New fields should not appear when not set
        assert "section_context" not in d
        assert "is_placeholder" not in d

    def test_span_id_empty_allowed_for_prep_phase(self) -> None:
        """Phase 2.1: Empty span_id allowed as pre-slicing placeholder."""
        span = SpanIR(span_id="", text="hello")
        assert span.span_id == ""

    def test_span_id_must_start_with_s_when_nonempty(self) -> None:
        """Non-empty span_id must start with 's'."""
        import pytest
        with pytest.raises(ValueError, match="span_id must start with"):
            SpanIR(span_id="x1", text="hello")
