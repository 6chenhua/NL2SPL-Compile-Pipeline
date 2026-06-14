"""S1 source-layer serializer round-trip tests — using actual IR field names."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.serialization.registry import build_default_registry
from nl2spl.ir.field_route_ir import FieldRouteIR, RouteAnnotation
from nl2spl.ir.span_ir import AmbiguityInfo, SpanIR


def _rt(registry, obj):
    data = registry.serialize(obj)
    restored = registry.deserialize(data)
    return data, restored


class TestSpanIRRoundTrip:
    def test_all_fields_populated(self) -> None:
        reg = build_default_registry()
        s = SpanIR(
            span_id="s1", text="Extract the draft content",
            ambiguity=AmbiguityInfo(is_ambiguous=False),
            source_section_id="sec_steps", source_packet_id="pkt_extract",
            section_context="Step definitions", is_placeholder=False,
        )
        data, restored = _rt(reg, s)
        assert data["$type"] == "SpanIR"
        assert restored.span_id == "s1"
        assert restored.source_section_id == "sec_steps"

    def test_none_optionals_preserved(self) -> None:
        reg = build_default_registry()
        s = SpanIR(span_id="s2", text="Simple span")
        data, restored = _rt(reg, s)
        assert restored.source_section_id is None
        assert data["source_section_id"] is None


class TestRouteAnnotationRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        a = RouteAnnotation(span_id="s1", field="communication_type",
                            semantic_role="action", route_family="flow_relevant")
        data, restored = _rt(reg, a)
        assert data["$type"] == "RouteAnnotation"
        assert restored.span_id == "s1"
        assert restored.field == "communication_type"


class TestFieldRouteIRRoundTrip:
    def test_with_annotations(self) -> None:
        reg = build_default_registry()
        r = FieldRouteIR(
            identity=["s1"],
            annotations=[RouteAnnotation(span_id="s1", field="communication_type",
                                         semantic_role="action", route_family="flow_relevant")],
        )
        data, restored = _rt(reg, r)
        assert data["$type"] == "FieldRouteIR"
        assert restored.identity == ["s1"]
        assert len(restored.annotations) == 1


class TestCanonicalCompileInputRoundTrip:
    def test_minimal_roundtrip(self) -> None:
        reg = build_default_registry()
        from nl2spl.canonical.compile_input import CanonicalCompileInput

        c = CanonicalCompileInput(
            source_schema="generic_nl", schema_version="1.0",
            raw_text="Extract draft and send email.",
        )
        data, restored = _rt(reg, c)
        assert data["$type"] == "CanonicalCompileInput"
        assert restored.raw_text == "Extract draft and send email."

    def test_no_python_repr(self) -> None:
        reg = build_default_registry()
        from nl2spl.canonical.compile_input import CanonicalCompileInput

        c = CanonicalCompileInput(
            source_schema="generic_nl", schema_version="1.0", raw_text="Test.",
        )
        data = reg.serialize(c)
        payload_str = str(data)
        assert "CanonicalCompileInput object" not in payload_str
