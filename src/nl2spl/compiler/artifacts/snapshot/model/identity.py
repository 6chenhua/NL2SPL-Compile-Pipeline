"""Snapshot identity — revision and lineage model.

Defines ``SnapshotIdentity`` as a frozen dataclass with factory functions
for base and overlay snapshots.  Lineage validation enforces the contract:
    - Base: ``overlay_version == 0``, ``base_snapshot_id == snapshot_id``,
      ``parent_snapshot_id is None``.
    - Overlay: ``overlay_version > 0``, ``base_snapshot_id`` points to the
      original base, ``parent_snapshot_id`` points to the immediate predecessor.
"""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.artifacts.snapshot.constants import (
    BASE_OVERLAY_VERSION,
    IDENTITY_BASE_SNAPSHOT_ID,
    IDENTITY_COMPILE_RUN_ID,
    IDENTITY_OVERLAY_VERSION,
    IDENTITY_PARENT_SNAPSHOT_ID,
    IDENTITY_SNAPSHOT_ID,
    PRODUCER_NAME,
    SNAPSHOT_SCHEMA_VERSION,
)
from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotLineageError

# ---------------------------------------------------------------------------
# SnapshotIdentity
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotIdentity:
    """Immutable identity for one snapshot revision.

    Attributes:
        compile_run_id: The NL2SPL pipeline run that produced the base.
        snapshot_id: Unique identifier for this specific snapshot revision.
        base_snapshot_id: The original base snapshot id (same as
            ``snapshot_id`` for base; preserved across overlays).
        parent_snapshot_id: The immediate predecessor snapshot id
            (``None`` for base; set to previous overlay for overlays).
        overlay_version: 0 for base, monotonically increasing for overlays.
        created_at: ISO 8601 timestamp.
        producer: Canonical producer name (``"nl2spl"``).
        producer_version: Producer version string.
    """

    compile_run_id: str
    snapshot_id: str
    base_snapshot_id: str
    parent_snapshot_id: str | None
    overlay_version: int
    created_at: str
    producer: str = PRODUCER_NAME
    producer_version: str = SNAPSHOT_SCHEMA_VERSION

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    @property
    def is_base(self) -> bool:
        """``True`` when this is a base (non-overlay) snapshot."""
        return self.overlay_version == BASE_OVERLAY_VERSION

    @property
    def is_overlay(self) -> bool:
        """``True`` when this is an overlay snapshot."""
        return self.overlay_version > BASE_OVERLAY_VERSION


# ---------------------------------------------------------------------------
# Factory functions — create correctly-structured identities
# ---------------------------------------------------------------------------


def new_base_identity(
    compile_run_id: str,
    snapshot_id: str,
    *,
    created_at: str,
    producer_version: str = SNAPSHOT_SCHEMA_VERSION,
) -> SnapshotIdentity:
    """Create a base snapshot identity with ``overlay_version == 0``.

    Args:
        compile_run_id: The pipeline run identifier.
        snapshot_id: Unique identifier for this snapshot.
        created_at: ISO 8601 creation timestamp.
        producer_version: Producer version string.

    Returns:
        A ``SnapshotIdentity`` with ``is_base == True``.
    """
    return SnapshotIdentity(
        compile_run_id=compile_run_id,
        snapshot_id=snapshot_id,
        base_snapshot_id=snapshot_id,
        parent_snapshot_id=None,
        overlay_version=BASE_OVERLAY_VERSION,
        created_at=created_at,
        producer=PRODUCER_NAME,
        producer_version=producer_version,
    )


def new_overlay_identity(
    base_identity: SnapshotIdentity,
    new_snapshot_id: str,
    *,
    created_at: str,
    parent_identity: SnapshotIdentity | None = None,
) -> SnapshotIdentity:
    """Create an overlay snapshot identity with incremented ``overlay_version``.

    Args:
        base_identity: The original base snapshot identity.
        new_snapshot_id: Unique identifier for this new overlay snapshot.
        created_at: ISO 8601 creation timestamp.
        parent_identity: The immediate predecessor (defaults to *base_identity*
            for the first overlay; pass the previous overlay for subsequent
            overlays).

    Returns:
        A ``SnapshotIdentity`` with ``is_overlay == True``.

    Raises:
        SnapshotLineageError: If *parent_identity* is not from the same
            run and base lineage as *base_identity*.
    """
    prev = parent_identity if parent_identity is not None else base_identity

    # Validate parent lineage when an explicit parent is provided.
    if parent_identity is not None:
        if parent_identity.compile_run_id != base_identity.compile_run_id:
            raise SnapshotLineageError(
                f"Parent {IDENTITY_COMPILE_RUN_ID} "
                f"{parent_identity.compile_run_id!r} != base "
                f"{base_identity.compile_run_id!r}"
            )
        if parent_identity.base_snapshot_id != base_identity.base_snapshot_id:
            raise SnapshotLineageError(
                f"Parent {IDENTITY_BASE_SNAPSHOT_ID} "
                f"{parent_identity.base_snapshot_id!r} != base "
                f"{base_identity.base_snapshot_id!r}"
            )
        if parent_identity.overlay_version < base_identity.overlay_version:
            raise SnapshotLineageError(
                f"Parent {IDENTITY_OVERLAY_VERSION} "
                f"{parent_identity.overlay_version} < base "
                f"{base_identity.overlay_version}"
            )
        if parent_identity.snapshot_id == new_snapshot_id:
            raise SnapshotLineageError(
                f"Parent {IDENTITY_SNAPSHOT_ID} "
                f"{parent_identity.snapshot_id!r} must differ from "
                f"new {IDENTITY_SNAPSHOT_ID} {new_snapshot_id!r}"
            )

    return SnapshotIdentity(
        compile_run_id=base_identity.compile_run_id,
        snapshot_id=new_snapshot_id,
        base_snapshot_id=base_identity.base_snapshot_id,
        parent_snapshot_id=prev.snapshot_id,
        overlay_version=prev.overlay_version + 1,
        created_at=created_at,
        producer=base_identity.producer,
        producer_version=base_identity.producer_version,
    )


