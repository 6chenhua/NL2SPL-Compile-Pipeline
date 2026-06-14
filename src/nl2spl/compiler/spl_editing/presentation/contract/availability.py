"""Repair option availability contract."""

from __future__ import annotations

from enum import StrEnum


class RepairOptionAvailability(StrEnum):
    AVAILABLE = "available"
    UNAVAILABLE_SNAPSHOT_CAPABILITY = "unavailable_snapshot_capability"
    UNAVAILABLE_MISSING_HANDLER = "unavailable_missing_handler"
    UNAVAILABLE_MISSING_TARGET_RESOLVER = "unavailable_missing_target_resolver"
    UNAVAILABLE_MISSING_CONTEXT_BUILDER = "unavailable_missing_context_builder"
    UNAVAILABLE_UNSUPPORTED_PATCH_TYPE = "unavailable_unsupported_patch_type"
    REVIEW_ONLY = "review_only"


__all__ = ["RepairOptionAvailability"]
