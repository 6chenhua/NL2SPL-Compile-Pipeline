"""Suggested resolution resolver.

Suggested resolution is informational only.  It never determines repair option
availability.
"""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import EditableIssue, UserFacingIssue


def suggested_resolution_for_issue(
    issue: EditableIssue | UserFacingIssue,
    related_diagnostics: tuple[object, ...] = (),
) -> str | None:
    if issue.suggested_resolution:
        return issue.suggested_resolution
    for diagnostic in related_diagnostics:
        value = getattr(diagnostic, "suggested_resolution", None)
        if isinstance(value, str) and value.strip():
            return value
    return None


__all__ = ["suggested_resolution_for_issue"]
