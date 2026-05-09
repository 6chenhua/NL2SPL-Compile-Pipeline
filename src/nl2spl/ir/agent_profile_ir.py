"""AgentProfileIR - Persona, Audience, Concepts."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Aspect:
    """Aspect of persona or audience.

    Attributes:
        name: Aspect name (PascalCase)
        text: Aspect description
    """

    name: str
    text: str


@dataclass
class Concept:
    """Domain concept.

    Attributes:
        term: Concept term
        definition: Concept definition
    """

    term: str
    definition: str


@dataclass
class PersonaIR:
    """Persona information.

    Attributes:
        role: Core role description
        aspects: Additional persona aspects
    """

    role: str = "General Assistant"
    aspects: list[Aspect] = field(default_factory=list)


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
