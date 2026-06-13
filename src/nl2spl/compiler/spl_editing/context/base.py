"""Repair context builder interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot


class RepairContextBuilder(ABC):
    """Gather issue-specific data for a repair handler.

    Each builder handles one ``context_id`` (from
    ``RepairCatalogEntry.context_id``) and produces a ``RepairContext``
    scoped to the target issue.
    """

    @property
    @abstractmethod
    def context_id(self) -> str: ...

    @abstractmethod
    def build(
        self,
        issue: EditableIssue,
        target: RepairTarget,
        snapshot: ArtifactSnapshot,
        user_instruction: str | None = None,
    ) -> RepairContext: ...
