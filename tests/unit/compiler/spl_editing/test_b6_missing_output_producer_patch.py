"""B6: InsertProducerStep and BindExistingProducerStep patch tests.

R6: InsertProducerStep validator rejects dict payloads (must be
ConstructRepairIntent).  InsertProducerStepApplier is disabled.
Direct BindExistingProducerStep applier is disabled after R11.
"""

from __future__ import annotations

import pytest

from nl2spl.compiler.spl_editing.core.errors import PatchValidationError, SPLEditingError
from nl2spl.compiler.spl_editing.core.model import RepairEvidence, RepairPatch
from nl2spl.compiler.spl_editing.core.revision import ArtifactSnapshot
from nl2spl.compiler.spl_editing.intent.model import ConstructRepairIntent
from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.applier import (
    BindExistingProducerStepApplier,
)
from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.validator import (
    BindExistingProducerStepValidator,
)
from nl2spl.compiler.spl_editing.patches.bind_existing_producer_step.verifier import (
    BindExistingProducerStepVerifier,
)
from nl2spl.compiler.spl_editing.patches.insert_producer_step.applier import (
    InsertProducerStepApplier,
)
from nl2spl.compiler.spl_editing.patches.insert_producer_step.validator import (
    InsertProducerStepValidator,
)
from nl2spl.compiler.spl_editing.patches.insert_producer_step.verifier import (
    InsertProducerStepVerifier,
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


def _make_intent_payload(**kw: object) -> ConstructRepairIntent:
    d: dict[str, object] = dict(
        intent_id="int_001",
        issue_id="issue_1",
        patch_type="InsertProducerStep",
        affordance_id="required_output.insert_or_bind_producer",
        target_construct_type="REQUIRED_OUTPUT",
        target_construct_id="worker:w_main.output:draft",
        target_slot_name="producer",
        target_ref_id="required_output:w_main:required_output_context::draft",
        selected_ref_ids=(),
        intent_summary="Draft the document.",
        repair_goal="Draft the document.",
        materialization_plan_id="stage7.step_producer_repair.v1",
        constraints=(),
        payload=None,
    )
    d.update(kw)
    return ConstructRepairIntent(**d)  # type: ignore[arg-type]


def _patch(patch_type: str, **kw: object) -> RepairPatch:
    d: dict[str, object] = dict(
        patch_id="p1",
        affordance_id="required_output.insert_or_bind_producer",
        patch_type=patch_type,
        target_ref="worker:w_main.output:draft",
        irs_ref=DiagnosticIRSRef(
            construct_type="REQUIRED_OUTPUT", construct_id="x", slot_name="producer"
        ),
        base_compile_run_id="run_1",
        artifact_snapshot_id="snap_1",
        overlay_version=0,
        verification_lane="A",
        payload={
            "worker_id": "w_main",
            "output_name": "draft",
            "producer_text": "Draft the document.",
            "command_type": "GENERAL_COMMAND",
        },
        evidence=RepairEvidence(related_diagnostic_id="diag_target", user_text="Add producer."),
    )
    d.update(kw)
    return RepairPatch(**d)  # type: ignore[arg-type]


def _insert_patch(**kw: object) -> RepairPatch:
    """Patch with ConstructRepairIntent payload for InsertProducerStep R6."""
    d: dict[str, object] = dict(
        patch_id="p1",
        affordance_id="required_output.insert_or_bind_producer",
        patch_type="InsertProducerStep",
        target_ref="worker:w_main.output:draft",
        irs_ref=DiagnosticIRSRef(
            construct_type="REQUIRED_OUTPUT", construct_id="x", slot_name="producer"
        ),
        base_compile_run_id="run_1",
        artifact_snapshot_id="snap_1",
        overlay_version=0,
        verification_lane="A",
        payload=_make_intent_payload(),
        evidence=RepairEvidence(related_diagnostic_id="diag_target", user_text="Add producer."),
    )
    d.update(kw)
    return RepairPatch(**d)  # type: ignore[arg-type]


# ===========================================================================
# B6-1: InsertProducerStep
# ===========================================================================


class TestB6InsertProducerStep:
    def test_validator_accepts_intent_payload(self) -> None:
        """R6: Validator accepts ConstructRepairIntent."""
        InsertProducerStepValidator().validate(_insert_patch(), _snap())

    def test_validator_rejects_dict_payload(self) -> None:
        """R6: Dict payload is rejected."""
        with pytest.raises(PatchValidationError, match="must be ConstructRepairIntent"):
            InsertProducerStepValidator().validate(_patch("InsertProducerStep"), _snap())

    def test_validator_rejects_intent_without_target_ref(self) -> None:
        """R6: Intent without target_ref_id is rejected."""
        with pytest.raises(PatchValidationError, match="target_ref_id"):
            InsertProducerStepValidator().validate(
                _insert_patch(payload=_make_intent_payload(target_ref_id="")), _snap()
            )

    def test_validator_rejects_intent_without_plan_id(self) -> None:
        """R6: Intent without materialization_plan_id is rejected."""
        with pytest.raises(PatchValidationError, match="materialization_plan_id"):
            InsertProducerStepValidator().validate(
                _insert_patch(payload=_make_intent_payload(materialization_plan_id=None)), _snap()
            )

    def test_stale_revision_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="compile_run_id"):
            InsertProducerStepValidator().validate(
                _insert_patch(base_compile_run_id="other"), _snap()
            )

    def test_applier_raises_disabled(self) -> None:
        """R6: InsertProducerStepApplier is disabled."""
        with pytest.raises(SPLEditingError, match="disabled"):
            InsertProducerStepApplier().apply(_insert_patch(), _snap())

    def test_verifier_finds_producer(self) -> None:
        verifier = InsertProducerStepVerifier()
        patch = _insert_patch()

        class FakeGated:
            steps = [
                StepIR(
                    "st_x",
                    "Draft",
                    ["s1"],
                    "GENERAL_COMMAND",
                    outputs=["draft"],
                    metadata={"origin": "user_confirmed_repair"},
                )
            ]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = "draft: [GENERAL_COMMAND] Draft the document."

        failures = verifier.verify(patch, _snap(), _snap(), FakeArtifacts())
        assert failures == ()

    def test_verifier_producer_index_rejects_non_renderable_step(self) -> None:
        """B6: Step without source spans or user_confirmed_repair
        → ProducerIndex rejects → verifier fails."""
        verifier = InsertProducerStepVerifier()

        class FakeGated:
            steps = [StepIR("st_x", "Draft", [], "GENERAL_COMMAND", outputs=["draft"])]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(_insert_patch(), _snap(), _snap(), FakeArtifacts())
        assert len(failures) > 0
        assert "ProducerIndex" in failures[0]


