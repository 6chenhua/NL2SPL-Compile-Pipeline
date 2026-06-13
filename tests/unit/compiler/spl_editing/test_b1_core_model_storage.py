"""B1: Core model, revision, and storage tests.

Verifies:
  1. All data models construct correctly (frozen, typed).
  2. RepairPatch has required fields.
  3. ArtifactSnapshot require_* accessors fail early on missing artifact.
  4. RevisionToken monotonic overlay + stale detection.
  5. Storage stores accept, retrieve, reject duplicates.
  6. Suggestion does not mutate artifacts.
  7. Overlay version monotonic.
"""

from __future__ import annotations

import json
from dataclasses import is_dataclass

import pytest

from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    StaleRevisionError,
)
from nl2spl.compiler.spl_editing.core.model import (
    EditingSession,
    EditableIssue,
    PatchPrecondition,
    RepairContext,
    RepairEvidence,
    RepairPatch,
    RepairSuggestion,
    RepairTarget,
    VerificationResult,
)
from nl2spl.compiler.spl_editing.core.revision import (
    AcceptedRepairPatch,
    ArtifactSnapshot,
    OverlayEvent,
    RevisionToken,
)
from nl2spl.compiler.spl_editing.storage.artifact_snapshot_store import (
    ArtifactSnapshotStore,
)
from nl2spl.compiler.spl_editing.storage.overlay_store import OverlayStore
from nl2spl.compiler.spl_editing.storage.session_store import SessionStore
from nl2spl.compiler.spl_editing.storage.suggestion_store import SuggestionStore
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef


# ===========================================================================
# B1-1: Data model construction
# ===========================================================================


