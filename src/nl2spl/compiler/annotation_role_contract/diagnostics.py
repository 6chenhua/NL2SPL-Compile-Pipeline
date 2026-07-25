"""Annotation role contract diagnostic kind constants and typed diagnostic model.

Typed ``AnnotationValidationDiagnostic`` is the canonical diagnostic shape
for ARC4+.  It carries expected/actual values, provenance, and a human-readable
message.  ARC7 projects these into ``CompileDiagnostic``.
"""

from __future__ import annotations

from dataclasses import dataclass

# -- typed diagnostic model (ARC4+) -------------------------------------------

@dataclass(frozen=True)
class AnnotationValidationDiagnostic:
    """Typed diagnostic for a single role-contract field conflict.

    Carries machine-readable expected/actual values so that ARC7 can
    project into ``CompileDiagnostic`` without parsing free-form strings.
    """

    kind: str
    """Stable diagnostic kind (e.g. ``annotation_invalid_field_for_role``)."""

    span_id: str
    """The span whose annotation triggered this diagnostic."""

    semantic_role: str
    """Canonical semantic role (after alias resolution)."""

    field_name: str
    """The contract field that was checked (e.g. ``construct_target``)."""

    expected: str | bool | None
    """The contract-expected value."""

    actual: str | bool | None
    """The raw LLM/hint value that conflicted."""

    source_section_id: str | None = None
    """Adapter section provenance."""

    source_packet_id: str | None = None
    """Adapter packet provenance."""

    message: str = ""
    """Human-readable description of the conflict."""

    def to_dict(self) -> dict:
        """Project to a JSON-safe dict for downstream diagnostic consumers.

        ``expected`` and ``actual`` are stored as raw values (str, bool,
        or ``None``) — no ``repr()`` wrapping.  ARC7 can consume these
        directly without string parsing.
        """
        return {
            "kind": self.kind,
            "span_id": self.span_id,
            "semantic_role": self.semantic_role,
            "field_name": self.field_name,
            "expected": self.expected,
            "actual": self.actual,
            "source_section_id": self.source_section_id,
            "source_packet_id": self.source_packet_id,
            "message": self.message,
        }


# -- role contract conflict kinds ---------------------------------------------

ANNOTATION_ROLE_CONTRACT_CONFLICT = "annotation_role_contract_conflict"
"""Raw LLM/hint field conflicts with the canonical role contract."""

ANNOTATION_INVALID_FIELD_FOR_ROLE = "annotation_invalid_field_for_role"
"""``field`` does not match the role contract expectation."""

ANNOTATION_INVALID_ROUTE_FAMILY_FOR_ROLE = "annotation_invalid_route_family_for_role"
"""``route_family`` does not match the role contract expectation."""

ANNOTATION_INVALID_CONSTRUCT_TARGET_FOR_ROLE = (
    "annotation_invalid_construct_target_for_role"
)
"""``construct_target`` does not match the role contract expectation,
including expected ``None``."""

ANNOTATION_INVALID_SLOT_TARGET_FOR_ROLE = "annotation_invalid_slot_target_for_role"
"""``slot_target`` does not match the role contract expectation,
including expected ``None``."""

ANNOTATION_INVALID_EXECUTABLE_FOR_ROLE = "annotation_invalid_executable_for_role"
"""``executable`` does not match the role contract expectation."""

ANNOTATION_MISSING_REQUIREDNESS = "annotation_missing_requiredness"
"""Resource contract annotation is missing ``requiredness`` metadata."""

ANNOTATION_REJECTED_AFTER_ROLE_CONTRACT_VALIDATION = (
    "annotation_rejected_after_role_contract_validation"
)
"""Annotation was rejected because it failed full-field role contract validation."""

ANNOTATION_LEGACY_FIELD_OVERRIDDEN_BY_ROLE_CONTRACT = (
    "annotation_legacy_field_overridden_by_role_contract"
)
"""Raw LLM/hint field was overridden by canonical role contract normalization."""

ANNOTATION_COVERAGE_GAP = "annotation_coverage_gap"
"""A structural fact has no matching confirmed annotation."""
