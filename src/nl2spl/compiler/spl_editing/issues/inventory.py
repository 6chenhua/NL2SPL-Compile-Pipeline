"""Complete issue inventory extraction.

Editable issues remain RepairCatalog-driven.  Non-editable user-facing issues
are extracted from explicit structured metadata such as
``presentation_disposition=deferred_validation``; diagnostic kind alone is not
used to make an issue fixable.
"""

from __future__ import annotations

from collections import defaultdict

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalog
from nl2spl.compiler.spl_editing.core.model import IssueInventory, UserFacingIssue
from nl2spl.compiler.spl_editing.issues.extractor import EditableIssueExtractor
from nl2spl.ir.diagnostics import (
    METADATA_KEY_AUTHORITY,
    METADATA_KEY_IRS_REF,
    METADATA_KEY_ISSUE_GROUP_ID,
    METADATA_KEY_ISSUE_ROLE,
    METADATA_KEY_PRESENTATION_DISPOSITION,
    METADATA_KEY_REPAIRABILITY,
    METADATA_KEY_VALIDATION_AUTHORITY,
    CompileDiagnostic,
    DiagnosticIRSRef,
)

_API_DEFERRED_SLOT_ORDER: dict[str, int] = {
    "functions": 0,
    "openapi_schema": 1,
    "authentication": 2,
}


class IssueInventoryExtractor:
    """Extract complete SPL Editing issue inventory.

    The editable partition delegates to ``EditableIssueExtractor``.  Deferred
    and review partitions are built only from explicit metadata and never gain
    repair affordances.
    """

    def __init__(self, catalog: RepairCatalog) -> None:
        self._editable_extractor = EditableIssueExtractor(catalog)

    def extract(self, diagnostics: list[CompileDiagnostic]) -> IssueInventory:
        editable = self._editable_extractor.extract(diagnostics)
        editable_diag_ids = {
            diagnostic_id
            for issue in editable
            for diagnostic_id in issue.related_diagnostic_ids
        }

        grouped: dict[str, list[CompileDiagnostic]] = defaultdict(list)
        developer: list[UserFacingIssue] = []

        for diagnostic in diagnostics:
            if diagnostic.diagnostic_id in editable_diag_ids:
                continue
            if not _has_structured_irs_ref(diagnostic):
                continue
            disposition = _disposition_for_diagnostic(diagnostic)
            if disposition is None:
                continue
            group_id = _group_id_for(diagnostic)
            grouped[group_id].append(diagnostic)

        review: list[UserFacingIssue] = []
        deferred: list[UserFacingIssue] = []
        for group in grouped.values():
            issue = _build_user_facing_issue(group)
            if issue is None:
                fallback = _build_developer_issue(group)
                if fallback is not None:
                    developer.append(fallback)
                continue
            if issue.disposition == "deferred_validation":
                deferred.append(issue)
            elif issue.disposition == "developer_only":
                developer.append(issue)
            else:
                review.append(issue)

        return IssueInventory(
            editable=editable,
            review=tuple(sorted(review, key=lambda issue: issue.issue_id)),
            deferred=tuple(sorted(deferred, key=lambda issue: issue.issue_id)),
            developer=tuple(sorted(developer, key=lambda issue: issue.issue_id)),
        )


def _has_structured_irs_ref(diagnostic: CompileDiagnostic) -> bool:
    return _coerce_irs_ref(diagnostic) is not None


def _coerce_irs_ref(diagnostic: CompileDiagnostic) -> DiagnosticIRSRef | None:
    irs_ref = diagnostic.metadata.get(METADATA_KEY_IRS_REF)
    if isinstance(irs_ref, DiagnosticIRSRef):
        return irs_ref
    if isinstance(irs_ref, dict) and irs_ref.get("construct_type"):
        return DiagnosticIRSRef.from_dict(irs_ref)
    return None


def _disposition_for_diagnostic(diagnostic: CompileDiagnostic) -> str | None:
    presentation = diagnostic.metadata.get(METADATA_KEY_PRESENTATION_DISPOSITION)
    if presentation == "deferred_validation":
        return "deferred_validation"
    repairability = diagnostic.metadata.get(METADATA_KEY_REPAIRABILITY)
    if repairability == "review_only":
        return "review_only"
    if repairability in {"non_repairable", "developer_only"}:
        return "developer_only"
    return None


