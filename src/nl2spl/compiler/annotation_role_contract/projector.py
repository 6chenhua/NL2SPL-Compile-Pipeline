"""Diagnostic projector — convert ARC4 typed diagnostics into ``CompileDiagnostic``.

Provides ``project_stage2_to_compile_diagnostics()`` which converts
``routes.structured_route_diagnostics`` entries (both legacy string-based
dicts and ARC4 ``AnnotationValidationDiagnostic.to_dict()`` dicts) into
``CompileDiagnostic`` objects for the diagnostic consolidator.
"""

from __future__ import annotations

from typing import Any

from nl2spl.compiler.annotation_role_contract.diagnostics import (
    ANNOTATION_INVALID_CONSTRUCT_TARGET_FOR_ROLE,
    ANNOTATION_INVALID_EXECUTABLE_FOR_ROLE,
    ANNOTATION_INVALID_FIELD_FOR_ROLE,
    ANNOTATION_INVALID_ROUTE_FAMILY_FOR_ROLE,
    ANNOTATION_INVALID_SLOT_TARGET_FOR_ROLE,
    ANNOTATION_MISSING_REQUIREDNESS,
    ANNOTATION_REJECTED_AFTER_ROLE_CONTRACT_VALIDATION,
    ANNOTATION_ROLE_CONTRACT_CONFLICT,
)
from nl2spl.ir.diagnostics import CompileDiagnostic

# Severity mapping from ARC4 diagnostic kinds to CompileDiagnostic severity
_KIND_SEVERITY: dict[str, str] = {
    ANNOTATION_ROLE_CONTRACT_CONFLICT: "warning",
    ANNOTATION_INVALID_FIELD_FOR_ROLE: "warning",
    ANNOTATION_INVALID_ROUTE_FAMILY_FOR_ROLE: "warning",
    ANNOTATION_INVALID_CONSTRUCT_TARGET_FOR_ROLE: "warning",
    ANNOTATION_INVALID_SLOT_TARGET_FOR_ROLE: "warning",
    ANNOTATION_INVALID_EXECUTABLE_FOR_ROLE: "warning",
    ANNOTATION_MISSING_REQUIREDNESS: "info",
    ANNOTATION_REJECTED_AFTER_ROLE_CONTRACT_VALIDATION: "warning",
}

# Typed diagnostic kinds (have field_name in the dict)
_TYPED_KINDS = frozenset(_KIND_SEVERITY.keys())


def _make_diagnostic_id(kind: str, span_id: str, semantic_role: str = "",
                        field_name: str | None = None) -> str:
    """Build a stable diagnostic id uniquely keyed by (kind, span, role, field)."""
    base = f"arc4_{kind}_{span_id}"
    if semantic_role:
        base = f"{base}_{semantic_role}"
    if field_name:
        base = f"{base}_{field_name}"
    return base


def project_stage2_to_compile_diagnostics(
    structured_route_diagnostics: list[dict[str, Any]],
) -> list[CompileDiagnostic]:
    """Project Stage 2 structured route diagnostics into ``CompileDiagnostic``.

    Typed ARC4 diagnostics carry structured payload in ``CompileDiagnostic.metadata``
    (semantic_role, field_name, expected, actual, source_section_id, source_packet_id).
    Legacy string-based diagnostics are projected for backward compatibility.

    Deduplication: when a typed diagnostic covers the same span + semantic_role
    + field_name, any legacy diagnostic for the same span whose message is a
    substring of the typed message is skipped to avoid double-projection.
    """
    result: list[CompileDiagnostic] = []
    # Track typed diagnostic keys for dedup
    typed_span_messages: set[tuple[str, str]] = set()  # (span_id, message)

    # First pass: collect typed diagnostics
    typed_entries: list[dict[str, Any]] = []
    legacy_entries: list[dict[str, Any]] = []

    for entry in structured_route_diagnostics:
        kind = entry.get("kind", "")
        if kind in _TYPED_KINDS and "field_name" in entry:
            typed_entries.append(entry)
        else:
            legacy_entries.append(entry)

    # Project typed entries first
    for entry in typed_entries:
        kind = entry["kind"]
        span_id = entry.get("span_id", "")
        message = entry.get("message", "")
        field_name = entry.get("field_name", "")
        semantic_role = entry.get("semantic_role", "")
        expected = entry.get("expected")
        actual = entry.get("actual")
        source_section_id = entry.get("source_section_id")
        source_packet_id = entry.get("source_packet_id")

        diag_id = _make_diagnostic_id(kind, span_id, semantic_role, field_name)
        severity = _KIND_SEVERITY.get(kind, "warning")

        result.append(
            CompileDiagnostic(
                diagnostic_id=diag_id,
                kind=kind,
                severity=severity,
                message=f"[{semantic_role}] {field_name}: expected={expected}, got={actual}. {message}",
                target_ref=f"span:{span_id}",
                source_span_ids=[span_id] if span_id else [],
                source_section_id=source_section_id,
                source_packet_id=source_packet_id,
                metadata={
                    "semantic_role": semantic_role,
                    "field_name": field_name,
                    "expected": expected,
                    "actual": actual,
                },
                blocks_completion=False,
            )
        )
        typed_span_messages.add((span_id, message))

    # Project legacy entries, skipping those covered by typed diagnostics
    for entry in legacy_entries:
        kind = entry.get("kind", "route_refinement_diagnostic")
        span_id = entry.get("span_id", "")
        message = entry.get("message", str(entry))
        severity = _KIND_SEVERITY.get(kind, "info")

        # Skip if a typed diagnostic covers the same (span_id, message)
        # — same event already represented as structured diagnostic.
        if (span_id, message) in typed_span_messages:
            continue

        diag_id = f"stage2_{kind}_{span_id}"
        result.append(
            CompileDiagnostic(
                diagnostic_id=diag_id,
                kind=kind,
                severity=severity,
                message=message,
                target_ref=f"span:{span_id}" if span_id else None,
                source_span_ids=[span_id] if span_id else [],
                blocks_completion=False,
            )
        )

    return result
