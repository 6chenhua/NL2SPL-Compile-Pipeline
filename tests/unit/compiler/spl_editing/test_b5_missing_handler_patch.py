"""B5: AddExceptionHandlerStep patch tests — real IR fixtures."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError
from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.applier import (
    AddExceptionHandlerStepApplier,
)
from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.preview import (
    AddExceptionHandlerStepPreviewer,
)
from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.validator import (
    AddExceptionHandlerStepValidator,
)
from nl2spl.compiler.spl_editing.patches.add_exception_handler_step.verifier import (
    AddExceptionHandlerStepVerifier,
)
from nl2spl.ir.block_structure_ir import BlockIR, BlockStructureIR
from nl2spl.ir.flow_structure_ir import FlowStructureIR
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import (
    WorkerBlockPlanIR,
    WorkerFlowPlanIR,
    WorkerStepPlanIR,
)
from nl2spl.ir.diagnostics import CompileDiagnostic, DiagnosticIRSRef


# ===========================================================================
# Helpers
# ===========================================================================


class _ExceptionFlowRefStub:
    """Minimal stub with flow_id for FlowStructureIR.exception_flows."""
    def __init__(self, flow_id: str) -> None:
        self.flow_id = flow_id


def _snap(**kw: object) -> ArtifactSnapshot:
    """Create a snapshot with WorkerStepPlanIR, BlockPlanIR, and FlowPlanIR."""
    d: dict[str, object] = dict(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=0,
        worker_flow_plan=WorkerFlowPlanIR(
            worker_flows={"w_main": FlowStructureIR(
                exception_flows=[_ExceptionFlowRefStub("exc_1")],
            )},
        ),
        worker_step_plan=WorkerStepPlanIR(
            main_worker_id="w_main",
            worker_steps={"w_main": []},
        ),
        worker_block_plan=WorkerBlockPlanIR(
            worker_blocks={"w_main": BlockStructureIR()},
        ),
    )
    d.update(kw)
    return ArtifactSnapshot(**d)  # type: ignore[arg-type]


def _patch(**kw: object) -> RepairPatch:
    d: dict[str, object] = dict(
        patch_id="p1", affordance_id="exception_flow.add_handler_step",
        patch_type="AddExceptionHandlerStep",
        target_ref="worker:w_main.exception_flow:exc_1",
        irs_ref=DiagnosticIRSRef(
            construct_type="EXCEPTION_FLOW", construct_id="x",
            slot_name="handler_action",
        ),
        base_compile_run_id="run_1", artifact_snapshot_id="snap_1",
        overlay_version=0,
        payload={
            "worker_id": "w_main",
            "exception_flow_id": "exc_1",
            "handler_text": "Ask user for input.",
            "command_type": "REQUEST_INPUT",
            "inputs": [],
            "outputs": ["approved"],
        },
        verification_lane="A",
        evidence=RepairEvidence(
            related_diagnostic_id="diag_target",
            user_text="Add a handler.",
        ),
    )
    d.update(kw)
    return RepairPatch(**d)  # type: ignore[arg-type]


# ===========================================================================
# B5-1: Validator
# ===========================================================================


class TestB5Validator:
    def test_valid_payload_passes(self) -> None:
        AddExceptionHandlerStepValidator().validate(_patch(), _snap())

    def test_missing_worker_id_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="worker_id"):
            AddExceptionHandlerStepValidator().validate(
                _patch(payload={}), _snap(),
            )

    def test_wrong_command_type_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="command_type"):
            AddExceptionHandlerStepValidator().validate(
                _patch(payload={
                    "worker_id": "w_main", "exception_flow_id": "exc_1",
                    "handler_text": "H", "command_type": "INVALID",
                }), _snap(),
            )

    def test_wrong_patch_type_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="!="):
            AddExceptionHandlerStepValidator().validate(
                _patch(patch_type="WrongType"), _snap(),
            )

    def test_request_input_without_outputs_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="output"):
            AddExceptionHandlerStepValidator().validate(
                _patch(payload={
                    "worker_id": "w_main", "exception_flow_id": "exc_1",
                    "handler_text": "H", "command_type": "REQUEST_INPUT",
                    "outputs": [],
                }), _snap(),
            )

    def test_display_message_with_outputs_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="DISPLAY_MESSAGE"):
            AddExceptionHandlerStepValidator().validate(
                _patch(payload={
                    "worker_id": "w_main", "exception_flow_id": "exc_1",
                    "handler_text": "H", "command_type": "DISPLAY_MESSAGE",
                    "outputs": ["out1"],
                }), _snap(),
            )

    def test_duplicate_handler_rejected(self) -> None:
        """B5: Validator rejects when exception flow already has a handler."""
        snap = _snap(
            worker_step_plan=WorkerStepPlanIR(
                main_worker_id="w_main",
                worker_steps={
                    "w_main": [StepIR(
                        "st_existing", "existing handler", [],
                        "GENERAL_COMMAND", flow_ref="exc_1",
                    )],
                },
            ),
        )
        with pytest.raises(PatchValidationError, match="already has"):
            AddExceptionHandlerStepValidator().validate(_patch(), snap)

    def test_missing_step_plan_rejected(self) -> None:
        snap = ArtifactSnapshot("snap_1", "run_1", 0)
        with pytest.raises(PatchValidationError, match="worker_step_plan"):
            AddExceptionHandlerStepValidator().validate(_patch(), snap)


# ===========================================================================
# B5-2: Applier
# ===========================================================================


class TestB5Applier:
    def test_applier_creates_patched_snapshot(self) -> None:
        applier = AddExceptionHandlerStepApplier()
        diag = CompileDiagnostic("diag_target", "missing_handler", "warning",
                                  "test", target_ref="x", blocks_completion=True)
        snap = _snap(compile_diagnostics=(diag,))
        patched, event = applier.apply(_patch(), snap)

        assert patched.overlay_version == 1
        assert event.overlay_version == 1
        assert event.patch_type == "AddExceptionHandlerStep"

    def test_applier_does_not_mutate_base(self) -> None:
        applier = AddExceptionHandlerStepApplier()
        diag = CompileDiagnostic("diag_target", "missing_handler", "warning",
                                  "test", target_ref="x", blocks_completion=True)
        snap = _snap(compile_diagnostics=(diag,))
        base_overlay = snap.overlay_version

        applier.apply(_patch(), snap)

        assert snap.overlay_version == base_overlay

    def test_applier_step_has_repair_metadata(self) -> None:
        applier = AddExceptionHandlerStepApplier()
        snap = _snap()
        patched, _ = applier.apply(_patch(), snap)

        wsp = patched.worker_step_plan
        assert wsp is not None
        assert "w_main" in wsp.worker_steps
        steps = wsp.worker_steps["w_main"]
        assert len(steps) == 1
        step = steps[0]
        assert step.metadata.get("origin") == "user_confirmed_repair"
        assert step.metadata.get("related_diagnostic_id") == "diag_target"
        assert step.flow_ref == "exc_1"

    def test_applier_creates_block(self) -> None:
        applier = AddExceptionHandlerStepApplier()
        snap = _snap()
        patched, _ = applier.apply(_patch(), snap)

        wbp = patched.worker_block_plan
        assert wbp is not None
        assert "w_main" in wbp.worker_blocks
        bs = wbp.worker_blocks["w_main"]
        assert "exc_1" in bs.exception_flow_blocks
        assert len(bs.exception_flow_blocks["exc_1"]) == 1
        block = bs.exception_flow_blocks["exc_1"][0]
        assert block.block_type == "SEQUENTIAL"

    def test_applier_step_refs_block(self) -> None:
        applier = AddExceptionHandlerStepApplier()
        snap = _snap()
        patched, _ = applier.apply(_patch(), snap)

        wsp = patched.worker_step_plan
        wbp = patched.worker_block_plan
        step = wsp.worker_steps["w_main"][0]
        block = wbp.worker_blocks["w_main"].exception_flow_blocks["exc_1"][0]
        assert step.block_ref == block.block_id

    def test_applier_clears_stale_final_outputs(self) -> None:
        """B5: After stage-artifact change, final_spl and final_worker are None."""
        applier = AddExceptionHandlerStepApplier()
        snap = _snap(final_spl="OLD SPL", final_worker=object())
        patched, _ = applier.apply(_patch(), snap)
        assert patched.final_spl is None
        assert patched.final_worker is None


# ===========================================================================
# B5-3: Previewer + Verifier
# ===========================================================================


class TestB5Previewer:
    def test_preview_includes_command(self) -> None:
        preview = AddExceptionHandlerStepPreviewer().preview({
            "handler_text": "Ask user.", "command_type": "REQUEST_INPUT",
            "inputs": ["a"], "outputs": ["b"],
        })
        assert "REQUEST_INPUT" in preview


class TestB5Verifier:
    def test_verifier_checks_gated_worker(self) -> None:
        verifier = AddExceptionHandlerStepVerifier()

        class FakeBlock:
            block_id = "b_repair_exc_1"

        class FakeExcFlow:
            flow_id = "exc_1"
            blocks = [FakeBlock()]

        class FakeGated:
            steps = [StepIR(
                "st_repair", "Ask.", [], "REQUEST_INPUT",
                flow_ref="exc_1", block_ref="b_repair_exc_1",
                metadata={"origin": "user_confirmed_repair"},
            )]
            exception_flows = [FakeExcFlow()]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = "[REQUEST_INPUT] Ask user for input."

        failures = verifier.verify(
            _patch(), _snap(), _snap(), FakeArtifacts(),
        )
        assert failures == ()

    def test_verifier_reports_missing_handler_in_gated(self) -> None:
        verifier = AddExceptionHandlerStepVerifier()

        class FakeGated:
            steps = []

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(
            _patch(), _snap(), _snap(), FakeArtifacts(),
        )
        assert len(failures) > 0
        assert "gated" in failures[0]

    def test_verifier_fails_when_gated_is_none(self) -> None:
        verifier = AddExceptionHandlerStepVerifier()

        class FakeArtifacts:
            gated_worker = None
            rendered_spl = ""

        failures = verifier.verify(
            _patch(), _snap(), _snap(), FakeArtifacts(),
        )
        assert len(failures) > 0
        assert "missing" in failures[0]


# ===========================================================================
# B5-4: Mutation safety
# ===========================================================================


class TestB5MutationSafety:
    """B5: Applier must not mutate base snapshot nested collections."""

    def test_base_step_plan_not_mutated(self) -> None:
        applier = AddExceptionHandlerStepApplier()
        snap = _snap()
        base_steps_before = len(
            snap.worker_step_plan.worker_steps.get("w_main", [])
        )
        applier.apply(_patch(), snap)
        base_steps_after = len(
            snap.worker_step_plan.worker_steps.get("w_main", [])
        )
        assert base_steps_after == base_steps_before

    def test_base_block_plan_not_mutated(self) -> None:
        applier = AddExceptionHandlerStepApplier()
        snap = _snap()
        bs = snap.worker_block_plan.worker_blocks.get("w_main")
        base_exc_count_before = len(
            bs.exception_flow_blocks.get("exc_1", [])
        ) if bs else 0
        applier.apply(_patch(), snap)
        base_exc_count_after = len(
            snap.worker_block_plan.worker_blocks["w_main"]
            .exception_flow_blocks.get("exc_1", [])
        )
        assert base_exc_count_after == base_exc_count_before


# ===========================================================================
# B5-5: Flow existence check
# ===========================================================================


class TestB5FlowExistence:
    """B5: Validator requires target exception flow to exist."""

    def test_missing_flow_plan_rejected(self) -> None:
        snap = ArtifactSnapshot("snap_1", "run_1", 0,
            worker_step_plan=WorkerStepPlanIR("w_main", {}),
            worker_block_plan=WorkerBlockPlanIR({}),
        )
        with pytest.raises(PatchValidationError, match="worker_flow_plan"):
            AddExceptionHandlerStepValidator().validate(_patch(), snap)

    def test_nonexistent_flow_rejected(self) -> None:
        snap = ArtifactSnapshot("snap_1", "run_1", 0,
            worker_step_plan=WorkerStepPlanIR("w_main", {}),
            worker_block_plan=WorkerBlockPlanIR({}),
            worker_flow_plan=WorkerFlowPlanIR(
                worker_flows={"w_main": FlowStructureIR(
                    exception_flows=[_ExceptionFlowRefStub("other_flow")],
                )},
            ),
        )
        with pytest.raises(PatchValidationError, match="not found"):
            AddExceptionHandlerStepValidator().validate(_patch(), snap)


# ===========================================================================
# B5-6: Stale revision + exact target_ref
# ===========================================================================


class TestB5StaleRevision:
    def test_compile_run_id_mismatch_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="compile_run_id"):
            AddExceptionHandlerStepValidator().validate(
                _patch(base_compile_run_id="other_run"), _snap(),
            )

    def test_snapshot_id_mismatch_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="snapshot_id"):
            AddExceptionHandlerStepValidator().validate(
                _patch(artifact_snapshot_id="other_snap"), _snap(),
            )

    def test_overlay_version_mismatch_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="overlay_version"):
            AddExceptionHandlerStepValidator().validate(
                _patch(overlay_version=5), _snap(),
            )


class TestB5ExactTargetRef:
    def test_partial_match_rejected(self) -> None:
        """B5: target_ref substring match (exc_1 matching exc_10) rejected."""
        with pytest.raises(PatchValidationError, match="target_ref"):
            AddExceptionHandlerStepValidator().validate(
                _patch(target_ref="worker:w_main.exception_flow:exc_10",
                       payload={
                           "worker_id": "w_main",
                           "exception_flow_id": "exc_1",
                           "handler_text": "H",
                           "command_type": "GENERAL_COMMAND",
                       }),
                _snap(),
            )


class TestB5StepIdScope:
    """B5: Step id uniqueness check scoped to exact ID, not prefix."""

    def test_existing_repair_for_other_flow_not_rejected(self) -> None:
        """B5: An existing repair step for another exception flow
        does NOT block a new repair for a different flow."""
        snap = _snap(
            worker_step_plan=WorkerStepPlanIR(
                main_worker_id="w_main",
                worker_steps={
                    "w_main": [StepIR(
                        "st_repair_1_w_main", "old repair", [],
                        "GENERAL_COMMAND", flow_ref="other_flow",
                    )],
                },
            ),
            overlay_version=1,
        )
        # Generated step_id = st_repair_2_w_main (different from existing)
        # Should pass — old repair is for other_flow, not exc_1
        AddExceptionHandlerStepValidator().validate(_patch(overlay_version=1), snap)

    def test_exact_generated_id_duplicate_rejected(self) -> None:
        """B5: Exact step_id collision is rejected."""
        snap = _snap(
            worker_step_plan=WorkerStepPlanIR(
                main_worker_id="w_main",
                worker_steps={
                    "w_main": [StepIR(
                        "st_repair_1_w_main", "existing", [],
                        "GENERAL_COMMAND",
                    )],
                },
            ),
        )
        with pytest.raises(PatchValidationError, match="st_repair_1_w_main"):
            AddExceptionHandlerStepValidator().validate(_patch(), snap)


class TestB5VerifierBlockRef:
    """B5: Verifier checks block_ref belongs to target exception flow."""

    def test_wrong_block_ref_rejected(self) -> None:
        verifier = AddExceptionHandlerStepVerifier()

        class FakeBlock:
            block_id = "b_correct"

        class FakeExcFlow:
            flow_id = "exc_1"
            blocks = [FakeBlock()]

        class FakeGated:
            steps = [StepIR(
                "st_repair", "Ask.", [], "REQUEST_INPUT",
                flow_ref="exc_1", block_ref="wrong_block",
                metadata={"origin": "user_confirmed_repair"},
            )]
            exception_flows = [FakeExcFlow()]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = "[REQUEST_INPUT] Ask user for input."

        failures = verifier.verify(
            _patch(), _snap(), _snap(), FakeArtifacts(),
        )
        assert len(failures) > 0
        assert "block_ref" in failures[0]

    def test_empty_block_ids_rejected(self) -> None:
        """B5: Exception flow with no blocks → verifier fails
        (cannot confirm block_ref ownership)."""
        verifier = AddExceptionHandlerStepVerifier()

        class FakeExcFlow:
            flow_id = "exc_1"
            blocks = []  # empty

        class FakeGated:
            steps = [StepIR(
                "st_repair", "Ask.", [], "REQUEST_INPUT",
                flow_ref="exc_1", block_ref="some_block",
                metadata={"origin": "user_confirmed_repair"},
            )]
            exception_flows = [FakeExcFlow()]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = "[REQUEST_INPUT] Ask user."

        failures = verifier.verify(
            _patch(), _snap(), _snap(), FakeArtifacts(),
        )
        assert len(failures) > 0
        assert "no blocks" in failures[0]


class TestB5EmptyItems:
    def test_empty_input_item_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="non-empty"):
            AddExceptionHandlerStepValidator().validate(
                _patch(payload={
                    "worker_id": "w_main",
                    "exception_flow_id": "exc_1",
                    "handler_text": "H",
                    "command_type": "GENERAL_COMMAND",
                    "inputs": [""],
                }),
                _snap(),
            )
