"""B8: SPL Editing service tests."""

import pytest

from nl2spl.compiler.spl_editing.core.errors import (
    PatchValidationError,
    SPLEditingError,
    StaleRevisionError,
    UnsupportedIssueError,
)
from nl2spl.compiler.spl_editing.core.model import (
    EditableIssue,
    RepairContext,
    RepairPatch,
    RepairSuggestion,
    RepairTarget,
)
from nl2spl.compiler.spl_editing.core.registry import SPLEditingRuntimeRegistry
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot, OverlayEvent
from nl2spl.compiler.spl_editing.core.service import SPLEditingService
from nl2spl.compiler.spl_editing.patches.registry import PatchBundle
from nl2spl.compiler.spl_editing.verification.lanes import (
    LaneAReplayAdapter,
    VerificationArtifacts,
)
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef

# ===========================================================================
# Stubs
# ===========================================================================


class _StubResolver:
    def resolve(self, issue, snapshot):
        return RepairTarget(
            target_ref=issue.target_ref,
            target_kind=issue.irs_ref.construct_type,
            irs_ref=issue.irs_ref,
            affordance_id=issue.default_affordance_id or "",
            construct_path=(),
        )


class _StubContextBuilder:
    def build(self, issue, target, snapshot, instruction=None):
        return RepairContext(issue=issue, target=target,
                              user_instruction=instruction)


class _StubHandler:
    def generate_suggestions(
        self, issue, target, context, entries,
        instruction=None, selected_patch_types=None,
        *,
        rendered_user_prompt=None,
    ):
        return (RepairSuggestion(
            suggestion_id="sug_0", session_id="",
            affordance_id="exception_flow.add_handler_step",
            title="Add handler", explanation="Add a handler.",
            patch=RepairPatch(
                patch_id="p1", affordance_id="exception_flow.add_handler_step",
                patch_type="AddExceptionHandlerStep",
                target_ref=issue.target_ref, irs_ref=issue.irs_ref,
                base_compile_run_id="", artifact_snapshot_id="",
                overlay_version=0, payload={
                    "worker_id": "w_main",
                    "exception_flow_id": "exc_1",
                    "handler_text": "Handle error.",
                    "command_type": "GENERAL_COMMAND",
                },
                verification_lane="A",
            ),
        ),)


class _StubValidator:
    def validate(self, patch, snapshot):
        pass


class _StubApplier:
    def apply(self, patch, snapshot):
        from nl2spl.compiler.spl_editing.core.revision import RevisionToken
        from nl2spl.ir.block_structure_ir import BlockStructureIR
        from nl2spl.ir.step_ir import StepIR
        from nl2spl.ir.worker_plan_ir import WorkerBlockPlanIR, WorkerStepPlanIR

        sp = WorkerStepPlanIR("w_main", {"w_main": [StepIR(
            "st_repair_1", "Handle error.", [], "GENERAL_COMMAND",
            flow_ref="exc_1",
            metadata={"origin": "user_confirmed_repair"},
        )]})
        bp = WorkerBlockPlanIR({"w_main": BlockStructureIR()})

        next_token = RevisionToken(
            snapshot.compile_run_id, snapshot.snapshot_id,
            snapshot.overlay_version + 1,
        )
        patched = snapshot.derive(
            next_token, worker_step_plan=sp, worker_block_plan=bp,
            compile_diagnostics=tuple(
                d for d in snapshot.compile_diagnostics
                if d.diagnostic_id != patch.evidence.related_diagnostic_id
            ),
            final_spl=None, final_worker=None,
        )
        event = OverlayEvent(
            overlay_id=f"ov_{snapshot.snapshot_id}_{snapshot.overlay_version + 1}",
            base_compile_run_id=snapshot.compile_run_id,
            base_artifact_snapshot_id=snapshot.snapshot_id,
            overlay_version=snapshot.overlay_version + 1,
            patch_type=patch.patch_type,
            affordance_id=patch.affordance_id,
            patch_id=patch.patch_id, accepted=True,
        )
        return patched, event


class _StubVerifier:
    def verify(self, patch, base, patched, artifacts):
        return ()


# ===========================================================================
# Tests
# ===========================================================================


