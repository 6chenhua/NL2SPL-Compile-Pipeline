"""Validated snapshot document loader.

This module is the persistence-facing typed loader.  It validates canonical
JSON through the repository, then reconstructs a ``SnapshotDocument``.  It does
not import SPL Editing runtime objects.
"""

from __future__ import annotations

from pathlib import Path

from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument
from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
    JsonFileSnapshotRepository,
)


class SnapshotLoader:
    """Load canonical snapshot JSON into typed ``SnapshotDocument`` values."""

    def __init__(self, repository: JsonFileSnapshotRepository | None = None) -> None:
        self._repository = repository or JsonFileSnapshotRepository()

    def load(self, path: Path) -> SnapshotDocument:
        """Load and validate one canonical snapshot file.

        Invalid snapshots never produce a ``SnapshotDocument``.
        """
        data = self._repository.load(path)
        return self._repository.document_from_dict(data)

    def load_run_dir(
        self,
        run_dir: Path,
        *,
        filename: str = "spl_editing_snapshot.json",
    ) -> SnapshotDocument:
        """Load ``filename`` from a compile output directory."""
        return self.load(Path(run_dir) / filename)
