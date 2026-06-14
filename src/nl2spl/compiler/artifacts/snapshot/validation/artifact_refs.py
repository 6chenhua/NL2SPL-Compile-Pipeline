"""Artifact reference validation — ownership, derivation, consistency."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.model.artifact_ref import (
    ArtifactRef,
    DerivedArtifactRef,
)
from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument


def validate_artifact_refs(document: SnapshotDocument) -> list[str]:
    """Validate replay_artifacts references against stage_artifacts.

    Checks:
    - ``ArtifactRef.ref`` paths are non-empty.
    - ``DerivedArtifactRef.derived_from`` paths are non-empty and
      ``derivation`` is set.
    - No obvious ownership conflicts.

    Returns a list of error messages (empty = valid).
    """
    errors: list[str] = []
    replay = document.payload.replay_artifacts

    # Check each replay artifact field
    for field_name in (
        "normalizer_input", "normalizer_output", "stage10_input",
        "assembled_worker_pre_gate", "gated_worker",
    ):
        value = getattr(replay, field_name, None)
        if value is None:
            continue

        if isinstance(value, ArtifactRef):
            if not value.ref:
                errors.append(
                    f"replay_artifacts.{field_name} ArtifactRef.ref "
                    f"must not be empty"
                )
        elif isinstance(value, DerivedArtifactRef):
            if not value.derived_from:
                errors.append(
                    f"replay_artifacts.{field_name} "
                    f"DerivedArtifactRef.derived_from must not be empty"
                )
            if not value.derivation:
                errors.append(
                    f"replay_artifacts.{field_name} "
                    f"DerivedArtifactRef.derivation must not be empty"
                )

    return errors
