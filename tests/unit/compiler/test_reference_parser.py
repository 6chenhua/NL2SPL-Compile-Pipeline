from __future__ import annotations

import pytest

from nl2spl.compiler.reference_parser import (
    parse_description_reference_result,
    parse_description_references,
)


def test_parse_description_references_preserves_offsets_and_order() -> None:
    text = "When <REF>*x</REF> and <REF>a_b.y</REF> are ready"

    tokens = parse_description_references(text)

    assert [token.raw_text for token in tokens] == [
        "<REF>*x</REF>",
        "<REF>a_b.y</REF>",
    ]
    assert tokens[0].is_by_value is True
    assert tokens[0].name == "x"
    assert tokens[0].top_level_name == "x"
    assert tokens[1].qualified_path == ("a_b", "y")
    assert text[tokens[1].start_offset : tokens[1].end_offset] == tokens[1].raw_text


def test_parse_description_references_requires_explicit_ref_tokens() -> None:
    assert parse_description_references("when x is available") == ()


def test_invalid_qualified_reference_reports_diagnostic() -> None:
    result = parse_description_reference_result("When <REF>a.</REF> is ready")

    assert result.tokens == ()
    assert result.diagnostics[0].kind == "invalid_ref_name"


def test_parse_description_references_raises_on_invalid_token() -> None:
    with pytest.raises(ValueError):
        parse_description_references("<REF></REF>")
