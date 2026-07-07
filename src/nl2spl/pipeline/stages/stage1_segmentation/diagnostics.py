"""Diagnostic kinds and constructors for Stage 1 Span Segmentation validation."""

from __future__ import annotations

from typing import Any
from nl2spl.ir.diagnostics import CompileDiagnostic

# Stage 1 diagnostic kinds
PARAPHRASE_REJECTED = "stage1_segmentation_paraphrase_rejected"
COVERAGE_GAP = "stage1_segmentation_coverage_gap"
CROSS_SECTION_MERGE = "stage1_segmentation_cross_section_merge"
FABRICATED_PACKET_IDS = "stage1_segmentation_fabricated_packet_ids"
OVERLAP_REJECTED = "stage1_segmentation_overlap_rejected"
INVALID_KIND = "stage1_segmentation_invalid_kind"
GUARDED_ACTION_MISSING_ELEMENTS = "stage1_segmentation_guarded_action_missing_elements"
GUARD_ACTION_NOT_SUBSTRING = "stage1_segmentation_guard_action_not_substring"
DUPLICATE_RANGE_AMBIGUOUS = "stage1_segmentation_duplicate_range_ambiguous"

def make_diagnostic(
    kind: str,
    message: str,
    source_section_id: str,
    metadata: dict[str, Any] | None = None,
) -> CompileDiagnostic:
    """Create a Stage 1 validation CompileDiagnostic.

    Args:
        kind: The diagnostic kind (e.g., stage1_segmentation_paraphrase_rejected)
        message: Human readable error message
        source_section_id: The ID of the section where the error occurred
        metadata: Optional extra metadata

    Returns:
        A CompileDiagnostic object
    """
    meta = {
        "source_section_id": source_section_id,
        "stage": "stage1_span_slicer",
        "irs_ref": {
            "construct_type": "SPAN_SEGMENTATION",
            "section_id": source_section_id,
        }
    }
    if metadata:
        meta.update(metadata)

    return CompileDiagnostic(
        diagnostic_id=f"diag_{kind}_{source_section_id}",
        kind=kind,
        message=message,
        severity="error",
        target_ref=f"section:{source_section_id}",
        metadata=meta,
    )