def _make_mh_issue() -> EditableIssue:
    return EditableIssue(
        issue_id="i1", primary_diagnostic_id="d1",
        related_diagnostic_ids=("d1",), issue_group_id=None,
        kind="missing_handler",
        target_ref="worker:w_main.exception_flow:exc_1",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW", construct_id="x",
            slot_name="handler_action",
        ),
        missing_slot="handler_action", source_span_ids=(),
        message="No handler.", authority="post_normalize_irs",
        affordance_ids=("exception_flow.add_handler_step",),
        default_affordance_id="exception_flow.add_handler_step",
    )


class _StubLane(LaneAReplayAdapter):
    def replay(self, snapshot):
        return VerificationArtifacts(
            consolidated_diagnostics=snapshot.compile_diagnostics,
            rendered_spl=snapshot.final_spl or "",
        )


def _make_service() -> SPLEditingService:
    reg = SPLEditingRuntimeRegistry()
    reg.target_resolvers.register("exception_flow_target", _StubResolver())
    reg.context_builders.register("exception_flow_context", _StubContextBuilder())
    reg.handlers.register("missing_handler", _StubHandler())
    from nl2spl.compiler.spl_editing.core.model import PatchTypeContract
    reg.patches.register("AddExceptionHandlerStep", PatchBundle(
        patch_type="AddExceptionHandlerStep",
        validator=_StubValidator(), applier=_StubApplier(),
        verifier=_StubVerifier(), previewer=object(),
        contract=PatchTypeContract(
            patch_type="AddExceptionHandlerStep",
            produces_step_ir=True,
            evidence_targets=("step",),
        ),
    ))
    return SPLEditingService(reg, lane_a=_StubLane())


class TestB8Service:
    def test_register_and_list_issues(self) -> None:
        svc = _make_service()
        diag = CompileDiagnostic(
            "diag_1", "missing_handler", "warning",
            "No handler.", target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
        )
        diag.metadata["irs_ref"] = {
            "construct_type": "EXCEPTION_FLOW", "construct_id": "x",
            "slot_name": "handler_action", "construct_path": [],
            "source_authority": "post_normalize_irs",
        }
        diag.metadata["authority"] = "post_normalize_irs"
        snap = ArtifactSnapshot("snap_1", "run_1", 0, compile_diagnostics=(diag,))
        run_id = svc.register_compile_result(snap)
        issues = svc.list_editable_issues(run_id)
        assert len(issues) == 1

    def test_create_session_and_generate_suggestions(self) -> None:
        svc = _make_service()
        issue = _make_mh_issue()
        diag = CompileDiagnostic(
            "diag_1", "missing_handler", "warning",
            "No handler.", target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
        )
        diag.metadata["irs_ref"] = {
            "construct_type": "EXCEPTION_FLOW", "construct_id": "x",
            "slot_name": "handler_action", "construct_path": [],
            "source_authority": "post_normalize_irs",
        }
        diag.metadata["authority"] = "post_normalize_irs"
        snap = ArtifactSnapshot("snap_1", "run_1", 0, compile_diagnostics=(diag,))
        svc.register_compile_result(snap)
        session = svc.create_session("run_1", issue)
        assert session.session_id.startswith("sess_")

        suggestions = svc.generate_suggestions(session.session_id)
        assert len(suggestions) >= 1
        assert suggestions[0].patch.patch_type == "AddExceptionHandlerStep"

    def test_unknown_issue_raises(self) -> None:
        svc = _make_service()
        # Register a base snapshot first
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        svc.register_compile_result(snap)

        issue = EditableIssue(
            issue_id="i1", primary_diagnostic_id="d1",
            related_diagnostic_ids=("d1",), issue_group_id=None,
            kind="unknown_kind",
            target_ref="x",
            irs_ref=DiagnosticIRSRef(
                construct_type="UNKNOWN", construct_id="x",
                slot_name="x",
            ),
            missing_slot="x", source_span_ids=(), message="test",
        )
        session = svc.create_session("run_1", issue)
        with pytest.raises(UnsupportedIssueError):
            svc.generate_suggestions(session.session_id)


