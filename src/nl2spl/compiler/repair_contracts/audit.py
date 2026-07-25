"""Local shape validation for repair contract metadata.

Cross-layer strategy linkage audits must live outside repair_contracts because
they need SPL Editing strategy registry access.
"""

from __future__ import annotations

from nl2spl.compiler.repair_contracts.model import RepairAffordanceSpec


def validate_repair_affordance_shape(affordance: RepairAffordanceSpec) -> list[str]:
    """Return local metadata shape errors for one affordance."""
    errors: list[str] = []
    if not affordance.affordance_id.strip():
        errors.append("affordance_id cannot be blank")
    if not affordance.description.strip():
        errors.append("description cannot be blank")
    if affordance.default_patch_type and (
        affordance.default_patch_type not in affordance.supported_patch_types
    ):
        errors.append("default_patch_type must be listed in supported_patch_types")
    return errors


__all__ = ["validate_repair_affordance_shape"]
