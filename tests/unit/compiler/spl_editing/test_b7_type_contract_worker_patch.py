"""B7b/B7c: ConvertDelegationIntent patches tests."""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError, SPLEditingError
from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.patches.convert_delegation_to_main_flow_step.applier import (
    ConvertDelegationToMainFlowStepApplier,
)
from nl2spl.compiler.spl_editing.patches.convert_delegation_to_main_flow_step.validator import (
    ConvertDelegationToMainFlowStepValidator,
)
from nl2spl.compiler.spl_editing.patches.convert_delegation_to_main_flow_step.verifier import (
    ConvertDelegationToMainFlowStepVerifier,
)
from nl2spl.compiler.spl_editing.patches.convert_delegation_to_request_input.applier import (
    ConvertDelegationToRequestInputApplier,
)
from nl2spl.compiler.spl_editing.patches.convert_delegation_to_request_input.validator import (
    ConvertDelegationToRequestInputValidator,
)
from nl2spl.compiler.spl_editing.patches.convert_delegation_to_request_input.verifier import (
    ConvertDelegationToRequestInputVerifier,
)
from nl2spl.ir.diagnostics import DiagnosticIRSRef
from nl2spl.ir.step_ir import StepIR
from nl2spl.ir.worker_plan_ir import WorkerStepPlanIR


def _snap(**kw: object) -> ArtifactSnapshot:
    d: dict[str, object] = dict(
        snapshot_id="snap_1",
        compile_run_id="run_1",
        overlay_version=0,
        worker_step_plan=WorkerStepPlanIR("w_main", {"w_main": []}),
    )
    d.update(kw)
    return ArtifactSnapshot(**d)  # type: ignore[arg-type]


def _irs_ref() -> DiagnosticIRSRef:
    return DiagnosticIRSRef(
        construct_type="WORKER_PROMOTION",
        construct_id="worker_promotion:cand_1",
        slot_name="promotion_input_contract",
    )


def _b7b_patch(**kw: object) -> RepairPatch:
    d: dict[str, object] = dict(
        patch_id="p1",
        affordance_id="worker_promotion.resolve_contract",
        patch_type="ConvertDelegationIntentToMainFlowStep",
        target_ref="worker_promotion:cand_1",
        irs_ref=_irs_ref(),
        base_compile_run_id="run_1",
        artifact_snapshot_id="snap_1",
        overlay_version=0,
        verification_lane="A",
        payload={"worker_id": "w_main", "action_text": "Do work."},
        evidence=RepairEvidence(related_diagnostic_id="diag_target"),
    )
    d.update(kw)
    return RepairPatch(**d)  # type: ignore[arg-type]


def _b7c_patch(**kw: object) -> RepairPatch:
    d: dict[str, object] = dict(
        patch_id="p1",
        affordance_id="worker_promotion.resolve_contract",
        patch_type="ConvertDelegationIntentToRequestInput",
        target_ref="worker_promotion:cand_1",
        irs_ref=_irs_ref(),
        base_compile_run_id="run_1",
        artifact_snapshot_id="snap_1",
        overlay_version=0,
        verification_lane="A",
        payload={"worker_id": "w_main", "prompt_text": "Ask user.", "value_target": "user_input"},
        evidence=RepairEvidence(related_diagnostic_id="diag_target"),
    )
    d.update(kw)
    return RepairPatch(**d)  # type: ignore[arg-type]


# ===========================================================================
# B7b
# ===========================================================================


class TestB7bConvertToMainFlow:
    def test_validator_passes(self) -> None:
        ConvertDelegationToMainFlowStepValidator().validate(_b7b_patch(), _snap())

    def test_wrong_construct_type_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="construct_type"):
            ConvertDelegationToMainFlowStepValidator().validate(
                _b7b_patch(
                    irs_ref=DiagnosticIRSRef(
                        construct_type="EXCEPTION_FLOW",
                        construct_id="x",
                        slot_name="promotion_input_contract",
                    )
                ),
                _snap(),
            )

    def test_empty_construct_id_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="construct_id"):
            ConvertDelegationToMainFlowStepValidator().validate(
                _b7b_patch(
                    irs_ref=DiagnosticIRSRef(
                        construct_type="WORKER_PROMOTION",
                        construct_id="",
                        slot_name="promotion_input_contract",
                    )
                ),
                _snap(),
            )

    def test_insertion_target_block_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="insertion_target"):
            ConvertDelegationToMainFlowStepValidator().validate(
                _b7b_patch(
                    payload={"worker_id": "w_main", "action_text": "T", "insertion_target": "block"}
                ),
                _snap(),
            )

    def test_target_ref_mismatch_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="target_ref"):
            ConvertDelegationToMainFlowStepValidator().validate(
                _b7b_patch(target_ref="worker_promotion:other_candidate"), _snap()
            )


