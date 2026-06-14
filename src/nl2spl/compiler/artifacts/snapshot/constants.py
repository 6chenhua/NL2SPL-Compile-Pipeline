"""Frozen constants for the SPL Editing artifact snapshot contract.

All downstream modules MUST import these constants.  Redefining identical
string literals in other modules is forbidden -- the S-1 test suite enforces
this by verifying that every constant defined here is the single source of
truth.
"""

from __future__ import annotations

from enum import Enum

# ---------------------------------------------------------------------------
# Artifact kind -- identifies the JSON document as a canonical snapshot
# ---------------------------------------------------------------------------

SNAPSHOT_ARTIFACT_KIND: str = "spl_editing_artifact_snapshot"
"""The ``artifact_kind`` value written into every snapshot JSON document."""

# ---------------------------------------------------------------------------
# Schema version -- compatibility gate
# ---------------------------------------------------------------------------

SNAPSHOT_SCHEMA_VERSION: str = "1.0.0"
"""Current snapshot schema version.  MVP uses exact-match compatibility."""

# ---------------------------------------------------------------------------
# Top-level JSON section names
# ---------------------------------------------------------------------------

SECTION_ARTIFACT_KIND: str = "artifact_kind"
SECTION_SCHEMA_VERSION: str = "schema_version"
SECTION_IDENTITY: str = "identity"
SECTION_CAPABILITIES: str = "capabilities"
SECTION_PAYLOAD: str = "payload"
SECTION_INTEGRITY: str = "integrity"

TOP_LEVEL_SECTIONS: tuple[str, ...] = (
    SECTION_ARTIFACT_KIND,
    SECTION_SCHEMA_VERSION,
    SECTION_IDENTITY,
    SECTION_CAPABILITIES,
    SECTION_PAYLOAD,
    SECTION_INTEGRITY,
)
"""Required top-level keys in every snapshot JSON document, in canonical order."""

# ---------------------------------------------------------------------------
# Payload sub-section names
# ---------------------------------------------------------------------------

PAYLOAD_SOURCE: str = "source"
PAYLOAD_STAGE_ARTIFACTS: str = "stage_artifacts"
PAYLOAD_REPLAY_ARTIFACTS: str = "replay_artifacts"
PAYLOAD_DIAGNOSTICS: str = "diagnostics"
PAYLOAD_PROVENANCE: str = "provenance"
PAYLOAD_EDITING: str = "editing"

PAYLOAD_SECTIONS: tuple[str, ...] = (
    PAYLOAD_SOURCE,
    PAYLOAD_STAGE_ARTIFACTS,
    PAYLOAD_REPLAY_ARTIFACTS,
    PAYLOAD_DIAGNOSTICS,
    PAYLOAD_PROVENANCE,
    PAYLOAD_EDITING,
)
"""Payload sub-sections in canonical order."""

# ---------------------------------------------------------------------------
# Identity field names
# ---------------------------------------------------------------------------

IDENTITY_COMPILE_RUN_ID: str = "compile_run_id"
IDENTITY_SNAPSHOT_ID: str = "snapshot_id"
IDENTITY_BASE_SNAPSHOT_ID: str = "base_snapshot_id"
IDENTITY_PARENT_SNAPSHOT_ID: str = "parent_snapshot_id"
IDENTITY_OVERLAY_VERSION: str = "overlay_version"
IDENTITY_CREATED_AT: str = "created_at"
IDENTITY_PRODUCER: str = "producer"
IDENTITY_PRODUCER_VERSION: str = "producer_version"

IDENTITY_FIELDS: tuple[str, ...] = (
    IDENTITY_COMPILE_RUN_ID,
    IDENTITY_SNAPSHOT_ID,
    IDENTITY_BASE_SNAPSHOT_ID,
    IDENTITY_PARENT_SNAPSHOT_ID,
    IDENTITY_OVERLAY_VERSION,
    IDENTITY_CREATED_AT,
    IDENTITY_PRODUCER,
    IDENTITY_PRODUCER_VERSION,
)
"""Identity fields in canonical order."""

# ---------------------------------------------------------------------------
# Integrity field names
# ---------------------------------------------------------------------------

INTEGRITY_PAYLOAD_HASH: str = "payload_hash"
INTEGRITY_ARTIFACT_SET_HASH: str = "artifact_set_hash"

# ---------------------------------------------------------------------------
# Snapshot persistence mode
# ---------------------------------------------------------------------------


class SnapshotMode(str, Enum):  # noqa: UP042
    """Controls whether and how snapshot persistence occurs during a compile run.

    Attributes:
        DISABLED: No snapshot is written.  ``PipelineResult`` status is
            ``NOT_REQUESTED``.
        BEST_EFFORT: Snapshot is written if possible.  Failure does not
            block the compile run.  Status is ``FAILED_BEST_EFFORT`` on
            error, and SPL Editing is unavailable for that run.
        REQUIRED: Snapshot MUST be produced.  Failure blocks the editing
            flow (but may or may not block the compile run depending on
            consumer policy).
    """

    DISABLED = "disabled"
    BEST_EFFORT = "best_effort"
    REQUIRED = "required"


# ---------------------------------------------------------------------------
# Snapshot status -- reported via PipelineResult
# ---------------------------------------------------------------------------


class SnapshotStatus(str, Enum):  # noqa: UP042
    """Status of the snapshot artifact as reported by ``PipelineResult``.

    These values are the ONLY allowed values for
    ``PipelineResult.spl_editing_snapshot_status``.
    """

    NOT_REQUESTED = "not_requested"
    """Snapshot persistence was not configured (mode=disabled)."""

    AVAILABLE = "available"
    """A valid snapshot was successfully written and is ready for SPL Editing."""

    FAILED_BEST_EFFORT = "failed_best_effort"
    """Snapshot writing failed in best_effort mode.  Compile succeeded but
    SPL Editing is unavailable for this run."""

    FAILED_REQUIRED = "failed_required"
    """Snapshot writing failed in required mode.  The editing flow is blocked."""


# ---------------------------------------------------------------------------
# Overlay version sentinel
# ---------------------------------------------------------------------------

BASE_OVERLAY_VERSION: int = 0
"""Every base (non-overlay) snapshot MUST have ``overlay_version = 0``."""

# ---------------------------------------------------------------------------
# Producer identity
# ---------------------------------------------------------------------------

PRODUCER_NAME: str = "nl2spl"
"""Canonical producer name written into snapshot identity."""
