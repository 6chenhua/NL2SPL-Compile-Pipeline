"""Structured issue subject projection DTOs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class IssueSubjectView:
    subject_kind: Literal[
        "construct",
        "delegated_task_candidate",
        "worker",
        "output",
        "exception_condition",
        "api",
        "unknown",
    ]
    display_name: str | None = None
    summary: str | None = None
    specificity: Literal["concrete", "candidate", "ambiguous", "unknown"] = "unknown"
    source_excerpt: str | None = None
    source_ref_ids: tuple[str, ...] = ()
    internal_ref: str | None = None


__all__ = ["IssueSubjectView"]
