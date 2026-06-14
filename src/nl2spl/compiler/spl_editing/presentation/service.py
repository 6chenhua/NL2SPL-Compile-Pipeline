"""Narrow presentation facade for CLI and UI consumers."""

from __future__ import annotations

from pathlib import Path

from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairSuggestion,
    VerificationResult,
)
from nl2spl.compiler.spl_editing.core.service import SPLEditingService
from nl2spl.compiler.spl_editing.presentation.builders import (
    IssuePresentationBuilder,
    build_apply_confirmation,
    build_run_presentation,
    build_suggestion_presentations,
    build_verification_presentation,
)
from nl2spl.compiler.spl_editing.presentation.errors import (
    IssuePresentationNotFoundError,
)
from nl2spl.compiler.spl_editing.presentation.model.confirmation import (
    ApplyConfirmationView,
)
from nl2spl.compiler.spl_editing.presentation.model.issue import (
    IssueDetailPresentationView,
)
from nl2spl.compiler.spl_editing.presentation.model.run import RunPresentationView
from nl2spl.compiler.spl_editing.presentation.model.sections import (
    IssueListPresentationView,
)
from nl2spl.compiler.spl_editing.presentation.model.suggestion import (
    SuggestionPresentationView,
)
from nl2spl.compiler.spl_editing.presentation.model.verification import (
    VerificationPresentationView,
)


class SPLEditingPresentationService:
    """Backend-owned presentation projection service.

    This facade intentionally wraps ``SPLEditingService`` instead of replacing
    repair/session/apply behavior.  It exposes frozen presentation DTOs for
    CLI/UI consumers and keeps raw diagnostics out of default renderers.
    """

    def __init__(self, editing_service: SPLEditingService) -> None:
        self._editing = editing_service
        self._issue_builder = IssuePresentationBuilder(
            catalog=editing_service._catalog,
            runtime=editing_service._runtime,
        )

    def get_run_presentation(
        self,
        run_id: str,
        *,
        run_label: str | None = None,
        snapshot_path: Path | None = None,
    ) -> RunPresentationView:
        snapshot = self._editing._get_snapshot(run_id)
        issue_list = self.list_issue_presentations(run_id)
        editable = any(
            card.can_fix
            for section in issue_list.sections
            for card in section.items
        )
        return build_run_presentation(
            snapshot=snapshot,
            issue_summary=issue_list.summary,
            snapshot_path=snapshot_path,
            run_label=run_label,
            editable=editable,
        )

    def list_run_presentations(self) -> tuple[RunPresentationView, ...]:
        """Return registered runs as presentation DTOs."""
        views: list[RunPresentationView] = []
        for run_id in sorted(self._editing._run_snapshot):
            run_dir = self._editing._run_dirs.get(run_id)
            snapshot_path = (
                Path(run_dir) / "spl_editing_snapshot.json"
                if run_dir is not None
                else None
            )
            views.append(
                self.get_run_presentation(
                    run_id,
                    run_label=Path(run_dir).name if run_dir is not None else run_id,
                    snapshot_path=snapshot_path,
                )
            )
        return tuple(views)

    def list_issue_presentations(
        self,
        run_id: str,
        *,
        include_developer: bool = False,
    ) -> IssueListPresentationView:
        snapshot = self._editing._get_snapshot(run_id)
        issues = self._editing.list_editable_issues(run_id)
        return self._issue_builder.build_list(
            run_id=run_id,
            snapshot=snapshot,
            issues=issues,
            include_developer=include_developer,
        )

    def get_issue_detail_presentation(
        self,
        run_id: str,
        issue_id: str,
    ) -> IssueDetailPresentationView:
        snapshot = self._editing._get_snapshot(run_id)
        issues = self._editing.list_editable_issues(run_id)
        return self._issue_builder.build_detail(
            issue_id=issue_id,
            snapshot=snapshot,
            issues=issues,
        )

    def issue_for_display_id(
        self,
        run_id: str,
        display_id: int,
    ) -> EditableIssue:
        issue_list = self.list_issue_presentations(run_id)
        for section in issue_list.sections:
            for card in section.items:
                if card.display_id == display_id:
                    return self.issue_by_id(run_id, card.issue_id)
        raise IssuePresentationNotFoundError(str(display_id))

    def issue_by_id(
        self,
        run_id: str,
        issue_id: str,
    ) -> EditableIssue:
        for issue in self._editing.list_editable_issues(run_id):
            if issue.issue_id == issue_id:
                return issue
        raise IssuePresentationNotFoundError(issue_id)

    def present_suggestions(
        self,
        suggestions: tuple[RepairSuggestion, ...],
    ) -> tuple[SuggestionPresentationView, ...]:
        return build_suggestion_presentations(suggestions)

    def present_apply_confirmation(
        self,
        suggestion: RepairSuggestion,
    ) -> ApplyConfirmationView:
        return build_apply_confirmation(suggestion)

    def present_verification(
        self,
        run_id: str,
        result: VerificationResult,
        *,
        updated_spl: str | None = None,
    ) -> VerificationPresentationView:
        snapshot = self._editing._get_snapshot(run_id)
        return build_verification_presentation(
            result,
            snapshot=snapshot,
            updated_spl=updated_spl,
        )


__all__ = ["SPLEditingPresentationService"]