# ===========================================================================
# B6-2: BindExistingProducerStep
# ===========================================================================


class TestB6BindExistingProducerStep:
    def test_validator_passes_with_renderable_step(self) -> None:
        snap = _snap(
            worker_step_plan=WorkerStepPlanIR(
                "w_main",
                {
                    "w_main": [
                        StepIR(
                            "st_existing",
                            "Existing work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["other"],
                        )
                    ]
                },
            )
        )
        BindExistingProducerStepValidator().validate(
            _patch(
                "BindExistingProducerStep",
                payload={
                    "worker_id": "w_main",
                    "step_id": "st_existing",
                    "output_name": "draft",
                },
            ),
            snap,
        )

    def test_validator_rejects_non_renderable_step(self) -> None:
        snap = _snap(
            worker_step_plan=WorkerStepPlanIR(
                "w_main",
                {
                    "w_main": [
                        StepIR(
                            "st_synth",
                            "Synthetic",
                            [],
                            "GENERAL_COMMAND",
                        )
                    ]
                },
            )
        )
        with pytest.raises(PatchValidationError, match="no source evidence"):
            BindExistingProducerStepValidator().validate(
                _patch(
                    "BindExistingProducerStep",
                    payload={
                        "worker_id": "w_main",
                        "step_id": "st_synth",
                        "output_name": "draft",
                    },
                ),
                snap,
            )

    def test_direct_bind_applier_is_disabled(self) -> None:
        snap = _snap(
            worker_step_plan=WorkerStepPlanIR(
                "w_main",
                {
                    "w_main": [
                        StepIR(
                            "st_existing",
                            "Work",
                            ["s1"],
                            "GENERAL_COMMAND",
                            outputs=["other"],
                        )
                    ]
                },
            )
        )
        with pytest.raises(SPLEditingError, match="RepairMaterializationService"):
            BindExistingProducerStepApplier().apply(
                _patch(
                    "BindExistingProducerStep",
                    payload={
                        "worker_id": "w_main",
                        "step_id": "st_existing",
                        "output_name": "draft",
                    },
                ),
                snap,
            )
        assert snap.worker_step_plan.worker_steps["w_main"][0].outputs == ["other"]

    def test_bind_validator_scoped_to_worker_id(self) -> None:
        """B6: Bind rejects step in different worker."""
        snap = _snap(
            worker_step_plan=WorkerStepPlanIR(
                "w_main",
                {
                    "w_main": [],
                    "child": [StepIR("st_child", "Child work", ["s1"], "GENERAL_COMMAND")],
                },
            )
        )
        with pytest.raises(PatchValidationError, match="not found"):
            BindExistingProducerStepValidator().validate(
                _patch(
                    "BindExistingProducerStep",
                    payload={
                        "worker_id": "w_main",
                        "step_id": "st_child",
                        "output_name": "draft",
                    },
                ),
                snap,
            )


