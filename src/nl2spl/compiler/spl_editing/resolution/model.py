from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class PromotionResolutionMarker:
    marker_id: str
    target_worker_promotion_id: str
    resolved_diagnostic_group_id: str
    resolution_kind: Literal["kept_in_main_flow", "defined_child_worker"]
    normalized_directive_id: str
    materialized_construct_refs: tuple[str, ...]
    evidence_ref: str
    repair_patch_id: str = ""
    user_confirmed: bool = False


@dataclass(frozen=True)
class PromotionResolutionMarkerValidity:
    valid: bool
    reasons: tuple[str, ...] = ()


def validate_promotion_resolution_marker(
    marker: PromotionResolutionMarker,
    issue_target_ref: str,
    *,
    expected_repair_patch_id: str | None = None,
    require_materialized_refs: bool = True,
) -> PromotionResolutionMarkerValidity:
    """Validate marker authority for presentation and patch verification."""
    reasons: list[str] = []
    if marker.target_worker_promotion_id != issue_target_ref:
        reasons.append("target_mismatch")
    if marker.user_confirmed is not True:
        reasons.append("not_user_confirmed")
    if not marker.repair_patch_id:
        reasons.append("missing_repair_patch_id")
    if (
        expected_repair_patch_id is not None
        and marker.repair_patch_id != expected_repair_patch_id
    ):
        reasons.append("repair_patch_mismatch")
    if require_materialized_refs and not marker.materialized_construct_refs:
        reasons.append("missing_materialized_construct_refs")
    if len(marker.materialized_construct_refs) != len(set(marker.materialized_construct_refs)):
        reasons.append("duplicate_materialized_construct_refs")
    return PromotionResolutionMarkerValidity(valid=not reasons, reasons=tuple(reasons))


__all__ = [
    "PromotionResolutionMarker",
    "PromotionResolutionMarkerValidity",
    "validate_promotion_resolution_marker",
]
