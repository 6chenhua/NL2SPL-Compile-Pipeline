"""ResourceContractDemandView diagnostic kind constants.

Stable kind identifiers — implementers must not freely concatenate strings.
"""

from __future__ import annotations

# -- builder diagnostics -----------------------------------------------------

RESOURCE_CONTRACT_ANNOTATION_MISSING_DIRECTION = (
    "resource_contract_annotation_missing_direction"
)
"""A resource contract annotation has no discernible direction (semantic_role or slot_target)."""

RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION = (
    "resource_contract_annotation_conflicting_direction"
)
"""Multiple annotations for the same span disagree on direction (input vs output)."""

RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS = (
    "resource_contract_annotation_missing_requiredness"
)
"""A resource contract annotation does not carry requiredness information."""

RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS = (
    "resource_contract_annotation_conflicting_requiredness"
)
"""Multiple annotations for the same demand disagree on requiredness."""

RESOURCE_CONTRACT_DUPLICATE_DEMAND_ID = "resource_contract_duplicate_demand_id"
"""A duplicate demand ID was detected during building."""

RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT = (
    "resource_contract_invalid_annotation_contract"
)
"""A resource contract annotation is structurally invalid and cannot be consumed."""

RESOURCE_CONTRACT_AMBIGUOUS_MULTI_DIRECTION_SPAN = (
    "resource_contract_ambiguous_multi_direction_span"
)
"""The same span has both input and output contract annotations (conflict)."""

RESOURCE_CONTRACT_MULTI_ANNOTATION_REQUIRES_SPLIT = (
    "resource_contract_multi_annotation_requires_split"
)
"""Multiple contract annotations exist for one span but cannot be resolved without splitting."""

# -- coverage validator diagnostics ------------------------------------------
# (Phase C implementation, but the kind strings are part of the contract now.)

RESOURCE_CONTRACT_ANNOTATION_MISSING = "resource_contract_annotation_missing"
"""Coverage gap: a structural fact has no matching Stage 2 confirmed annotation."""

RESOURCE_CONTRACT_ANNOTATION_COVERAGE_GAP = "resource_contract_annotation_coverage_gap"
"""A structural fact falls outside the coverage of Stage 2 annotations."""

RESOURCE_CONTRACT_ANNOTATION_UNMATCHED_STRUCTURAL_FACT = (
    "resource_contract_annotation_unmatched_structural_fact"
)
"""A structural fact exists but has no corresponding contract annotation."""

# -- compat diagnostics ------------------------------------------------------

RESOURCE_CONTRACT_HEADER_FALLBACK_USED = "resource_contract_header_fallback_used"
"""Header fallback was used to infer contract demands (compatibility path only)."""

# -- severity mapping --------------------------------------------------------

DIAGNOSTIC_KIND_SEVERITY: dict[str, str] = {
    RESOURCE_CONTRACT_ANNOTATION_MISSING_DIRECTION: "warning",
    RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_DIRECTION: "warning",
    RESOURCE_CONTRACT_ANNOTATION_MISSING_REQUIREDNESS: "info",
    RESOURCE_CONTRACT_ANNOTATION_CONFLICTING_REQUIREDNESS: "warning",
    RESOURCE_CONTRACT_DUPLICATE_DEMAND_ID: "error",
    RESOURCE_CONTRACT_INVALID_ANNOTATION_CONTRACT: "warning",
    RESOURCE_CONTRACT_AMBIGUOUS_MULTI_DIRECTION_SPAN: "warning",
    RESOURCE_CONTRACT_MULTI_ANNOTATION_REQUIRES_SPLIT: "warning",
    RESOURCE_CONTRACT_ANNOTATION_MISSING: "warning",
    RESOURCE_CONTRACT_ANNOTATION_COVERAGE_GAP: "warning",
    RESOURCE_CONTRACT_ANNOTATION_UNMATCHED_STRUCTURAL_FACT: "info",
    RESOURCE_CONTRACT_HEADER_FALLBACK_USED: "info",
}
"""Severity level for each diagnostic kind."""


def severity_for_kind(kind: str) -> str:
    """Return the mapped severity for *kind*, falling back to ``warning``."""
    return DIAGNOSTIC_KIND_SEVERITY.get(kind, "warning")
