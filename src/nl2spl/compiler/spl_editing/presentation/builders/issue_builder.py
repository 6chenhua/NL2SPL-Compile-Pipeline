"""Issue presentation builder orchestration."""

from __future__ import annotations

from nl2spl.compiler.spl_editing.core.catalog import RepairCatalog
from nl2spl.compiler.spl_editing.core.errors import SPLEditingError
from nl2spl.compiler.spl_editing.core.model import EditableIssue, RepairContext, RepairTarget
from nl2spl.compiler.spl_editing.core.registry import SPLEditingRuntimeRegistry
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.presentation.builders.section_builder import (
    build_sections,
    summarize_cards,
)
from nl2spl.compiler.spl_editing.presentation.contract.categories import (
    IssueCategory,
)
from nl2spl.compiler.spl_editing.presentation.contract.quality import (
    PresentationQuality,
)
from nl2spl.compiler.spl_editing.presentation.errors import (
    IssuePresentationNotFoundError,
)
from nl2spl.compiler.spl_editing.presentation.issue_presenters import (
    ExceptionHandlingPresenter,
    GenericIssuePresenter,
    RequiredOutputPresenter,
    WorkerDelegationPresenter,
)
from nl2spl.compiler.spl_editing.presentation.model.issue import (
    IssueCardView,
    IssueDetailPresentationView,
)
from nl2spl.compiler.spl_editing.presentation.model.sections import (
    IssueListPresentationView,
)
from nl2spl.compiler.spl_editing.presentation.resolvers import (
    build_advanced_details,
    build_display_context,
    category_for_issue,
    repair_options_for_issue,
    suggested_resolution_for_issue,
)
from nl2spl.ir.diagnostics import CompileDiagnostic


