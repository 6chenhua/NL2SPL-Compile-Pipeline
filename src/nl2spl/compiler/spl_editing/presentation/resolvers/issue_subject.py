"""Resolve user-facing issue subjects from structured artifacts and source spans."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairTarget,
    UserFacingIssue,
)
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation.model.subject import IssueSubjectView
from nl2spl.compiler.spl_editing.presentation.resolvers.source_excerpt import (
    source_excerpt_for_issue,
)


def issue_subject_for(
    issue: EditableIssue | UserFacingIssue,
    snapshot: ArtifactSnapshot,
    *,
    target: RepairTarget | None = None,
    context: RepairContext | None = None,
    related_diagnostics: tuple[object, ...] = (),
) -> IssueSubjectView:
    """Project identity without parsing diagnostic or feedback prose."""

    source_excerpt = source_excerpt_for_issue(issue, snapshot, related_diagnostics)
    source_ids = tuple(dict.fromkeys(issue.source_span_ids))
    if issue.irs_ref.construct_type != "WORKER_PROMOTION":
        return IssueSubjectView(
            subject_kind="construct",
            display_name=target.canonical_name if target is not None else None,
            source_excerpt=source_excerpt,
            source_ref_ids=source_ids,
            internal_ref=issue.target_ref,
        )

    metadata = context.metadata if context is not None else {}
    child_id = metadata.get("derived_child_worker_id")
    if isinstance(child_id, str) and child_id:
        child = _worker(snapshot, child_id)
        name = getattr(child, "worker_name", None) or child_id
        purpose = getattr(child, "purpose", None)
        return IssueSubjectView(
            subject_kind="worker",
            display_name=name,
            summary=purpose if isinstance(purpose, str) and purpose.strip() else None,
            specificity="concrete",
            source_excerpt=source_excerpt,
            source_ref_ids=source_ids,
            internal_ref=issue.target_ref,
        )

    summary = _structured_candidate_summary(metadata)
    specificity = "candidate" if summary else "ambiguous"
    # A source excerpt is display context, not an inferred worker identity.  It
    # is used as a conservative summary only when no structured candidate
    # summary exists.
    return IssueSubjectView(
        subject_kind="delegated_task_candidate",
        summary=summary or source_excerpt,
        specificity=specificity,
        source_excerpt=source_excerpt,
        source_ref_ids=source_ids,
        internal_ref=issue.target_ref,
    )


def _structured_candidate_summary(metadata: dict) -> str | None:
    for key in ("candidate_task_summary", "delegated_responsibility", "task_summary"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _worker(snapshot: ArtifactSnapshot, worker_id: str):
    plan = snapshot.worker_plan
    if plan is None:
        return None
    return next((worker for worker in plan.workers if worker.worker_id == worker_id), None)


__all__ = ["issue_subject_for"]