class TestB6InsertionTarget:
    """B6/R6: Insert dict payload rejects.  Insertion target is now
    determined by the stage materializer, not the LLM or validator."""

    def test_dict_payload_with_block_insertion_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="must be ConstructRepairIntent"):
            InsertProducerStepValidator().validate(
                _patch(
                    "InsertProducerStep",
                    payload={
                        "worker_id": "w_main",
                        "output_name": "draft",
                        "producer_text": "T",
                        "command_type": "GENERAL_COMMAND",
                        "insertion_target": "block",
                    },
                ),
                _snap(),
            )

    def test_dict_payload_with_block_ref_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="must be ConstructRepairIntent"):
            InsertProducerStepValidator().validate(
                _patch(
                    "InsertProducerStep",
                    payload={
                        "worker_id": "w_main",
                        "output_name": "draft",
                        "producer_text": "T",
                        "command_type": "GENERAL_COMMAND",
                        "block_ref": "b1",
                    },
                ),
                _snap(),
            )

    def test_dict_payload_with_non_string_block_ref_rejected(self) -> None:
        with pytest.raises(PatchValidationError, match="must be ConstructRepairIntent"):
            InsertProducerStepValidator().validate(
                _patch(
                    "InsertProducerStep",
                    payload={
                        "worker_id": "w_main",
                        "output_name": "draft",
                        "producer_text": "T",
                        "command_type": "GENERAL_COMMAND",
                        "block_ref": 0,
                    },
                ),
                _snap(),
            )