class IssuePresentationBuilder:
    """Project editable issues into presentation DTOs.

    The builder orchestrates resolvers and family presenters.  It does not
    parse diagnostic messages or decide repair capability outside the catalog
    and runtime registry.
    """

    def __init__(
        self,
        *,
        catalog: RepairCatalog,
        runtime: SPLEditingRuntimeRegistry,
    ) -> None:
        self._catalog = catalog
        self._runtime = runtime
        self._exception = ExceptionHandlingPresenter()
        self._required = RequiredOutputPresenter()
        self._delegation = WorkerDelegationPresenter()
        self._generic = GenericIssuePresenter()

    def build_list(
        self,
        *,
        run_id: str,
        snapshot: ArtifactSnapshot,
        issues: tuple[EditableIssue, ...],
        include_developer: bool = False,
    ) -> IssueListPresentationView:
        diagnostics = snapshot.compile_diagnostics
        cards = tuple(
            self.build_card(
                display_id=index,
                issue=issue,
                snapshot=snapshot,
                diagnostics=diagnostics,
            )
            for index, issue in enumerate(issues, start=1)
        )
        if include_developer:
            cards = cards + self._developer_cards(
                start=len(cards) + 1,
                issues=issues,
                diagnostics=diagnostics,
            )
        return IssueListPresentationView(
            run_id=run_id,
            snapshot_id=snapshot.snapshot_id,
            sections=build_sections(cards, include_developer=include_developer),
            summary=summarize_cards(cards),
        )

    def build_card(
        self,
        *,
        display_id: int,
        issue: EditableIssue,
        snapshot: ArtifactSnapshot,
        diagnostics: tuple[CompileDiagnostic, ...],
    ) -> IssueCardView:
        related = _related_diagnostics(issue, diagnostics)
        entries = self._catalog.find_by_irs_ref(issue.irs_ref, issue.kind)
        target = self._try_resolve_target(issue, snapshot, entries)
        context = self._try_build_context(issue, snapshot, entries, target)
        display_context = build_display_context(
            issue,
            snapshot,
            target=target,
            context=context,
            related_diagnostics=related,
        )
        options = repair_options_for_issue(issue, entries, self._runtime, snapshot)
        advanced = build_advanced_details(issue, related)
        suggested = suggested_resolution_for_issue(issue, related)
        presenter = self._presenter_for(category_for_issue(issue))
        return presenter.build_card(
            display_id=display_id,
            issue=issue,
            context=display_context,
            repair_options=options,
            suggested_resolution=suggested,
            advanced=advanced,
        )

    def build_detail(
        self,
        *,
        issue_id: str,
        snapshot: ArtifactSnapshot,
        issues: tuple[EditableIssue, ...],
    ) -> IssueDetailPresentationView:
        issue = _issue_by_id(issue_id, issues)
        diagnostics = snapshot.compile_diagnostics
        related = _related_diagnostics(issue, diagnostics)
        entries = self._catalog.find_by_irs_ref(issue.irs_ref, issue.kind)
        target = self._try_resolve_target(issue, snapshot, entries)
        context = self._try_build_context(issue, snapshot, entries, target)
        display_context = build_display_context(
            issue,
            snapshot,
            target=target,
            context=context,
            related_diagnostics=related,
        )
        options = repair_options_for_issue(issue, entries, self._runtime, snapshot)
        advanced = build_advanced_details(issue, related)
        suggested = suggested_resolution_for_issue(issue, related)
        presenter = self._presenter_for(category_for_issue(issue))
        return presenter.build_detail(
            issue=issue,
            context=display_context,
            repair_options=options,
            suggested_resolution=suggested,
            advanced=advanced,
        )

    def _try_resolve_target(
        self,
        issue: EditableIssue,
        snapshot: ArtifactSnapshot,
        entries,
    ) -> RepairTarget | None:
        for entry in entries:
            resolver_id = entry.target_resolver_id
            if resolver_id is None or not self._runtime.target_resolvers.has(resolver_id):
                continue
            try:
                return self._runtime.target_resolvers.get(resolver_id).resolve(
                    issue,
                    snapshot,
                )
            except (AttributeError, KeyError, SPLEditingError, TypeError):
                return None
        return None

    def _try_build_context(
        self,
        issue: EditableIssue,
        snapshot: ArtifactSnapshot,
        entries,
        target: RepairTarget | None,
    ) -> RepairContext | None:
        if target is None:
            return None
        for entry in entries:
            context_id = entry.context_id
            if context_id is None or not self._runtime.context_builders.has(context_id):
                continue
            try:
                return self._runtime.context_builders.get(context_id).build(
                    issue,
                    target,
                    snapshot,
                )
            except (AttributeError, KeyError, SPLEditingError, TypeError):
                return None
        return None

    def _presenter_for(self, category: IssueCategory):
        if category == IssueCategory.EXCEPTION_HANDLING:
            return self._exception
        if category == IssueCategory.REQUIRED_OUTPUTS:
            return self._required
        if category == IssueCategory.WORKER_DELEGATION:
            return self._delegation
        return self._generic

    def _developer_cards(
        self,
        *,
        start: int,
        issues: tuple[EditableIssue, ...],
        diagnostics: tuple[CompileDiagnostic, ...],
    ) -> tuple[IssueCardView, ...]:
        mapped = {d for issue in issues for d in issue.related_diagnostic_ids}
        cards: list[IssueCardView] = []
        for diagnostic in diagnostics:
            if diagnostic.diagnostic_id in mapped:
                continue
            cards.append(
                IssueCardView(
                    display_id=start + len(cards),
                    issue_id=diagnostic.diagnostic_id,
                    category=IssueCategory.DEVELOPER_DIAGNOSTIC,
                    title="Developer diagnostic",
                    impact="This diagnostic is not exposed as a fixable user issue.",
                    fix_label="Review in developer mode",
                    repairability="developer_only",
                    can_fix=False,
                    presentation_quality=PresentationQuality.DEGRADED,
                )
            )
        return tuple(cards)


def _related_diagnostics(
    issue: EditableIssue,
    diagnostics: tuple[CompileDiagnostic, ...],
) -> tuple[CompileDiagnostic, ...]:
    wanted = set(issue.related_diagnostic_ids)
    return tuple(d for d in diagnostics if d.diagnostic_id in wanted)


def _issue_by_id(
    issue_id: str,
    issues: tuple[EditableIssue, ...],
) -> EditableIssue:
    for issue in issues:
        if issue.issue_id == issue_id:
            return issue
    raise IssuePresentationNotFoundError(issue_id)


__all__ = ["IssuePresentationBuilder"]
