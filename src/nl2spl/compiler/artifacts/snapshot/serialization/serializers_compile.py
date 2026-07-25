"""Serializers for ConstraintIR and AgentProfileIR family.

Nested types (Aspect, Concept, PersonaIR) are handled inline rather
than via recursive registry dispatch to avoid circular imports between
serializer modules and the registry.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.artifacts.snapshot.serialization.protocol import (
    ArtifactSerializer,
)
from nl2spl.compiler.artifacts.snapshot.serialization.registry import (
    SerializerRegistry,
)
from nl2spl.ir.agent_profile_ir import AgentProfileIR, Aspect, Concept, PersonaIR
from nl2spl.ir.constraint_ir import ConstraintIR


def _list_str(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if isinstance(item, str) and item]


def _profile_relation(data: dict[str, Any], fallback_with_spans: str) -> str:
    relation = data.get("provenance_relation")
    if isinstance(relation, str) and relation:
        return relation
    return fallback_with_spans if _list_str(data.get("source_span_ids")) else "assumed"


class ConstraintIRSerializer(ArtifactSerializer):
    type_id = "ConstraintIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        c: ConstraintIR = obj
        return {
            "$type": self.type_id,
            "constraint_id": c.constraint_id,
            "text": c.text,
            "kind": c.kind,
            "targets": c.targets,
            "source_span_ids": c.source_span_ids,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return ConstraintIR(
            constraint_id=data["constraint_id"],
            text=data["text"],
            kind=data["kind"],
            targets=data.get("targets", []),
            source_span_ids=data.get("source_span_ids", []),
        )


class AspectSerializer(ArtifactSerializer):
    type_id = "Aspect"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        a: Aspect = obj
        return {
            "$type": self.type_id,
            "name": a.name,
            "text": a.text,
            "source_span_ids": list(a.source_span_ids),
            "source_section_id": a.source_section_id,
            "source_packet_id": a.source_packet_id,
            "provenance_relation": a.provenance_relation,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return Aspect(
            name=data["name"],
            text=data["text"],
            source_span_ids=_list_str(data.get("source_span_ids")),
            source_section_id=data.get("source_section_id"),
            source_packet_id=data.get("source_packet_id"),
            provenance_relation=_profile_relation(data, "direct"),
        )


class ConceptSerializer(ArtifactSerializer):
    type_id = "Concept"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        c: Concept = obj
        return {
            "$type": self.type_id,
            "term": c.term,
            "definition": c.definition,
            "source_span_ids": list(c.source_span_ids),
            "source_section_id": c.source_section_id,
            "source_packet_id": c.source_packet_id,
            "provenance_relation": c.provenance_relation,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        return Concept(
            term=data["term"],
            definition=data["definition"],
            source_span_ids=_list_str(data.get("source_span_ids")),
            source_section_id=data.get("source_section_id"),
            source_packet_id=data.get("source_packet_id"),
            provenance_relation=_profile_relation(data, "normalized"),
        )


class PersonaIRSerializer(ArtifactSerializer):
    type_id = "PersonaIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        p: PersonaIR = obj
        # Inline Aspect serialization to avoid circular registry import
        aspect_ser = AspectSerializer()
        return {
            "$type": self.type_id,
            "role": p.role,
            "aspects": [aspect_ser.to_canonical(a) for a in p.aspects],
            "source_span_ids": list(p.source_span_ids),
            "source_section_id": p.source_section_id,
            "source_packet_id": p.source_packet_id,
            "provenance_relation": p.provenance_relation,
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        aspect_ser = AspectSerializer()
        return PersonaIR(
            role=data.get("role", "General Assistant"),
            aspects=[aspect_ser.from_canonical(a) for a in data.get("aspects", [])],
            source_span_ids=_list_str(data.get("source_span_ids")),
            source_section_id=data.get("source_section_id"),
            source_packet_id=data.get("source_packet_id"),
            provenance_relation=_profile_relation(data, "inferred"),
        )


class AgentProfileIRSerializer(ArtifactSerializer):
    type_id = "AgentProfileIR"

    def to_canonical(self, obj: Any) -> dict[str, Any]:
        p: AgentProfileIR = obj
        persona_ser = PersonaIRSerializer()
        aspect_ser = AspectSerializer()
        concept_ser = ConceptSerializer()
        return {
            "$type": self.type_id,
            "persona": persona_ser.to_canonical(p.persona),
            "audience_aspects": [aspect_ser.to_canonical(a) for a in p.audience_aspects],
            "concepts": [concept_ser.to_canonical(c) for c in p.concepts],
        }

    def from_canonical(self, data: dict[str, Any]) -> Any:
        persona_ser = PersonaIRSerializer()
        aspect_ser = AspectSerializer()
        concept_ser = ConceptSerializer()
        return AgentProfileIR(
            persona=persona_ser.from_canonical(data["persona"]),
            audience_aspects=[
                aspect_ser.from_canonical(a) for a in data.get("audience_aspects", [])
            ],
            concepts=[concept_ser.from_canonical(c) for c in data.get("concepts", [])],
        )


def register_all(registry: SerializerRegistry) -> None:
    s1 = ConstraintIRSerializer()
    s2 = AspectSerializer()
    s3 = ConceptSerializer()
    s4 = PersonaIRSerializer()
    s5 = AgentProfileIRSerializer()
    for s in (s1, s2, s3, s4, s5):
        registry.register(s)
    registry.register_for_class(ConstraintIR, s1)
    registry.register_for_class(Aspect, s2)
    registry.register_for_class(Concept, s3)
    registry.register_for_class(PersonaIR, s4)
    registry.register_for_class(AgentProfileIR, s5)
