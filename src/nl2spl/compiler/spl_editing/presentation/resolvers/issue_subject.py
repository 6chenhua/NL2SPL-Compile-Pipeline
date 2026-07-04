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
from nl2spl.compiler.spl_editing.resolution.model import (
    validate_promotion_resolution_marker,
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
    marker = _valid_marker(snapshot, issue.target_ref)
    if marker is not None and marker.resolution_kind == "defined_child_worker":
        child_id = _child_worker_id_from_marker(marker)
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
    if marker is not None and marker.resolution_kind == "kept_in_main_flow":
        summary = _structured_candidate_summary(metadata)
        return IssueSubjectView(
            subject_kind="delegated_task_candidate",
            summary=summary or source_excerpt,
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


def _valid_marker(snapshot: ArtifactSnapshot, target_ref: str):
    for marker in snapshot.promotion_resolution_markers:
        if validate_promotion_resolution_marker(marker, target_ref).valid:
            return marker
    return None


def _child_worker_id_from_marker(marker) -> str:
    for ref in marker.materialized_construct_refs:
        if isinstance(ref, str) and ref.startswith("worker:"):
            return ref.removeprefix("worker:")
    return ""


__all__ = ["issue_subject_for"]