class TestB7cIdentity:
    """B7c: construct id identity enforced."""

    def test_empty_construct_id_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="construct_id"):
            ConvertDelegationToRequestInputValidator().validate(
                _b7c_patch(
                    irs_ref=DiagnosticIRSRef(
                        construct_type="WORKER_PROMOTION",
                        construct_id="",
                        slot_name="promotion_input_contract",
                    )
                ),
                _snap(),
            )

    def test_target_ref_mismatch_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="target_ref"):
            ConvertDelegationToRequestInputValidator().validate(
                _b7c_patch(target_ref="worker_promotion:wrong_id"), _snap()
            )

    def test_direct_main_flow_applier_is_disabled(self) -> None:
        with pytest.raises(SPLEditingError, match="RepairMaterializationService"):
            ConvertDelegationToMainFlowStepApplier().apply(_b7b_patch(), _snap())

    def test_verifier_finds_step(self) -> None:
        verifier = ConvertDelegationToMainFlowStepVerifier()

        class FakeGated:
            steps = [
                StepIR(
                    "st_x",
                    "Do",
                    [],
                    "GENERAL_COMMAND",
                    metadata={
                        "resolution_kind": "converted_to_main_flow_step",
                        "repair_patch_id": "p1",
                        "origin": "user_confirmed_repair",
                        "related_diagnostic_id": "diag_target",
                    },
                )
            ]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        assert verifier.verify(_b7b_patch(), _snap(), _snap(), FakeArtifacts()) == ()

    def test_verifier_rejects_wrong_patch_id(self) -> None:
        verifier = ConvertDelegationToMainFlowStepVerifier()

        class FakeGated:
            steps = [
                StepIR(
                    "st_x",
                    "Do",
                    [],
                    "GENERAL_COMMAND",
                    metadata={
                        "resolution_kind": "converted_to_main_flow_step",
                        "repair_patch_id": "other_patch",
                    },
                )
            ]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(_b7b_patch(), _snap(), _snap(), FakeArtifacts())
        assert len(failures) > 0


# ===========================================================================
# B7c
# ===========================================================================


class TestB7cConvertToRequestInput:
    def test_validator_passes(self) -> None:
        ConvertDelegationToRequestInputValidator().validate(_b7c_patch(), _snap())

    def test_missing_value_target_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="value_target"):
            ConvertDelegationToRequestInputValidator().validate(
                _b7c_patch(payload={"worker_id": "w_main", "prompt_text": "Ask."}), _snap()
            )

    def test_wrong_slot_name_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="slot_name"):
            ConvertDelegationToRequestInputValidator().validate(
                _b7c_patch(
                    irs_ref=DiagnosticIRSRef(
                        construct_type="WORKER_PROMOTION",
                        construct_id="x",
                        slot_name="not_a_promotion_slot",
                    )
                ),
                _snap(),
            )

    def test_direct_request_input_applier_is_disabled(self) -> None:
        with pytest.raises(SPLEditingError, match="RepairMaterializationService"):
            ConvertDelegationToRequestInputApplier().apply(_b7c_patch(), _snap())

    def test_verifier_finds_step(self) -> None:
        verifier = ConvertDelegationToRequestInputVerifier()

        class FakeGated:
            steps = [
                StepIR(
                    "st_x",
                    "Ask.",
                    [],
                    "REQUEST_INPUT",
                    outputs=["user_input"],
                    metadata={
                        "resolution_kind": "converted_to_request_input",
                        "repair_patch_id": "p1",
                        "value_target": "user_input",
                        "origin": "user_confirmed_repair",
                        "related_diagnostic_id": "diag_target",
                    },
                )
            ]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        assert verifier.verify(_b7c_patch(), _snap(), _snap(), FakeArtifacts()) == ()

    def test_verifier_rejects_missing_value_target(self) -> None:
        verifier = ConvertDelegationToRequestInputVerifier()

        class FakeGated:
            steps = [
                StepIR(
                    "st_x",
                    "Ask.",
                    [],
                    "REQUEST_INPUT",
                    outputs=["user_input"],
                    metadata={
                        "resolution_kind": "converted_to_request_input",
                        "repair_patch_id": "p1",
                        "origin": "user_confirmed_repair",
                        "related_diagnostic_id": "diag_target",
                        # value_target missing
                    },
                )
            ]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(_b7c_patch(), _snap(), _snap(), FakeArtifacts())
        assert len(failures) > 0
        assert "value_target" in failures[0]