class TestB1DataModelConstruction:
    """B1: All models are importable, constructible, and frozen."""

    def test_editable_issue_is_frozen(self) -> None:
        issue = EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="diag_1",
            related_diagnostic_ids=("diag_1", "diag_2"),
            issue_group_id="group_1",
            kind="missing_handler",
            target_ref="worker:w_main.exception_flow:exc_1",
            irs_ref=DiagnosticIRSRef(
                construct_type="EXCEPTION_FLOW",
                construct_id="worker:w_main.exception_flow:exc_1",
                slot_name="handler_action",
            ),
            missing_slot="handler_action",
            source_span_ids=(),
            message="No handler step.",
        )
        assert issue.kind == "missing_handler"
        # Frozen: cannot set attributes
        with pytest.raises(Exception):
            issue.kind = "mutated"  # type: ignore[misc]

    def test_editing_session_construction(self) -> None:
        issue = EditableIssue(
            issue_id="issue_1",
            primary_diagnostic_id="diag_1",
            related_diagnostic_ids=("diag_1",),
            issue_group_id=None,
            kind="missing_handler",
            target_ref="x",
            irs_ref=DiagnosticIRSRef(
                construct_type="EXCEPTION_FLOW",
                construct_id="exc_1",
                slot_name="handler_action",
            ),
            missing_slot="handler_action",
            source_span_ids=(),
            message="No handler.",
        )
        session = EditingSession(
            session_id="sess_1",
            compile_run_id="run_1",
            artifact_snapshot_id="snap_1",
            overlay_version=0,
            issue=issue,
            created_at="2026-06-12T00:00:00Z",
        )
        assert session.compile_run_id == "run_1"
        assert session.overlay_version == 0

    def test_repair_patch_has_required_fields(self) -> None:
        """B1: RepairPatch must include base revision info."""
        patch = RepairPatch(
            patch_id="patch_1",
            affordance_id="exception_flow.add_handler_step",
            patch_type="AddExceptionHandlerStep",
            target_ref="worker:w_main.exception_flow:exc_1",
            irs_ref=DiagnosticIRSRef(
                construct_type="EXCEPTION_FLOW",
                construct_id="worker:w_main.exception_flow:exc_1",
                slot_name="handler_action",
            ),
            base_compile_run_id="run_1",
            artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={"handler_text": "Ask user"},
            preconditions=(
                PatchPrecondition("pre_1", "target exists", True),
            ),
            evidence=RepairEvidence(
                evidence_kind="user_confirmed_repair",
                user_text="Add a handler step.",
                related_diagnostic_id="diag_1",
            ),
            verification_lane="A",
        )
        assert patch.patch_type == "AddExceptionHandlerStep"
        assert patch.base_compile_run_id == "run_1"
        assert patch.artifact_snapshot_id == "snap_1"
        assert patch.overlay_version == 0

    def test_repair_suggestion_preview_is_not_apply_authority(self) -> None:
        """B1: Suggestion has spl_preview but apply uses patch payload."""
        patch = RepairPatch(
            patch_id="patch_1",
            affordance_id="exception_flow.add_handler_step",
            patch_type="AddExceptionHandlerStep",
            target_ref="x",
            irs_ref=DiagnosticIRSRef(
                construct_type="EXCEPTION_FLOW",
                construct_id="x",
                slot_name="handler_action",
            ),
            base_compile_run_id="run_1",
            artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={"handler_text": "Real payload"},
        )
        suggestion = RepairSuggestion(
            suggestion_id="sug_1",
            session_id="sess_1",
            affordance_id="exception_flow.add_handler_step",
            title="Add handler",
            explanation="Add a handler step.",
            patch=patch,
            spl_preview="REQUEST_INPUT Ask the user for input.",  # display only
        )
        # preview exists for display
        assert suggestion.spl_preview is not None
        # but the patch payload is the real authority
        assert suggestion.patch.payload == {"handler_text": "Real payload"}
        # preview text alone cannot drive apply
        assert suggestion.patch.patch_type == "AddExceptionHandlerStep"

    def test_verification_result_defaults(self) -> None:
        """B1: VerificationResult has sensible defaults."""
        result = VerificationResult(
            session_id="sess_1",
            patch_id="patch_1",
            accepted=False,
            lane="A",
        )
        assert result.accepted is False
        assert result.resolved_diagnostic_ids == ()
        assert result.new_blocking_diagnostic_ids == ()
        assert result.failure_reasons == ()

    def test_repair_target_maps_irs_ref(self) -> None:
        """B1: RepairTarget carries the irs_ref from the issue."""
        irs_ref = DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW",
            construct_id="worker:w_main.exception_flow:exc_1",
            slot_name="handler_action",
        )
        target = RepairTarget(
            target_ref="worker:w_main.exception_flow:exc_1",
            target_kind="EXCEPTION_FLOW",
            irs_ref=irs_ref,
            affordance_id="exception_flow.add_handler_step",
            construct_path=("worker", "w_main", "exception_flows", "exc_1"),
            worker_id="w_main",
        )
        assert target.irs_ref.construct_type == "EXCEPTION_FLOW"
        assert target.worker_id == "w_main"


# ===========================================================================
# B1-2: ArtifactSnapshot require_* accessors
# ===========================================================================


