"""SnapshotDocument — the top-level canonical snapshot envelope.

A ``SnapshotDocument`` is the in-memory representation of a complete
``spl_editing_snapshot.json`` document.  It combines identity, declared
capabilities, payload, and integrity into one frozen value object.

This is a pure data structure.  Validation, serialization, and
persistence are handled by separate modules (S1–S3).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from nl2spl.compiler.artifacts.snapshot.constants import (
    SNAPSHOT_ARTIFACT_KIND,
    SNAPSHOT_SCHEMA_VERSION,
)
from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
    SnapshotEditingHistory,
)
from nl2spl.compiler.artifacts.snapshot.model.errors import (
    SnapshotIdentityError,
    SnapshotLineageError,
)
from nl2spl.compiler.artifacts.snapshot.model.identity import SnapshotIdentity
from nl2spl.compiler.artifacts.snapshot.model.integrity import SnapshotIntegrity
from nl2spl.compiler.artifacts.snapshot.model.payload import SnapshotPayload
from nl2spl.compiler.artifacts.snapshot.model.validation import (
    SnapshotDeclaredCapabilities,
)

# ---------------------------------------------------------------------------
# SnapshotDocument
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotDocument:
    """Complete canonical snapshot document.

    This is the compiler-owned equivalent of the JSON document on disk.
    SPL Editing consumes it through the repository/loader boundary (S3–S5).

    Attributes:
        artifact_kind: Always ``"spl_editing_artifact_snapshot"``.
        schema_version: The schema version string (``"1.0.0"``).
        identity: Revision identity and lineage.
        declared_capabilities: Writer-declared capabilities (not authoritative).
        payload: All six payload sub-sections.
        integrity: Hash pair for storage and semantic verification.
    """

    artifact_kind: str = SNAPSHOT_ARTIFACT_KIND
    schema_version: str = SNAPSHOT_SCHEMA_VERSION
    identity: SnapshotIdentity = field(default_factory=lambda: _raise_required("identity"))
    declared_capabilities: SnapshotDeclaredCapabilities = field(
        default_factory=SnapshotDeclaredCapabilities,
    )
    payload: SnapshotPayload = field(default_factory=SnapshotPayload)
    integrity: SnapshotIntegrity | None = None

    # ------------------------------------------------------------------
    # Classification helpers
    # ------------------------------------------------------------------

    @property
    def is_base(self) -> bool:
        """``True`` when this document represents a base snapshot."""
        return self.identity.is_base

    @property
    def is_overlay(self) -> bool:
        """``True`` when this document represents an overlay snapshot."""
        return self.identity.is_overlay

    @property
    def editing_history(self) -> SnapshotEditingHistory:
        """Shortcut to ``payload.editing.history``."""
        return self.payload.editing.history

    # ------------------------------------------------------------------
    # Structural predicates
    # ------------------------------------------------------------------

    @property
    def has_base_editing_history(self) -> bool:
        """``True`` when the editing history is empty (base snapshot)."""
        return self.editing_history.is_empty


def new_base_document(
    identity: SnapshotIdentity,
    *,
    payload: SnapshotPayload | None = None,
    declared_capabilities: SnapshotDeclaredCapabilities | None = None,
    integrity: SnapshotIntegrity | None = None,
) -> SnapshotDocument:
    """Create a ``SnapshotDocument`` for a base snapshot.

    Enforces that *identity* satisfies base invariants and that the
    editing history is empty.

    Args:
        identity: A base snapshot identity (``is_base == True``).
        payload: Optional payload (defaults to empty).
        declared_capabilities: Optional declared capabilities.
        integrity: Optional integrity hashes.

    Raises:
        SnapshotIdentityError: If *identity* is not a base identity or the
            payload has a non-empty editing history.
    """
    if not identity.is_base:
        raise SnapshotIdentityError(
            f"Base document requires is_base=True, "
            f"got overlay_version={identity.overlay_version}"
        )
    p = payload if payload is not None else SnapshotPayload()
    if not p.editing.history.is_empty:
        raise SnapshotIdentityError(
            "Base document must have empty editing history"
        )
    return SnapshotDocument(
        identity=identity,
        payload=p,
        declared_capabilities=(
            declared_capabilities or SnapshotDeclaredCapabilities()
        ),
        integrity=integrity,
    )


def new_overlay_document(
    identity: SnapshotIdentity,
    parent_document: SnapshotDocument,
    *,
    payload: SnapshotPayload | None = None,
    declared_capabilities: SnapshotDeclaredCapabilities | None = None,
    integrity: SnapshotIntegrity | None = None,
) -> SnapshotDocument:
    """Create a ``SnapshotDocument`` for an overlay snapshot.

    Enforces that *identity* correctly derives from *parent_document*'s
    identity (same compile_run_id, same base_snapshot_id, exactly
    ``parent_document.overlay_version + 1``, and matching parent snapshot id).

    Args:
        identity: An overlay snapshot identity.
        parent_document: The immediate predecessor snapshot document
            (the base for the first overlay; the previous overlay for
            subsequent overlays).
        payload: Optional payload for the overlay.
        declared_capabilities: Optional declared capabilities.
        integrity: Optional integrity hashes.

    Raises:
        SnapshotIdentityError: If *identity* is not an overlay identity.
        SnapshotLineageError: If *identity* does not derive correctly from
            *parent_document*.
    """
    parent_ident = parent_document.identity

    if not identity.is_overlay:
        raise SnapshotIdentityError(
            f"Overlay document requires is_overlay=True, "
            f"got overlay_version={identity.overlay_version}"
        )
    if identity.compile_run_id != parent_ident.compile_run_id:
        raise SnapshotLineageError(
            f"Overlay compile_run_id {identity.compile_run_id!r} "
            f"!= parent {parent_ident.compile_run_id!r}"
        )
    if identity.base_snapshot_id != parent_ident.base_snapshot_id:
        raise SnapshotLineageError(
            f"Overlay base_snapshot_id {identity.base_snapshot_id!r} "
            f"!= parent {parent_ident.base_snapshot_id!r}"
        )
    expected_version = parent_ident.overlay_version + 1
    if identity.overlay_version != expected_version:
        raise SnapshotLineageError(
            f"Overlay overlay_version must be {expected_version} "
            f"(parent version {parent_ident.overlay_version} + 1), "
            f"got {identity.overlay_version}"
        )
    if identity.parent_snapshot_id != parent_ident.snapshot_id:
        raise SnapshotLineageError(
            f"Overlay parent_snapshot_id {identity.parent_snapshot_id!r} "
            f"!= parent snapshot_id {parent_ident.snapshot_id!r}"
        )
    p = payload if payload is not None else SnapshotPayload()
    return SnapshotDocument(
        identity=identity,
        payload=p,
        declared_capabilities=(
            declared_capabilities or SnapshotDeclaredCapabilities()
        ),
        integrity=integrity,
    )


def _raise_required(field_name: str) -> None:
    """Raise ValueError — *field_name* is required and must be set explicitly."""
    raise ValueError(
        f"SnapshotDocument.{field_name} is required and must be set explicitly"
    )
