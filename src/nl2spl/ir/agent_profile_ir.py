"""AgentProfileIR - Persona, Audience, Concepts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Aspect:
    """Aspect of persona or audience.

    Attributes:
        name: Aspect name (PascalCase)
        text: Aspect description
        source_span_ids: Source spans that evidence this aspect.
        source_section_id: Shared adapter section for the source spans, if any.
        source_packet_id: Shared adapter packet for the source spans, if any.
        provenance_relation: Relation to the source evidence. Defaults to
            ``assumed`` so profile items fail closed until Stage 8 binds
            validated evidence.
    """

    name: str
    text: str
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    provenance_relation: str = "assumed"


@dataclass
class Concept:
    """Domain concept.

    Attributes:
        term: Concept term
        definition: Concept definition
        source_span_ids: Source spans that evidence this concept.
        source_section_id: Shared adapter section for the source spans, if any.
        source_packet_id: Shared adapter packet for the source spans, if any.
        provenance_relation: Relation to the source evidence. Defaults to
            ``assumed`` until Stage 8 validates evidence.
    """

    term: str
    definition: str
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    provenance_relation: str = "assumed"


@dataclass
class PersonaIR:
    """Persona information.

    Attributes:
        role: Core role description
        aspects: Additional persona aspects
        source_span_ids: Source spans that evidence the role.
        source_section_id: Shared adapter section for the source spans, if any.
        source_packet_id: Shared adapter packet for the source spans, if any.
        provenance_relation: Relation to the source evidence. Defaults to
            ``assumed`` until Stage 8 validates evidence.
    """

    role: str = "General Assistant"
    aspects: list[Aspect] = field(default_factory=list)
    source_span_ids: list[str] = field(default_factory=list)
    source_section_id: str | None = None
    source_packet_id: str | None = None
    provenance_relation: str = "assumed"


@dataclass
class AgentProfileIR:
    """Agent profile information.

    Attributes:
        persona: Persona information
        audience_aspects: Audience aspects
        concepts: Domain concepts
    """

    persona: PersonaIR = field(default_factory=PersonaIR)
    audience_aspects: list[Aspect] = field(default_factory=list)
    concepts: list[Concept] = field(default_factory=list)
