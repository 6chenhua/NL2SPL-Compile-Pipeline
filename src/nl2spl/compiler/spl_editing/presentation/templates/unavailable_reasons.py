"""User-readable unavailable reason copy."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.presentation.contract.availability import (
    RepairOptionAvailability,
)

_REASONS = {
    RepairOptionAvailability.UNAVAILABLE_SNAPSHOT_CAPABILITY: (
        "Required snapshot capability is unavailable."
    ),
    RepairOptionAvailability.UNAVAILABLE_MISSING_HANDLER: ("The repair handler is not registered."),
    RepairOptionAvailability.UNAVAILABLE_MISSING_TARGET_RESOLVER: (
        "The target resolver is not registered."
    ),
    RepairOptionAvailability.UNAVAILABLE_MISSING_CONTEXT_BUILDER: (
        "The context builder is not registered."
    ),
    RepairOptionAvailability.UNAVAILABLE_UNSUPPORTED_PATCH_TYPE: (
        "No supported patch type is registered for this run."
    ),
    RepairOptionAvailability.REVIEW_ONLY: ("This item is review-only and cannot be fixed here."),
}


def unavailable_reason(availability: RepairOptionAvailability) -> str | None:
    return _REASONS.get(availability)


__all__ = ["unavailable_reason"]