class TestB1ArtifactSnapshot:
    """B1: ArtifactSnapshot is frozen and fails early on missing artifacts."""

    def test_snapshot_is_frozen(self) -> None:
        snap = ArtifactSnapshot(
            snapshot_id="snap_1",
            compile_run_id="run_1",
            overlay_version=0,
        )
        assert is_dataclass(snap)
        with pytest.raises(Exception):
            snap.snapshot_id = "mutated"  # type: ignore[misc]

    def test_require_worker_plan_fails_early(self) -> None:
        snap = ArtifactSnapshot(
            snapshot_id="snap_1",
            compile_run_id="run_1",
            overlay_version=0,
            worker_plan=None,
        )
        with pytest.raises(PatchValidationError, match="worker_plan"):
            snap.require_worker_plan()

    def test_require_worker_plan_succeeds_when_present(self) -> None:
        fake_plan = object()
        snap = ArtifactSnapshot(
            snapshot_id="snap_1",
            compile_run_id="run_1",
            overlay_version=0,
            worker_plan=fake_plan,
        )
        assert snap.require_worker_plan() is fake_plan

    def test_require_worker_step_plan_fails_early(self) -> None:
        snap = ArtifactSnapshot(
            snapshot_id="snap_1",
            compile_run_id="run_1",
            overlay_version=0,
        )
        with pytest.raises(PatchValidationError, match="worker_step_plan"):
            snap.require_worker_step_plan()

    def test_require_compile_diagnostics_always_works(self) -> None:
        """B1: compile_diagnostics defaults to empty tuple, never None."""
        snap = ArtifactSnapshot(
            snapshot_id="snap_1",
            compile_run_id="run_1",
            overlay_version=0,
        )
        assert snap.require_compile_diagnostics() == ()

    def test_derive_preserves_carried_artifacts(self) -> None:
        """B1: derive() carries over unmodified artifacts, updates revision."""
        diag = CompileDiagnostic(
            diagnostic_id="diag_1",
            kind="missing_handler",
            severity="warning",
            message="test",
            target_ref="x",
            blocks_completion=True,
        )
        snap = ArtifactSnapshot(
            snapshot_id="snap_1",
            compile_run_id="run_1",
            overlay_version=0,
            compile_diagnostics=(diag,),
        )
        token = RevisionToken("run_1", "snap_1", 1)
        derived = snap.derive(token)
        assert derived.overlay_version == 1
        assert derived.compile_diagnostics == (diag,)
        assert snap.overlay_version == 0  # original unchanged

    def test_derive_rejects_mismatched_run(self) -> None:
        """B1: derive() with different compile_run_id raises StaleRevisionError."""
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        token = RevisionToken("run_2", "snap_1", 1)
        with pytest.raises(StaleRevisionError, match="mismatched"):
            snap.derive(token)

    def test_derive_rejects_mismatched_snapshot_id(self) -> None:
        """B1: derive() with different snapshot_id raises StaleRevisionError."""
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        token = RevisionToken("run_1", "snap_2", 1)
        with pytest.raises(StaleRevisionError, match="mismatched"):
            snap.derive(token)

    def test_derive_rejects_non_increasing_overlay(self) -> None:
        """B1: derive() requires overlay_version to increase — StaleRevisionError."""
        snap = ArtifactSnapshot("snap_1", "run_1", 5)
        token = RevisionToken("run_1", "snap_1", 3)
        with pytest.raises(StaleRevisionError, match="must increase"):
            snap.derive(token)

    def test_derive_with_replacement_does_not_mutate_base(self) -> None:
        """B1: derive() with explicit replacement leaves base snapshot untouched."""
        base_final_spl = "ORIGINAL SPL"
        snap = ArtifactSnapshot(
            snapshot_id="snap_1",
            compile_run_id="run_1",
            overlay_version=0,
            final_spl=base_final_spl,
        )
        derived = snap.derive(
            RevisionToken("run_1", "snap_1", 1),
            final_spl="PATCHED SPL",
        )
        # Derived has new value
        assert derived.final_spl == "PATCHED SPL"
        # Base is untouched
        assert snap.final_spl == base_final_spl
        assert snap.overlay_version == 0

    def test_derive_without_replacement_carries_over(self) -> None:
        """B1: derive() without explicit replacement carries base artifact."""
        orig_plan = object()
        snap = ArtifactSnapshot(
            snapshot_id="snap_1",
            compile_run_id="run_1",
            overlay_version=0,
            worker_plan=orig_plan,
        )
        derived = snap.derive(RevisionToken("run_1", "snap_1", 1))
        assert derived.worker_plan is orig_plan

    def test_derive_explicit_none_clears_field(self) -> None:
        """B1: derive() with final_spl=None explicitly clears it
        (does NOT carry over old SPL)."""
        snap = ArtifactSnapshot(
            snapshot_id="snap_1",
            compile_run_id="run_1",
            overlay_version=0,
            final_spl="OLD SPL",
        )
        derived = snap.derive(
            RevisionToken("run_1", "snap_1", 1),
            final_spl=None,
        )
        assert derived.final_spl is None

    def test_derive_omitted_field_carries_over(self) -> None:
        """B1: derive() without mentioning final_spl carries it over."""
        snap = ArtifactSnapshot(
            snapshot_id="snap_1",
            compile_run_id="run_1",
            overlay_version=0,
            final_spl="OLD SPL",
        )
        derived = snap.derive(RevisionToken("run_1", "snap_1", 1))
        assert derived.final_spl == "OLD SPL"


