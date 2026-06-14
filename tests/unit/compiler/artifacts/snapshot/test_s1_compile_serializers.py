"""S1 compile-time serializer round-trip tests: ConstraintIR, AgentProfileIR family."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    build_default_registry,
)
from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, Concept, PersonaIR
from nl2spl.ir.constraint_ir import ConstraintIR


def _rt(registry, obj):
    data = registry.serialize(obj)
    restored = registry.deserialize(data)
    return data, restored


class TestConstraintIRRoundTrip:
    def test_full_roundtrip(self) -> None:
        reg = build_default_registry()
        c = ConstraintIR(
            constraint_id="c1",
            text="Must validate <REF:s3> before <REF:s4>",
            kind="gate",
            targets=["step:st1", "step:st2"],
            source_span_ids=["s3", "s4"],
        )
        data, restored = _rt(reg, c)
        assert data["$type"] == "ConstraintIR"
        assert restored.constraint_id == "c1"
        assert restored.kind == "gate"
        assert restored.targets == ["step:st1", "step:st2"]

    def test_minimal_roundtrip(self) -> None:
        reg = build_default_registry()
        c = ConstraintIR(constraint_id="c2", text="Simple constraint", kind="requirement")
        _data, restored = _rt(reg, c)
        assert restored.targets == []
        assert restored.source_span_ids == []


class TestAspectRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        a = Aspect(name="ContextAware", text="The assistant understands context")
        data, restored = _rt(reg, a)
        assert data["$type"] == "Aspect"
        assert restored.name == "ContextAware"


class TestConceptRoundTrip:
    def test_roundtrip(self) -> None:
        reg = build_default_registry()
        c = Concept(term="SPL", definition="Structured Prompt Language")
        data, restored = _rt(reg, c)
        assert data["$type"] == "Concept"
        assert restored.term == "SPL"


class TestPersonaIRRoundTrip:
    def test_with_aspects(self) -> None:
        reg = build_default_registry()
        p = PersonaIR(
            role="Technical Writer",
            aspects=[Aspect(name="Precise", text="Uses precise language")],
        )
        data, restored = _rt(reg, p)
        assert data["$type"] == "PersonaIR"
        assert restored.role == "Technical Writer"
        assert len(restored.aspects) == 1
        assert isinstance(restored.aspects[0], Aspect)
        assert restored.aspects[0].name == "Precise"

    def test_empty_aspects(self) -> None:
        reg = build_default_registry()
        p = PersonaIR()
        _data, restored = _rt(reg, p)
        assert restored.role == "General Assistant"
        assert restored.aspects == []


class TestAgentProfileIRRoundTrip:
    def test_full_roundtrip(self) -> None:
        reg = build_default_registry()
        profile = AgentProfileIR(
            persona=PersonaIR(role="Assistant"),
            audience_aspects=[Aspect(name="Technical", text="Technical audience")],
            concepts=[Concept(term="API", definition="Application Programming Interface")],
        )
        data, restored = _rt(reg, profile)
        assert data["$type"] == "AgentProfileIR"
        assert isinstance(restored.persona, PersonaIR)
        assert restored.persona.role == "Assistant"
        assert len(restored.audience_aspects) == 1
        assert len(restored.concepts) == 1

    def test_minimal_roundtrip(self) -> None:
        reg = build_default_registry()
        profile = AgentProfileIR()
        _data, restored = _rt(reg, profile)
        assert restored.audience_aspects == []
        assert restored.concepts == []

    def test_no_python_repr_in_payload(self) -> None:
        """No raw Python object repr in canonical dict."""
        reg = build_default_registry()
        profile = AgentProfileIR(
            persona=PersonaIR(role="Bot"),
            concepts=[Concept(term="X", definition="Y")],
        )
        data = reg.serialize(profile)
        payload_str = str(data)
        assert "__main__" not in payload_str
        assert "object at 0x" not in payload_str
