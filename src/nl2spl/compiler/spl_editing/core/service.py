"""SPL Editing service --wires extractors, handlers, patches, and verification.

No diagnostic-kind if-else in this module.  All dispatch goes through
registries keyed by handler_id / affordance_id / patch_type.

Materialized construct repair goes through the materialization path.
Patch types without a materialization context are rejected.
"""

# ruff: noqa: E501 -- legacy source contains one mojibake migration comment.

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from importlib import import_module
from pathlib import Path

from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument
from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
    JsonFileSnapshotRepository,
)
from nl2spl.compiler.artifacts.snapshot.persistence.loader import SnapshotLoader
from nl2spl.compiler.constructs import SPLConstructRegistry
from nl2spl.compiler.spl_editing.core.catalog import (
    RepairCatalog,
    RepairCatalogBuilder,
    RepairCatalogEntry,
)
from nl2spl.compiler.spl_editing.core.confirmation_context import (
    ConfirmationContextStore,
    RepairConfirmationContext,
)
from nl2spl.compiler.spl_editing.core.errors import (
    SPLEditingError,
    StaleRevisionError,
    UnsupportedIssueError,
)
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    EditingSession,
    IssueInventory,
    PatchApplyResult,
    RepairEvidence,
    RepairPatch,
    RepairSuggestion,
    RepairTarget,
    SuggestionGenerationResult,
    VerificationResult,
)
from nl2spl.compiler.spl_editing.core.registry import (
    SPLEditingRuntimeRegistry,
)
from nl2spl.compiler.spl_editing.core.revision import (
    AcceptedRepairPatch,
    ArtifactSnapshot,
)
from nl2spl.compiler.spl_editing.core.snapshot_adapter import (
    artifact_snapshot_from_document,
    document_from_artifact_snapshot,
    document_with_verification_record,
)
from nl2spl.compiler.spl_editing.intent import (
    ConstructRepairIntent,
    create_evidence_packet,
)
from nl2spl.compiler.spl_editing.issues.extractor import EditableIssueExtractor
from nl2spl.compiler.spl_editing.issues.inventory import IssueInventoryExtractor
from nl2spl.compiler.spl_editing.materialization import (
    MaterializationRequest,
    RepairMaterializationService,
    build_default_materialization_registry,
)
from nl2spl.compiler.spl_editing.selectable_refs import (
    SelectableRefSet,
    SelectableRefSetBuilder,
    resolve_ref_ids_to_result,
)
from nl2spl.compiler.spl_editing.storage.artifact_snapshot_store import (
    ArtifactSnapshotStore,
)
from nl2spl.compiler.spl_editing.storage.overlay_store import OverlayStore
from nl2spl.compiler.spl_editing.storage.session_store import SessionStore
from nl2spl.compiler.spl_editing.storage.suggestion_store import SuggestionStore
from nl2spl.compiler.spl_editing.storage.verification_result_store import (
    VerificationResultStore,
)
from nl2spl.compiler.spl_editing.verification.lanes import LaneReplayAdapter
from nl2spl.compiler.spl_editing.verification.runner import VerificationRunner
from nl2spl.ir.diagnostics import CompileDiagnostic