class TestB8ApplyVerify:
    def test_stale_double_apply_rejected(self) -> None:
        """B8: Applying the same suggestion twice is rejected."""
        svc = _make_service()
        issue = _make_mh_issue()
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        svc.register_compile_result(snap)
        session = svc.create_session("run_1", issue)
        suggestions = svc.generate_suggestions(session.session_id)
        # First apply succeeds
        svc.apply_suggestion(session.session_id, suggestions[0].suggestion_id)
        # Second apply with same (now stale) suggestion is rejected
        with pytest.raises(StaleRevisionError):
            svc.apply_suggestion(
                session.session_id, suggestions[0].suggestion_id)

    def test_cross_session_apply_rejected(self) -> None:
        """B8: Applying a suggestion from session A to session B is rejected."""
        svc = _make_service()
        issue_a = _make_mh_issue()
        issue_b = EditableIssue(
            issue_id="i2", primary_diagnostic_id="d2",
            related_diagnostic_ids=("d2",), issue_group_id=None,
            kind="missing_handler",
            target_ref="worker:w_main.exception_flow:exc_2",
            irs_ref=DiagnosticIRSRef(
                construct_type="EXCEPTION_FLOW", construct_id="x2",
                slot_name="handler_action",
            ),
            missing_slot="handler_action", source_span_ids=(),
            message="No handler.", authority="post_normalize_irs",
            affordance_ids=("exception_flow.add_handler_step",),
            default_affordance_id="exception_flow.add_handler_step",
        )
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        svc.register_compile_result(snap)
        sess_a = svc.create_session("run_1", issue_a)
        sess_b = svc.create_session("run_1", issue_b)
        sug_a = svc.generate_suggestions(sess_a.session_id)[0]
        with pytest.raises(SPLEditingError, match="belongs to session"):
            svc.apply_suggestion(sess_b.session_id, sug_a.suggestion_id)

    def test_apply_and_verify(self) -> None:
        svc = _make_service()
        issue = _make_mh_issue()
        diag = CompileDiagnostic(
            "d1", "missing_handler", "warning",  # matching issue.primary_diagnostic_id
            "No handler.", target_ref="worker:w_main.exception_flow:exc_1",
            blocks_completion=True,
        )
        diag.metadata["irs_ref"] = {
            "construct_type": "EXCEPTION_FLOW", "construct_id": "x",
            "slot_name": "handler_action", "construct_path": [],
            "source_authority": "post_normalize_irs",
        }
        diag.metadata["authority"] = "post_normalize_irs"
        snap = ArtifactSnapshot("snap_1", "run_1", 0, compile_diagnostics=(diag,))
        svc.register_compile_result(snap)

        session = svc.create_session("run_1", issue)
        suggestions = svc.generate_suggestions(session.session_id)
        assert len(suggestions) >= 1

        updated = svc.apply_suggestion(
            session.session_id, suggestions[0].suggestion_id)
        assert updated.overlay_version > 0

        result = svc.verify_session(session.session_id)
        assert result.accepted is True
        assert "d1" in result.resolved_diagnostic_ids

    def test_validator_blocks_before_apply(self) -> None:
        # Fresh service with failing validator
        from nl2spl.compiler.spl_editing.core.model import PatchTypeContract
        reg = SPLEditingRuntimeRegistry()
        reg.target_resolvers.register("exception_flow_target", _StubResolver())
        reg.context_builders.register("exception_flow_context", _StubContextBuilder())
        reg.handlers.register("missing_handler", _StubHandler())
        class _FailingValidator:
            def validate(self, patch, snap):
                raise PatchValidationError("test failure")
        reg.patches.register("AddExceptionHandlerStep", PatchBundle(
            patch_type="AddExceptionHandlerStep",
            validator=_FailingValidator(),
            applier=_StubApplier(),
            verifier=_StubVerifier(),
            previewer=object(),
            contract=PatchTypeContract(
                patch_type="AddExceptionHandlerStep",
                produces_step_ir=True,
                evidence_targets=("step",),
            ),
        ))
        svc = SPLEditingService(reg)
        issue = _make_mh_issue()
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        svc.register_compile_result(snap)

        session = svc.create_session("run_1", issue)
        suggestions = svc.generate_suggestions(session.session_id)
        with pytest.raises(PatchValidationError, match="test failure"):
            svc.apply_suggestion(session.session_id, suggestions[0].suggestion_id)

    def test_generate_suggestions_does_not_mutate_artifacts(self) -> None:
        svc = _make_service()
        issue = _make_mh_issue()
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        svc.register_compile_result(snap)
        session = svc.create_session("run_1", issue)
        svc.generate_suggestions(session.session_id)
        # Snapshot still at v0
        retrieved = svc._get_snapshot("run_1")
        assert retrieved.overlay_version == 0
