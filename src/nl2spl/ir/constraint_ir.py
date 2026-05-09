"""ConstraintIR - Constraint rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ConstraintKind = Literal[
    "requirement",
    "prohibition",
    "gate",
    "evidence",
    "approval",
    "safety",
    "audit",
    "delegation_boundary",
    "promotion_requirement",
]


@dataclass
class ConstraintIR:
    """Constraint rule.

    Attributes:
        constraint_id: Unique identifier (format: c{N})
        text: Constraint text (may contain <REF> tags)
        kind: Constraint type
        targets: Target references (format: type:id)
        source_span_ids: Source span IDs
    """

    constraint_id: str
    text: str
    kind: ConstraintKind
    targets: list[str] = field(default_factory=list)
    source_span_ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Validate constraint_id format."""
        if not self.constraint_id.startswith("c"):
            raise ValueError(
                f"constraint_id must start with 'c', got: {self.constraint_id}"
            )
