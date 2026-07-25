"""Scheduling boundary for asynchronous issue explanations."""

from __future__ import annotations

from concurrent.futures import Future
from pathlib import Path
from typing import Protocol

from nl2spl.compiler.spl_editing.presentation.ai_explainer import IssueExplanationLLM
from nl2spl.compiler.spl_editing.presentation.explanation_cache import (
    ExplanationPrecomputeResult,
    schedule_issue_explanations,
)


class ExplanationScheduler(Protocol):
    """Schedule snapshot-level explanation generation without exposing an LLM to routes."""

    def schedule(self, snapshot_path: Path) -> Future[ExplanationPrecomputeResult]: ...


class SnapshotExplanationScheduler:
    """Public adapter around the snapshot-level explanation batch scheduler."""

    def __init__(
        self,
        llm: IssueExplanationLLM,
        *,
        language: str = "zh-CN",
        max_workers: int = 4,
    ) -> None:
        self._llm = llm
        self._language = language
        self._max_workers = max_workers

    def schedule(self, snapshot_path: Path) -> Future[ExplanationPrecomputeResult]:
        return schedule_issue_explanations(
            snapshot_path,
            self._llm,
            language=self._language,
            max_workers=self._max_workers,
        )


__all__ = ["ExplanationScheduler", "SnapshotExplanationScheduler"]
