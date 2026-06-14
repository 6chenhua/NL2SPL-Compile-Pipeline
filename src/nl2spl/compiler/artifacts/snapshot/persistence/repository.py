"""SnapshotRepository protocol — the boundary between storage and SPL Editing.

All repository implementations (file-backed, DB-backed) must satisfy this
protocol.  SPL Editing services depend on this protocol, never on concrete
file paths or DB connections.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument


class SnapshotRepository(ABC):
    """Abstract repository for snapshot persistence.

    Implementations:
    - ``JsonFileSnapshotRepository`` — local JSON files (MVP).
    - ``DatabaseSnapshotRepository`` — DB JSON/JSONB column (future).
    """

    @abstractmethod
    def save(self, document: SnapshotDocument, path: Path) -> None:
        """Persist *document* as a canonical JSON file at *path*.

        Must validate the document via S2 before writing.  Must write
        atomically (write to temp + rename) to avoid partial writes.
        """
        ...

    @abstractmethod
    def load(self, path: Path) -> dict[str, Any]:
        """Load and validate a snapshot JSON file from *path*.

        Returns the raw validated canonical dict.  The caller is
        responsible for reconstructing typed ``SnapshotDocument``
        accessors from this dict if needed.

        Raises:
            FileNotFoundError: *path* does not exist.
            ValueError: JSON is invalid or S2 validation fails.
        """
        ...

    @abstractmethod
    def save_overlay(
        self, document: SnapshotDocument, path: Path,
    ) -> None:
        """Persist an overlay *document* at *path*.

        Same atomic-write semantics as ``save``.
        """
        ...
