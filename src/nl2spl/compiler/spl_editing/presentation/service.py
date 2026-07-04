"""Narrow presentation facade for CLI and UI consumers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from nl2spl.compiler.spl_editing.admission.errors import NewFactAdmissionError
from nl2spl.compiler.spl_editing.admission.output_declaration import NewFactAdmissionService
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairSuggestion,
    UserFacingIssue,
    VerificationResult,
)
from nl2spl.compiler.spl_editing.core.service import SPLEditingService
from nl2spl.compiler.spl_editing.interaction.defaults import build_default_interaction_registry
from nl2spl.compiler.spl_editing.interaction.model import (
    RepairDirectiveValidationResult,
    RepairInputValidationError,
    RepairInteractionView,
    SubmitRepairDirectiveDraftRequest,
    WorkerDelegationPreviewHandle,
    revision_token_string,
)
from nl2spl.compiler.spl_editing.interaction.normalization import (
    normalize_worker_delegation_directive,
)
from nl2spl.compiler.spl_editing.interaction.store import NormalizedDirectiveStore
from nl2spl.compiler.spl_editing.interaction.validation import (
    parse_worker_delegation_draft,
    validate_worker_delegation_draft,
)
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
from nl2spl.compiler.spl_editing.presentation.resolvers.issue_subject import issue_subject_for
from nl2spl.compiler.spl_editing.selectable_refs.builder import SelectableRefSetBuilder


class SPLEditingPresentationService:
    """Backend-owned presentation projection service.

    This facade intentionally wraps ``SPLEditingService`` instead of replacing
    repair/session/apply behavior.  It exposes frozen presentation DTOs for
    CLI/UI consumers and keeps raw diagnostics out of default renderers.
    """

    def __init__(self, editing_service: SPLEditingService) -> None:
        self._editing = editing_service
        self._interaction_registry = build_default_interaction_registry()
        self._issue_builder = IssuePresentationBuilder(
            catalog=editing_service._catalog,
            runtime=editing_service._runtime,
            option_runtime_complete=self._option_runtime_complete,
        )
        self._admission = NewFactAdmissionService()
        self._directives = NormalizedDirectiveStore()
        self._directive_context: dict[str, tuple[Any, ...]] = {}
        self._preview_handles: dict[str, WorkerDelegationPreviewHandle] = {}

    def _option_runtime_complete(self, entry, option) -> bool:
        if not self._interaction_registry.has_complete(option.interaction_contract_id):
            return False
        plan_id = entry.materialization_plan_id
        if not plan_id or not self._editing._materialization.registry.has_complete(plan_id):
            return False
        for patch_type in option.execution_patch_types:
            if not self._editing._runtime.patches.has(patch_type):
                return False
            bundle = self._editing._runtime.patches.get(patch_type)
            if any(
                getattr(bundle, component, None) is None
                for component in ("validator", "previewer", "applier", "verifier")
            ):
                return False
        return True

    def get_run_presentation(
        self,
        run_id: str,
        *,
        run_label: str | None = None,
        snapshot_path: Path | None = None,
    ) -> RunPresentationView:
        snapshot = self._editing._get_snapshot(run_id)
        inventory = self._editing.list_issue_inventory(run_id)
        issue_list = self.list_issue_presentations(run_id)
        editable = any(card.can_fix for section in issue_list.sections for card in section.items)
        return build_run_presentation(
            snapshot=snapshot,
            issue_summary=issue_list.summary,
            snapshot_path=snapshot_path,
            run_label=run_label,
            editable=editable,
            editable_issue_count=len(inventory.editable),
            review_issue_count=len(inventory.review),
            deferred_validation_count=len(inventory.deferred),
            developer_issue_count=len(inventory.developer),
        )

    def list_run_presentations(self) -> tuple[RunPresentationView, ...]:
        """Return registered runs as presentation DTOs."""
        views: list[RunPresentationView] = []
        for run_id in sorted(self._editing._run_snapshot):
            run_dir = self._editing._run_dirs.get(run_id)
            snapshot_path = (
                Path(run_dir) / "spl_editing_snapshot.json" if run_dir is not None else None
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
        inventory = self._editing.list_issue_inventory(run_id)
        return self._issue_builder.build_inventory_list(
            run_id=run_id,
            snapshot=snapshot,
            inventory=inventory,
            include_developer=include_developer,
        )

    def get_issue_detail_presentation(
        self,
        run_id: str,
        issue_id: str,
    ) -> IssueDetailPresentationView:
        snapshot = self._editing._get_snapshot(run_id)
        inventory = self._editing.list_issue_inventory(run_id)
        issues = inventory.user_facing
        return self._issue_builder.build_detail(
            issue_id=issue_id,
            snapshot=snapshot,
            issues=issues,
        )

    def get_repair_interaction(
        self,
        run_id: str,
        issue_id: str,
        option_id: str,
        revision_token: str,
    ) -> RepairInteractionView:
        issue, snapshot, entry, option, target, context, subject, refset = (
            self._worker_delegation_context(run_id, issue_id, option_id)
        )
        current_revision = revision_token_string(snapshot.revision_token)
        if revision_token != current_revision:
            raise ValueError("stale_revision")
        spec, provider = self._interaction_registry.resolve(option.interaction_contract_id)
        if option.availability.value != "available":
            return RepairInteractionView(
                issue_id=issue.issue_id,
                strategy_id=option.strategy_id or "",
                option_id=option.option_id or "",
                contract_id=spec.contract_id,
                contract_version=spec.contract_version,
                revision_token=current_revision,
                interaction_kind="none",
                availability=option.availability.value,
                input_readiness="not_evaluated",
            )
        return provider.build(
            spec=spec,
            issue=issue,
            option=next(item for item in entry.strategy_options if item.option_id == option_id),
            subject=subject,
            refset=refset,
            snapshot=snapshot,
        )

    def submit_repair_directive_draft(
        self,
        request: SubmitRepairDirectiveDraftRequest,
    ) -> RepairDirectiveValidationResult:
        try:
            issue, snapshot, entry, option, target, context, subject, refset = (
                self._worker_delegation_context(request.run_id, request.issue_id, request.option_id)
            )
            interaction = self.get_repair_interaction(
                request.run_id,
                request.issue_id,
                request.option_id,
                request.revision_token,
            )
        except (KeyError, ValueError) as exc:
            return RepairDirectiveValidationResult(
                input_readiness="input_invalid",
                normalized_directive_id=None,
                errors=(RepairInputValidationError(str(exc), None, str(exc)),),
            )
        identity_errors = []
        if request.strategy_id != option.strategy_id:
            identity_errors.append(
                RepairInputValidationError("unknown_option_id", None, "Strategy/option mismatch")
            )
        if request.contract_id != interaction.contract_id:
            identity_errors.append(
                RepairInputValidationError(
                    "interaction_contract_mismatch", None, "Contract mismatch"
                )
            )
        if request.contract_version != interaction.contract_version:
            identity_errors.append(
                RepairInputValidationError(
                    "interaction_contract_version_mismatch", None, "Contract version mismatch"
                )
            )
        if interaction.availability != "available":
            identity_errors.append(
                RepairInputValidationError("option_unavailable", None, interaction.availability)
            )
        if identity_errors:
            return RepairDirectiveValidationResult("input_invalid", None, tuple(identity_errors))

        try:
            draft = parse_worker_delegation_draft(request)
        except (TypeError, ValueError) as exc:
            return RepairDirectiveValidationResult(
                "input_invalid",
                None,
                (RepairInputValidationError("invalid_wire_value", None, str(exc)),),
            )
        errors = validate_worker_delegation_draft(draft, option=option, refset=refset)
        if errors:
            readiness = (
                "input_required"
                if all(error.code == "required_field_missing" for error in errors)
                else "input_invalid"
            )
            return RepairDirectiveValidationResult(readiness, None, errors)
        try:
            admitted = self._admission.admit_child_outputs(
                declarations=draft.returned_results,
                snapshot=snapshot,
                directive_id=draft.draft_id,
            )
            directive = normalize_worker_delegation_directive(
                draft,
                target_ref=target.target_ref,
                refset=refset,
                admitted_outputs=admitted,
            )
        except (NewFactAdmissionError, ValueError) as exc:
            return RepairDirectiveValidationResult(
                "input_invalid",
                None,
                (RepairInputValidationError("new_fact_conflict", "returned_results", str(exc)),),
            )
        self._directives.put(directive)
        self._directive_context[directive.directive_id] = (
            request.run_id,
            issue,
            target,
            entry,
            refset,
        )
        return RepairDirectiveValidationResult("input_complete", directive.directive_id, ())

    def preview_repair_directive(self, directive_id: str) -> WorkerDelegationPreviewHandle:
        directive = self._directives.get(directive_id)
        run_id, issue, target, entry, refset = self._directive_context[directive_id]
        session, suggestion = self._editing.seal_worker_delegation_directive(
            run_id=run_id,
            issue=issue,
            target=target,
            catalog_entry=entry,
            refset=refset,
            directive=directive,
        )
        evidence_user_text = self._directive_evidence_text(directive)
        preview = self._editing.preview_suggestion(
            session.session_id,
            suggestion.suggestion_id,
            user_text=evidence_user_text,
        )
        handle = WorkerDelegationPreviewHandle(
            directive_id=directive_id,
            session_id=session.session_id,
            suggestion_id=suggestion.suggestion_id,
            preview=preview,
            evidence_user_text=evidence_user_text,
        )
        self._preview_handles[directive_id] = handle
        return handle

    def apply_repair_preview(self, directive_id: str, preview_id: str):
        handle = self._preview_handles[directive_id]
        session = self._editing.apply_preview_result(
            handle.session_id,
            handle.suggestion_id,
            preview_id,
            user_text=handle.evidence_user_text,
        )
        verification = self._editing.verify_session(session.session_id)
        return session, verification

    @staticmethod
    def _directive_evidence_text(directive) -> str:
        """Canonical audit projection of the structured user confirmation."""

        return json.dumps(
            {
                "additional_instruction": directive.additional_instruction,
                "admitted_outputs": [
                    {
                        "data_type": item.data_type,
                        "name": item.canonical_name,
                        "output_id": item.output_id,
                    }
                    for item in directive.admitted_outputs
                ],
                "delegated_responsibility": directive.delegated_responsibility,
                "directive_id": directive.directive_id,
                "option_id": directive.option_id,
                "placement_mode": directive.invocation_timing.placement_mode,
                "placement_ref_id": (
                    directive.placement_ref.ref.ref_id
                    if directive.placement_ref is not None
                    else None
                ),
                "result_usage": [
                    {
                        "output_id": item.output_id,
                        "parent_ref_id": (
                            item.parent_ref.ref.ref_id if item.parent_ref is not None else None
                        ),
                        "parent_temporary_name": item.parent_temporary_name,
                    }
                    for item in directive.result_usage
                ],
                "selected_input_ref_ids": [
                    item.ref.ref_id for item in directive.selected_input_refs
                ],
                "strategy_id": directive.strategy_id,
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def _worker_delegation_context(self, run_id, issue_id, option_id):
        snapshot = self._editing._get_snapshot(run_id)
        issue = self.issue_by_id(run_id, issue_id)
        entries = self._editing._catalog.find_by_irs_ref(issue.irs_ref, issue.kind)
        entry = next(
            item
            for item in entries
            if any(option.option_id == option_id for option in item.strategy_options)
        )
        detail = self.get_issue_detail_presentation(run_id, issue_id)
        option = next(item for item in detail.available_repairs if item.option_id == option_id)
        target = self._editing._runtime.target_resolvers.get(entry.target_resolver_id).resolve(
            issue, snapshot
        )
        context = self._editing._runtime.context_builders.get(entry.context_id).build(
            issue, target, snapshot
        )
        subject = issue_subject_for(
            issue,
            snapshot,
            target=target,
            context=context,
            related_diagnostics=tuple(
                diagnostic
                for diagnostic in snapshot.compile_diagnostics
                if diagnostic.diagnostic_id in issue.related_diagnostic_ids
            ),
        )
        refset = SelectableRefSetBuilder.build(
            snapshot,
            context,
            policy_id=entry.selectable_ref_policy_id,
        )
        return issue, snapshot, entry, option, target, context, subject, refset

    def issue_for_display_id(
        self,
        run_id: str,
        display_id: int,
    ) -> EditableIssue | UserFacingIssue:
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
    ) -> EditableIssue | UserFacingIssue:
        inventory = self._editing.list_issue_inventory(run_id)
        for issue in inventory.user_facing:
            if issue.issue_id == issue_id:
                return issue
        raise IssuePresentationNotFoundError(issue_id)

    def generate_suggestions_for_option(
        self,
        run_id: str,
        issue_id: str,
        option_index: int,
        *,
        user_instruction: str | None = None,
    ) -> tuple[SuggestionPresentationView, ...]:
        """Generate suggestions for one specific repair strategy.

        Renders the issue detail, extracts the patch types for the chosen
        repair option, and delegates to the core service with
        ``selected_patch_types`` scoped to that option.
        """
        detail = self.get_issue_detail_presentation(run_id, issue_id)
        if option_index < 0 or option_index >= len(detail.available_repairs):
            raise IssuePresentationNotFoundError(str(option_index))
        option = detail.available_repairs[option_index]
        if option.option_id is not None:
            from nl2spl.compiler.spl_editing.core.errors import SPLEditingError

            raise SPLEditingError(
                "Stable option_id repair requires get_repair_interaction() and a typed directive"
            )
        issue = self.issue_by_id(run_id, issue_id)
        from nl2spl.compiler.spl_editing.core.errors import SPLEditingError

        if issue.repairability != "editable":
            raise SPLEditingError(f"Cannot generate suggestions for non-editable issue {issue_id}")
        session = self._editing.create_session(run_id, issue)
        generation = self._editing.generate_suggestions(
            session.session_id,
            user_instruction=user_instruction,
            selected_patch_types=option.patch_types,
        )
        return build_suggestion_presentations(generation.suggestions)

    def present_suggestions(
        self,
        suggestions: tuple[RepairSuggestion, ...],
    ) -> tuple[SuggestionPresentationView, ...]:
        return build_suggestion_presentations(suggestions)

    def present_apply_confirmation(
        self,
        suggestion: RepairSuggestion,
        confirmation_context: Any | None = None,
    ) -> ApplyConfirmationView:
        return build_apply_confirmation(suggestion, confirmation_context)

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
