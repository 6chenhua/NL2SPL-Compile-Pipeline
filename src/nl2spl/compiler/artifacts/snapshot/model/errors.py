"""Neutral snapshot errors — shared by compiler and SPL Editing consumers.

These errors belong to the snapshot contract, not to SPL Editing internals.
SPL Editing may wrap them in its own error hierarchy, but the base error
types live here so the compiler can raise them without importing SPL Editing.
"""

from __future__ import annotations


class SnapshotError(Exception):
    """Base for all snapshot contract errors."""


class SnapshotIdentityError(SnapshotError):
    """Identity field is missing, invalid, or inconsistent."""


class SnapshotLineageError(SnapshotError):
    """Lineage mismatch: base/overlay relationship is broken.

    Raised when an overlay has a different ``compile_run_id`` or
    ``base_snapshot_id`` than its base, or when ``overlay_version``
    does not strictly increase.
    """


class SnapshotCapabilityError(SnapshotError):
    """A required capability is not effective.

    Attributes:
        capability: The capability that was required but not effective.
        reason: Human-readable explanation.
    """

    def __init__(self, capability: str, reason: str) -> None:
        self.capability = capability
        self.reason = reason
        super().__init__(f"Capability {capability!r} is not effective: {reason}")


class SnapshotIntegrityError(SnapshotError):
    """Payload or artifact-set hash mismatch."""


class SnapshotSchemaError(SnapshotError):
    """Schema version incompatible or document shape invalid."""


class SnapshotArtifactRefError(SnapshotError):
    """Artifact reference is missing, broken, or inconsistent."""
