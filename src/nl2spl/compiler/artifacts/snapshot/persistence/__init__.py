"""Snapshot persistence — repository boundary for loading/saving snapshots."""

from __future__ import annotations

from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
    JsonFileSnapshotRepository,
)
from nl2spl.compiler.artifacts.snapshot.persistence.loader import SnapshotLoader
from nl2spl.compiler.artifacts.snapshot.persistence.repository import (
    SnapshotRepository,
)

__all__ = [
    "SnapshotRepository",
    "JsonFileSnapshotRepository",
    "SnapshotLoader",
]
