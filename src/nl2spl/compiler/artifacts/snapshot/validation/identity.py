"""Identity validation — delegates to S0 identity validators, adds producer check."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.constants import PRODUCER_NAME
from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument
from nl2spl.compiler.artifacts.snapshot.model.identity import (
    validate_base_identity,
)


def validate_identity(document: SnapshotDocument) -> list[str]:
    """Validate the identity section of *document*.

    For base snapshots: ensures ``overlay_version == 0``, no parent, etc.
    For overlay snapshots: ensures ``overlay_version > 0``, parent lineage ok.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    ident = document.identity

    # Producer check
    if ident.producer != PRODUCER_NAME:
        errors.append(
            f"identity.producer must be {PRODUCER_NAME!r}, got {ident.producer!r}"
        )

    # Created-at check
    if not ident.created_at:
        errors.append("identity.created_at must not be empty")

    # Base vs overlay invariants
    if ident.is_base:
        errors.extend(validate_base_identity(ident))
    elif ident.is_overlay:
        # For overlay: parent_snapshot_id must be set, version > 0
        if ident.parent_snapshot_id is None:
            errors.append("Overlay snapshot must have a non-None parent_snapshot_id")
        if ident.overlay_version <= 0:
            errors.append(
                f"Overlay snapshot overlay_version must be > 0, "
                f"got {ident.overlay_version}"
            )
    return errors
