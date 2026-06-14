"""SnapshotBuilder — constructs SnapshotDocument from pipeline artifacts."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.build.builder import SnapshotBuilder
from nl2spl.compiler.artifacts.snapshot.build.input import SnapshotBuildInput

__all__ = [
    "SnapshotBuildInput",
    "SnapshotBuilder",
]
