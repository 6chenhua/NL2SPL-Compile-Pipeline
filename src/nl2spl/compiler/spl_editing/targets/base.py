"""Target resolver interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairTarget
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot


class IssueTargetResolver(ABC):
    """Resolve an ``EditableIssue`` to a concrete ``RepairTarget``.

    Each resolver handles one or more ``(construct_type, slot_name)``
    pairs.  The resolver is selected by ``target_resolver_id`` from
    the ``RepairCatalogEntry``.
    """

    @property
    @abstractmethod
    def resolver_id(self) -> str:
        """Matches ``RepairCatalogEntry.target_resolver_id``."""

    @abstractmethod
    def resolve(
        self,
        issue: EditableIssue,
        snapshot: ArtifactSnapshot,
    ) -> RepairTarget:
        """Resolve the editable artifact target for *issue*."""
