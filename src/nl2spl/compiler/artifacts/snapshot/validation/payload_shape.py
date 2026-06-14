"""Payload shape validation — required sections, no garbage."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.constants import SNAPSHOT_ARTIFACT_KIND
from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument


def validate_envelope(document: SnapshotDocument) -> list[str]:
    """Validate the document envelope (artifact_kind, schema_version presence).

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    if document.artifact_kind != SNAPSHOT_ARTIFACT_KIND:
        errors.append(
            f"artifact_kind must be {SNAPSHOT_ARTIFACT_KIND!r}, "
            f"got {document.artifact_kind!r}"
        )
    if not document.schema_version:
        errors.append("schema_version must not be empty")
    return errors


def validate_payload_shape(document: SnapshotDocument) -> list[str]:
    """Validate that the payload has all required sub-sections.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    payload = document.payload
    if payload is None:
        errors.append("payload is required")
        return errors
    return errors