# ===========================================================================
# B1-3: Revision token
# ===========================================================================


class TestB1RevisionToken:
    """B1: RevisionToken monotonic overlay + stale detection."""

    def test_next_overlay_increments(self) -> None:
        tok = RevisionToken("run_1", "snap_1", 0)
        next_tok = tok.next_overlay()
        assert next_tok.overlay_version == 1
        assert next_tok.compile_run_id == "run_1"
        assert next_tok.artifact_snapshot_id == "snap_1"

    def test_not_stale_when_same_version(self) -> None:
        base = RevisionToken("run_1", "snap_1", 0)
        current = RevisionToken("run_1", "snap_1", 0)
        assert not base.is_stale_relative_to(current)

    def test_stale_when_behind(self) -> None:
        base = RevisionToken("run_1", "snap_1", 0)
        current = RevisionToken("run_1", "snap_1", 3)
        assert base.is_stale_relative_to(current)

    def test_stale_when_different_snapshot(self) -> None:
        base = RevisionToken("run_1", "snap_1", 5)
        current = RevisionToken("run_1", "snap_2", 0)
        assert base.is_stale_relative_to(current)

    def test_not_stale_when_ahead(self) -> None:
        base = RevisionToken("run_1", "snap_1", 5)
        current = RevisionToken("run_1", "snap_1", 3)
        assert not base.is_stale_relative_to(current)

    def test_overlay_version_monotonically_increasing(self) -> None:
        tok = RevisionToken("run_1", "snap_1", 0)
        for i in range(1, 6):
            tok = tok.next_overlay()
            assert tok.overlay_version == i


# ===========================================================================
# B1-4: In-memory stores
# ===========================================================================


