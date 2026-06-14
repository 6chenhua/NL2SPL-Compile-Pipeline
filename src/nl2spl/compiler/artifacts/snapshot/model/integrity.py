"""Snapshot integrity — hash container.

Holds ``payload_hash`` and ``artifact_set_hash`` as a frozen pair.
Hash computation is performed by the S2 validator; S0 only defines
the structural container.
"""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.artifacts.snapshot.constants import (
    INTEGRITY_ARTIFACT_SET_HASH,
    INTEGRITY_PAYLOAD_HASH,
)
from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotIntegrityError


@dataclass(frozen=True)
class SnapshotIntegrity:
    """Hash pair for storage and semantic integrity verification.

    Attributes:
        payload_hash: Complete canonical JSON payload hash
            (``sha256:...``).  Covers the full document including
            volatile fields.  Used to detect storage corruption.
        artifact_set_hash: Semantic compiler artifact hash
            (``sha256:...``).  Covers only the core compiler artifacts
            that affect issue extraction, replay, and verification.
            Excludes ``created_at``, validation status/errors, and
            overlay editing history.
    """

    payload_hash: str
    artifact_set_hash: str

    def __post_init__(self) -> None:
        if not self.payload_hash:
            raise SnapshotIntegrityError(f"{INTEGRITY_PAYLOAD_HASH} must not be empty")
        if not self.artifact_set_hash:
            raise SnapshotIntegrityError(
                f"{INTEGRITY_ARTIFACT_SET_HASH} must not be empty"
            )
