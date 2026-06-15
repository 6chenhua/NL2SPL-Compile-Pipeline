"""Repair handler interface and shared suggestion policy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalogEntry
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairSuggestion,
    RepairTarget,
)


@dataclass(frozen=True)
class SuggestionPolicy:
    """Shared suggestion limits for all handlers.

    Attributes:
        max_suggestions: Maximum unique suggestions to return (target).
        max_attempts_ratio: Multiplier on *max_suggestions* for total
            LLM call attempts.  Handlers retry up to
            ``max_suggestions * max_attempts_ratio`` times to fill
            the target despite duplicates and parse failures.
    """

    max_suggestions: int = 3
    max_attempts_ratio: int = 3


class IssueRepairHandler(ABC):
    """Generate repair suggestions for one diagnostic family.

    Each handler maps to a ``handler_id`` from the ``RepairCatalog``
    (e.g. ``"missing_handler"``, ``"missing_output_producer"``).

    Handlers must NOT import patch appliers and must NOT write IR.
    """

    @property
    @abstractmethod
    def handler_id(self) -> str: ...

    @property
    @abstractmethod
    def policy(self) -> SuggestionPolicy: ...

    @abstractmethod
    def generate_suggestions(
        self,
        issue: EditableIssue,
        target: RepairTarget,
        context: RepairContext,
        catalog_entries: tuple[RepairCatalogEntry, ...],
        user_instruction: str | None = None,
        selected_patch_types: tuple[str, ...] | None = None,
        *,
        rendered_user_prompt: str | None = None,
    ) -> tuple[RepairSuggestion, ...]: ...
