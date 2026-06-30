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


__all__ = ["PromotionResolutionMarker"]
