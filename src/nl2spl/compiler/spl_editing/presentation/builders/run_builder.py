"""Run presentation builder."""

from __future__ import annotations

from pathlib import Path

from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation.model.advanced import (
    RunAdvancedDetails,
)
from nl2spl.compiler.spl_editing.presentation.model.issue import (
    IssueCategorySummary,
)
from nl2spl.compiler.spl_editing.presentation.model.run import RunPresentationView


def build_run_presentation(
    *,
    snapshot: ArtifactSnapshot,
    issue_summary: tuple[IssueCategorySummary, ...],
    snapshot_path: Path | None = None,
    run_label: str | None = None,
    editable: bool = True,
    editable_issue_count: int = 0,
    review_issue_count: int = 0,
    deferred_validation_count: int = 0,
    developer_issue_count: int = 0,
) -> RunPresentationView:
    count = sum(item.count for item in issue_summary)
    return RunPresentationView(
        run_id=snapshot.compile_run_id,
        run_label=run_label or snapshot.compile_run_id,
        snapshot_id=snapshot.snapshot_id,
        overlay_version=snapshot.overlay_version,
        snapshot_status="available",
        editable=editable,
        issue_count=count,
        editable_issue_count=editable_issue_count,
        review_issue_count=review_issue_count,
        deferred_validation_count=deferred_validation_count,
        developer_issue_count=developer_issue_count,
        issue_summary=issue_summary,
        advanced=RunAdvancedDetails(
            snapshot_path=str(snapshot_path) if snapshot_path is not None else None,
        ),
    )


__all__ = ["build_run_presentation"]
