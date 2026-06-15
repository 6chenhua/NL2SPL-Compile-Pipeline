"""Per-patch-type metadata carried by IRS ``RepairAffordanceSpec``.

Presented to the user as a strategy-level choice *before* LLM-generated
suggestions are produced.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PatchTypeMeta:
    """User-facing label, description, and verification lane for one patch type.

    Carried by ``RepairAffordanceSpec.patch_type_metadata``, copied into
    ``RepairCatalogEntry`` at build time, and projected into
    ``RepairOptionView`` for display.
    """

    patch_type: str
    label: str
    description: str
    verification_lane: str = "A"


__all__ = ["PatchTypeMeta"]
