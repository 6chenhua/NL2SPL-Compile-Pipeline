"""Neutral snapshot data models — compiler-owned, no SPL Editing dependencies.

Every type in this package is a frozen dataclass that defines structure,
not business logic.  Serialization, validation logic, and persistence
live in sibling packages (``serialization/``, ``validation/``,
``persistence/``).
"""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import (
    ArtifactRef,
    DerivedArtifactRef,
)
from nl2spl.compiler.artifacts.snapshot.model.document import (
    SnapshotDocument,
    new_base_document,
    new_overlay_document,
)
from nl2spl.compiler.artifacts.snapshot.model.editing_history import (
    SnapshotAcceptedPatchDTO,
    SnapshotEditingHistory,
    SnapshotOverlayEventDTO,
    SnapshotVerificationRecordDTO,
    empty_editing_history,
)
from nl2spl.compiler.artifacts.snapshot.model.errors import (
    SnapshotArtifactRefError,
    SnapshotCapabilityError,
    SnapshotError,
    SnapshotIdentityError,
    SnapshotIntegrityError,
    SnapshotLineageError,
    SnapshotSchemaError,
)
from nl2spl.compiler.artifacts.snapshot.model.identity import (
    SnapshotIdentity,
    new_base_identity,
    new_overlay_identity,
    validate_base_identity,
    validate_overlay_lineage,
)
from nl2spl.compiler.artifacts.snapshot.model.integrity import SnapshotIntegrity
from nl2spl.compiler.artifacts.snapshot.model.payload import (
    DiagnosticsLayer,
    EditingLayer,
    ProvenanceLayer,
    ReplayArtifactsLayer,
    SnapshotPayload,
    SourceLayer,
    StageArtifactsLayer,
)
from nl2spl.compiler.artifacts.snapshot.model.validation import (
    SnapshotCapabilityFailure,
    SnapshotDeclaredCapabilities,
    SnapshotEffectiveCapabilities,
    SnapshotValidationResult,
)

__all__ = [
    # ── document ──
    "SnapshotDocument",
    "new_base_document",
    "new_overlay_document",
    # ── identity ──
    "SnapshotIdentity",
    "new_base_identity",
    "new_overlay_identity",
    "validate_base_identity",
    "validate_overlay_lineage",
    # ── payload ──
    "SnapshotPayload",
    "SourceLayer",
    "StageArtifactsLayer",
    "ReplayArtifactsLayer",
    "DiagnosticsLayer",
    "ProvenanceLayer",
    "EditingLayer",
    # ── artifact_ref ──
    "ArtifactRef",
    "DerivedArtifactRef",
    # ── integrity ──
    "SnapshotIntegrity",
    # ── validation ──
    "SnapshotDeclaredCapabilities",
    "SnapshotEffectiveCapabilities",
    "SnapshotCapabilityFailure",
    "SnapshotValidationResult",
    # ── editing_history ──
    "SnapshotEditingHistory",
    "SnapshotOverlayEventDTO",
    "SnapshotAcceptedPatchDTO",
    "SnapshotVerificationRecordDTO",
    "empty_editing_history",
    # ── errors ──
    "SnapshotError",
    "SnapshotIdentityError",
    "SnapshotLineageError",
    "SnapshotCapabilityError",
    "SnapshotIntegrityError",
    "SnapshotSchemaError",
    "SnapshotArtifactRefError",
]