class TestB1Stores:
    """B1: Stores accept, retrieve, reject duplicates. No silent fallback."""

    # -- helpers --

    @staticmethod
    def _make_issue() -> EditableIssue:
        return EditableIssue(
            issue_id="i1",
            primary_diagnostic_id="d1",
            related_diagnostic_ids=("d1",),
            issue_group_id=None,
            kind="missing_handler",
            target_ref="x",
            irs_ref=DiagnosticIRSRef(
                construct_type="EXCEPTION_FLOW",
                construct_id="x",
                slot_name="handler_action",
            ),
            missing_slot="handler_action",
            source_span_ids=(),
            message="No handler.",
        )

    @staticmethod
    def _make_patch(**kw: object) -> RepairPatch:
        defaults: dict[str, object] = dict(
            patch_id="p1",
            affordance_id="exception_flow.add_handler_step",
            patch_type="AddExceptionHandlerStep",
            target_ref="x",
            irs_ref=DiagnosticIRSRef(
                construct_type="EXCEPTION_FLOW",
                construct_id="x",
                slot_name="handler_action",
            ),
            base_compile_run_id="run_1",
            artifact_snapshot_id="snap_1",
            overlay_version=0,
            payload={},
        )
        defaults.update(kw)
        return RepairPatch(**defaults)  # type: ignore[arg-type]

    # -- snapshot store (run-scoped, multi-version) --

    def test_snapshot_store_put_and_get(self) -> None:
        store = ArtifactSnapshotStore()
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        store.put(snap)
        assert store.has("run_1", "snap_1")
        assert store.get("run_1", "snap_1") is snap

    def test_snapshot_store_put_and_get_latest(self) -> None:
        store = ArtifactSnapshotStore()
        store.put(ArtifactSnapshot("snap_1", "run_1", 0))
        store.put(ArtifactSnapshot("snap_1", "run_1", 1))
        latest = store.get("run_1", "snap_1")
        assert latest.overlay_version == 1

    def test_snapshot_store_get_by_exact_version(self) -> None:
        store = ArtifactSnapshotStore()
        store.put(ArtifactSnapshot("snap_1", "run_1", 0))
        store.put(ArtifactSnapshot("snap_1", "run_1", 1))
        v0 = store.get("run_1", "snap_1", overlay_version=0)
        assert v0.overlay_version == 0

    def test_snapshot_store_duplicate_revision_rejected(self) -> None:
        store = ArtifactSnapshotStore()
        store.put(ArtifactSnapshot("snap_1", "run_1", 0))
        with pytest.raises(KeyError):
            store.put(ArtifactSnapshot("snap_1", "run_1", 0))

    def test_snapshot_store_missing_raises(self) -> None:
        store = ArtifactSnapshotStore()
        with pytest.raises(KeyError):
            store.get("run_1", "no_such_snapshot")

    def test_snapshot_store_get_latest_overlay_version(self) -> None:
        store = ArtifactSnapshotStore()
        store.put(ArtifactSnapshot("snap_1", "run_1", 0))
        store.put(ArtifactSnapshot("snap_1", "run_1", 3))
        assert store.get_latest_overlay_version("run_1", "snap_1") == 3

    def test_snapshot_store_runs_are_isolated(self) -> None:
        """B1: run_A/snap_1/v0 and run_B/snap_1/v0 coexist independently."""
        store = ArtifactSnapshotStore()
        store.put(ArtifactSnapshot("snap_1", "run_A", 0))
        store.put(ArtifactSnapshot("snap_1", "run_B", 0))
        store.put(ArtifactSnapshot("snap_1", "run_A", 1))

        assert store.get_latest_overlay_version("run_A", "snap_1") == 1
        assert store.get_latest_overlay_version("run_B", "snap_1") == 0
        assert store.get("run_A", "snap_1").overlay_version == 1
        assert store.get("run_B", "snap_1").overlay_version == 0

    # -- session store --

    def test_session_store(self) -> None:
        store = SessionStore()
        session = EditingSession(
            session_id="s1",
            compile_run_id="run_1",
            artifact_snapshot_id="snap_1",
            overlay_version=0,
            issue=self._make_issue(),
            created_at="now",
        )
        store.put(session)
        assert store.has("s1")
        assert store.get("s1").session_id == "s1"

    # -- suggestion store (with registration) --

    def test_suggestion_store_unknown_session_raises(self) -> None:
        """B1: list_for_session on unknown session raises KeyError."""
        store = SuggestionStore()
        with pytest.raises(KeyError, match="not registered"):
            store.list_for_session("bad_session")

    def test_suggestion_store_put_to_unknown_session_raises(self) -> None:
        """B1: put() for unknown session raises KeyError."""
        store = SuggestionStore()
        sug = RepairSuggestion(
            suggestion_id="sug_1",
            session_id="bad_session",
            affordance_id="a1",
            title="T1",
            explanation="E1",
            patch=self._make_patch(),
        )
        with pytest.raises(KeyError, match="not registered"):
            store.put(sug)

    def test_suggestion_store_registered_session_empty_is_empty_tuple(
        self,
    ) -> None:
        """B1: Registered session with no suggestions returns ()."""
        store = SuggestionStore()
        store.register_session("sess_1")
        assert store.list_for_session("sess_1") == ()

    def test_suggestion_store_list_for_session(self) -> None:
        store = SuggestionStore()
        store.register_session("sess_1")
        sug1 = RepairSuggestion(
            suggestion_id="sug_1",
            session_id="sess_1",
            affordance_id="a1",
            title="T1",
            explanation="E1",
            patch=self._make_patch(),
        )
        sug2 = RepairSuggestion(
            suggestion_id="sug_2",
            session_id="sess_1",
            affordance_id="a2",
            title="T2",
            explanation="E2",
            patch=self._make_patch(),
        )
        store.put(sug1)
        store.put(sug2)
        assert len(store.list_for_session("sess_1")) == 2

    def test_suggestion_store_does_not_mutate_artifacts(self) -> None:
        """B1: Putting a suggestion does not change any snapshot."""
        snap_store = ArtifactSnapshotStore()
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        snap_store.put(snap)

        sug_store = SuggestionStore()
        sug_store.register_session("sess_1")
        sug = RepairSuggestion(
            suggestion_id="sug_1",
            session_id="sess_1",
            affordance_id="x",
            title="T",
            explanation="E",
            patch=self._make_patch(),
        )
        sug_store.put(sug)

        assert snap_store.get("run_1", "snap_1").overlay_version == 0

    # -- overlay store (run-scoped, with registration) --

    def test_overlay_store_unknown_snapshot_raises_on_list(self) -> None:
        store = OverlayStore()
        with pytest.raises(KeyError, match="not registered"):
            store.list_for_snapshot("run_1", "bad_snap")

    def test_overlay_store_unknown_snapshot_raises_on_latest_version(
        self,
    ) -> None:
        store = OverlayStore()
        with pytest.raises(KeyError, match="not registered"):
            store.latest_overlay_version("run_1", "bad_snap")

    def test_overlay_store_append_to_unknown_snapshot_raises(self) -> None:
        store = OverlayStore()
        event = OverlayEvent(
            overlay_id="ov_1",
            base_compile_run_id="run_1",
            base_artifact_snapshot_id="bad_snap",
            overlay_version=1,
            patch_type="T", affordance_id="A", patch_id="p_1", accepted=True,
        )
        with pytest.raises(KeyError, match="not registered"):
            store.append(event)

    def test_overlay_store_registered_snapshot_no_overlays_is_zero(
        self,
    ) -> None:
        store = OverlayStore()
        store.register_snapshot("run_1", "snap_1")
        assert store.latest_overlay_version("run_1", "snap_1") == 0
        assert store.list_for_snapshot("run_1", "snap_1") == ()

    def test_overlay_store_append_and_list(self) -> None:
        store = OverlayStore()
        store.register_snapshot("run_1", "snap_1")
        store.append(OverlayEvent(
            overlay_id="ov_1",
            base_compile_run_id="run_1",
            base_artifact_snapshot_id="snap_1",
            overlay_version=1,
            patch_type="AddExceptionHandlerStep",
            affordance_id="exception_flow.add_handler_step",
            patch_id="patch_1", accepted=True,
        ))
        assert store.has("ov_1")
        assert len(store.list_for_snapshot("run_1", "snap_1")) == 1

    def test_overlay_version_monotonic_only(self) -> None:
        store = OverlayStore()
        store.register_snapshot("run_1", "snap_1")
        for i in range(1, 4):
            store.append(OverlayEvent(
                overlay_id=f"ov_{i}",
                base_compile_run_id="run_1",
                base_artifact_snapshot_id="snap_1",
                overlay_version=i,
                patch_type="T", affordance_id="A", patch_id=f"p_{i}", accepted=True,
            ))
        assert store.latest_overlay_version("run_1", "snap_1") == 3

    def test_overlay_append_rejects_skip(self) -> None:
        """B1: append() rejects overlay_version != latest + 1 (skip).
        Raises StaleRevisionError (typed), not raw ValueError."""
        store = OverlayStore()
        store.register_snapshot("run_1", "snap_1")
        store.append(OverlayEvent(
            overlay_id="ov_1",
            base_compile_run_id="run_1",
            base_artifact_snapshot_id="snap_1",
            overlay_version=1,
            patch_type="T", affordance_id="A", patch_id="p_1", accepted=True,
        ))
        with pytest.raises(StaleRevisionError, match="must be 2"):
            store.append(OverlayEvent(
                overlay_id="ov_3",
                base_compile_run_id="run_1",
                base_artifact_snapshot_id="snap_1",
                overlay_version=3,
                patch_type="T", affordance_id="A", patch_id="p_3", accepted=True,
            ))

    def test_overlay_append_rejects_duplicate_version(self) -> None:
        """B1: append() rejects duplicate overlay version.
        Raises StaleRevisionError (typed), not raw ValueError."""
        store = OverlayStore()
        store.register_snapshot("run_1", "snap_1")
        store.append(OverlayEvent(
            overlay_id="ov_1",
            base_compile_run_id="run_1",
            base_artifact_snapshot_id="snap_1",
            overlay_version=1,
            patch_type="T", affordance_id="A", patch_id="p_1", accepted=True,
        ))
        with pytest.raises(StaleRevisionError, match="must be 2"):
            store.append(OverlayEvent(
                overlay_id="ov_1b",
                base_compile_run_id="run_1",
                base_artifact_snapshot_id="snap_1",
                overlay_version=1,
                patch_type="T", affordance_id="A", patch_id="p_1b", accepted=True,
            ))

    def test_overlay_runs_are_isolated(self) -> None:
        """B1: run_A/snap_1 and run_B/snap_1 have independent overlay logs."""
        store = OverlayStore()
        store.register_snapshot("run_A", "snap_1")
        store.register_snapshot("run_B", "snap_1")

        store.append(OverlayEvent(
            overlay_id="ov_a1", base_compile_run_id="run_A",
            base_artifact_snapshot_id="snap_1", overlay_version=1,
            patch_type="T", affordance_id="A", patch_id="pa", accepted=True,
        ))
        # run_B is independent — its first overlay is still 1, not 2
        store.append(OverlayEvent(
            overlay_id="ov_b1", base_compile_run_id="run_B",
            base_artifact_snapshot_id="snap_1", overlay_version=1,
            patch_type="T", affordance_id="A", patch_id="pb", accepted=True,
        ))

        assert store.latest_overlay_version("run_A", "snap_1") == 1
        assert store.latest_overlay_version("run_B", "snap_1") == 1


