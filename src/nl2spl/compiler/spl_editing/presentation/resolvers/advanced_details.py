"""Advanced diagnostic detail projection."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import EditableIssue, UserFacingIssue
from nl2spl.compiler.spl_editing.presentation.model.advanced import (
    IssueAdvancedDetails,
)


def build_advanced_details(
    issue: EditableIssue | UserFacingIssue,
    related_diagnostics: tuple[object, ...] = (),
) -> IssueAdvancedDetails:
    metadata = _repairability_metadata(issue, related_diagnostics)
    return IssueAdvancedDetails(
        primary_diagnostic_id=issue.primary_diagnostic_id,
        related_diagnostic_ids=issue.related_diagnostic_ids,
        diagnostic_kind=issue.kind,
        target_ref=issue.target_ref,
        irs_construct_type=issue.irs_ref.construct_type,
        irs_construct_id=issue.irs_ref.construct_id,
        irs_slot_name=issue.irs_ref.slot_name,
        authority=issue.authority,
        repairability_metadata=metadata,
    )


def _repairability_metadata(
    issue: EditableIssue | UserFacingIssue,
    related_diagnostics: tuple[object, ...],
) -> tuple[tuple[str, str], ...]:
    values: dict[str, str] = {"repairability": issue.repairability}
    for diagnostic in related_diagnostics:
        meta = getattr(diagnostic, "metadata", {})
        if isinstance(meta, dict):
            for key in ("repairability", "issue_role", "issue_group_id"):
                value = meta.get(key)
                if value is not None:
                    values.setdefault(key, str(value))
    return tuple(sorted(values.items()))


__all__ = ["build_advanced_details"]