# ---------------------------------------------------------------------------
# Lineage validation
# ---------------------------------------------------------------------------


def validate_base_identity(identity: SnapshotIdentity) -> list[str]:
    """Validate that *identity* satisfies base snapshot invariants.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    if identity.overlay_version != BASE_OVERLAY_VERSION:
        errors.append(
            f"Base snapshot must have {IDENTITY_OVERLAY_VERSION}={BASE_OVERLAY_VERSION}, "
            f"got {identity.overlay_version}"
        )
    if identity.base_snapshot_id != identity.snapshot_id:
        errors.append(
            f"Base snapshot {IDENTITY_BASE_SNAPSHOT_ID} must equal "
            f"{IDENTITY_SNAPSHOT_ID}, got {identity.base_snapshot_id!r} != "
            f"{identity.snapshot_id!r}"
        )
    if identity.parent_snapshot_id is not None:
        errors.append(
            f"Base snapshot must have {IDENTITY_PARENT_SNAPSHOT_ID}=None, "
            f"got {identity.parent_snapshot_id!r}"
        )
    if not identity.compile_run_id:
        errors.append(f"{IDENTITY_COMPILE_RUN_ID} must not be empty")
    if not identity.snapshot_id:
        errors.append(f"{IDENTITY_SNAPSHOT_ID} must not be empty")
    return errors


def validate_overlay_lineage(
    overlay: SnapshotIdentity,
    parent: SnapshotIdentity,
) -> list[str]:
    """Validate that *overlay* correctly derives from *parent*.

    *parent* is the immediate predecessor (the base for the first overlay;
    the previous overlay for subsequent overlays).  The overlay must satisfy:

    - Same ``compile_run_id`` and ``base_snapshot_id``.
    - ``overlay_version == parent.overlay_version + 1`` (strict, no skipping).
    - ``parent_snapshot_id == parent.snapshot_id``.
    - ``snapshot_id != parent.snapshot_id``.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    if overlay.compile_run_id != parent.compile_run_id:
        errors.append(
            f"Overlay {IDENTITY_COMPILE_RUN_ID} {overlay.compile_run_id!r} "
            f"!= parent {parent.compile_run_id!r}"
        )
    if overlay.base_snapshot_id != parent.base_snapshot_id:
        errors.append(
            f"Overlay {IDENTITY_BASE_SNAPSHOT_ID} {overlay.base_snapshot_id!r} "
            f"!= parent {parent.base_snapshot_id!r}"
        )
    expected_version = parent.overlay_version + 1
    if overlay.overlay_version != expected_version:
        errors.append(
            f"Overlay {IDENTITY_OVERLAY_VERSION} must be "
            f"{expected_version} (parent {parent.overlay_version} + 1), "
            f"got {overlay.overlay_version}"
        )
    if overlay.parent_snapshot_id is None:
        errors.append(
            f"Overlay must have a non-None {IDENTITY_PARENT_SNAPSHOT_ID}"
        )
    elif overlay.parent_snapshot_id != parent.snapshot_id:
        errors.append(
            f"Overlay {IDENTITY_PARENT_SNAPSHOT_ID} "
            f"{overlay.parent_snapshot_id!r} != parent "
            f"{IDENTITY_SNAPSHOT_ID} {parent.snapshot_id!r}"
        )
    if not overlay.snapshot_id or overlay.snapshot_id == parent.snapshot_id:
        errors.append(
            f"Overlay {IDENTITY_SNAPSHOT_ID} must differ from parent "
            f"{parent.snapshot_id!r}"
        )
    return errors