class TestB6BindVerifier:
    """B6: Bind verifier checks provenance."""

    def test_verifier_accepts_matching_provenance(self) -> None:
        verifier = BindExistingProducerStepVerifier()
        patch = _patch(
            "BindExistingProducerStep",
            payload={
                "worker_id": "w_main",
                "step_id": "st_x",
                "output_name": "draft",
            },
        )

        class FakeGated:
            steps = [
                StepIR(
                    "st_x",
                    "Draft",
                    ["s1"],
                    "GENERAL_COMMAND",
                    outputs=["draft"],
                    metadata={
                        "repair_output_bindings": {
                            "draft": {
                                "repair_patch_id": "p1",
                                "related_diagnostic_id": "diag_target",
                            },
                        }
                    },
                )
            ]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(patch, _snap(), _snap(), FakeArtifacts())
        assert failures == ()

    def test_verifier_rejects_wrong_patch_id(self) -> None:
        verifier = BindExistingProducerStepVerifier()

        class FakeGated:
            steps = [
                StepIR(
                    "st_x",
                    "Draft",
                    ["s1"],
                    "GENERAL_COMMAND",
                    outputs=["draft"],
                    metadata={
                        "repair_output_bindings": {
                            "draft": {
                                "repair_patch_id": "other_patch",
                                "related_diagnostic_id": "diag_target",
                            },
                        }
                    },
                )
            ]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(
            _patch(
                "BindExistingProducerStep",
                payload={
                    "worker_id": "w_main",
                    "step_id": "st_x",
                    "output_name": "draft",
                },
            ),
            _snap(),
            _snap(),
            FakeArtifacts(),
        )
        assert len(failures) > 0
        assert "repair_patch_id" in failures[0]

    def test_verifier_rejects_wrong_diagnostic_id(self) -> None:
        verifier = BindExistingProducerStepVerifier()

        class FakeGated:
            steps = [
                StepIR(
                    "st_x",
                    "Draft",
                    ["s1"],
                    "GENERAL_COMMAND",
                    outputs=["draft"],
                    metadata={
                        "repair_output_bindings": {
                            "draft": {
                                "repair_patch_id": "p1",
                                "related_diagnostic_id": "wrong_diag",
                            },
                        }
                    },
                )
            ]

        class FakeArtifacts:
            gated_worker = FakeGated()
            rendered_spl = ""

        failures = verifier.verify(
            _patch(
                "BindExistingProducerStep",
                payload={
                    "worker_id": "w_main",
                    "step_id": "st_x",
                    "output_name": "draft",
                },
            ),
            _snap(),
            _snap(),
            FakeArtifacts(),
        )
        assert len(failures) > 0
        assert "related_diagnostic_id" in failures[0]


class TestB6WorkerScope:
    """B6: Worker scope enforced."""

    def test_bind_applier_does_not_modify_any_worker_when_disabled(self) -> None:
        """R11: BindExistingProducerStep direct mutation is disabled."""
        snap = _snap(
            worker_step_plan=WorkerStepPlanIR(
                "w_main",
                {
                    "w_main": [StepIR("st_shared", "Main work", ["s1"], "GENERAL_COMMAND")],
                    "child": [StepIR("st_shared", "Child work", ["s2"], "GENERAL_COMMAND")],
                },
            )
        )
        with pytest.raises(SPLEditingError):
            BindExistingProducerStepApplier().apply(
                _patch(
                    "BindExistingProducerStep",
                    payload={
                        "worker_id": "w_main",
                        "step_id": "st_shared",
                        "output_name": "draft",
                    },
                ),
                snap,
            )
        assert snap.worker_step_plan.worker_steps["w_main"][0].outputs == []
        assert snap.worker_step_plan.worker_steps["child"][0].outputs == []

    def test_insert_dict_payload_rejected_for_unknown_worker(self) -> None:
        """R6: Dict payload is rejected irrespective of worker existence."""
        snap = _snap(
            worker_step_plan=WorkerStepPlanIR(
                "w_main",
                {"w_known": []},
            )
        )
        with pytest.raises(PatchValidationError, match="must be ConstructRepairIntent"):
            InsertProducerStepValidator().validate(
                _patch(
                    "InsertProducerStep",
                    target_ref="worker:unknown_worker.output:draft",
                    payload={
                        "worker_id": "unknown_worker",
                        "output_name": "draft",
                        "producer_text": "T",
                        "command_type": "GENERAL_COMMAND",
                    },
                ),
                snap,
            )
