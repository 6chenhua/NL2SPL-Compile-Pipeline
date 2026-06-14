"""Schema version validation for snapshot documents."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.constants import SNAPSHOT_SCHEMA_VERSION
from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument
from nl2spl.compiler.artifacts.snapshot.schema import is_schema_compatible


def validate_schema_version(document: SnapshotDocument) -> list[str]:
    """Validate that *document* has a compatible schema version.

    Returns a list of error messages (empty = valid).
    """
    if not is_schema_compatible(document.schema_version):
        return [
            f"Schema version {document.schema_version!r} is not compatible. "
            f"Expected {SNAPSHOT_SCHEMA_VERSION!r} (exact match required)."
        ]
    return []
