"""Artifact reference model for replay artifact ownership.

Distinguishes between:
    - ``ArtifactRef``: A reference to an artifact owned by ``stage_artifacts``.
    - ``DerivedArtifactRef``: A replay artifact that was derived from a
      ``stage_artifacts`` entry (e.g., normalizer output).

These types enforce the ownership rules from the design:
    - ``stage_artifacts`` is the canonical editable owner.
    - ``replay_artifacts`` must record ``source_ref`` or ``derived_from``.
"""

from __future__ import annotations

from dataclasses import dataclass

from nl2spl.compiler.artifacts.snapshot.model.errors import SnapshotArtifactRefError

# ---------------------------------------------------------------------------
# ArtifactRef — reference to an owned artifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ArtifactRef:
    """A reference to a ``stage_artifacts`` artifact.

    Used by ``replay_artifacts`` entries that share the same object as
    their ``stage_artifacts`` counterpart (no copy).

    Attributes:
        ref: Dotted path to the artifact, e.g.
            ``"payload.stage_artifacts.worker_step_plan"``.
        artifact_hash: ``sha256:...`` of the referenced artifact.
    """

    ref: str
    artifact_hash: str

    def __post_init__(self) -> None:
        if not self.ref:
            raise SnapshotArtifactRefError("ArtifactRef.ref must not be empty")
        if not self.artifact_hash:
            raise SnapshotArtifactRefError("ArtifactRef.artifact_hash must not be empty")


# ---------------------------------------------------------------------------
# DerivedArtifactRef — a derived/copied replay artifact
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DerivedArtifactRef:
    """A replay artifact that was derived from a ``stage_artifacts`` entry.

    Normalizer output, assembled workers, and other pipeline products that
    are *derived from* (not identical to) editable stage artifacts must use
    this type to declare their lineage.

    Attributes:
        derived_from: Dotted path to the source artifact in ``stage_artifacts``.
        derivation: Pipeline stage that produced this artifact
            (e.g. ``"stage9_5_normalized"``, ``"stage10_assembled"``).
        artifact_hash: ``sha256:...`` of this derived artifact.
    """

    derived_from: str
    derivation: str
    artifact_hash: str

    def __post_init__(self) -> None:
        if not self.derived_from:
            raise SnapshotArtifactRefError("DerivedArtifactRef.derived_from must not be empty")
        if not self.derivation:
            raise SnapshotArtifactRefError("DerivedArtifactRef.derivation must not be empty")
        if not self.artifact_hash:
            raise SnapshotArtifactRefError("DerivedArtifactRef.artifact_hash must not be empty")