def _group_id_for(diagnostic: CompileDiagnostic) -> str:
    group_id = diagnostic.metadata.get(METADATA_KEY_ISSUE_GROUP_ID)
    if isinstance(group_id, str) and group_id:
        return group_id
    return diagnostic.diagnostic_id


def _build_user_facing_issue(
    group: list[CompileDiagnostic],
) -> UserFacingIssue | None:
    if not group:
        return None
    primaries = [d for d in group if d.metadata.get(METADATA_KEY_ISSUE_ROLE) == "primary"]
    if len(primaries) > 1:
        return None
    ordered = sorted(group, key=_diagnostic_sort_key)
    primary = primaries[0] if len(primaries) == 1 else ordered[0]
    irs_ref = _coerce_irs_ref(primary)
    if irs_ref is None:
        return None
    disposition = _disposition_for_diagnostic(primary)
    if disposition is None:
        disposition = _disposition_for_diagnostic(ordered[0])
    if disposition is None:
        return None
    related_ids = tuple(sorted(d.diagnostic_id for d in group))
    source_span_ids = tuple(sorted({span for d in group for span in d.source_span_ids}))
    missing_slot_name = primary.missing_slot.slot_name if primary.missing_slot else None
    repairability = (
        "developer_only"
        if disposition == "developer_only"
        else "review_only"
    )
    return UserFacingIssue(
        issue_id=primary.diagnostic_id,
        primary_diagnostic_id=primary.diagnostic_id,
        related_diagnostic_ids=related_ids,
        issue_group_id=primary.metadata.get(METADATA_KEY_ISSUE_GROUP_ID),
        kind=primary.kind,
        target_ref=primary.target_ref or primary.diagnostic_id,
        irs_ref=irs_ref,
        missing_slot=missing_slot_name,
        source_span_ids=source_span_ids,
        message=primary.message,
        suggested_resolution=primary.suggested_resolution,
        blocks_rendering=primary.blocks_rendering,
        blocks_completion=primary.blocks_completion,
        authority=str(primary.metadata.get(METADATA_KEY_AUTHORITY, "post_normalize_irs")),
        repairable=False,
        repairability=repairability,
        disposition=disposition,  # type: ignore[arg-type]
        presentation_disposition=_presentation_disposition(primary),
        validation_authority=_validation_authority(primary),
    )


def _build_developer_issue(group: list[CompileDiagnostic]) -> UserFacingIssue | None:
    ordered = sorted(group, key=_diagnostic_sort_key)
    if not ordered:
        return None
    primary = ordered[0]
    irs_ref = _coerce_irs_ref(primary)
    if irs_ref is None:
        return None
    return UserFacingIssue(
        issue_id=primary.diagnostic_id,
        primary_diagnostic_id=primary.diagnostic_id,
        related_diagnostic_ids=tuple(sorted(d.diagnostic_id for d in group)),
        issue_group_id=primary.metadata.get(METADATA_KEY_ISSUE_GROUP_ID),
        kind=primary.kind,
        target_ref=primary.target_ref or primary.diagnostic_id,
        irs_ref=irs_ref,
        missing_slot=primary.missing_slot.slot_name if primary.missing_slot else None,
        source_span_ids=tuple(sorted({span for d in group for span in d.source_span_ids})),
        message=primary.message,
        blocks_rendering=primary.blocks_rendering,
        blocks_completion=primary.blocks_completion,
        authority=str(primary.metadata.get(METADATA_KEY_AUTHORITY, "post_normalize_irs")),
        repairability="developer_only",
        disposition="developer_only",
    )


def _diagnostic_sort_key(diagnostic: CompileDiagnostic) -> tuple[int, str]:
    slot_name = diagnostic.missing_slot.slot_name if diagnostic.missing_slot else ""
    return (_API_DEFERRED_SLOT_ORDER.get(slot_name, 99), diagnostic.diagnostic_id)


def _presentation_disposition(diagnostic: CompileDiagnostic) -> str | None:
    value = diagnostic.metadata.get(METADATA_KEY_PRESENTATION_DISPOSITION)
    return value if isinstance(value, str) else None


def _validation_authority(diagnostic: CompileDiagnostic) -> str | None:
    value = diagnostic.metadata.get(METADATA_KEY_VALIDATION_AUTHORITY)
    return value if isinstance(value, str) else None


__all__ = ["IssueInventoryExtractor"]