# ===========================================================================
# B1-5: Stale revision detection through stores
# ===========================================================================


class TestB1StaleRevision:
    """B1: Applying to a stale base is detected."""

    def test_stale_when_newer_overlay_exists(self) -> None:
        overlay_store = OverlayStore()
        overlay_store.register_snapshot("run_1", "snap_1")
        overlay_store.append(OverlayEvent(
            overlay_id="ov_1",
            base_compile_run_id="run_1",
            base_artifact_snapshot_id="snap_1",
            overlay_version=1,
            patch_type="T", affordance_id="A", patch_id="p_1", accepted=True,
        ))
        base_token = RevisionToken("run_1", "snap_1", 0)
        latest = overlay_store.latest_overlay_version("run_1", "snap_1")
        current_token = RevisionToken("run_1", "snap_1", latest)
        assert base_token.is_stale_relative_to(current_token)

    def test_not_stale_when_targeting_latest(self) -> None:
        overlay_store = OverlayStore()
        overlay_store.register_snapshot("run_1", "snap_1")
        base_token = RevisionToken("run_1", "snap_1", 0)
        latest = overlay_store.latest_overlay_version("run_1", "snap_1")
        current_token = RevisionToken("run_1", "snap_1", latest)
        assert not base_token.is_stale_relative_to(current_token)

    def test_different_compile_run_id_is_stale(self) -> None:
        base = RevisionToken("run_A", "snap_1", 0)
        current = RevisionToken("run_B", "snap_1", 0)
        assert base.is_stale_relative_to(current)

    def test_stale_via_snapshot_store(self) -> None:
        store = ArtifactSnapshotStore()
        store.put(ArtifactSnapshot("snap_1", "run_1", 0))
        store.put(ArtifactSnapshot("snap_1", "run_1", 1))
        base_token = RevisionToken("run_1", "snap_1", 0)
        latest = store.get_latest_overlay_version("run_1", "snap_1")
        current_token = RevisionToken("run_1", "snap_1", latest)
        assert base_token.is_stale_relative_to(current_token)


# ===========================================================================
# B1-6: Error on missing required artifact
# ===========================================================================


class TestB1MissingArtifactFailsEarly:
    """B1: Missing required artifacts produce typed errors before apply."""

    def test_missing_worker_plan_fails_before_patch_validation(self) -> None:
        """B1: Accessing a missing artifact raises PatchValidationError,
        not a generic AttributeError or NoneType error.
        """
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        with pytest.raises(PatchValidationError):
            snap.require_worker_plan()

    def test_missing_worker_flow_plan_fails_early(self) -> None:
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        with pytest.raises(PatchValidationError):
            snap.require_worker_flow_plan()

    def test_missing_resources_fails_early(self) -> None:
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        with pytest.raises(PatchValidationError):
            snap.require_resources()

    def test_missing_final_worker_fails_early(self) -> None:
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        with pytest.raises(PatchValidationError):
            snap.require_final_worker()