class SPLEditingService:
    """Top-level entry point for AI-assisted SPL Editing.

    Usage::

        service = SPLEditingService(runtime_registry)
        run_id = service.register_compile_result(snapshot)
        issues = service.list_editable_issues(run_id)
        session = service.create_session(run_id, issues[0])
        suggestions = service.generate_suggestions(session.session_id, "Fix it")
        service.apply_suggestion(session.session_id, suggestions[0].suggestion_id)
        result = service.verify_session(session.session_id)
    """

    def __init__(
        self,
        runtime: SPLEditingRuntimeRegistry,
        catalog: RepairCatalog | None = None,
        lane_a: LaneReplayAdapter | None = None,
        snapshot_repository: JsonFileSnapshotRepository | None = None,
        snapshot_run_dir: Path | None = None,
        materialization_service: RepairMaterializationService | None = None,
    ) -> None:
        self._runtime = runtime
        self._strategy_registry = self._build_default_strategy_registry()
        self._catalog = catalog or RepairCatalogBuilder.from_construct_registry(
            SPLConstructRegistry.default(),
            strategy_registry=self._strategy_registry,
        )
        self._snapshots = ArtifactSnapshotStore()
        self._sessions = SessionStore()
        self._suggestions = SuggestionStore()
        self._overlays = OverlayStore()
        self._verifier = VerificationRunner(lane_a=lane_a)
        self._extractor = EditableIssueExtractor(self._catalog)
        self._inventory_extractor = IssueInventoryExtractor(self._catalog)
        self._applied_patches: dict[str, RepairPatch] = {}
        self._apply_results: dict[str, PatchApplyResult] = {}
        self._verification_results = VerificationResultStore()
        self._session_overlays: dict[str, list[str]] = {}
        # compile_run_id 闁?snapshot_id
        self._run_snapshot: dict[str, str] = {}
        self._snapshot_repository = snapshot_repository
        self._snapshot_run_dir = Path(snapshot_run_dir) if snapshot_run_dir else None
        self._snapshot_documents: dict[tuple[str, str], SnapshotDocument] = {}
        self._session_current_snapshot_id: dict[str, str] = {}
        self._run_current_snapshot_id: dict[str, str] = {}
        self._run_dirs: dict[str, Path] = {}
        # R6: Materialization path
        self._materialization = materialization_service or RepairMaterializationService(
            build_default_materialization_registry()
        )
        self._confirmation_contexts = ConfirmationContextStore()
        self._preview_store = self._build_preview_store()
        self._preview_service = self._build_preview_service()

    @staticmethod
    def _build_default_strategy_registry():
        defaults = import_module("nl2spl.compiler.spl_editing.strategy.defaults")
        return defaults.build_default_strategy_registry()

    @staticmethod
    def _build_preview_store():
        store_module = import_module("nl2spl.compiler.spl_editing.preview.store")
        return store_module.PreviewStore()

    def _build_preview_service(self):
        preview_service_module = import_module("nl2spl.compiler.spl_editing.preview.service")
        return preview_service_module.PreviewDryRunService(self._materialization)

    @staticmethod
    def _preview_runtime():
        strategy_model = import_module("nl2spl.compiler.spl_editing.strategy.model")
        preview_store = import_module("nl2spl.compiler.spl_editing.preview.store")
        preview_validators = import_module("nl2spl.compiler.spl_editing.preview.validators")
        return (
            strategy_model.RepairDirective,
            preview_store.PreviewStore,
            preview_validators.PreviewApplyExpectedState,
            preview_validators.validate_preview_not_stale,
        )

    @staticmethod
    def _requested_behavior_from_intent(
        intent: ConstructRepairIntent, user_text: str | None
    ) -> str:
        if user_text and user_text.strip():
            return user_text.strip()
        payload = intent.payload
        for field_name in (
            "handler_goal",
            "producer_goal",
            "action_text",
            "prompt_text",
            "value_target",
        ):
            value = getattr(payload, field_name, None)
            if isinstance(value, str) and value.strip():
                return value.strip()
        if intent.repair_goal.strip():
            return intent.repair_goal.strip()
        if intent.intent_summary.strip():
            return intent.intent_summary.strip()
        return "Apply the selected construct repair."

    def _build_preview_directive(
        self,
        intent: ConstructRepairIntent,
        *,
        user_text: str | None,
    ):
        repair_directive_cls, _, _, _ = self._preview_runtime()
        return repair_directive_cls(
            directive_id=f"dir_{intent.intent_id}",
            source="user" if user_text and user_text.strip() else "system_default",
            target_construct_type=intent.target_construct_type,
            target_slot_name=intent.target_slot_name,
            requested_behavior=self._requested_behavior_from_intent(intent, user_text),
            selected_ref_hints=tuple(intent.selected_ref_ids),
            constraints=tuple(intent.constraints),
            option_id=getattr(intent.payload, "option_id", None),
        )

    def _generate_preview_for_context(
        self,
        *,
        session: EditingSession,
        ctx: RepairConfirmationContext,
        patch: RepairPatch,
        user_text: str | None,
        store,
        ttl_seconds: float | None = None,
    ):
        intent = patch.payload
        if not isinstance(intent, ConstructRepairIntent):
            raise SPLEditingError(
                f"{patch.patch_type} payload must be ConstructRepairIntent, "
                f"got {type(intent).__name__}"
            )
        strategy_id = getattr(ctx.catalog_entry, "repair_strategy_id", None)
        if not strategy_id:
            raise SPLEditingError(
                f"Catalog entry '{ctx.catalog_entry.entry_id}' does not declare a repair strategy."
            )
        strategy = self._strategy_registry.get(strategy_id)
        directive = self._build_preview_directive(intent, user_text=user_text)
        snap = self._get_snapshot(session.compile_run_id)
        return self._preview_service.preview(
            session=session,
            issue=ctx.issue,
            strategy=strategy,
            directive=directive,
            target=ctx.target,
            refset=ctx.refset,
            snapshot=snap,
            store=store,
            candidate_intent=intent,
            ttl_seconds=ttl_seconds,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_compile_result(
        self,
        snapshot: ArtifactSnapshot,
    ) -> str:
        """Store a base snapshot and return its run_id.

        Compatibility wrapper for older in-memory callers.
        """
        return self.register_artifact_snapshot(snapshot)

    def register_artifact_snapshot(
        self,
        snapshot: ArtifactSnapshot,
    ) -> str:
        """Store a typed runtime artifact snapshot and return its run_id."""
        self._snapshots.put(snapshot)
        self._run_snapshot[snapshot.compile_run_id] = snapshot.snapshot_id
        self._overlays.register_snapshot(
            snapshot.compile_run_id,
            snapshot.snapshot_id,
        )
        return snapshot.compile_run_id

    def register_snapshot_file(self, path: Path) -> str:
        """Load a canonical JSON snapshot file and register it for editing."""
        path = Path(path)
        self._snapshot_repository = self._snapshot_repository or JsonFileSnapshotRepository()
        document = SnapshotLoader(self._snapshot_repository).load(path)
        snapshot = artifact_snapshot_from_document(document)
        run_id = self.register_artifact_snapshot(snapshot)
        self._snapshot_documents[(run_id, document.identity.snapshot_id)] = document
        self._run_current_snapshot_id[run_id] = document.identity.snapshot_id
        self._run_dirs[run_id] = path.parent
        return run_id

    def _get_snapshot(self, compile_run_id: str) -> ArtifactSnapshot:
        sid = self._run_snapshot.get(compile_run_id, "")
        return self._snapshots.get(compile_run_id, sid)

    def list_editable_issues(
        self,
        compile_run_id: str,
    ) -> tuple[EditableIssue, ...]:
        """Return user-actionable editable issues for a run."""
        return self.list_issue_inventory(compile_run_id).editable

    def list_issue_inventory(
        self,
        compile_run_id: str,
    ) -> IssueInventory:
        """Return complete issue inventory for a run."""
        snap = self._get_snapshot(compile_run_id)
        return self._inventory_extractor.extract(list(snap.compile_diagnostics))

    def list_editable_issues_from_diagnostics(
        self,
        diagnostics: tuple[CompileDiagnostic, ...],
    ) -> tuple[EditableIssue, ...]:
        """Return editable issues from raw diagnostics (no snapshot needed)."""
        return self.issue_inventory_from_diagnostics(diagnostics).editable

    def issue_inventory_from_diagnostics(
        self,
        diagnostics: tuple[CompileDiagnostic, ...],
    ) -> IssueInventory:
        """Return complete issue inventory from raw diagnostics."""
        return self._inventory_extractor.extract(list(diagnostics))

    def create_session(
        self,
        compile_run_id: str,
        issue: EditableIssue,
    ) -> EditingSession:
        """Create an editing session for one issue."""
        snap = self._get_snapshot(compile_run_id)
        session = EditingSession(
            session_id=f"sess_{compile_run_id}_{issue.issue_id}",
            compile_run_id=compile_run_id,
            artifact_snapshot_id=snap.snapshot_id,
            overlay_version=snap.overlay_version,
            issue=issue,
            created_at="",
        )
        self._sessions.put(session)
        self._suggestions.register_session(session.session_id)
        self._session_current_snapshot_id[session.session_id] = self._run_current_snapshot_id.get(
            compile_run_id, snap.snapshot_id
        )
        return session

    def generate_suggestions(
        self,
        session_id: str,
        user_instruction: str | None = None,
        selected_patch_types: tuple[str, ...] | None = None,
    ) -> SuggestionGenerationResult:
        """Generate repair suggestions for the issue in *session_id*.

        The return value preserves context-readiness state.  Blocked or
        unavailable generation is not collapsed into an empty tuple.
        """
        session = self._sessions.get(session_id)
        issue = session.issue

        # Find handler
        handler_id = self._resolve_handler_id(issue)
        handler = self._runtime.handlers.get(handler_id)

        # Find target
        resolver_id = self._resolve_target_resolver_id(issue)
        resolver = self._runtime.target_resolvers.get(resolver_id)
        snap = self._get_snapshot(session.compile_run_id)
        target = resolver.resolve(issue, snap)

        # Build RepairContext
        context_id = self._resolve_context_id(issue)
        ctx_builder = self._runtime.context_builders.get(context_id)
        context = ctx_builder.build(issue, target, snap, user_instruction)

        # Find catalog entries --resolve the primary entry for this issue.
        entries = self._catalog.find_by_construct_slot_kind(
            issue.irs_ref.construct_type,
            issue.irs_ref.slot_name,
            issue.kind,
        )
        if not entries:
            raise UnsupportedIssueError(f"No catalog entries for {issue.kind}")
        default_affordance = issue.default_affordance_id or entries[0].affordance_id
        default_patch_type = entries[0].default_patch_type or entries[0].supported_patch_types[0]
        entry = self._resolve_catalog_entry(issue, default_affordance, default_patch_type)

        # R6: Build SelectableRefSet for intent-aware repair
        selectable_refset = None
        if entry and entry.selectable_ref_policy_id:
            selectable_refset = SelectableRefSetBuilder.build(
                snapshot=snap,
                context=context,
                policy_id=entry.selectable_ref_policy_id,
            )

        # Build LLMRepairContext for prompt rendering when formally registered.
        rendered_prompt: str | None = None
        readiness_status = "ready"
        readiness_reasons: tuple[str, ...] = ()
        readiness_warnings: tuple[str, ...] = ()
        if self._runtime.llm_context_builders.has(
            handler_id,
        ) and self._runtime.prompt_renderers.has(handler_id):
            llm_ctx_builder = self._runtime.llm_context_builders.get(handler_id)
            llm_ctx_renderer = self._runtime.prompt_renderers.get(handler_id)
            selected_patch_type = self._selected_patch_type(
                entries,
                selected_patch_types,
            )
            if not selected_patch_type:
                return SuggestionGenerationResult(
                    status="repair_unavailable",
                    reasons=("No repair patch type is available for this issue.",),
                )
            llm_ctx = llm_ctx_builder.build(
                session_id=session_id,
                issue=issue,
                target=target,
                repair_context=context,
                artifact_snapshot=snap,
                selected_patch_type=selected_patch_type,
                affordance_id=entry.affordance_id if entry else "",
                user_instruction=user_instruction,
                source_spans=context.source_spans,
                catalog_entry=entry,
                patch_registry=self._runtime.patches,
                selectable_refset=selectable_refset,  # R6
            )
            readiness_status = llm_ctx.generation_readiness.status
            readiness_reasons = llm_ctx.generation_readiness.reasons
            readiness_warnings = llm_ctx.quality.warnings
            if llm_ctx.generation_readiness.status in (
                "generation_blocked",
                "repair_unavailable",
            ):
                return SuggestionGenerationResult(
                    status=readiness_status,
                    reasons=readiness_reasons,
                    warnings=readiness_warnings,
                )
            rendered_prompt = llm_ctx_renderer.render(llm_ctx)

        # Generate --pass rendered_prompt + R6 params
        suggestions = handler.generate_suggestions(
            issue,
            target,
            context,
            entries,
            user_instruction,
            selected_patch_types=selected_patch_types,
            rendered_user_prompt=rendered_prompt,
            selectable_refset=selectable_refset,  # R6
            catalog_entry=entry,  # R6
        )

        # Stamp with session metadata, revision, and evidence
        snap = self._get_snapshot(session.compile_run_id)
        result: list[RepairSuggestion] = []
        for s in suggestions:
            payload = s.patch.payload

            # R6: Server overrides intent_id before sealing
            if selectable_refset is not None and isinstance(payload, ConstructRepairIntent):
                server_intent_id = f"int_{session_id}_{snap.snapshot_id}_{len(result):04d}"
                payload = replace(payload, intent_id=server_intent_id)

            # R6: Validate + seal context BEFORE writing to stores.
            # If ref resolution fails, the suggestion is NOT saved.
            stamped_suggestion_id = f"{session_id}_sug_{len(result):02d}"
            stamped_patch_id = f"{session_id}_patch_{len(result):02d}"
            ctx_sealed = False
            if (
                selectable_refset is not None
                and isinstance(payload, ConstructRepairIntent)
                and entry is not None
            ):
                resolution = resolve_ref_ids_to_result(
                    selectable_refset,
                    payload.selected_ref_ids,
                    "selectable_input",
                )
                if resolution.is_success:
                    target_role = "target_output"
                    if payload.patch_type == "AddExceptionHandlerStep":
                        target_role = "target_exception_flow"
                    elif payload.patch_type in {
                        "CreateWorkerHandoffContract",
                        "ConvertDelegationIntentToMainFlowStep",
                        "ConvertDelegationIntentToRequestInput",
                    }:
                        target_role = "target_worker"
                    target_resolution = resolve_ref_ids_to_result(
                        selectable_refset,
                        (payload.target_ref_id,),
                        target_role,
                    )
                    if target_resolution.is_success:
                        self._confirmation_contexts.seal(
                            RepairConfirmationContext(
                                context_id=f"ctx_{stamped_suggestion_id}",
                                session_id=session_id,
                                suggestion_id=stamped_suggestion_id,
                                patch_id=stamped_patch_id,
                                compile_run_id=snap.compile_run_id,
                                intent_id=payload.intent_id,
                                issue=issue,
                                target=target,
                                catalog_entry=entry,
                                refset=selectable_refset,
                                selected_ref_ids=payload.selected_ref_ids,
                                resolved_refs=resolution.resolved_refs,
                                snapshot_id=snap.snapshot_id,
                                overlay_version=snap.overlay_version,
                                created_at=datetime.now(UTC).isoformat(),
                            )
                        )
                        ctx_sealed = True
                if not ctx_sealed:
                    continue  # reject this suggestion --don't write to store

            stamped_patch = RepairPatch(
                patch_id=stamped_patch_id,
                affordance_id=s.patch.affordance_id,
                patch_type=s.patch.patch_type,
                target_ref=s.patch.target_ref,
                irs_ref=s.patch.irs_ref,
                base_compile_run_id=snap.compile_run_id,
                artifact_snapshot_id=snap.snapshot_id,
                overlay_version=snap.overlay_version,
                payload=payload,
                preconditions=s.patch.preconditions,
                evidence=s.patch.evidence,
                verification_lane=s.patch.verification_lane,
            )
            stamped = RepairSuggestion(
                suggestion_id=stamped_suggestion_id,
                session_id=session_id,
                affordance_id=s.affordance_id,
                title=s.title,
                explanation=s.explanation,
                patch=stamped_patch,
                spl_preview=s.spl_preview,
                expected_effect=s.expected_effect,
                risks=s.risks,
            )
            self._suggestions.put(stamped)
            result.append(stamped)
        return SuggestionGenerationResult(
            status=readiness_status,
            suggestions=tuple(result),
            reasons=readiness_reasons,
            warnings=readiness_warnings,
        )

    def get_preview_store(self):
        """Return the in-memory preview store for diagnostics and tests."""
        return self._preview_store

    def seal_worker_delegation_directive(
        self,
        *,
        run_id: str,
        issue: EditableIssue,
        target: RepairTarget,
        catalog_entry: RepairCatalogEntry,
        refset: SelectableRefSet,
        directive,
    ) -> tuple[EditingSession, RepairSuggestion]:
        """Create a sealed suggestion from a validated v2 typed directive.

        This is the only bridge from the interaction/admission domain into the
        existing preview/apply lifecycle.  It performs no LLM generation.
        """
        from datetime import UTC, datetime

        from nl2spl.compiler.spl_editing.core.confirmation_context import (
            RepairConfirmationContext,
        )
        from nl2spl.compiler.spl_editing.selectable_refs.resolver import (
            resolve_ref_ids_to_result,
        )

        snapshot = self._get_snapshot(run_id)
        if directive.base_revision != (
            f"{snapshot.compile_run_id}:{snapshot.snapshot_id}:{snapshot.overlay_version}"
        ):
            raise StaleRevisionError("Normalized directive base revision is stale")
        patch_type = (
            "DefineChildWorkerClosure"
            if directive.option_id == "define_child_worker"
            else "ConvertDelegationIntentToMainFlowStep"
        )
        selected_ref_ids = tuple(item.ref.ref_id for item in directive.selected_input_refs)
        resolved = resolve_ref_ids_to_result(refset, selected_ref_ids, "selectable_input")
        if not resolved.is_success:
            raise SPLEditingError("Sealed directive references are no longer valid")
        target_ref = next(
            (
                ref.ref_id
                for ref in refset.refs
                if ref.ref_role == "target_worker" and ref.canonical_name == target.canonical_name
            ),
            None,
        )
        if target_ref is None:
            raise SPLEditingError("Worker promotion target ref is unavailable")
        intent = ConstructRepairIntent(
            intent_id=f"intent_{directive.directive_id}",
            issue_id=issue.issue_id,
            patch_type=patch_type,
            affordance_id=catalog_entry.affordance_id,
            target_construct_type="WORKER_PROMOTION",
            target_construct_id=issue.irs_ref.construct_id,
            target_slot_name=issue.irs_ref.slot_name,
            target_ref_id=target_ref,
            selected_ref_ids=selected_ref_ids,
            intent_summary="Complete Worker Delegation closure",
            repair_goal=directive.delegated_responsibility,
            materialization_plan_id="worker_delegation.complete_closure.v2",
            constraints=(directive.option_id,),
            payload=directive,
        )
        session = self.create_session(run_id, issue)
        suggestion_id = f"suggestion_{directive.directive_id}"
        patch = RepairPatch(
            patch_id=f"patch_{directive.directive_id}",
            affordance_id=catalog_entry.affordance_id,
            patch_type=patch_type,
            target_ref=target.target_ref,
            irs_ref=issue.irs_ref,
            base_compile_run_id=snapshot.compile_run_id,
            artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=snapshot.overlay_version,
            payload=intent,
            verification_lane="B",
        )
        if patch_type == "DefineChildWorkerClosure" and self._runtime.patches.has(patch_type):
            self._runtime.patches.get(patch_type).validator.validate(patch, snapshot)
        suggestion = RepairSuggestion(
            suggestion_id=suggestion_id,
            session_id=session.session_id,
            affordance_id=catalog_entry.affordance_id,
            title=(
                "Define this work as a child worker"
                if directive.option_id == "define_child_worker"
                else "Keep this work in the main workflow"
            ),
            explanation="Validated typed Worker Delegation directive.",
            patch=patch,
            expected_effect=(directive.delegated_responsibility,),
        )
        self._suggestions.put(suggestion)
        self._confirmation_contexts.seal(
            RepairConfirmationContext(
                context_id=f"ctx_{suggestion_id}",
                session_id=session.session_id,
                suggestion_id=suggestion_id,
                patch_id=patch.patch_id,
                compile_run_id=run_id,
                intent_id=intent.intent_id,
                issue=issue,
                target=target,
                catalog_entry=catalog_entry,
                refset=refset,
                selected_ref_ids=selected_ref_ids,
                resolved_refs=resolved.resolved_refs,
                snapshot_id=snapshot.snapshot_id,
                overlay_version=snapshot.overlay_version,
                created_at=datetime.now(UTC).isoformat(),
            )
        )
        return session, suggestion

    def preview_suggestion(
        self,
        session_id: str,
        suggestion_id: str,
        *,
        user_text: str | None = None,
        ttl_seconds: float | None = None,
    ):
        """Generate a dry-run preview for a sealed suggestion without applying it."""
        session = self._sessions.get(session_id)
        suggestion = self._suggestions.get(suggestion_id)
        if suggestion.session_id != session_id:
            raise SPLEditingError(
                f"Suggestion '{suggestion_id}' belongs to session "
                f"'{suggestion.session_id}', not '{session_id}'"
            )
        ctx = self._confirmation_contexts.get(f"ctx_{suggestion_id}")
        return self._generate_preview_for_context(
            session=session,
            ctx=ctx,
            patch=suggestion.patch,
            user_text=user_text,
            store=self._preview_store,
            ttl_seconds=ttl_seconds,
        )

    def apply_preview_result(
        self,
        session_id: str,
        suggestion_id: str,
        preview_id: str,
        *,
        user_text: str | None = None,
    ) -> EditingSession:
        """Apply a suggestion only after the stored preview passes stale validation."""
        session = self._sessions.get(session_id)
        suggestion = self._suggestions.get(suggestion_id)
        if suggestion.session_id != session_id:
            raise SPLEditingError(
                f"Suggestion '{suggestion_id}' belongs to session "
                f"'{suggestion.session_id}', not '{session_id}'"
            )
        ctx = self._confirmation_contexts.get(f"ctx_{suggestion_id}")
        _, preview_store_cls, expected_state_cls, validate_preview_not_stale = (
            self._preview_runtime()
        )
        candidate_store = preview_store_cls()
        candidate = self._generate_preview_for_context(
            session=session,
            ctx=ctx,
            patch=suggestion.patch,
            user_text=user_text,
            store=candidate_store,
        )
        expected = expected_state_cls(
            session_id=session.session_id,
            issue_id=session.issue.issue_id,
            base_snapshot_id=candidate.base_snapshot_id,
            intent_hash=candidate.intent_hash,
            directive_hash=candidate.directive_hash,
            closure_plan_hash=candidate.closure_plan_hash,
            selected_refset_id=candidate.selected_refset_id,
            slice_typed_plan_hashes=candidate.slice_typed_plan_hashes,
            preview_construct_hashes=candidate.preview_construct_hashes,
            llm_generation_config_hash=candidate.llm_generation_config_hash,
            strategy_id=candidate.strategy_id,
            option_id=candidate.option_id,
            interaction_contract_hash=candidate.interaction_contract_hash,
            normalized_directive_hash=candidate.normalized_directive_hash,
            admitted_fact_hashes=candidate.admitted_fact_hashes,
        )
        validate_preview_not_stale(self._preview_store, preview_id, expected)

        patch = suggestion.patch
        confirmed_patch = RepairPatch(
            patch_id=patch.patch_id,
            affordance_id=patch.affordance_id,
            patch_type=patch.patch_type,
            target_ref=patch.target_ref,
            irs_ref=patch.irs_ref,
            base_compile_run_id=patch.base_compile_run_id,
            artifact_snapshot_id=patch.artifact_snapshot_id,
            overlay_version=patch.overlay_version,
            payload=patch.payload,
            preconditions=patch.preconditions,
            evidence=RepairEvidence(
                evidence_kind="user_confirmed_repair",
                user_text=user_text or "",
                related_diagnostic_id=session.issue.primary_diagnostic_id,
            ),
            verification_lane=patch.verification_lane,
        )
        updated = self._apply_via_materialization(
            session_id,
            suggestion_id,
            confirmed_patch,
            user_text,
        )
        self._preview_store.expire(preview_id)
        return updated

    def apply_suggestion(
        self,
        session_id: str,
        suggestion_id: str,
        *,
        user_text: str | None = None,
    ) -> EditingSession:
        """Apply a confirmed suggestion.

        Materialized construct repair goes through the materialization path.
        Patch types without a materialization context are rejected.
        """
        session = self._sessions.get(session_id)
        suggestion = self._suggestions.get(suggestion_id)

        snap = self._get_snapshot(session.compile_run_id)
        patch = suggestion.patch

        confirmed_patch = RepairPatch(
            patch_id=patch.patch_id,
            affordance_id=patch.affordance_id,
            patch_type=patch.patch_type,
            target_ref=patch.target_ref,
            irs_ref=patch.irs_ref,
            base_compile_run_id=patch.base_compile_run_id,
            artifact_snapshot_id=patch.artifact_snapshot_id,
            overlay_version=patch.overlay_version,
            payload=patch.payload,
            preconditions=patch.preconditions,
            evidence=RepairEvidence(
                evidence_kind="user_confirmed_repair",
                user_text=user_text or "",
                related_diagnostic_id=session.issue.primary_diagnostic_id,
            ),
            verification_lane=patch.verification_lane,
        )

        # 闁冲厜鍋撻柍鍏夊亾 R6: Insert dispatch BEFORE stale prechecks 闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋?
        # Insert path handles cross-session/stale via the context state
        # machine (expire/reject), not via pre-check exceptions.
        if confirmed_patch.patch_type == "InsertProducerStep" or isinstance(
            confirmed_patch.payload, ConstructRepairIntent
        ):
            if not isinstance(confirmed_patch.payload, ConstructRepairIntent):
                raise SPLEditingError(
                    f"{patch.patch_type} payload must be ConstructRepairIntent, "
                    f"got {type(confirmed_patch.payload).__name__}"
                )
            return self._apply_via_materialization(
                session_id,
                suggestion_id,
                confirmed_patch,
                user_text,
            )

        # 闁冲厜鍋撻柍鍏夊亾 Non-materialized payload prechecks 闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋? # noqa: E501
        if suggestion.session_id != session_id:
            raise SPLEditingError(
                f"Suggestion '{suggestion_id}' belongs to session "
                f"'{suggestion.session_id}', not '{session_id}'"
            )

        if confirmed_patch.base_compile_run_id != snap.compile_run_id:
            raise StaleRevisionError("compile_run_id mismatch")
        if confirmed_patch.artifact_snapshot_id != snap.snapshot_id:
            raise StaleRevisionError("snapshot_id mismatch")
        if confirmed_patch.overlay_version != snap.overlay_version:
            raise StaleRevisionError(
                f"Patch overlay {confirmed_patch.overlay_version} != "
                f"snapshot {snap.overlay_version}"
            )

        # 闁冲厜鍋撻柍鍏夊亾 No direct mutation bridge 闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾  # noqa: E501
        raise SPLEditingError(
            f"Patch type '{confirmed_patch.patch_type}' has no "
            "materialization plan/context and cannot be applied directly."
        )

    # 闁冲厜鍋撻柍鍏夊亾 R6: Materialization apply path 闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾闁冲厜鍋撻柍鍏夊亾  # noqa: E501

    def _apply_via_materialization(
        self,
        session_id: str,
        suggestion_id: str,
        patch: RepairPatch,
        user_text: str | None,
    ) -> EditingSession:
        session = self._sessions.get(session_id)
        snap = self._get_snapshot(session.compile_run_id)
        ctx_id = f"ctx_{suggestion_id}"

        # 1. begin_apply --atomically occupy context
        ctx = self._confirmation_contexts.begin_apply(ctx_id)

        try:
            # 2. Validation: session match, stale, payload, intent
            if ctx.session_id != session_id:
                self._confirmation_contexts.reject(ctx_id, "Cross-session access")
                raise SPLEditingError("Confirmation context session mismatch")
            if ctx.snapshot_id != snap.snapshot_id or ctx.overlay_version != snap.overlay_version:
                self._confirmation_contexts.expire(ctx_id, "Stale revision")
                raise StaleRevisionError(
                    f"Confirmation context revision stale: "
                    f"ctx={ctx.snapshot_id}@{ctx.overlay_version}, "
                    f"snap={snap.snapshot_id}@{snap.overlay_version}"
                )

            intent = patch.payload
            if not isinstance(intent, ConstructRepairIntent):
                self._confirmation_contexts.reject(ctx_id, "Payload is not ConstructRepairIntent")
                raise SPLEditingError(
                    f"{patch.patch_type} payload must be ConstructRepairIntent, "
                    f"got {type(intent).__name__}"
                )
            if intent.intent_id != ctx.intent_id:
                self._confirmation_contexts.reject(ctx_id, "Intent ID mismatch")
                raise SPLEditingError("Intent ID does not match sealed context")
            if intent.selected_ref_ids != ctx.selected_ref_ids:
                self._confirmation_contexts.reject(ctx_id, "Selected ref IDs mismatch")
                raise SPLEditingError("Selected ref IDs do not match sealed context")

            # 3. Create evidence packet
            evidence_packet = create_evidence_packet(
                intent=intent,
                repair_patch_id=patch.patch_id,
                related_diagnostic_id=patch.evidence.related_diagnostic_id,
                user_text=user_text or "",
            )

            # 4. Build MaterializationRequest with SEALED resolved_refs
            request = MaterializationRequest(
                snapshot=snap,
                issue=ctx.issue,
                target=ctx.target,
                catalog_entry=ctx.catalog_entry,
                intent=intent,
                refset=ctx.refset,
                resolved_refs=ctx.resolved_refs,
                evidence_packet=evidence_packet,
            )

            # 5. Execute materialization
            result = self._materialization.materialize(request)

            # 5.5 SPL Editing fail-closed gate: multiple outputs not allowed.
            if result.patched_snapshot.worker_step_plan:
                for w_steps in result.patched_snapshot.worker_step_plan.worker_steps.values():
                    for step in w_steps:
                        if len(step.outputs) > 1:
                            raise ValueError("SPL Editing fail-closed gate: multiple outputs not allowed.")

            # 6. Persistence with rollback
            run_id = result.patched_snapshot.compile_run_id
            sid = result.patched_snapshot.snapshot_id
            ov = result.patched_snapshot.overlay_version
            ov_id = result.overlay_event.overlay_id

            snapshot_written = False
            overlay_appended = False
            try:
                self._snapshots.put(result.patched_snapshot)
                snapshot_written = True

                self._overlays.register_snapshot(run_id, sid)
                self._overlays.append(result.overlay_event)
                overlay_appended = True

                apply_result = PatchApplyResult(
                    patched_snapshot=result.patched_snapshot,
                    overlay_event=result.overlay_event,
                    changed_refs=result.changed_refs,
                    changed_step_ids=result.changed_step_ids,
                    changed_handoff_ids=result.changed_handoff_ids,
                    evidence_refs=result.evidence_refs,
                    audit_metadata={
                        "materialization_plan_id": result.materialization_plan_id,
                        "materializer_id": result.materializer_id,
                        "materialization_authority": result.materialization_authority,
                        "evidence_packet_id": result.evidence_packet_id,
                        "consumed_selected_ref_ids": result.consumed_selected_ref_ids,
                        "stage_slice_results": result.stage_slice_results,
                    },
                )
                self._applied_patches[ov_id] = patch
                self._apply_results[ov_id] = apply_result
                self._session_overlays.setdefault(session_id, []).append(ov_id)

                self._persist_overlay_snapshot_if_configured(
                    session_id=session_id,
                    patched_snapshot=result.patched_snapshot,
                    overlay_event=result.overlay_event,
                    patch=patch,
                )

                updated = EditingSession(
                    session_id=session.session_id,
                    compile_run_id=session.compile_run_id,
                    artifact_snapshot_id=result.patched_snapshot.snapshot_id,
                    overlay_version=result.patched_snapshot.overlay_version,
                    issue=session.issue,
                    created_at=session.created_at,
                )
                self._sessions.replace(updated)

            except Exception:
                # Rollback in reverse order
                if overlay_appended:
                    self._overlays.remove_event(ov_id)
                if snapshot_written:
                    self._snapshots.remove(run_id, sid, ov)
                self._applied_patches.pop(ov_id, None)
                self._apply_results.pop(ov_id, None)
                if (
                    session_id in self._session_overlays
                    and ov_id in self._session_overlays[session_id]
                ):
                    self._session_overlays[session_id].remove(ov_id)
                raise

            # 7. commit_consumed --only after ALL persistence succeeds
            self._confirmation_contexts.commit_consumed(ctx_id)
            return updated

        except Exception:
            # abort_apply --returns to SEALED for transient failures
            self._confirmation_contexts.abort_apply(ctx_id)
            raise

    def verify_session(
        self,
        session_id: str,
    ) -> VerificationResult:
        """Run verification for the latest applied suggestion."""
        session = self._sessions.get(session_id)
        sid = self._run_snapshot.get(session.compile_run_id, "")
        # Use the session's applied overlay version, not the global latest
        session_ov_ids = self._session_overlays.get(session_id, [])
        if not session_ov_ids:
            result = VerificationResult(
                session_id=session_id,
                patch_id="",
                accepted=False,
                lane="A",
                failure_reasons=("No overlay events for this session",),
            )
            self._verification_results.append(session_id, result)
            return result
        last_ov_id = session_ov_ids[-1]
        last_event = self._overlays.get(last_ov_id)
        ov = last_event.overlay_version
        snap = self._snapshots.get(session.compile_run_id, sid, overlay_version=ov)
        base = self._snapshots.get(
            session.compile_run_id,
            sid,
            overlay_version=0,
        )

        patch = self._applied_patches.get(last_ov_id)
        if patch is None:
            result = VerificationResult(
                session_id=session_id,
                patch_id=last_event.patch_id,
                accepted=False,
                lane="A",
                failure_reasons=("Applied patch not found in storage",),
            )
        else:
            bundle = self._runtime.patches.get(last_event.patch_type)
            apply_result = self._apply_results.get(last_ov_id)
            result = self._verifier.verify(
                patch,
                base,
                snap,
                bundle.verifier,
                apply_result=apply_result,
            )
        self._persist_verification_if_configured(session_id, result)
        self._verification_results.append(session_id, result)
        return result

    def get_latest_verification(self, session_id: str) -> VerificationResult:
        """Return the most recent verification result for *session_id*."""
        return self._verification_results.get_latest(session_id)

    def list_verifications(
        self,
        session_id: str,
    ) -> tuple[VerificationResult, ...]:
        """Return all verification results for *session_id*."""
        return self._verification_results.list_all(session_id)

    def get_patched_spl(self, run_id: str) -> str:
        """Render the latest patched snapshot through full Lane B replay.

        SPL Editing materializes stage-owned pre-normalize artifacts.  Reusing
        Lane A here could display a different program from the one accepted by
        verification, especially for Worker Delegation closure repairs.
        """
        from nl2spl.compiler.spl_editing.verification.lanes import LaneBReplayAdapter

        snap = self._get_snapshot(run_id)
        artifacts = LaneBReplayAdapter().replay(snap)
        return artifacts.rendered_spl

    # ------------------------------------------------------------------
    # Optional persisted snapshot support
    # ------------------------------------------------------------------

    def _persist_overlay_snapshot_if_configured(
        self,
        *,
        session_id: str,
        patched_snapshot: ArtifactSnapshot,
        overlay_event,
        patch: RepairPatch,
    ) -> None:
        if self._snapshot_repository is None:
            return
        run_id = patched_snapshot.compile_run_id
        current_doc_id = self._session_current_snapshot_id.get(session_id)
        if current_doc_id is None:
            return
        parent_document = self._snapshot_documents.get((run_id, current_doc_id))
        if parent_document is None:
            return
        accepted = AcceptedRepairPatch(
            patch_id=patch.patch_id,
            patch_type=patch.patch_type,
            affordance_id=patch.affordance_id,
            overlay_id=overlay_event.overlay_id,
        )
        document = document_from_artifact_snapshot(
            patched_snapshot,
            parent_document=parent_document,
            overlay_event=overlay_event,
            accepted_patch=accepted,
        )
        run_dir = self._run_dirs.get(run_id, self._snapshot_run_dir)
        if run_dir is None:
            return
        self._snapshot_repository.save_overlay(
            document,
            self._overlay_path(run_dir, document.identity.snapshot_id),
        )
        self._snapshot_documents[(run_id, document.identity.snapshot_id)] = document
        self._session_current_snapshot_id[session_id] = document.identity.snapshot_id
        self._run_current_snapshot_id[run_id] = document.identity.snapshot_id

    def _persist_verification_if_configured(
        self,
        session_id: str,
        result: VerificationResult,
    ) -> None:
        if self._snapshot_repository is None:
            return
        session = self._sessions.get(session_id)
        current_doc_id = self._session_current_snapshot_id.get(session_id)
        if current_doc_id is None:
            return
        document = self._snapshot_documents.get((session.compile_run_id, current_doc_id))
        if document is None:
            return
        overlay_ids = self._session_overlays.get(session_id, [])
        event = self._overlays.get(overlay_ids[-1]) if overlay_ids else None
        updated = document_with_verification_record(document, result, event)
        run_dir = self._run_dirs.get(session.compile_run_id, self._snapshot_run_dir)
        if run_dir is None:
            return
        self._snapshot_repository.save_overlay(
            updated,
            self._overlay_path(run_dir, updated.identity.snapshot_id),
        )
        self._snapshot_documents[(session.compile_run_id, updated.identity.snapshot_id)] = updated

    @staticmethod
    def _overlay_path(run_dir: Path, snapshot_id: str) -> Path:
        return Path(run_dir) / "spl_editing_overlays" / f"{snapshot_id}.json"

    # ------------------------------------------------------------------
    # Registry resolution helpers
    # ------------------------------------------------------------------

    def _resolve_catalog_entry(
        self,
        issue: EditableIssue,
        affordance_id: str,
        patch_type: str,
    ) -> RepairCatalogEntry:
        """Resolve exactly one catalog entry by affordance_id + patch_type.

        Zero or multiple matches 闁?fail-fast.  Never falls back to
        ``entries[0]``.
        """
        entries = self._catalog.find_by_construct_slot_kind(
            issue.irs_ref.construct_type,
            issue.irs_ref.slot_name,
            issue.kind,
        )
        if not entries:
            raise UnsupportedIssueError(
                f"No catalog entries for construct={issue.irs_ref.construct_type}, "
                f"slot={issue.irs_ref.slot_name}, kind={issue.kind}"
            )
        matches = [
            e
            for e in entries
            if e.affordance_id == affordance_id and patch_type in e.supported_patch_types
        ]
        if len(matches) == 0:
            raise UnsupportedIssueError(
                f"No catalog entry matches affordance_id='{affordance_id}' "
                f"and patch_type='{patch_type}'"
            )
        if len(matches) > 1:
            raise UnsupportedIssueError(
                f"Multiple catalog entries match affordance_id='{affordance_id}' "
                f"and patch_type='{patch_type}': "
                f"{[m.entry_id for m in matches]}"
            )
        return matches[0]

    def _resolve_handler_id(self, issue: EditableIssue) -> str:
        entries = self._catalog.find_by_construct_slot_kind(
            issue.irs_ref.construct_type,
            issue.irs_ref.slot_name,
            issue.kind,
        )
        if not entries:
            raise UnsupportedIssueError(f"No catalog entries for {issue.kind}")
        # All entries for the same construct_slot_kind must agree on handler_id.
        handler_ids = {e.handler_id for e in entries if e.handler_id}
        if len(handler_ids) == 0:
            raise UnsupportedIssueError(f"No handler_id in catalog entries for {issue.kind}")
        if len(handler_ids) > 1:
            raise UnsupportedIssueError(f"Conflicting handler_ids for {issue.kind}: {handler_ids}")
        return next(iter(handler_ids))

    def _resolve_target_resolver_id(self, issue: EditableIssue) -> str:
        entries = self._catalog.find_by_construct_slot_kind(
            issue.irs_ref.construct_type,
            issue.irs_ref.slot_name,
            issue.kind,
        )
        if not entries:
            raise UnsupportedIssueError(f"No catalog entries for {issue.kind}")
        tids = {e.target_resolver_id for e in entries if e.target_resolver_id}
        if len(tids) == 0:
            raise UnsupportedIssueError("No target_resolver_id in catalog entries")
        if len(tids) > 1:
            raise UnsupportedIssueError(f"Conflicting target_resolver_ids: {tids}")
        return next(iter(tids))

    def _resolve_context_id(self, issue: EditableIssue) -> str:
        entries = self._catalog.find_by_construct_slot_kind(
            issue.irs_ref.construct_type,
            issue.irs_ref.slot_name,
            issue.kind,
        )
        if not entries:
            raise UnsupportedIssueError(f"No catalog entries for {issue.kind}")
        cids = {e.context_id for e in entries if e.context_id}
        if len(cids) == 0:
            raise UnsupportedIssueError("No context_id in catalog entries")
        if len(cids) > 1:
            raise UnsupportedIssueError(f"Conflicting context_ids: {cids}")
        return next(iter(cids))

    @staticmethod
    def _selected_patch_type(
        entries,
        selected_patch_types: tuple[str, ...] | None,
    ) -> str:
        supported = tuple(
            patch_type for entry in entries for patch_type in entry.supported_patch_types
        )
        if selected_patch_types:
            for patch_type in selected_patch_types:
                if patch_type in supported:
                    return patch_type
            return ""
        return supported[0] if supported else ""
