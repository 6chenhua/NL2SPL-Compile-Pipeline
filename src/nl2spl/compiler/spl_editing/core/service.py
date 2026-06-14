"""SPL Editing service — wires extractors, handlers, patches, and verification.

No diagnostic-kind if-else in this module.  All dispatch goes through
registries keyed by handler_id / affordance_id / patch_type.
"""

from __future__ import annotations

from pathlib import Path

from nl2spl.compiler.artifacts.snapshot.model.document import SnapshotDocument
from nl2spl.compiler.artifacts.snapshot.persistence.file_repository import (
    JsonFileSnapshotRepository,
)
from nl2spl.compiler.artifacts.snapshot.persistence.loader import SnapshotLoader
from nl2spl.compiler.construct_registry import SPLConstructRegistry
from nl2spl.compiler.spl_editing.core.catalog import (
    RepairCatalog,
    RepairCatalogBuilder,
)
from nl2spl.compiler.spl_editing.core.errors import (
    SPLEditingError,
    StaleRevisionError,
    UnsupportedIssueError,
)
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    EditingSession,
    RepairEvidence,
    RepairPatch,
    RepairSuggestion,
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
from nl2spl.compiler.spl_editing.issues.extractor import EditableIssueExtractor
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
    ) -> None:
        self._runtime = runtime
        self._catalog = catalog or RepairCatalogBuilder.from_construct_registry(
            SPLConstructRegistry.default(),
        )
        self._snapshots = ArtifactSnapshotStore()
        self._sessions = SessionStore()
        self._suggestions = SuggestionStore()
        self._overlays = OverlayStore()
        self._verifier = VerificationRunner(lane_a=lane_a)
        self._extractor = EditableIssueExtractor(self._catalog)
        self._applied_patches: dict[str, RepairPatch] = {}
        self._verification_results = VerificationResultStore()
        self._session_overlays: dict[str, list[str]] = {}
        # compile_run_id → snapshot_id
        self._run_snapshot: dict[str, str] = {}
        self._snapshot_repository = snapshot_repository
        self._snapshot_run_dir = Path(snapshot_run_dir) if snapshot_run_dir else None
        self._snapshot_documents: dict[tuple[str, str], SnapshotDocument] = {}
        self._session_current_snapshot_id: dict[str, str] = {}
        self._run_current_snapshot_id: dict[str, str] = {}
        self._run_dirs: dict[str, Path] = {}

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
            snapshot.compile_run_id, snapshot.snapshot_id,
        )
        return snapshot.compile_run_id

    def register_snapshot_file(self, path: Path) -> str:
        """Load a canonical JSON snapshot file and register it for editing."""
        path = Path(path)
        self._snapshot_repository = (
            self._snapshot_repository or JsonFileSnapshotRepository()
        )
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
        snap = self._get_snapshot(compile_run_id)
        return self._extractor.extract(list(snap.compile_diagnostics))

    def list_editable_issues_from_diagnostics(
        self,
        diagnostics: tuple[CompileDiagnostic, ...],
    ) -> tuple[EditableIssue, ...]:
        """Return editable issues from raw diagnostics (no snapshot needed)."""
        return self._extractor.extract(list(diagnostics))

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
        self._session_current_snapshot_id[session.session_id] = (
            self._run_current_snapshot_id.get(compile_run_id, snap.snapshot_id)
        )
        return session

    def generate_suggestions(
        self,
        session_id: str,
        user_instruction: str | None = None,
    ) -> tuple[RepairSuggestion, ...]:
        """Generate repair suggestions for the issue in *session_id*."""
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

        # Build context
        context_id = self._resolve_context_id(issue)
        context_builder = self._runtime.context_builders.get(context_id)
        context = context_builder.build(issue, target, snap, user_instruction)

        # Find catalog entries
        entries = self._catalog.find_by_construct_slot_kind(
            issue.irs_ref.construct_type,
            issue.irs_ref.slot_name,
            issue.kind,
        )

        # Generate
        suggestions = handler.generate_suggestions(
            issue, target, context, entries, user_instruction,
        )

        # Stamp with session metadata, revision, and evidence
        snap = self._get_snapshot(session.compile_run_id)
        result: list[RepairSuggestion] = []
        for s in suggestions:
            stamped_patch = RepairPatch(
                patch_id=f"{session_id}_patch_{len(result):02d}",
                affordance_id=s.patch.affordance_id,
                patch_type=s.patch.patch_type,
                target_ref=s.patch.target_ref,
                irs_ref=s.patch.irs_ref,
                base_compile_run_id=snap.compile_run_id,
                artifact_snapshot_id=snap.snapshot_id,
                overlay_version=snap.overlay_version,
                payload=s.patch.payload,
                preconditions=s.patch.preconditions,
                evidence=s.patch.evidence,  # no confirmed evidence yet
                verification_lane=s.patch.verification_lane,
            )
            stamped = RepairSuggestion(
                suggestion_id=f"{session_id}_sug_{len(result):02d}",
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
        return tuple(result)

    def apply_suggestion(
        self,
        session_id: str,
        suggestion_id: str,
    ) -> EditingSession:
        """Apply a confirmed suggestion.

        Returns an updated session with incremented overlay_version.
        Raises StaleRevisionError if the base snapshot has changed.
        """
        session = self._sessions.get(session_id)
        suggestion = self._suggestions.get(suggestion_id)

        # Cross-session guard
        if suggestion.session_id != session_id:
            raise SPLEditingError(
                f"Suggestion '{suggestion_id}' belongs to session "
                f"'{suggestion.session_id}', not '{session_id}'"
            )

        snap = self._get_snapshot(session.compile_run_id)
        patch = suggestion.patch

        # User-confirmed evidence stamped at apply time.
        # Preserve the original patch revision — do NOT rewrite it to
        # current snapshot.  Stale check below rejects outdated revisions.
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
                user_text="",
                related_diagnostic_id=session.issue.primary_diagnostic_id,
            ),
            verification_lane=patch.verification_lane,
        )

        # Stale revision check — exact match required
        if confirmed_patch.base_compile_run_id != snap.compile_run_id:
            raise StaleRevisionError("compile_run_id mismatch")
        if confirmed_patch.artifact_snapshot_id != snap.snapshot_id:
            raise StaleRevisionError("snapshot_id mismatch")
        if confirmed_patch.overlay_version != snap.overlay_version:
            raise StaleRevisionError(
                f"Patch overlay {confirmed_patch.overlay_version} != "
                f"snapshot {snap.overlay_version}"
            )

        # Find bundle and run validator BEFORE apply
        bundle = self._runtime.patches.get(confirmed_patch.patch_type)
        bundle.validator.validate(confirmed_patch, snap)

        applier = bundle.applier
        patched_snap, overlay_event = applier.apply(confirmed_patch, snap)
        self._snapshots.put(patched_snap)
        self._overlays.register_snapshot(
            patched_snap.compile_run_id, patched_snap.snapshot_id,
        )
        self._overlays.append(overlay_event)

        # Persist applied patch for verification
        self._applied_patches[overlay_event.overlay_id] = confirmed_patch
        self._session_overlays.setdefault(session_id, []).append(
            overlay_event.overlay_id,
        )
        self._persist_overlay_snapshot_if_configured(
            session_id=session_id,
            patched_snapshot=patched_snap,
            overlay_event=overlay_event,
            patch=confirmed_patch,
        )

        # Persist updated session
        updated = EditingSession(
            session_id=session.session_id,
            compile_run_id=session.compile_run_id,
            artifact_snapshot_id=patched_snap.snapshot_id,
            overlay_version=patched_snap.overlay_version,
            issue=session.issue,
            created_at=session.created_at,
        )
        self._sessions.replace(updated)
        return updated

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
                session_id=session_id, patch_id="", accepted=False,
                lane="A", failure_reasons=("No overlay events for this session",),
            )
            self._verification_results.append(session_id, result)
            return result
        last_ov_id = session_ov_ids[-1]
        last_event = self._overlays.get(last_ov_id)
        ov = last_event.overlay_version
        snap = self._snapshots.get(session.compile_run_id, sid, overlay_version=ov)
        base = self._snapshots.get(
            session.compile_run_id, sid, overlay_version=0,
        )

        patch = self._applied_patches.get(last_ov_id)
        if patch is None:
            result = VerificationResult(
                session_id=session_id, patch_id=last_event.patch_id,
                accepted=False, lane="A",
                failure_reasons=("Applied patch not found in storage",),
            )
        else:
            bundle = self._runtime.patches.get(last_event.patch_type)
            result = self._verifier.verify(
                patch, base, snap, bundle.verifier,
            )
        self._persist_verification_if_configured(session_id, result)
        self._verification_results.append(session_id, result)
        return result

    def get_latest_verification(self, session_id: str) -> VerificationResult:
        """Return the most recent verification result for *session_id*."""
        return self._verification_results.get_latest(session_id)

    def list_verifications(
        self, session_id: str,
    ) -> tuple[VerificationResult, ...]:
        """Return all verification results for *session_id*."""
        return self._verification_results.list_all(session_id)

    def get_patched_spl(self, run_id: str) -> str:
        """Return the rendered SPL from real Lane A replay of the latest
        patched snapshot.  Raises if replay fails — caller should handle
        or display the error."""
        from nl2spl.compiler.spl_editing.verification.lanes import LaneAReplayAdapter

        snap = self._get_snapshot(run_id)
        artifacts = LaneAReplayAdapter().replay(snap)
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
            document, self._overlay_path(run_dir, document.identity.snapshot_id),
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
            updated, self._overlay_path(run_dir, updated.identity.snapshot_id),
        )
        self._snapshot_documents[
            (session.compile_run_id, updated.identity.snapshot_id)
        ] = updated

    @staticmethod
    def _overlay_path(run_dir: Path, snapshot_id: str) -> Path:
        return Path(run_dir) / "spl_editing_overlays" / f"{snapshot_id}.json"

    # ------------------------------------------------------------------
    # Registry resolution helpers
    # ------------------------------------------------------------------

    def _resolve_handler_id(self, issue: EditableIssue) -> str:
        entries = self._catalog.find_by_construct_slot_kind(
            issue.irs_ref.construct_type,
            issue.irs_ref.slot_name,
            issue.kind,
        )
        if not entries:
            raise UnsupportedIssueError(
                f"No catalog entries for {issue.kind}")
        hid = entries[0].handler_id
        if hid is None:
            raise UnsupportedIssueError(
                f"No handler_id in catalog entry for {issue.kind}")
        return hid

    def _resolve_target_resolver_id(self, issue: EditableIssue) -> str:
        entries = self._catalog.find_by_construct_slot_kind(
            issue.irs_ref.construct_type,
            issue.irs_ref.slot_name,
            issue.kind,
        )
        tid = entries[0].target_resolver_id
        if tid is None:
            raise UnsupportedIssueError("No target_resolver_id in catalog entry")
        return tid

    def _resolve_context_id(self, issue: EditableIssue) -> str:
        entries = self._catalog.find_by_construct_slot_kind(
            issue.irs_ref.construct_type,
            issue.irs_ref.slot_name,
            issue.kind,
        )
        cid = entries[0].context_id
        if cid is None:
            raise UnsupportedIssueError("No context_id in catalog entry")
        return cid
