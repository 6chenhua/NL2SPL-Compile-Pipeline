"""Presentation section keys."""

from __future__ import annotations

from enum import StrEnum


class IssueSectionKind(StrEnum):
    EDITABLE = "editable"
    REVIEW_NEEDED = "review_needed"
    DEFERRED_VALIDATION = "deferred_validation"
    DEVELOPER_DIAGNOSTICS = "developer_diagnostics"


class IssueSectionKey(StrEnum):
    EDITABLE_ISSUES = "editable_issues"
    REVIEW_NEEDED = "review_needed"
    DEFERRED_VALIDATION = "deferred_validation"
    DEVELOPER_DIAGNOSTICS = "developer_diagnostics"


__all__ = ["IssueSectionKey", "IssueSectionKind"]
